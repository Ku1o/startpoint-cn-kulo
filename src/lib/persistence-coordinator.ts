import { performance } from "node:perf_hooks"
import { getDb } from "../data/db"
import { registerMemoryCounters } from "./memory-diagnostics"
import { createWriterCommandContext, getWriterCommand } from "./persistence/command-registry"
import {
    executeSqliteWriterCommand,
    isSqliteWriterEnabled,
    isSqliteWriterReady,
    waitForSqliteWriterReady,
    writerThreadSettings,
} from "./persistence/writer-client"
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

export interface PersistenceTransactionOptions<T> {
    /** Runs after SQLite COMMIT succeeds, before the per-player queue is released. */
    afterCommit?: (result: T) => void
}

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
let writerFallbackCount = 0
let writerStartupWaitCount = 0

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
    counters["writer.fallbacks"] = writerFallbackCount
    counters["writer.startupWaits"] = writerStartupWaitCount
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
    options: PersistenceTransactionOptions<T> = {},
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
            if (options.afterCommit) {
                try {
                    options.afterCommit(result)
                } catch (error) {
                    // The database is already committed. Observability or
                    // non-durable side effects must not turn success into a retry.
                    console.error(
                        `[PERSISTENCE] afterCommit failed: domain=${context.domain} operation=${context.operation}`,
                        error,
                    )
                }
            }
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
 * Execute a registered write command.
 *
 * The command runs in the SQLite writer thread when `CN_WRITER_THREAD` is
 * enabled and the thread is ready, and in-process otherwise. Both paths share
 * the same registry entry, the same per-player/global ordering and the same
 * domain metrics, so flipping the switch cannot change business results.
 *
 * The command implementation owns its transaction: the writer thread already
 * wraps every command in the batch transaction, and the in-process path leaves
 * the existing `runPersistenceTransactionSync` contract untouched.
 */
export async function runWriterCommand<Args, Result>(
    name: string,
    args: Args,
    context: PersistenceContext,
): Promise<Result> {
    const queuedAt = performance.now()
    const stats = statsFor(context.domain)
    stats.queued++
    stats.maxPending = Math.max(stats.maxPending, stats.queued - stats.committed - stats.failed)
    const execute = async (): Promise<Result> => {
        await yieldToEventLoop()
        const queueMs = performance.now() - queuedAt
        stats.queueMs += queueMs
        stats.maxQueueMs = Math.max(stats.maxQueueMs, queueMs)
        recordServerWork("persistence.queue", queueMs)
        const startedAt = performance.now()
        try {
            const result = await executeRegisteredWriterCommand<Args, Result>(name, args, context)
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

/** Bounded wait so the first requests after a restart do not fail on warm-up. */
const WRITER_STARTUP_WAIT_MS = 10_000

async function executeRegisteredWriterCommand<Args, Result>(
    name: string,
    args: Args,
    context: PersistenceContext,
): Promise<Result> {
    if (isSqliteWriterEnabled()) {
        if (!isSqliteWriterReady()) {
            writerStartupWaitCount++
            await waitForSqliteWriterReady(WRITER_STARTUP_WAIT_MS)
        }
        if (isSqliteWriterReady()) {
            const value = await executeSqliteWriterCommand({
                name,
                args,
                meta: {
                    domain: context.domain,
                    operation: context.operation,
                    playerId: context.playerId,
                },
            })
            return value as Result
        }
        // The worker is configured but never became ready. An explicit
        // fallback switch may continue in-process; otherwise the caller must
        // see the failure instead of an unverified write.
        const reason = `SQLite writer thread is not ready; command ${name} was not executed.`
        if (!writerThreadSettings().fallback) throw new Error(reason)
        writerFallbackCount++
        console.error(`[PERSISTENCE] ${reason} Falling back to the in-process implementation.`)
    }
    return runRegisteredWriterCommandInProcess<Args, Result>(name, args, context)
}

let writerCommandsLoaded = false

/**
 * Bind command names to domain code on first use.
 *
 * The requirement is intentionally lazy: `commands` imports domain modules
 * that import this coordinator, so a top-level import would create a
 * module-load cycle. Requiring it here keeps the import graph acyclic while
 * still letting any entry point (server, test or script) run a command
 * in-process without remembering to import the registry.
 */
function ensureWriterCommandsLoaded(): void {
    if (writerCommandsLoaded) return
    writerCommandsLoaded = true
    require("./persistence/commands")
}

function runRegisteredWriterCommandInProcess<Args, Result>(
    name: string,
    args: Args,
    context: PersistenceContext,
): Result {
    ensureWriterCommandsLoaded()
    const handler = getWriterCommand(name)
    if (handler === undefined) {
        throw new Error(`Writer command is not registered: ${name}`)
    }
    const effects: Array<() => void> = []
    const commandContext = createWriterCommandContext(
        { domain: context.domain, operation: context.operation, playerId: context.playerId },
        effect => effects.push(effect),
    )
    const result = handler(args, commandContext) as Result
    for (const effect of effects) {
        try {
            effect()
        } catch (error) {
            // Mirrors runPersistenceTransaction: an already committed command
            // must not be reported as failed because a side effect threw.
            console.error(
                `[PERSISTENCE] afterCommit failed: domain=${context.domain} operation=${context.operation}`,
                error,
            )
        }
    }
    return result
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
