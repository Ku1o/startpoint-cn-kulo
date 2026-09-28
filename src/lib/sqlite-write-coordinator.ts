import { getDb } from "../data/db"
import { performance } from "node:perf_hooks"
import { measureServerWork, recordServerWork } from "./server-work-performance"
import { beginCommitProbe, endCommitProbe, type CommitProbe } from "./sqlite-commit-diagnostics"
import type { Database } from "better-sqlite3"

const playerWriteTails = new Map<number, Promise<void>>()

function delay(milliseconds: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, milliseconds))
}

export function isSqliteBusyError(error: unknown): boolean {
    if (!(error instanceof Error) || !("code" in error)) return false
    const code = String((error as Error & { code?: string }).code ?? "")
    return code === "SQLITE_BUSY" || code === "SQLITE_BUSY_SNAPSHOT" || code.startsWith("SQLITE_BUSY_")
}

export async function withPlayerWriteQueue<T>(playerId: number, operation: () => Promise<T>): Promise<T> {
    const previous = playerWriteTails.get(playerId) ?? Promise.resolve()
    let release!: () => void
    const current = new Promise<void>(resolve => { release = resolve })
    const tail = previous.then(() => current)
    playerWriteTails.set(playerId, tail)
    const queuedAt = performance.now()
    await previous
    recordServerWork("db.playerQueue", performance.now() - queuedAt)
    try {
        return await operation()
    } finally {
        release()
        void tail.finally(() => {
            if (playerWriteTails.get(playerId) === tail) playerWriteTails.delete(playerId)
        })
    }
}

/** Wait for every currently queued player mutation before closing the database. */
export async function drainPlayerWriteQueues(): Promise<void> {
    // A request may enqueue another player while the first snapshot drains.
    // Keep taking snapshots until the map stays empty so shutdown cannot race
    // the final per-player transaction.
    while (playerWriteTails.size > 0) {
        await Promise.all([...playerWriteTails.values()])
    }
}

/** Run a short write transaction and retry the complete mutation on snapshot contention. */
export async function runImmediateTransactionWithRetry<T>(
    operation: () => T,
    maxAttempts = 3,
): Promise<T> {
    const db = getDb()
    let lastError: unknown
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        let began = false
        try {
            measureServerWork("db.begin", () => db.exec("BEGIN IMMEDIATE"))
            began = true
            const result = measureServerWork("db.body", operation)
            const probe = beginCommitProbe(db, "immediate")
            try {
                measureServerWork("db.commit", () => db.exec("COMMIT"))
                endCommitProbe(db, probe, true)
            } catch (error) { endCommitProbe(db, probe, false, error); throw error }
            return result
        } catch (error) {
            if (began && db.inTransaction) {
                try { db.exec("ROLLBACK") } catch {}
            }
            if (!isSqliteBusyError(error) || attempt >= maxAttempts) throw error
            lastError = error
            await delay(10 * (2 ** (attempt - 1)))
        }
    }
    throw lastError
}

/** Keep better-sqlite3's transaction/rollback semantics; time its actual commit separately. */
export function runMeasuredSingleTransaction<T>(db: Database, operation: () => T): T {
    const nested = db.inTransaction
    let bodyEndedAt = 0
    let probe: CommitProbe | undefined
    let result: T
    try {
        result = db.transaction(() => {
            const value = measureServerWork("db.single.body", operation)
            // Nested better-sqlite3 transactions release a savepoint, not a WAL commit.
            probe = nested ? undefined : beginCommitProbe(db, "single")
            bodyEndedAt = performance.now()
            return value
        })()
    } catch (error) { endCommitProbe(db, probe, false, error); throw error }
    recordServerWork("db.single.commit", performance.now() - bodyEndedAt)
    endCommitProbe(db, probe, true)
    return result
}
