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
const better_sqlite3_1 = __importDefault(require("better-sqlite3"));
const node_worker_threads_1 = require("node:worker_threads");
const memory_diagnostics_1 = require("../lib/memory-diagnostics");
const input = node_worker_threads_1.workerData;
const database = new better_sqlite3_1.default(input.databasePath);
database.pragma("journal_mode = WAL");
database.pragma("synchronous = NORMAL");
database.pragma(`busy_timeout = ${Math.max(0, input.busyTimeoutMs)}`);
// Checkpoint ownership remains with the optional checkpoint worker or the
// main connection. This connection only executes business write commands.
database.pragma("wal_autocheckpoint = 0");
database.pragma("foreign_keys = ON");
let closed = false;
let executing = false;
let completed = 0;
let failed = 0;
let busyRetries = 0;
function isBusyError(error) {
    var _a;
    if (!(error instanceof Error) || !("code" in error))
        return false;
    const code = String((_a = error.code) !== null && _a !== void 0 ? _a : "");
    return code === "SQLITE_BUSY"
        || code === "SQLITE_BUSY_SNAPSHOT"
        || code.startsWith("SQLITE_BUSY_");
}
function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}
function runCommand(command) {
    if (!Array.isArray(command.statements) || command.statements.length === 0) {
        throw new Error("Persistence command must contain at least one statement.");
    }
    return database.transaction(() => {
        var _a;
        let changes = 0;
        let lastInsertRowid = null;
        for (const statement of command.statements) {
            if (!statement || typeof statement.sql !== "string" || statement.sql.length === 0) {
                throw new Error("Persistence command contains an invalid SQL statement.");
            }
            const result = database.prepare(statement.sql).run(...((_a = statement.params) !== null && _a !== void 0 ? _a : []));
            changes += result.changes;
            lastInsertRowid = Number(result.lastInsertRowid);
        }
        return { changes, lastInsertRowid };
    }).immediate();
}
function execute(command) {
    return __awaiter(this, void 0, void 0, function* () {
        var _a;
        if (closed)
            throw new Error("SQLite persistence worker is closed.");
        executing = true;
        try {
            let lastError;
            for (let attempt = 1; attempt <= Math.max(1, input.maxAttempts); attempt += 1) {
                try {
                    const result = runCommand(command);
                    completed++;
                    node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.postMessage(Object.assign({ type: "result", id: command.id, operation: command.operation }, result));
                    return;
                }
                catch (error) {
                    lastError = error;
                    if (!isBusyError(error) || attempt >= input.maxAttempts)
                        throw error;
                    busyRetries++;
                    yield delay(10 * (2 ** (attempt - 1)));
                }
            }
            throw lastError;
        }
        catch (error) {
            failed++;
            node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.postMessage({
                type: "error",
                id: command.id,
                operation: command.operation,
                code: error instanceof Error && "code" in error
                    ? String((_a = error.code) !== null && _a !== void 0 ? _a : "") : null,
                error: error instanceof Error ? error.message : String(error),
            });
        }
        finally {
            executing = false;
        }
    });
}
(0, memory_diagnostics_1.installWorkerMemoryProbe)(() => ({ completed, failed, busyRetries, executing }));
node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.on("message", (message) => {
    if (typeof message === "object" && "type" in message && message.type === "close") {
        if (executing || closed)
            return;
        closed = true;
        try {
            database.close();
        }
        catch (_a) { }
        node_worker_threads_1.parentPort === null || node_worker_threads_1.parentPort === void 0 ? void 0 : node_worker_threads_1.parentPort.postMessage({ type: "closed" });
        return;
    }
    void execute(message);
});
