import { performance } from "node:perf_hooks"
import { getDb } from "../data/db"
import { registerMemoryCounters } from "./memory-diagnostics"
import { recordServerWork } from "./server-work-performance"
import { drainPlayerWriteQueues, runImmediateTransactionWithRetry, withPlayerWriteQueue } from "./sqlite-write-coordinator"

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

export interface PersistenceSqlStatement {
    sql: string
    params: readonly unknown[]
}

export type PersistenceSqlExecutor = (
    context: PersistenceContext,
    statements: readonly PersistenceSqlStatement[],
) => Promise<void>

let globalWriteTail = Promise.resolve()
// The first migration step keeps SQLite in the main process. Nested domain
// transactions belong to the outer command for metrics, but retain savepoints
// so a caught inner error cannot leave partial writes in the outer transaction.
let activePersistenceContext: PersistenceContext | undefined
type PersistenceStats = {
    queued: number
    committed: number
    failed: number
    maxPending: number
    queueMs: number
    transactionMs: number
    maxQueueMs: number
    maxTransactionMs: number
}
const persistenceStats = new Map<PersistenceDomain, PersistenceStats>()
let persistenceSqlExecutor: PersistenceSqlExecutor | null = null

function yieldToEventLoop(): Promise<void> {
    return new Promise(resolve => setImmediate(resolve))
}

function statsFor(domain: PersistenceDomain): PersistenceStats {
    const existing = persistenceStats.get(domain)
    if (existing) return existing
    const created: PersistenceStats = {
        queued: 0, committed: 0, failed: 0, maxPending: 0, queueMs: 0, transactionMs: 0,
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
        const pending = Math.max(0, value.queued - value.committed - value.failed)
        counters[`domain.${domain}.pending`] = pending
        counters[`domain.${domain}.maxPending`] = value.maxPending
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

function withPersistenceContext<T>(context: PersistenceContext, operation: () => T): T {
    const previous = activePersistenceContext
    activePersistenceContext = context
    try { return operation() }
    finally { activePersistenceContext = previous }
}

/**
 * Install the optional worker-backed SQL command executor. The normal
 * transaction callback path remains available for commands that still need
 * in-process domain logic. Only explicitly commandized writes use this hook.
 */
export function configurePersistenceSqlExecutor(executor: PersistenceSqlExecutor | null): void {
    persistenceSqlExecutor = executor
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
    stats.maxPending = Math.max(stats.maxPending, stats.queued - stats.committed - stats.failed)
    const execute = async (): Promise<T> => {
        // A burst of queued SQLite commands otherwise chains through promise
        // microtasks without returning to libuv. Give TCP heartbeats and HTTP
        // callbacks one scheduling turn between transactions.
        await yieldToEventLoop()
        const queueMs = performance.now() - queuedAt
        stats.queueMs += queueMs
        stats.maxQueueMs = Math.max(stats.maxQueueMs, queueMs)
        recordServerWork("persistence.queue", queueMs)
        const startedAt = performance.now()
        try {
            const result = await runImmediateTransactionWithRetry(() => (
                withPersistenceContext(context, operation)
            ))
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
 * Execute a serializable write command through the optional persistence
 * worker. When the worker is disabled, use the same in-process coordinator so
 * local development and existing deployments keep identical semantics.
 */
export function runPersistenceSqlCommand(
    context: PersistenceContext,
    statements: readonly PersistenceSqlStatement[],
    fallback: () => void,
): Promise<void> {
    if (persistenceSqlExecutor === null) {
        return runPersistenceTransaction(context, () => { fallback() }).then(() => undefined)
    }

    const queuedAt = performance.now()
    const stats = statsFor(context.domain)
    stats.queued++
    stats.maxPending = Math.max(stats.maxPending, stats.queued - stats.committed - stats.failed)
    const execute = async (): Promise<void> => {
        await yieldToEventLoop()
        const queueMs = performance.now() - queuedAt
        stats.queueMs += queueMs
        stats.maxQueueMs = Math.max(stats.maxQueueMs, queueMs)
        recordServerWork("persistence.queue", queueMs)
        const startedAt = performance.now()
        try {
            await persistenceSqlExecutor!(context, statements)
            stats.committed++
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
    if (context.playerId !== undefined) return withPlayerWriteQueue(context.playerId, execute)
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
    // better-sqlite3 creates a savepoint when already inside a transaction.
    // Do not replace this with operation(): some callers catch an inner failure
    // and continue, and still require that inner operation to roll back.
    if (activePersistenceContext) return getDb().transaction(operation)()

    const stats = statsFor(context.domain)
    stats.queued++
    stats.maxPending = Math.max(stats.maxPending, stats.queued - stats.committed - stats.failed)
    const startedAt = performance.now()
    try {
        const result = getDb().transaction(() => (
            withPersistenceContext(context, operation)
        )).immediate()
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
    await drainPlayerWriteQueues()
}
