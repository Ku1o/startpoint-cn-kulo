import { performance } from "node:perf_hooks"
import { getDb } from "../data/db"
import { registerMemoryCounters } from "./memory-diagnostics"
import { recordServerWork } from "./server-work-performance"
import { runImmediateTransactionWithRetry, withPlayerWriteQueue } from "./sqlite-write-coordinator"

/**
 * Stable ownership labels for the main database write path.
 *
 * This is intentionally an in-process boundary for the first migration step.
 * It keeps the current transaction semantics while giving every caller an
 * explicit owner. A later worker/process executor can replace the implementation
 * behind this function without making route modules know about SQLite transport.
 */
export type PersistenceDomain =
    | "account"
    | "player"
    | "single-quest"
    | "multi-settlement"
    | "mail"
    | "mission"
    | "gacha"
    | "shop"
    | "event"
    | "leaderboard"
    | "admin"
    | "maintenance"

export interface PersistenceContext {
    domain: PersistenceDomain
    playerId?: number
    /** Stable command label reserved for the future worker transport. */
    operation: string
}

let globalWriteTail = Promise.resolve()
type PersistenceStats = {
    queued: number
    committed: number
    failed: number
    queueMs: number
    transactionMs: number
    maxQueueMs: number
    maxTransactionMs: number
}
const persistenceStats = new Map<PersistenceDomain, PersistenceStats>()

function statsFor(domain: PersistenceDomain): PersistenceStats {
    const existing = persistenceStats.get(domain)
    if (existing) return existing
    const created: PersistenceStats = {
        queued: 0, committed: 0, failed: 0, queueMs: 0, transactionMs: 0,
        maxQueueMs: 0, maxTransactionMs: 0,
    }
    persistenceStats.set(domain, created)
    return created
}

registerMemoryCounters("persistence", () => {
    const counters: Record<string, number | boolean | null> = {}
    for (const [domain, value] of persistenceStats) {
        counters[`domain.${domain}.queued`] = value.queued
        counters[`domain.${domain}.committed`] = value.committed
        counters[`domain.${domain}.failed`] = value.failed
        counters[`domain.${domain}.avgQueueMs`] = value.queued === 0 ? 0 : value.queueMs / value.queued
        counters[`domain.${domain}.avgTransactionMs`] = value.committed + value.failed === 0
            ? 0 : value.transactionMs / (value.committed + value.failed)
        counters[`domain.${domain}.maxQueueMs`] = value.maxQueueMs
        counters[`domain.${domain}.maxTransactionMs`] = value.maxTransactionMs
    }
    return counters
}, "sqlite")

function enqueueGlobalWrite<T>(operation: () => Promise<T>): Promise<T> {
    const previous = globalWriteTail
    let release!: () => void
    const current = new Promise<void>(resolve => { release = resolve })
    globalWriteTail = previous.then(() => current)
    return previous.then(async () => {
        try { return await operation() }
        finally { release() }
    })
}

/**
 * Execute one complete main-database transaction under an explicit domain.
 *
 * The operation remains synchronous from better-sqlite3's point of view. The
 * queue and timing seam are deliberate: business modules can migrate here one
 * by one, while a future worker-backed executor can preserve the same contract.
 */
export async function runPersistenceTransaction<T>(
    context: PersistenceContext,
    operation: () => T,
): Promise<T> {
    const queuedAt = performance.now()
    const stats = statsFor(context.domain)
    stats.queued++
    const execute = async (): Promise<T> => {
        const queueMs = performance.now() - queuedAt
        stats.queueMs += queueMs
        stats.maxQueueMs = Math.max(stats.maxQueueMs, queueMs)
        recordServerWork("persistence.queue", queueMs)
        const startedAt = performance.now()
        try {
            const result = await runImmediateTransactionWithRetry(operation)
            stats.committed++
            return result
        } catch (error) {
            stats.failed++
            throw error
        } finally {
            const transactionMs = performance.now() - startedAt
            stats.transactionMs += transactionMs
            stats.maxTransactionMs = Math.max(stats.maxTransactionMs, transactionMs)
            recordServerWork("persistence.transaction", transactionMs)
        }
    }

    if (context.playerId !== undefined) {
        return withPlayerWriteQueue(context.playerId, execute)
    }
    return enqueueGlobalWrite(execute)
}

/**
 * Compatibility boundary for legacy synchronous callers.
 *
 * Synchronous APIs cannot wait on the async queue, so this helper keeps the
 * existing better-sqlite3 immediate-transaction contract and contributes to
 * the same domain metrics. New request paths should use the async variant.
 */
export function runPersistenceTransactionSync<T>(
    context: PersistenceContext,
    operation: () => T,
): T {
    const stats = statsFor(context.domain)
    stats.queued++
    const startedAt = performance.now()
    try {
        const result = getDb().transaction(operation).immediate()
        stats.committed++
        return result
    } catch (error) {
        stats.failed++
        throw error
    } finally {
        const transactionMs = performance.now() - startedAt
        stats.transactionMs += transactionMs
        stats.maxTransactionMs = Math.max(stats.maxTransactionMs, transactionMs)
        recordServerWork("persistence.transaction", transactionMs)
    }
}

/** Wait for queued asynchronous persistence work before a graceful shutdown. */
export async function drainPersistence(): Promise<void> {
    await globalWriteTail
}
