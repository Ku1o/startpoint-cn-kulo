"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.drainPersistence = exports.runPersistenceTransactionSync = exports.runPersistenceSqlCommand = exports.runPersistenceTransaction = exports.configurePersistenceSqlExecutor = void 0;
const node_perf_hooks_1 = require("node:perf_hooks");
const db_1 = require("../data/db");
const memory_diagnostics_1 = require("./memory-diagnostics");
const server_work_performance_1 = require("./server-work-performance");
const sqlite_write_coordinator_1 = require("./sqlite-write-coordinator");
let globalWriteTail = Promise.resolve();
// The first migration step keeps SQLite in the main process. Nested domain
// transactions belong to the outer command for metrics, but retain savepoints
// so a caught inner error cannot leave partial writes in the outer transaction.
let activePersistenceContext;
const persistenceStats = new Map();
let persistenceSqlExecutor = null;
function yieldToEventLoop() {
    return new Promise(resolve => setImmediate(resolve));
}
function statsFor(domain) {
    const existing = persistenceStats.get(domain);
    if (existing)
        return existing;
    const created = {
        queued: 0, committed: 0, failed: 0, maxPending: 0, queueMs: 0, transactionMs: 0,
        maxQueueMs: 0, maxTransactionMs: 0,
    };
    persistenceStats.set(domain, created);
    return created;
}
(0, memory_diagnostics_1.registerMemoryCounters)("persistence", () => {
    const counters = {};
    for (const [domain, value] of persistenceStats) {
        counters[`domain.${domain}.queued`] = value.queued;
        counters[`domain.${domain}.committed`] = value.committed;
        counters[`domain.${domain}.failed`] = value.failed;
        const pending = Math.max(0, value.queued - value.committed - value.failed);
        counters[`domain.${domain}.pending`] = pending;
        counters[`domain.${domain}.maxPending`] = value.maxPending;
        counters[`domain.${domain}.avgQueueMs`] = value.queued === 0 ? 0 : value.queueMs / value.queued;
        counters[`domain.${domain}.avgTransactionMs`] = value.committed + value.failed === 0
            ? 0 : value.transactionMs / (value.committed + value.failed);
        counters[`domain.${domain}.maxQueueMs`] = value.maxQueueMs;
        counters[`domain.${domain}.maxTransactionMs`] = value.maxTransactionMs;
    }
    return counters;
}, "sqlite");
function enqueueGlobalWrite(operation) {
    const previous = globalWriteTail;
    let release;
    const current = new Promise(resolve => { release = resolve; });
    globalWriteTail = previous.then(() => current);
    return previous.then(() => __awaiter(this, void 0, void 0, function* () {
        try {
            return yield operation();
        }
        finally {
            release();
        }
    }));
}
function withPersistenceContext(context, operation) {
    const previous = activePersistenceContext;
    activePersistenceContext = context;
    try {
        return operation();
    }
    finally {
        activePersistenceContext = previous;
    }
}
/**
 * Install the optional worker-backed SQL command executor. The normal
 * transaction callback path remains available for commands that still need
 * in-process domain logic. Only explicitly commandized writes use this hook.
 */
function configurePersistenceSqlExecutor(executor) {
    persistenceSqlExecutor = executor;
}
exports.configurePersistenceSqlExecutor = configurePersistenceSqlExecutor;
/**
 * Execute one complete main-database transaction under an explicit domain.
 *
 * The operation remains synchronous from better-sqlite3's point of view. The
 * queue and timing seam are deliberate: business modules can migrate here one
 * by one, while a future worker-backed executor can preserve the same contract.
 */
function runPersistenceTransaction(context, operation) {
    return __awaiter(this, void 0, void 0, function* () {
        const queuedAt = node_perf_hooks_1.performance.now();
        const stats = statsFor(context.domain);
        stats.queued++;
        stats.maxPending = Math.max(stats.maxPending, stats.queued - stats.committed - stats.failed);
        const execute = () => __awaiter(this, void 0, void 0, function* () {
            // A burst of queued SQLite commands otherwise chains through promise
            // microtasks without returning to libuv. Give TCP heartbeats and HTTP
            // callbacks one scheduling turn between transactions.
            yield yieldToEventLoop();
            const queueMs = node_perf_hooks_1.performance.now() - queuedAt;
            stats.queueMs += queueMs;
            stats.maxQueueMs = Math.max(stats.maxQueueMs, queueMs);
            (0, server_work_performance_1.recordServerWork)("persistence.queue", queueMs);
            const startedAt = node_perf_hooks_1.performance.now();
            try {
                const result = yield (0, sqlite_write_coordinator_1.runImmediateTransactionWithRetry)(() => (withPersistenceContext(context, operation)));
                stats.committed++;
                return result;
            }
            catch (error) {
                stats.failed++;
                throw error;
            }
            finally {
                const transactionMs = node_perf_hooks_1.performance.now() - startedAt;
                stats.transactionMs += transactionMs;
                stats.maxTransactionMs = Math.max(stats.maxTransactionMs, transactionMs);
                (0, server_work_performance_1.recordServerWork)("persistence.transaction", transactionMs);
            }
        });
        if (context.playerId !== undefined) {
            return (0, sqlite_write_coordinator_1.withPlayerWriteQueue)(context.playerId, execute);
        }
        return enqueueGlobalWrite(execute);
    });
}
exports.runPersistenceTransaction = runPersistenceTransaction;
/**
 * Execute a serializable write command through the optional persistence
 * worker. When the worker is disabled, use the same in-process coordinator so
 * local development and existing deployments keep identical semantics.
 */
function runPersistenceSqlCommand(context, statements, fallback) {
    if (persistenceSqlExecutor === null) {
        return runPersistenceTransaction(context, () => { fallback(); }).then(() => undefined);
    }
    const queuedAt = node_perf_hooks_1.performance.now();
    const stats = statsFor(context.domain);
    stats.queued++;
    stats.maxPending = Math.max(stats.maxPending, stats.queued - stats.committed - stats.failed);
    const execute = () => __awaiter(this, void 0, void 0, function* () {
        yield yieldToEventLoop();
        const queueMs = node_perf_hooks_1.performance.now() - queuedAt;
        stats.queueMs += queueMs;
        stats.maxQueueMs = Math.max(stats.maxQueueMs, queueMs);
        (0, server_work_performance_1.recordServerWork)("persistence.queue", queueMs);
        const startedAt = node_perf_hooks_1.performance.now();
        try {
            yield persistenceSqlExecutor(context, statements);
            stats.committed++;
        }
        catch (error) {
            stats.failed++;
            throw error;
        }
        finally {
            const transactionMs = node_perf_hooks_1.performance.now() - startedAt;
            stats.transactionMs += transactionMs;
            stats.maxTransactionMs = Math.max(stats.maxTransactionMs, transactionMs);
            (0, server_work_performance_1.recordServerWork)("persistence.transaction", transactionMs);
        }
    });
    if (context.playerId !== undefined)
        return (0, sqlite_write_coordinator_1.withPlayerWriteQueue)(context.playerId, execute);
    return enqueueGlobalWrite(execute);
}
exports.runPersistenceSqlCommand = runPersistenceSqlCommand;
/**
 * Compatibility boundary for legacy synchronous callers.
 *
 * Synchronous APIs cannot wait on the async queue, so this helper keeps the
 * existing better-sqlite3 immediate-transaction contract and contributes to
 * the same domain metrics. New request paths should use the async variant.
 */
function runPersistenceTransactionSync(context, operation) {
    // better-sqlite3 creates a savepoint when already inside a transaction.
    // Do not replace this with operation(): some callers catch an inner failure
    // and continue, and still require that inner operation to roll back.
    if (activePersistenceContext)
        return (0, db_1.getDb)().transaction(operation)();
    const stats = statsFor(context.domain);
    stats.queued++;
    stats.maxPending = Math.max(stats.maxPending, stats.queued - stats.committed - stats.failed);
    const startedAt = node_perf_hooks_1.performance.now();
    try {
        const result = (0, db_1.getDb)().transaction(() => (withPersistenceContext(context, operation))).immediate();
        stats.committed++;
        return result;
    }
    catch (error) {
        stats.failed++;
        throw error;
    }
    finally {
        const transactionMs = node_perf_hooks_1.performance.now() - startedAt;
        stats.transactionMs += transactionMs;
        stats.maxTransactionMs = Math.max(stats.maxTransactionMs, transactionMs);
        (0, server_work_performance_1.recordServerWork)("persistence.transaction", transactionMs);
    }
}
exports.runPersistenceTransactionSync = runPersistenceTransactionSync;
/** Wait for queued asynchronous persistence work before a graceful shutdown. */
function drainPersistence() {
    return __awaiter(this, void 0, void 0, function* () {
        yield globalWriteTail;
        yield (0, sqlite_write_coordinator_1.drainPlayerWriteQueues)();
    });
}
exports.drainPersistence = drainPersistence;
