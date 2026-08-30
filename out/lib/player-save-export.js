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
exports.exportPlayerSaveInWorker = exports.PlayerSaveExportError = exports.DEFAULT_PLAYER_SAVE_EXPORT_MAX_BYTES = void 0;
const fs_1 = require("fs");
const path_1 = __importDefault(require("path"));
const worker_threads_1 = require("worker_threads");
const admin_database_backup_1 = require("./admin-database-backup");
exports.DEFAULT_PLAYER_SAVE_EXPORT_MAX_BYTES = 64 * 1024 * 1024;
const DEFAULT_PLAYER_SAVE_EXPORT_TIMEOUT_MS = 120000;
class PlayerSaveExportError extends Error {
    constructor(code, message) {
        super(message);
        this.code = code;
        this.name = "PlayerSaveExportError";
    }
}
exports.PlayerSaveExportError = PlayerSaveExportError;
let activeExportWorker = null;
function getWorkerLocation() {
    const compiledWorker = path_1.default.resolve(__dirname, "../workers/player-save-export-worker.js");
    if ((0, fs_1.existsSync)(compiledWorker))
        return { filename: compiledWorker };
    return {
        filename: path_1.default.resolve(__dirname, "../workers/player-save-export-worker.ts"),
        execArgv: ["-r", require.resolve("ts-node/register/transpile-only")],
    };
}
function normalizeLimit(value, fallback, minimum, maximum) {
    if (value === undefined || !Number.isFinite(value))
        return fallback;
    return Math.max(minimum, Math.min(maximum, Math.trunc(value)));
}
function exportPlayerSaveInWorker(playerId_1) {
    return __awaiter(this, arguments, void 0, function* (playerId, options = {}) {
        var _a, _b;
        if (!Number.isSafeInteger(playerId) || playerId < 1) {
            throw new PlayerSaveExportError("export-failed", "玩家 ID 无效");
        }
        if ((_a = options.signal) === null || _a === void 0 ? void 0 : _a.aborted) {
            throw new PlayerSaveExportError("aborted", "客户端已取消存档导出");
        }
        if (activeExportWorker !== null) {
            throw new PlayerSaveExportError("busy", "已有一个存档正在导出，请稍后再试");
        }
        const maxBytes = normalizeLimit(options.maxBytes, exports.DEFAULT_PLAYER_SAVE_EXPORT_MAX_BYTES, 1, exports.DEFAULT_PLAYER_SAVE_EXPORT_MAX_BYTES);
        const configuredTimeout = Number.parseInt((_b = process.env.PLAYER_SAVE_EXPORT_TIMEOUT_MS) !== null && _b !== void 0 ? _b : "", 10);
        const timeoutMs = normalizeLimit(options.timeoutMs, Number.isFinite(configuredTimeout) ? configuredTimeout : DEFAULT_PLAYER_SAVE_EXPORT_TIMEOUT_MS, 1000, 10 * 60000);
        const workerLocation = getWorkerLocation();
        const worker = new worker_threads_1.Worker(workerLocation.filename, {
            execArgv: workerLocation.execArgv,
            workerData: {
                databasePath: path_1.default.join((0, admin_database_backup_1.getDatabaseDirectory)(), "wdfp_data.db"),
                playerId,
                maxBytes,
            },
        });
        worker.unref();
        activeExportWorker = worker;
        return new Promise((resolve, reject) => {
            var _a;
            let settled = false;
            const finish = (callback) => {
                var _a;
                if (settled)
                    return;
                settled = true;
                clearTimeout(timeout);
                (_a = options.signal) === null || _a === void 0 ? void 0 : _a.removeEventListener("abort", onAbort);
                if (activeExportWorker === worker)
                    activeExportWorker = null;
                callback();
            };
            const fail = (code, message) => {
                finish(() => reject(new PlayerSaveExportError(code, message)));
            };
            const onAbort = () => {
                void worker.terminate();
                fail("aborted", "客户端已取消存档导出");
            };
            const timeout = setTimeout(() => {
                void worker.terminate();
                fail("timeout", `存档导出超过 ${timeoutMs / 1000} 秒，已终止`);
            }, timeoutMs);
            timeout.unref();
            (_a = options.signal) === null || _a === void 0 ? void 0 : _a.addEventListener("abort", onAbort, { once: true });
            worker.once("message", (message) => {
                var _a, _b, _c;
                if (message.type === "completed" && message.payload instanceof ArrayBuffer) {
                    const payload = Buffer.from(message.payload, 0, (_a = message.byteLength) !== null && _a !== void 0 ? _a : message.payload.byteLength);
                    finish(() => resolve({
                        payload,
                        rowCount: Number(message.rowCount) || 0,
                    }));
                    return;
                }
                fail((_b = message.code) !== null && _b !== void 0 ? _b : "export-failed", (_c = message.error) !== null && _c !== void 0 ? _c : "存档导出 worker 返回了无效结果");
            });
            worker.once("error", error => fail("export-failed", error.message));
            worker.once("exit", code => {
                if (!settled)
                    fail("export-failed", `存档导出 worker 未返回结果（code=${code}）`);
            });
        });
    });
}
exports.exportPlayerSaveInWorker = exportPlayerSaveInWorker;
