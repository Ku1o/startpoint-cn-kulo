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
exports.runMeasuredSingleTransaction = exports.runImmediateTransactionWithRetry = exports.withPlayerWriteQueue = exports.isSqliteBusyError = void 0;
const db_1 = require("../data/db");
const node_perf_hooks_1 = require("node:perf_hooks");
const server_work_performance_1 = require("./server-work-performance");
const playerWriteTails = new Map();
function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}
function isSqliteBusyError(error) {
    var _a;
    if (!(error instanceof Error) || !("code" in error))
        return false;
    const code = String((_a = error.code) !== null && _a !== void 0 ? _a : "");
    return code === "SQLITE_BUSY" || code === "SQLITE_BUSY_SNAPSHOT" || code.startsWith("SQLITE_BUSY_");
}
exports.isSqliteBusyError = isSqliteBusyError;
function withPlayerWriteQueue(playerId, operation) {
    return __awaiter(this, void 0, void 0, function* () {
        var _a;
        const previous = (_a = playerWriteTails.get(playerId)) !== null && _a !== void 0 ? _a : Promise.resolve();
        let release;
        const current = new Promise(resolve => { release = resolve; });
        const tail = previous.then(() => current);
        playerWriteTails.set(playerId, tail);
        const queuedAt = node_perf_hooks_1.performance.now();
        yield previous;
        (0, server_work_performance_1.recordServerWork)("db.playerQueue", node_perf_hooks_1.performance.now() - queuedAt);
        try {
            return yield operation();
        }
        finally {
            release();
            void tail.finally(() => {
                if (playerWriteTails.get(playerId) === tail)
                    playerWriteTails.delete(playerId);
            });
        }
    });
}
exports.withPlayerWriteQueue = withPlayerWriteQueue;
/** Run a short write transaction and retry the complete mutation on snapshot contention. */
function runImmediateTransactionWithRetry(operation_1) {
    return __awaiter(this, arguments, void 0, function* (operation, maxAttempts = 3) {
        const db = (0, db_1.getDb)();
        let lastError;
        for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
            let began = false;
            try {
                (0, server_work_performance_1.measureServerWork)("db.begin", () => db.exec("BEGIN IMMEDIATE"));
                began = true;
                const result = (0, server_work_performance_1.measureServerWork)("db.body", operation);
                (0, server_work_performance_1.measureServerWork)("db.commit", () => db.exec("COMMIT"));
                return result;
            }
            catch (error) {
                if (began && db.inTransaction) {
                    try {
                        db.exec("ROLLBACK");
                    }
                    catch (_a) { }
                }
                if (!isSqliteBusyError(error) || attempt >= maxAttempts)
                    throw error;
                lastError = error;
                yield delay(10 * (2 ** (attempt - 1)));
            }
        }
        throw lastError;
    });
}
exports.runImmediateTransactionWithRetry = runImmediateTransactionWithRetry;
/** Keep better-sqlite3's transaction/rollback semantics; time its actual commit separately. */
function runMeasuredSingleTransaction(db, operation) {
    let bodyEndedAt = 0;
    const result = db.transaction(() => {
        try {
            return (0, server_work_performance_1.measureServerWork)("db.single.body", operation);
        }
        finally {
            bodyEndedAt = node_perf_hooks_1.performance.now();
        }
    })();
    (0, server_work_performance_1.recordServerWork)("db.single.commit", node_perf_hooks_1.performance.now() - bodyEndedAt);
    return result;
}
exports.runMeasuredSingleTransaction = runMeasuredSingleTransaction;
