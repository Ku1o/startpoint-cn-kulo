/**
 * Configuration for the optional single-writer SQLite thread.
 *
 * The writer thread owns every business write while the main thread keeps
 * protocol, realtime and read work. It is opt-in so a deployment can always
 * fall back to the in-process persistence coordinator by unsetting one switch.
 */

// 2: the client pushes the main thread's virtual-clock offset to the worker
//    (`set_time_offset`) before dispatching commands.
export const WRITER_PROTOCOL_VERSION = 2

export interface WriterThreadConfig {
    /** Route registered commands through the writer thread instead of the main process. */
    enabled: boolean
    /** Run a command in-process when the queue is saturated instead of failing it. */
    fallback: boolean
    /** Maximum number of commands waiting for the worker on the main thread. */
    queueMax: number
    /** Maximum number of commands handed to the worker at the same time. */
    maxInFlight: number
    /** Reject and restart the worker when a command exceeds this. 0 disables the deadline. */
    commandTimeoutMs: number
    /** Group-commit window: how long to collect commands before one COMMIT. 0 disables batching. */
    groupCommitWindowMs: number
    /** Upper bound on commands folded into a single transaction. */
    groupCommitMax: number
    /** SQLite busy timeout for the writer connection. */
    busyTimeoutMs: number
    /** Automatic worker restarts after an unexpected exit before commands start failing permanently. */
    maxRestarts: number
}

function integer(value: string | undefined, fallback: number, min: number, max: number): number {
    if (!value?.trim()) return fallback
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) && parsed >= min && parsed <= max ? parsed : fallback
}

function switchValue(value: string | undefined, fallback: boolean): boolean {
    if (/^(1|true|yes|on)$/i.test(value ?? "")) return true
    if (/^(0|false|no|off)$/i.test(value ?? "")) return false
    return fallback
}

export function writerThreadConfig(environment: NodeJS.ProcessEnv = process.env): WriterThreadConfig {
    return {
        enabled: switchValue(environment.CN_WRITER_THREAD, false),
        fallback: switchValue(environment.SQLITE_WRITER_FALLBACK, false),
        queueMax: integer(environment.SQLITE_WRITER_QUEUE_MAX, 512, 1, 100_000),
        maxInFlight: integer(environment.SQLITE_WRITER_MAX_IN_FLIGHT, 32, 1, 512),
        commandTimeoutMs: integer(environment.SQLITE_WRITER_COMMAND_TIMEOUT_MS, 30_000, 0, 600_000),
        groupCommitWindowMs: integer(environment.SQLITE_GROUP_COMMIT_WINDOW_MS, 2, 0, 50),
        groupCommitMax: integer(environment.SQLITE_GROUP_COMMIT_MAX, 64, 1, 512),
        busyTimeoutMs: integer(environment.SQLITE_WRITER_BUSY_TIMEOUT_MS, 1_000, 0, 60_000),
        maxRestarts: integer(environment.SQLITE_WRITER_MAX_RESTARTS, 5, 0, 100),
    }
}
