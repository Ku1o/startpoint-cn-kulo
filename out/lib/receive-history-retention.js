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
exports.createReceiveHistoryRetentionService = exports.runReceiveHistoryRetentionPass = exports.millisecondsUntilNextReceiveHistoryRetentionRun = exports.getReceiveHistoryRetentionSchedule = exports.isReceiveHistoryRetentionEnabled = void 0;
const DEFAULT_MAX_ROWS = 500;
const DEFAULT_DAILY_HOUR = 4;
const DEFAULT_DAILY_MINUTE = 30;
const DEFAULT_BATCH_PLAYERS = 5;
const DEFAULT_PAUSE_MS = 100;
const DEFAULT_BUSY_RETRY_ATTEMPTS = 5;
const DEFAULT_BUSY_RETRY_DELAY_MS = 20;
function normalizedInteger(value, fallback, minimum) {
    if (!Number.isSafeInteger(value) || value === undefined || value < minimum)
        return fallback;
    return value;
}
function normalizedBoundedInteger(value, fallback, minimum, maximum) {
    if (!Number.isSafeInteger(value) || value === undefined || value < minimum || value > maximum) {
        return fallback;
    }
    return value;
}
function isReceiveHistoryRetentionEnabled(env = process.env) {
    var _a;
    const value = (_a = env.RECEIVE_HISTORY_RETENTION_ENABLED) === null || _a === void 0 ? void 0 : _a.trim().toLowerCase();
    return value !== "0" && value !== "false" && value !== "off" && value !== "no";
}
exports.isReceiveHistoryRetentionEnabled = isReceiveHistoryRetentionEnabled;
function getReceiveHistoryRetentionSchedule(env = process.env) {
    var _a, _b;
    const value = (_b = (_a = env.RECEIVE_HISTORY_RETENTION_TIME) === null || _a === void 0 ? void 0 : _a.trim()) !== null && _b !== void 0 ? _b : "";
    const match = /^(\d{1,2}):(\d{2})$/.exec(value);
    if (!match)
        return { hour: DEFAULT_DAILY_HOUR, minute: DEFAULT_DAILY_MINUTE };
    const hour = Number(match[1]);
    const minute = Number(match[2]);
    if (!Number.isInteger(hour) || hour < 0 || hour > 23 || !Number.isInteger(minute) || minute < 0 || minute > 59) {
        return { hour: DEFAULT_DAILY_HOUR, minute: DEFAULT_DAILY_MINUTE };
    }
    return { hour, minute };
}
exports.getReceiveHistoryRetentionSchedule = getReceiveHistoryRetentionSchedule;
function millisecondsUntilNextReceiveHistoryRetentionRun(now, hour, minute) {
    const nextRun = new Date(now.getTime());
    nextRun.setHours(hour, minute, 0, 0);
    if (nextRun.getTime() <= now.getTime())
        nextRun.setDate(nextRun.getDate() + 1);
    return Math.max(1, nextRun.getTime() - now.getTime());
}
exports.millisecondsUntilNextReceiveHistoryRetentionRun = millisecondsUntilNextReceiveHistoryRetentionRun;
function resolveOptions(options) {
    var _a, _b;
    const schedule = getReceiveHistoryRetentionSchedule();
    return {
        enabled: (_a = options.enabled) !== null && _a !== void 0 ? _a : isReceiveHistoryRetentionEnabled(),
        maxRows: normalizedInteger(options.maxRows, DEFAULT_MAX_ROWS, 1),
        initialDelayMs: options.initialDelayMs === undefined
            ? null
            : normalizedInteger(options.initialDelayMs, 0, 0),
        dailyHour: normalizedBoundedInteger(options.dailyHour, schedule.hour, 0, 23),
        dailyMinute: normalizedBoundedInteger(options.dailyMinute, schedule.minute, 0, 59),
        batchPlayers: normalizedInteger(options.batchPlayers, DEFAULT_BATCH_PLAYERS, 1),
        pauseMs: normalizedInteger(options.pauseMs, DEFAULT_PAUSE_MS, 0),
        busyRetryAttempts: normalizedInteger(options.busyRetryAttempts, DEFAULT_BUSY_RETRY_ATTEMPTS, 1),
        busyRetryDelayMs: normalizedInteger(options.busyRetryDelayMs, DEFAULT_BUSY_RETRY_DELAY_MS, 0),
        logger: (_b = options.logger) !== null && _b !== void 0 ? _b : console,
    };
}
function delay(milliseconds) {
    if (milliseconds <= 0)
        return Promise.resolve();
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}
function isSqliteBusyError(error) {
    var _a;
    if (!(error instanceof Error) || !("code" in error))
        return false;
    const code = String((_a = error.code) !== null && _a !== void 0 ? _a : "");
    return code === "SQLITE_BUSY" || code === "SQLITE_BUSY_SNAPSHOT" || code.startsWith("SQLITE_BUSY_");
}
function describeError(error) {
    return error instanceof Error ? error.message : String(error);
}
function prunePlayerWithRetry(database, playerId, maxRows, maxAttempts, retryDelayMs) {
    return __awaiter(this, void 0, void 0, function* () {
        const prune = database.prepare(`
        DELETE FROM players_receive_history
        WHERE player_id = ?
          AND id NOT IN (
              SELECT id
              FROM players_receive_history
              WHERE player_id = ?
              ORDER BY create_time DESC, id DESC
              LIMIT ?
          )
    `);
        let lastError;
        for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
            let began = false;
            try {
                database.exec("BEGIN IMMEDIATE");
                began = true;
                const deletedRows = prune.run(playerId, playerId, maxRows).changes;
                database.exec("COMMIT");
                return deletedRows;
            }
            catch (error) {
                if (began && database.inTransaction) {
                    try {
                        database.exec("ROLLBACK");
                    }
                    catch (_a) { }
                }
                if (!isSqliteBusyError(error) || attempt >= maxAttempts)
                    throw error;
                lastError = error;
                yield delay(retryDelayMs * (2 ** (attempt - 1)));
            }
        }
        throw lastError;
    });
}
function runReceiveHistoryRetentionPass(database_1) {
    return __awaiter(this, arguments, void 0, function* (database, options = {}, shouldStop = () => false) {
        const config = resolveOptions(options);
        const startedAt = Date.now();
        const result = {
            candidatePlayers: 0,
            processedPlayers: 0,
            prunedPlayers: 0,
            deletedRows: 0,
            failedPlayers: 0,
            stopped: false,
            elapsedMs: 0,
        };
        if (!config.enabled) {
            result.elapsedMs = Date.now() - startedAt;
            return result;
        }
        const selectCandidates = database.prepare(`
        SELECT player_id, COUNT(*) AS record_count
        FROM players_receive_history
        WHERE player_id > ?
        GROUP BY player_id
        HAVING COUNT(*) > ?
        ORDER BY player_id
        LIMIT ?
    `);
        let playerCursor = 0;
        while (!shouldStop()) {
            const candidates = selectCandidates.all(playerCursor, config.maxRows, config.batchPlayers);
            if (candidates.length === 0)
                break;
            for (const candidate of candidates) {
                playerCursor = candidate.player_id;
                if (shouldStop()) {
                    result.stopped = true;
                    break;
                }
                result.candidatePlayers += 1;
                try {
                    const deletedRows = yield prunePlayerWithRetry(database, candidate.player_id, config.maxRows, config.busyRetryAttempts, config.busyRetryDelayMs);
                    result.processedPlayers += 1;
                    result.deletedRows += deletedRows;
                    if (deletedRows > 0)
                        result.prunedPlayers += 1;
                }
                catch (error) {
                    result.failedPlayers += 1;
                    config.logger.warn(`[DB_MAINTENANCE] receive history retention failed for player ${candidate.player_id}: ${describeError(error)}`);
                }
                if (!shouldStop())
                    yield delay(config.pauseMs);
            }
            if (result.stopped)
                break;
        }
        if (shouldStop())
            result.stopped = true;
        result.elapsedMs = Date.now() - startedAt;
        return result;
    });
}
exports.runReceiveHistoryRetentionPass = runReceiveHistoryRetentionPass;
function createReceiveHistoryRetentionService(database, options = {}) {
    const config = resolveOptions(options);
    let stopped = true;
    let timer = null;
    let activePass = null;
    const schedule = (overrideDelayMs = null) => {
        if (stopped || !config.enabled || timer !== null)
            return;
        const now = new Date();
        const delayMs = overrideDelayMs !== null && overrideDelayMs !== void 0 ? overrideDelayMs : millisecondsUntilNextReceiveHistoryRetentionRun(now, config.dailyHour, config.dailyMinute);
        const nextRunAt = new Date(now.getTime() + delayMs);
        config.logger.log(`[DB_MAINTENANCE] receive history retention scheduled: nextRunAt=${nextRunAt.toString()}`);
        timer = setTimeout(() => {
            timer = null;
            if (stopped)
                return;
            activePass = (() => __awaiter(this, void 0, void 0, function* () {
                try {
                    const result = yield runReceiveHistoryRetentionPass(database, {
                        enabled: config.enabled,
                        maxRows: config.maxRows,
                        batchPlayers: config.batchPlayers,
                        pauseMs: config.pauseMs,
                        busyRetryAttempts: config.busyRetryAttempts,
                        busyRetryDelayMs: config.busyRetryDelayMs,
                        logger: config.logger,
                    }, () => stopped);
                    config.logger.log(`[DB_MAINTENANCE] receive history retention completed: candidates=${result.candidatePlayers} prunedPlayers=${result.prunedPlayers} deletedRows=${result.deletedRows} failures=${result.failedPlayers} stopped=${result.stopped} elapsedMs=${result.elapsedMs}`);
                }
                catch (error) {
                    config.logger.warn(`[DB_MAINTENANCE] receive history retention pass failed: ${describeError(error)}`);
                }
            }))();
            void activePass.then(() => {
                activePass = null;
                if (!stopped)
                    schedule();
            });
        }, delayMs);
        timer.unref();
    };
    return {
        start() {
            if (!stopped)
                return;
            stopped = false;
            if (!config.enabled) {
                config.logger.log("[DB_MAINTENANCE] receive history retention disabled by RECEIVE_HISTORY_RETENTION_ENABLED");
                return;
            }
            config.logger.log(`[DB_MAINTENANCE] receive history retention enabled: maxRows=${config.maxRows} dailyTime=${String(config.dailyHour).padStart(2, "0")}:${String(config.dailyMinute).padStart(2, "0")} localServerTime`);
            schedule(config.initialDelayMs);
        },
        stop() {
            return __awaiter(this, void 0, void 0, function* () {
                stopped = true;
                if (timer !== null) {
                    clearTimeout(timer);
                    timer = null;
                }
                if (activePass !== null)
                    yield activePass;
            });
        },
    };
}
exports.createReceiveHistoryRetentionService = createReceiveHistoryRetentionService;
