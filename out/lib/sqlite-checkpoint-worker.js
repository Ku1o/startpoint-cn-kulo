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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.requestSqliteCheckpoint = exports.stopSqliteCheckpointWorker = exports.startSqliteCheckpointWorker = void 0;
const node_path_1 = __importDefault(require("node:path"));
const file_exists_1 = require("../lib/file-exists");
const node_worker_threads_1 = require("node:worker_threads");
const memory_diagnostics_1 = require("./memory-diagnostics");
let worker = null;
const state = {
    enabled: false, started: false, completed: 0, errors: 0, busy: 0,
    truncateAttempts: 0, truncateCompleted: 0, truncateBusy: 0,
    lastDurationMs: null, lastLogFrames: null, lastCheckpointedFrames: null,
    lastWasTruncate: false, lastWalBytes: null, lastPassiveLogFrames: null,
    lastPassiveCheckpointedFrames: null, lastError: null,
};
(0, memory_diagnostics_1.registerMemoryCounters)("sqliteCheckpoint", () => {
    var _a, _b;
    return ({
        enabled: state.enabled, started: state.started, completed: state.completed,
        errors: state.errors, busy: state.busy, truncateAttempts: state.truncateAttempts,
        truncateCompleted: state.truncateCompleted, truncateBusy: state.truncateBusy,
        lastDurationMs: state.lastDurationMs, lastWasTruncate: state.lastWasTruncate,
        lastWalBytes: state.lastWalBytes,
        lastPassiveLogFrames: state.lastPassiveLogFrames,
        lastPassiveCheckpointedFrames: state.lastPassiveCheckpointedFrames,
        lastLogFrames: state.lastLogFrames,
        lastCheckpointedFrames: state.lastCheckpointedFrames,
        lastError: state.lastError !== null,
        lastErrorLength: (_b = (_a = state.lastError) === null || _a === void 0 ? void 0 : _a.length) !== null && _b !== void 0 ? _b : 0,
    });
}, "sqlite");
function enabled(environment = process.env) {
    var _a;
    return /^(1|true|yes|on)$/i.test((_a = environment.SQLITE_CHECKPOINT_WORKER) !== null && _a !== void 0 ? _a : "");
}
function positiveInteger(value, fallback, minimum) {
    const parsed = Number.parseInt(value !== null && value !== void 0 ? value : "", 10);
    return Number.isFinite(parsed) ? Math.max(minimum, parsed) : fallback;
}
function workerLocation() {
    const compiled = node_path_1.default.resolve(__dirname, "../workers/sqlite-checkpoint-worker.js");
    if ((0, file_exists_1.existsSync)(compiled))
        return { filename: compiled };
    return {
        filename: node_path_1.default.resolve(__dirname, "../workers/sqlite-checkpoint-worker.ts"),
        execArgv: ["-r", require.resolve("ts-node/register/transpile-only")],
    };
}
function startSqliteCheckpointWorker(databasePath, environment = process.env) {
    var _a, _b;
    if (worker || !enabled(environment))
        return;
    state.enabled = true;
    state.started = false;
    const location = workerLocation();
    const intervalMs = Math.max(1000, Number.parseInt((_a = environment.SQLITE_CHECKPOINT_INTERVAL_MS) !== null && _a !== void 0 ? _a : "5000", 10) || 5000);
    const truncateFrames = positiveInteger(environment.SQLITE_CHECKPOINT_TRUNCATE_FRAMES, 131072, 1000);
    const truncateBytes = positiveInteger(environment.SQLITE_CHECKPOINT_TRUNCATE_BYTES, 536870912, 4 * 1024 * 1024);
    const truncateCooldownMs = positiveInteger(environment.SQLITE_CHECKPOINT_TRUNCATE_COOLDOWN_MS, 60000, 5000);
    const busyTimeoutMs = Math.max(0, Number.parseInt((_b = environment.SQLITE_CHECKPOINT_BUSY_TIMEOUT_MS) !== null && _b !== void 0 ? _b : "0", 10) || 0);
    const current = new node_worker_threads_1.Worker(location.filename, Object.assign(Object.assign({}, (location.execArgv ? { execArgv: location.execArgv } : {})), { workerData: { databasePath, intervalMs, truncateFrames, truncateBytes, truncateCooldownMs, busyTimeoutMs } }));
    worker = current;
    (0, memory_diagnostics_1.observeWorkerMemory)("sqlite-checkpoint", current);
    current.on("online", () => { state.started = true; });
    current.on("message", message => {
        var _a;
        if (worker !== current)
            return;
        if ((message === null || message === void 0 ? void 0 : message.type) === "checkpoint") {
            state.completed++;
            state.busy += message.busy === 1 ? 1 : 0;
            state.truncateAttempts += message.truncateAttempted === true ? 1 : 0;
            state.truncateCompleted += message.truncateAttempted === true && message.truncateBusy === 0 ? 1 : 0;
            state.truncateBusy += Number(message.truncateBusy) === 1 ? 1 : 0;
            state.lastDurationMs = Number(message.durationMs) || 0;
            state.lastWasTruncate = message.mode === "truncate";
            state.lastWalBytes = Number.isFinite(Number(message.walBytes)) ? Number(message.walBytes) : null;
            state.lastPassiveLogFrames = Number.isFinite(Number(message.passiveLogFrames))
                ? Number(message.passiveLogFrames) : null;
            state.lastPassiveCheckpointedFrames = Number.isFinite(Number(message.passiveCheckpointedFrames))
                ? Number(message.passiveCheckpointedFrames) : null;
            state.lastLogFrames = Number(message.logFrames) || 0;
            state.lastCheckpointedFrames = Number(message.checkpointedFrames) || 0;
            state.lastError = null;
        }
        else if ((message === null || message === void 0 ? void 0 : message.type) === "checkpoint_error") {
            state.errors++;
            state.lastDurationMs = Number(message.durationMs) || 0;
            state.lastError = String((_a = message.error) !== null && _a !== void 0 ? _a : "checkpoint failed").slice(0, 240);
        }
    });
    current.on("error", error => {
        if (worker !== current)
            return;
        state.errors++;
        state.lastError = error.message.slice(0, 240);
    });
    current.once("exit", () => {
        if (worker === current)
            worker = null;
        state.started = false;
    });
    console.log(`[DB] sqlite checkpoint worker enabled intervalMs=${intervalMs}`
        + ` truncateFrames=${truncateFrames} truncateBytes=${truncateBytes}`
        + ` truncateCooldownMs=${truncateCooldownMs} busyTimeoutMs=${busyTimeoutMs}`);
}
exports.startSqliteCheckpointWorker = startSqliteCheckpointWorker;
function stopSqliteCheckpointWorker() {
    return __awaiter(this, void 0, void 0, function* () {
        const current = worker;
        if (!current)
            return;
        worker = null;
        try {
            current.postMessage({ type: "close" });
        }
        catch (_a) { }
        yield current.terminate();
        state.started = false;
    });
}
exports.stopSqliteCheckpointWorker = stopSqliteCheckpointWorker;
function requestSqliteCheckpoint() {
    try {
        worker === null || worker === void 0 ? void 0 : worker.postMessage({ type: "checkpoint_now" });
    }
    catch (_a) { }
}
exports.requestSqliteCheckpoint = requestSqliteCheckpoint;
