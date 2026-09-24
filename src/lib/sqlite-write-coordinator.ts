import { getDb } from "../data/db"
import { performance } from "node:perf_hooks"
import { measureServerWork, recordServerWork } from "./server-work-performance"
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
            measureServerWork("db.commit", () => db.exec("COMMIT"))
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
    let bodyEndedAt = 0
    const result = db.transaction(() => {
        try { return measureServerWork("db.single.body", operation) }
        finally { bodyEndedAt = performance.now() }
    })()
    recordServerWork("db.single.commit", performance.now() - bodyEndedAt)
    return result
}
