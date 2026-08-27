import type { Database } from "better-sqlite3"

const DEFAULT_MAX_ROWS = 500
const DEFAULT_DAILY_HOUR = 4
const DEFAULT_DAILY_MINUTE = 30
const DEFAULT_BATCH_PLAYERS = 5
const DEFAULT_PAUSE_MS = 100
const DEFAULT_BUSY_RETRY_ATTEMPTS = 5
const DEFAULT_BUSY_RETRY_DELAY_MS = 20

interface ReceiveHistoryCandidateRow {
    player_id: number
    record_count: number
}

export interface ReceiveHistoryRetentionLogger {
    log(message: string): void
    warn(message: string): void
}

export interface ReceiveHistoryRetentionOptions {
    enabled?: boolean
    maxRows?: number
    initialDelayMs?: number
    dailyHour?: number
    dailyMinute?: number
    batchPlayers?: number
    pauseMs?: number
    busyRetryAttempts?: number
    busyRetryDelayMs?: number
    logger?: ReceiveHistoryRetentionLogger
}

interface ResolvedReceiveHistoryRetentionOptions {
    enabled: boolean
    maxRows: number
    initialDelayMs: number | null
    dailyHour: number
    dailyMinute: number
    batchPlayers: number
    pauseMs: number
    busyRetryAttempts: number
    busyRetryDelayMs: number
    logger: ReceiveHistoryRetentionLogger
}

export interface ReceiveHistoryRetentionPassResult {
    candidatePlayers: number
    processedPlayers: number
    prunedPlayers: number
    deletedRows: number
    failedPlayers: number
    stopped: boolean
    elapsedMs: number
}

export interface ReceiveHistoryRetentionService {
    start(): void
    stop(): Promise<void>
}

export interface ReceiveHistoryRetentionSchedule {
    hour: number
    minute: number
}

function normalizedInteger(value: number | undefined, fallback: number, minimum: number): number {
    if (!Number.isSafeInteger(value) || value === undefined || value < minimum) return fallback
    return value
}

function normalizedBoundedInteger(
    value: number | undefined,
    fallback: number,
    minimum: number,
    maximum: number,
): number {
    if (!Number.isSafeInteger(value) || value === undefined || value < minimum || value > maximum) {
        return fallback
    }
    return value
}

export function isReceiveHistoryRetentionEnabled(
    env: NodeJS.ProcessEnv = process.env,
): boolean {
    const value = env.RECEIVE_HISTORY_RETENTION_ENABLED?.trim().toLowerCase()
    return value !== "0" && value !== "false" && value !== "off" && value !== "no"
}

export function getReceiveHistoryRetentionSchedule(
    env: NodeJS.ProcessEnv = process.env,
): ReceiveHistoryRetentionSchedule {
    const value = env.RECEIVE_HISTORY_RETENTION_TIME?.trim() ?? ""
    const match = /^(\d{1,2}):(\d{2})$/.exec(value)
    if (!match) return { hour: DEFAULT_DAILY_HOUR, minute: DEFAULT_DAILY_MINUTE }
    const hour = Number(match[1])
    const minute = Number(match[2])
    if (!Number.isInteger(hour) || hour < 0 || hour > 23 || !Number.isInteger(minute) || minute < 0 || minute > 59) {
        return { hour: DEFAULT_DAILY_HOUR, minute: DEFAULT_DAILY_MINUTE }
    }
    return { hour, minute }
}

export function millisecondsUntilNextReceiveHistoryRetentionRun(
    now: Date,
    hour: number,
    minute: number,
): number {
    const nextRun = new Date(now.getTime())
    nextRun.setHours(hour, minute, 0, 0)
    if (nextRun.getTime() <= now.getTime()) nextRun.setDate(nextRun.getDate() + 1)
    return Math.max(1, nextRun.getTime() - now.getTime())
}

function resolveOptions(options: ReceiveHistoryRetentionOptions): ResolvedReceiveHistoryRetentionOptions {
    const schedule = getReceiveHistoryRetentionSchedule()
    return {
        enabled: options.enabled ?? isReceiveHistoryRetentionEnabled(),
        maxRows: normalizedInteger(options.maxRows, DEFAULT_MAX_ROWS, 1),
        initialDelayMs: options.initialDelayMs === undefined
            ? null
            : normalizedInteger(options.initialDelayMs, 0, 0),
        dailyHour: normalizedBoundedInteger(options.dailyHour, schedule.hour, 0, 23),
        dailyMinute: normalizedBoundedInteger(options.dailyMinute, schedule.minute, 0, 59),
        batchPlayers: normalizedInteger(options.batchPlayers, DEFAULT_BATCH_PLAYERS, 1),
        pauseMs: normalizedInteger(options.pauseMs, DEFAULT_PAUSE_MS, 0),
        busyRetryAttempts: normalizedInteger(
            options.busyRetryAttempts,
            DEFAULT_BUSY_RETRY_ATTEMPTS,
            1,
        ),
        busyRetryDelayMs: normalizedInteger(
            options.busyRetryDelayMs,
            DEFAULT_BUSY_RETRY_DELAY_MS,
            0,
        ),
        logger: options.logger ?? console,
    }
}

function delay(milliseconds: number): Promise<void> {
    if (milliseconds <= 0) return Promise.resolve()
    return new Promise(resolve => setTimeout(resolve, milliseconds))
}

function isSqliteBusyError(error: unknown): boolean {
    if (!(error instanceof Error) || !("code" in error)) return false
    const code = String((error as Error & { code?: string }).code ?? "")
    return code === "SQLITE_BUSY" || code === "SQLITE_BUSY_SNAPSHOT" || code.startsWith("SQLITE_BUSY_")
}

function describeError(error: unknown): string {
    return error instanceof Error ? error.message : String(error)
}

async function prunePlayerWithRetry(
    database: Database,
    playerId: number,
    maxRows: number,
    maxAttempts: number,
    retryDelayMs: number,
): Promise<number> {
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
    `)

    let lastError: unknown
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        let began = false
        try {
            database.exec("BEGIN IMMEDIATE")
            began = true
            const deletedRows = prune.run(playerId, playerId, maxRows).changes
            database.exec("COMMIT")
            return deletedRows
        } catch (error) {
            if (began && database.inTransaction) {
                try { database.exec("ROLLBACK") } catch {}
            }
            if (!isSqliteBusyError(error) || attempt >= maxAttempts) throw error
            lastError = error
            await delay(retryDelayMs * (2 ** (attempt - 1)))
        }
    }
    throw lastError
}

export async function runReceiveHistoryRetentionPass(
    database: Database,
    options: ReceiveHistoryRetentionOptions = {},
    shouldStop: () => boolean = () => false,
): Promise<ReceiveHistoryRetentionPassResult> {
    const config = resolveOptions(options)
    const startedAt = Date.now()
    const result: ReceiveHistoryRetentionPassResult = {
        candidatePlayers: 0,
        processedPlayers: 0,
        prunedPlayers: 0,
        deletedRows: 0,
        failedPlayers: 0,
        stopped: false,
        elapsedMs: 0,
    }
    if (!config.enabled) {
        result.elapsedMs = Date.now() - startedAt
        return result
    }

    const selectCandidates = database.prepare(`
        SELECT player_id, COUNT(*) AS record_count
        FROM players_receive_history
        WHERE player_id > ?
        GROUP BY player_id
        HAVING COUNT(*) > ?
        ORDER BY player_id
        LIMIT ?
    `)

    let playerCursor = 0
    while (!shouldStop()) {
        const candidates = selectCandidates.all(
            playerCursor,
            config.maxRows,
            config.batchPlayers,
        ) as ReceiveHistoryCandidateRow[]
        if (candidates.length === 0) break

        for (const candidate of candidates) {
            playerCursor = candidate.player_id
            if (shouldStop()) {
                result.stopped = true
                break
            }
            result.candidatePlayers += 1
            try {
                const deletedRows = await prunePlayerWithRetry(
                    database,
                    candidate.player_id,
                    config.maxRows,
                    config.busyRetryAttempts,
                    config.busyRetryDelayMs,
                )
                result.processedPlayers += 1
                result.deletedRows += deletedRows
                if (deletedRows > 0) result.prunedPlayers += 1
            } catch (error) {
                result.failedPlayers += 1
                config.logger.warn(
                    `[DB_MAINTENANCE] receive history retention failed for player ${candidate.player_id}: ${describeError(error)}`,
                )
            }
            if (!shouldStop()) await delay(config.pauseMs)
        }
        if (result.stopped) break
    }
    if (shouldStop()) result.stopped = true
    result.elapsedMs = Date.now() - startedAt
    return result
}

export function createReceiveHistoryRetentionService(
    database: Database,
    options: ReceiveHistoryRetentionOptions = {},
): ReceiveHistoryRetentionService {
    const config = resolveOptions(options)
    let stopped = true
    let timer: NodeJS.Timeout | null = null
    let activePass: Promise<void> | null = null

    const schedule = (overrideDelayMs: number | null = null): void => {
        if (stopped || !config.enabled || timer !== null) return
        const now = new Date()
        const delayMs = overrideDelayMs ?? millisecondsUntilNextReceiveHistoryRetentionRun(
            now,
            config.dailyHour,
            config.dailyMinute,
        )
        const nextRunAt = new Date(now.getTime() + delayMs)
        config.logger.log(
            `[DB_MAINTENANCE] receive history retention scheduled: nextRunAt=${nextRunAt.toString()}`,
        )
        timer = setTimeout(() => {
            timer = null
            if (stopped) return
            activePass = (async () => {
                try {
                    const result = await runReceiveHistoryRetentionPass(
                        database,
                        {
                            enabled: config.enabled,
                            maxRows: config.maxRows,
                            batchPlayers: config.batchPlayers,
                            pauseMs: config.pauseMs,
                            busyRetryAttempts: config.busyRetryAttempts,
                            busyRetryDelayMs: config.busyRetryDelayMs,
                            logger: config.logger,
                        },
                        () => stopped,
                    )
                    config.logger.log(
                        `[DB_MAINTENANCE] receive history retention completed: candidates=${result.candidatePlayers} prunedPlayers=${result.prunedPlayers} deletedRows=${result.deletedRows} failures=${result.failedPlayers} stopped=${result.stopped} elapsedMs=${result.elapsedMs}`,
                    )
                } catch (error) {
                    config.logger.warn(
                        `[DB_MAINTENANCE] receive history retention pass failed: ${describeError(error)}`,
                    )
                }
            })()
            void activePass.then(() => {
                activePass = null
                if (!stopped) schedule()
            })
        }, delayMs)
        timer.unref()
    }

    return {
        start(): void {
            if (!stopped) return
            stopped = false
            if (!config.enabled) {
                config.logger.log(
                    "[DB_MAINTENANCE] receive history retention disabled by RECEIVE_HISTORY_RETENTION_ENABLED",
                )
                return
            }
            config.logger.log(
                `[DB_MAINTENANCE] receive history retention enabled: maxRows=${config.maxRows} dailyTime=${String(config.dailyHour).padStart(2, "0")}:${String(config.dailyMinute).padStart(2, "0")} localServerTime`,
            )
            schedule(config.initialDelayMs)
        },
        async stop(): Promise<void> {
            stopped = true
            if (timer !== null) {
                clearTimeout(timer)
                timer = null
            }
            if (activePass !== null) await activePass
        },
    }
}
