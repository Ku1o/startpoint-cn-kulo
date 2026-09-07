import { existsSync } from "fs"
import path from "path"
import { Worker } from "worker_threads"
import { getDatabaseDirectory } from "./admin-database-backup"

export const DEFAULT_PLAYER_SAVE_EXPORT_MAX_BYTES = 64 * 1024 * 1024
const DEFAULT_PLAYER_SAVE_EXPORT_TIMEOUT_MS = 120_000

export type PlayerSaveExportErrorCode = "busy" | "aborted" | "timeout" | "too-large" | "export-failed"

export class PlayerSaveExportError extends Error {
    constructor(
        public readonly code: PlayerSaveExportErrorCode,
        message: string,
    ) {
        super(message)
        this.name = "PlayerSaveExportError"
    }
}

export interface PlayerSaveExportOptions {
    signal?: AbortSignal
    maxBytes?: number
    timeoutMs?: number
}

export interface PlayerSaveExportResult {
    payload: Buffer
    rowCount: number
}

interface WorkerMessage {
    type?: string
    code?: PlayerSaveExportErrorCode
    error?: string
    payload?: ArrayBuffer
    byteLength?: number
    rowCount?: number
}

let activeExportWorker: Worker | null = null

function getWorkerLocation(): { filename: string; execArgv?: string[] } {
    const compiledWorker = path.resolve(__dirname, "../workers/player-save-export-worker.js")
    if (existsSync(compiledWorker)) return { filename: compiledWorker }
    return {
        filename: path.resolve(__dirname, "../workers/player-save-export-worker.ts"),
        execArgv: ["-r", require.resolve("ts-node/register/transpile-only")],
    }
}

function normalizeLimit(value: number | undefined, fallback: number, minimum: number, maximum: number): number {
    if (value === undefined || !Number.isFinite(value)) return fallback
    return Math.max(minimum, Math.min(maximum, Math.trunc(value)))
}

export async function exportPlayerSaveInWorker(
    playerId: number,
    options: PlayerSaveExportOptions = {},
): Promise<PlayerSaveExportResult> {
    if (!Number.isSafeInteger(playerId) || playerId < 1) {
        throw new PlayerSaveExportError("export-failed", "玩家 ID 无效")
    }
    if (options.signal?.aborted) {
        throw new PlayerSaveExportError("aborted", "客户端已取消存档导出")
    }
    if (activeExportWorker !== null) {
        throw new PlayerSaveExportError("busy", "已有一个存档正在导出，请稍后再试")
    }

    const maxBytes = normalizeLimit(
        options.maxBytes,
        DEFAULT_PLAYER_SAVE_EXPORT_MAX_BYTES,
        1,
        DEFAULT_PLAYER_SAVE_EXPORT_MAX_BYTES,
    )
    const configuredTimeout = Number.parseInt(process.env.PLAYER_SAVE_EXPORT_TIMEOUT_MS ?? "", 10)
    const timeoutMs = normalizeLimit(
        options.timeoutMs,
        Number.isFinite(configuredTimeout) ? configuredTimeout : DEFAULT_PLAYER_SAVE_EXPORT_TIMEOUT_MS,
        1_000,
        10 * 60_000,
    )
    const workerLocation = getWorkerLocation()
    const worker = new Worker(workerLocation.filename, {
        execArgv: workerLocation.execArgv,
        workerData: {
            databasePath: path.join(getDatabaseDirectory(), "wdfp_data.db"),
            playerId,
            maxBytes,
        },
    })
    worker.unref()
    activeExportWorker = worker

    return new Promise<PlayerSaveExportResult>((resolve, reject) => {
        let settled = false
        const finish = (callback: () => void): void => {
            if (settled) return
            settled = true
            clearTimeout(timeout)
            options.signal?.removeEventListener("abort", onAbort)
            if (activeExportWorker === worker) activeExportWorker = null
            callback()
        }
        const fail = (code: PlayerSaveExportErrorCode, message: string): void => {
            finish(() => reject(new PlayerSaveExportError(code, message)))
        }
        const onAbort = (): void => {
            void worker.terminate()
            fail("aborted", "客户端已取消存档导出")
        }
        const timeout = setTimeout(() => {
            void worker.terminate()
            fail("timeout", `存档导出超过 ${timeoutMs / 1000} 秒，已终止`)
        }, timeoutMs)
        timeout.unref()
        options.signal?.addEventListener("abort", onAbort, { once: true })

        worker.once("message", (message: WorkerMessage) => {
            if (message.type === "completed" && message.payload instanceof ArrayBuffer) {
                const payload = Buffer.from(message.payload, 0, message.byteLength ?? message.payload.byteLength)
                finish(() => resolve({
                    payload,
                    rowCount: Number(message.rowCount) || 0,
                }))
                return
            }
            fail(message.code ?? "export-failed", message.error ?? "存档导出 worker 返回了无效结果")
        })
        worker.once("error", error => fail("export-failed", error.message))
        worker.once("exit", code => {
            if (!settled) fail("export-failed", `存档导出 worker 未返回结果（code=${code}）`)
        })
    })
}
