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
    lastDurationMs: null, lastLogFrames: null, lastCheckpointedFrames: null,
    lastError: null,
};
(0, memory_diagnostics_1.registerMemoryCounters)("sqliteCheckpoint", () => {
    var _a, _b;
    return ({
        enabled: state.enabled, started: state.started, completed: state.completed,
        errors: state.errors, busy: state.busy, lastDurationMs: state.lastDurationMs,
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
    var _a;
    if (worker || !enabled(environment))
        return;
    state.enabled = true;
    state.started = false;
    const location = workerLocation();
    const intervalMs = Math.max(1000, Number.parseInt((_a = environment.SQLITE_CHECKPOINT_INTERVAL_MS) !== null && _a !== void 0 ? _a : "5000", 10) || 5000);
    const current = new node_worker_threads_1.Worker(location.filename, Object.assign(Object.assign({}, (location.execArgv ? { execArgv: location.execArgv } : {})), { workerData: { databasePath, intervalMs } }));
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
            state.lastDurationMs = Number(message.durationMs) || 0;
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
    console.log(`[DB] sqlite checkpoint worker enabled intervalMs=${intervalMs}`);
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
