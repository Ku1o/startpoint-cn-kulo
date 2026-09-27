"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const better_sqlite3_1 = __importDefault(require("better-sqlite3"));
const node_worker_threads_1 = require("node:worker_threads");
const node_perf_hooks_1 = require("node:perf_hooks");
const input = node_worker_threads_1.workerData;
const database = new better_sqlite3_1.default(input.databasePath);
database.pragma("journal_mode = WAL");
database.pragma("synchronous = NORMAL");
database.pragma("busy_timeout = 250");
database.pragma("wal_autocheckpoint = 0");
let closed = false;
function checkpoint() {
    var _a;
    if (closed)
        return;
    const startedAt = node_perf_hooks_1.performance.now();
    try {
        const result = database.pragma("wal_checkpoint(PASSIVE)");
        const state = (_a = result[0]) !== null && _a !== void 0 ? _a : {};
        node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.postMessage({
            type: "checkpoint",
            durationMs: node_perf_hooks_1.performance.now() - startedAt,
            busy: Number(state.busy) || 0,
            logFrames: Number(state.log) || 0,
            checkpointedFrames: Number(state.checkpointed) || 0,
        });
    }
    catch (error) {
        node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.postMessage({
            type: "checkpoint_error",
            durationMs: node_perf_hooks_1.performance.now() - startedAt,
            error: error instanceof Error ? error.message : String(error),
        });
    }
}
const interval = setInterval(checkpoint, Math.max(250, input.intervalMs));
interval.unref();
checkpoint();
node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.on("message", message => {
    if ((message === null || message === void 0 ? void 0 : message.type) === "checkpoint_now")
        checkpoint();
    if ((message === null || message === void 0 ? void 0 : message.type) !== "close" || closed)
        return;
    closed = true;
    clearInterval(interval);
    try {
        database.close();
    }
    catch (_a) { }
    node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.postMessage({ type: "closed" });
});
