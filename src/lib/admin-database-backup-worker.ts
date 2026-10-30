import path from "path"
import { statSync } from "fs"
import { Worker } from "worker_threads"
import { existsSync } from "./file-exists"
import { assertServerAcceptingWork, ServerClosingError } from "./shutdown-state"

export type AdminDatabaseBackupErrorCode = "cancelled" | "timeout" | "stalled" | "wal-growth"
    | "busy" | "not-wal" | "destination-exists" | "failed"

export class AdminDatabaseBackupError extends Error {
    backupDirectory?: string
    backupName?: string
    constructor(public readonly code: AdminDatabaseBackupErrorCode, message: string) {
        super(message)
        this.name = "AdminDatabaseBackupError"
    }
}

export interface AdminDatabaseBackupProgress {
    phase: "opening" | "copying" | "verifying"
    totalPages: number
    remainingPages: number
    copiedPages: number
    elapsedMs: number
    walBytes: number
    walGrowthBytes: number
}

export interface AdminDatabaseBackupOptions {
    signal?: AbortSignal
    onProgress?: (progress: AdminDatabaseBackupProgress) => void
    timeoutMs?: number
    stallTimeoutMs?: number
    maxWalGrowthBytes?: number
    /** Captured by the full-backup wrapper before the worker pins its snapshot. */
    activeAccountState?: string
    versionSidecar?: { filename: string; contents: string }
}

export interface AdminDatabaseBackupWorkerResult {
    totalPages: number
    elapsedMs: number
    quickCheck: "ok"
    snapshot: true
    snapshotPinnedAt?: string
    sidecarValidated?: boolean
}

export interface AdminDatabaseBackupWorkerData {
    databasePath: string
    destinationPath: string
    startedAt: number
    timeoutMs: number
    stallTimeoutMs: number
    maxWalGrowthBytes: number
    cancelBuffer: SharedArrayBuffer
    activeAccountState?: string
    versionSidecar?: { filename: string; contents: string }
}

interface WorkerMessage {
    type?: string
    progress?: AdminDatabaseBackupProgress
    result?: AdminDatabaseBackupWorkerResult
    code?: AdminDatabaseBackupErrorCode
    error?: string
}

interface ActiveBackup {
    worker: Worker
    exit: Promise<void>
    cancel: (code: AdminDatabaseBackupErrorCode, reason: string) => void
}

let activeBackup: ActiveBackup | null = null
let stopping = false

/** Cancellation never releases the slot before the native connection has exited. */
export function cancelActiveDatabaseBackups(reason = "完整数据库备份已取消"): void {
    activeBackup?.cancel("cancelled", reason)
}

export async function drainDatabaseBackups(): Promise<void> {
    while (activeBackup) await activeBackup.exit
}

/** Sticky shutdown admission; ordinary cancellation leaves future backups available. */
export async function stopDatabaseBackups(reason = "服务器正在关闭，完整数据库备份已取消"): Promise<void> {
    stopping = true
    cancelActiveDatabaseBackups(reason)
    await drainDatabaseBackups()
}

function workerLocation(): { filename: string; execArgv?: string[] } {
    const compiled = path.resolve(__dirname, "../workers/admin-database-backup-worker.js")
    if (existsSync(compiled)) return { filename: compiled }
    return {
        filename: path.resolve(__dirname, "../workers/admin-database-backup-worker.ts"),
        execArgv: ["-r", require.resolve("ts-node/register/transpile-only")],
    }
}

function limit(value: number | undefined, fallback: number, minimum: number): number {
    if (value === undefined) return fallback
    if (!Number.isSafeInteger(value) || value < minimum) {
        throw new AdminDatabaseBackupError("failed", "完整数据库备份的安全上限无效")
    }
    return value
}

function walSize(filename: string): number {
    const stat = statSync(`${filename}-wal`, { throwIfNoEntry: false })
    return stat?.size ?? 0
}

/** No migration, source writes or journal-mode changes occur in this controller. */
export async function backupDatabaseInWorker(
    databasePath: string,
    destination: string,
    options: AdminDatabaseBackupOptions = {},
): Promise<AdminDatabaseBackupWorkerResult> {
    if (stopping) throw new ServerClosingError()
    assertServerAcceptingWork()
    if (options.signal?.aborted) throw new AdminDatabaseBackupError("cancelled", "完整数据库备份已取消")
    if (activeBackup) throw new AdminDatabaseBackupError("busy", "已有完整数据库备份正在运行，请稍后再试")
    const source = path.resolve(databasePath)
    const target = path.resolve(destination)
    if (source === target) throw new AdminDatabaseBackupError("failed", "备份目标不能覆盖源数据库")
    if (existsSync(target)) throw new AdminDatabaseBackupError("destination-exists", "备份目标已存在，未覆盖文件")
    const timeoutMs = limit(options.timeoutMs, 5 * 60_000, 1)
    const stallTimeoutMs = limit(options.stallTimeoutMs, 30_000, 1)
    const maxWalGrowthBytes = limit(options.maxWalGrowthBytes, 512 * 1024 * 1024, 0)
    const startedAt = Date.now()
    const initialWalBytes = walSize(source)
    const cancelBuffer = new SharedArrayBuffer(4)
    const cancelFlag = new Int32Array(cancelBuffer)
    const location = workerLocation()
    const worker = new Worker(location.filename, {
        execArgv: location.execArgv,
        workerData: {
            databasePath: source, destinationPath: target, startedAt, timeoutMs, stallTimeoutMs,
            maxWalGrowthBytes, cancelBuffer,
            activeAccountState: options.activeAccountState, versionSidecar: options.versionSidecar,
        } satisfies AdminDatabaseBackupWorkerData,
    })
    let resolveExit!: () => void
    const exit = new Promise<void>(resolve => { resolveExit = resolve })
    let result: AdminDatabaseBackupWorkerResult | undefined
    let failure: AdminDatabaseBackupError | undefined
    let forceTimer: NodeJS.Timeout | undefined
    let lastAdvanceAt = startedAt
    let maximumCopiedPages = 0
    let lastPhase = "opening"
    const awaitExit = (): void => {
        if (forceTimer) return
        forceTimer = setTimeout(() => {
            // A terminal message is not proof of native-handle release.
            // Termination also cannot release the slot ahead of actual exit.
            void worker.terminate().catch(() => {})
        }, 1000)
        forceTimer.unref()
    }
    const cancel = (code: AdminDatabaseBackupErrorCode, reason: string): void => {
        // A completed, verified backup is kept when an abort races its exit.
        if (result || failure) return
        failure = new AdminDatabaseBackupError(code, reason)
        Atomics.store(cancelFlag, 0, 1)
        try { worker.postMessage({ type: "cancel", code, error: reason }) } catch { /* exit still owns settlement */ }
        awaitExit()
    }
    activeBackup = { worker, exit, cancel }
    return new Promise<AdminDatabaseBackupWorkerResult>((resolve, reject) => {
        const onAbort = (): void => cancel("cancelled", "完整数据库备份已取消")
        const timeout = setTimeout(() => cancel("timeout", `完整数据库备份超过 ${timeoutMs / 1000} 秒，已取消`), timeoutMs)
        timeout.unref()
        const monitor = setInterval(() => {
            if (result || failure) return
            try {
                // Verification has released the source snapshot and uses a
                // synchronous destination scan. Only its total deadline and
                // cancellation apply; there are no page-progress heartbeats.
                if (lastPhase === "verifying") return
                if (walSize(source) - initialWalBytes > maxWalGrowthBytes) {
                    cancel("wal-growth", "备份期间 WAL 增长超过安全上限，已取消以释放读快照")
                } else if (Date.now() - lastAdvanceAt >= stallTimeoutMs) {
                    cancel("stalled", "完整数据库备份长时间没有有效进展，已取消")
                }
            } catch (error) {
                cancel("failed", `无法检查备份安全边界：${error instanceof Error ? error.message : String(error)}`)
            }
        }, Math.min(100, stallTimeoutMs))
        monitor.unref()
        options.signal?.addEventListener("abort", onAbort, { once: true })
        if (options.signal?.aborted) onAbort()

        worker.on("message", (message: WorkerMessage) => {
            if (message.type === "progress" && message.progress) {
                const progress = message.progress
                if (Number.isFinite(progress.copiedPages) && progress.copiedPages > maximumCopiedPages) {
                    maximumCopiedPages = progress.copiedPages
                    lastAdvanceAt = Date.now()
                }
                if (progress.phase !== lastPhase) {
                    lastPhase = progress.phase
                    lastAdvanceAt = Date.now()
                }
                try { options.onProgress?.(progress) }
                catch (error) {
                    cancel("failed", `备份进度处理失败：${error instanceof Error ? error.message : String(error)}`)
                }
            } else if (message.type === "completed" && message.result?.quickCheck === "ok"
                && message.result.snapshot === true && Number.isSafeInteger(message.result.totalPages)) {
                result = message.result
                awaitExit()
            } else if (message.type === "failed") {
                if (!failure) failure = new AdminDatabaseBackupError(message.code ?? "failed", message.error ?? "完整数据库备份失败")
                awaitExit()
            } else {
                cancel("failed", "完整数据库备份 Worker 返回了无效结果")
            }
        })
        worker.once("error", error => cancel("failed", `完整数据库备份 Worker 失败：${error.message}`))
        worker.once("exit", code => {
            clearTimeout(timeout)
            clearInterval(monitor)
            if (forceTimer) clearTimeout(forceTimer)
            options.signal?.removeEventListener("abort", onAbort)
            if (!failure && (!result || code !== 0)) {
                failure = new AdminDatabaseBackupError("failed", `完整数据库备份 Worker 未成功结束（code=${code}）`)
            }
            if (activeBackup?.worker === worker) activeBackup = null
            // Resolve the operation first so wrapper metadata is finalized
            // before observers waiting to drain this worker continue.
            if (failure) reject(failure)
            else resolve(result!)
            resolveExit()
        })
    })
}
