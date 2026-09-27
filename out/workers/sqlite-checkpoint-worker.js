"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const better_sqlite3_1 = __importDefault(require("better-sqlite3"));
const node_fs_1 = __importDefault(require("node:fs"));
const node_worker_threads_1 = require("node:worker_threads");
const node_perf_hooks_1 = require("node:perf_hooks");
const input = node_worker_threads_1.workerData;
const database = new better_sqlite3_1.default(input.databasePath);
database.pragma("journal_mode = WAL");
database.pragma("synchronous = NORMAL");
database.pragma("busy_timeout = 250");
database.pragma("wal_autocheckpoint = 0");
let closed = false;
// Allow the first oversized WAL to be reclaimed immediately after startup.
let lastTruncateAt = Number.NEGATIVE_INFINITY;
function walBytes() {
    try {
        return node_fs_1.default.statSync(`${input.databasePath}-wal`).size;
    }
    catch (_a) {
        return null;
    }
}
function numberValue(value) {
    return Number.isFinite(Number(value)) ? Number(value) : 0;
}
function checkpoint() {
    var _a, _b;
    if (closed)
        return;
    const startedAt = node_perf_hooks_1.performance.now();
    try {
        const passiveResult = database.pragma("wal_checkpoint(PASSIVE)");
        const passiveState = (_a = passiveResult[0]) !== null && _a !== void 0 ? _a : {};
        const passiveLogFrames = numberValue(passiveState.log);
        const passiveCheckpointedFrames = numberValue(passiveState.checkpointed);
        const currentWalBytes = walBytes();
        const truncateDue = (passiveLogFrames >= input.truncateFrames
            || (currentWalBytes !== null && currentWalBytes >= input.truncateBytes)) && node_perf_hooks_1.performance.now() - lastTruncateAt >= input.truncateCooldownMs;
        let state = passiveState;
        let mode = "passive";
        let truncateAttempted = false;
        let truncateBusy = 0;
        if (truncateDue) {
            truncateAttempted = true;
            lastTruncateAt = node_perf_hooks_1.performance.now();
            const truncateResult = database.pragma("wal_checkpoint(TRUNCATE)");
            state = (_b = truncateResult[0]) !== null && _b !== void 0 ? _b : {};
            truncateBusy = numberValue(state.busy);
            mode = "truncate";
        }
        node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.postMessage({
            type: "checkpoint",
            durationMs: node_perf_hooks_1.performance.now() - startedAt,
            mode,
            busy: Math.max(numberValue(passiveState.busy), truncateBusy),
            logFrames: numberValue(state.log),
            checkpointedFrames: numberValue(state.checkpointed),
            passiveLogFrames,
            passiveCheckpointedFrames,
            truncateAttempted,
            truncateBusy,
            walBytes: walBytes(),
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
