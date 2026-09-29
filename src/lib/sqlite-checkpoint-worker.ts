import path from "node:path"
import { existsSync } from "../lib/file-exists"
import { Worker } from "node:worker_threads"
import { observeWorkerMemory, registerMemoryCounters } from "./memory-diagnostics"

interface CheckpointState {
    enabled: boolean
    started: boolean
    completed: number
    errors: number
    busy: number
    truncateAttempts: number
    truncateCompleted: number
    truncateBusy: number
    lastDurationMs: number | null
    lastWasTruncate: boolean
    lastWalBytes: number | null
    lastPassiveLogFrames: number | null
    lastPassiveCheckpointedFrames: number | null
    lastLogFrames: number | null
    lastCheckpointedFrames: number | null
    lastError: string | null
}

let worker: Worker | null = null
const state: CheckpointState = {
    enabled: false, started: false, completed: 0, errors: 0, busy: 0,
    truncateAttempts: 0, truncateCompleted: 0, truncateBusy: 0,
    lastDurationMs: null, lastLogFrames: null, lastCheckpointedFrames: null,
    lastWasTruncate: false, lastWalBytes: null, lastPassiveLogFrames: null,
    lastPassiveCheckpointedFrames: null, lastError: null,
}

registerMemoryCounters("sqliteCheckpoint", () => ({
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
    lastErrorLength: state.lastError?.length ?? 0,
}), "sqlite")

function enabled(environment: NodeJS.ProcessEnv = process.env): boolean {
    return /^(1|true|yes|on)$/i.test(environment.SQLITE_CHECKPOINT_WORKER ?? "")
}

function positiveInteger(value: string | undefined, fallback: number, minimum: number): number {
    const parsed = Number.parseInt(value ?? "", 10)
    return Number.isFinite(parsed) ? Math.max(minimum, parsed) : fallback
}

function workerLocation(): { filename: string, execArgv?: string[] } {
    const compiled = path.resolve(__dirname, "../workers/sqlite-checkpoint-worker.js")
    if (existsSync(compiled)) return { filename: compiled }
    return {
        filename: path.resolve(__dirname, "../workers/sqlite-checkpoint-worker.ts"),
        execArgv: ["-r", require.resolve("ts-node/register/transpile-only")],
    }
}

export function startSqliteCheckpointWorker(databasePath: string, environment: NodeJS.ProcessEnv = process.env): void {
    if (worker || !enabled(environment)) return
    state.enabled = true
    state.started = false
    const location = workerLocation()
    const intervalMs = Math.max(1_000, Number.parseInt(environment.SQLITE_CHECKPOINT_INTERVAL_MS ?? "5000", 10) || 5_000)
    const truncateFrames = positiveInteger(environment.SQLITE_CHECKPOINT_TRUNCATE_FRAMES, 131_072, 1_000)
    const truncateBytes = positiveInteger(environment.SQLITE_CHECKPOINT_TRUNCATE_BYTES, 536_870_912, 4 * 1024 * 1024)
    const truncateCooldownMs = positiveInteger(environment.SQLITE_CHECKPOINT_TRUNCATE_COOLDOWN_MS, 60_000, 5_000)
    const busyTimeoutMs = Math.max(0, Number.parseInt(environment.SQLITE_CHECKPOINT_BUSY_TIMEOUT_MS ?? "0", 10) || 0)
    const current = new Worker(location.filename, {
        ...(location.execArgv ? { execArgv: location.execArgv } : {}),
        workerData: { databasePath, intervalMs, truncateFrames, truncateBytes, truncateCooldownMs, busyTimeoutMs },
    })
    worker = current
    observeWorkerMemory("sqlite-checkpoint", current)
    current.on("online", () => { state.started = true })
    current.on("message", message => {
        if (worker !== current) return
        if (message?.type === "checkpoint") {
            state.completed++
            state.busy += message.busy === 1 ? 1 : 0
            state.truncateAttempts += message.truncateAttempted === true ? 1 : 0
            state.truncateCompleted += message.truncateAttempted === true && message.truncateBusy === 0 ? 1 : 0
            state.truncateBusy += Number(message.truncateBusy) === 1 ? 1 : 0
            state.lastDurationMs = Number(message.durationMs) || 0
            state.lastWasTruncate = message.mode === "truncate"
            state.lastWalBytes = Number.isFinite(Number(message.walBytes)) ? Number(message.walBytes) : null
            state.lastPassiveLogFrames = Number.isFinite(Number(message.passiveLogFrames))
                ? Number(message.passiveLogFrames) : null
            state.lastPassiveCheckpointedFrames = Number.isFinite(Number(message.passiveCheckpointedFrames))
                ? Number(message.passiveCheckpointedFrames) : null
            state.lastLogFrames = Number(message.logFrames) || 0
            state.lastCheckpointedFrames = Number(message.checkpointedFrames) || 0
            state.lastError = null
        } else if (message?.type === "checkpoint_error") {
            state.errors++
            state.lastDurationMs = Number(message.durationMs) || 0
            state.lastError = String(message.error ?? "checkpoint failed").slice(0, 240)
        }
    })
    current.on("error", error => {
        if (worker !== current) return
        state.errors++
        state.lastError = error.message.slice(0, 240)
    })
    current.once("exit", () => {
        if (worker === current) worker = null
        state.started = false
    })
    console.log(`[DB] sqlite checkpoint worker enabled intervalMs=${intervalMs}`
        + ` truncateFrames=${truncateFrames} truncateBytes=${truncateBytes}`
        + ` truncateCooldownMs=${truncateCooldownMs} busyTimeoutMs=${busyTimeoutMs}`)
}

export async function stopSqliteCheckpointWorker(): Promise<void> {
    const current = worker
    if (!current) return
    worker = null
    try { current.postMessage({ type: "close" }) } catch {}
    await current.terminate()
    state.started = false
}

export function requestSqliteCheckpoint(): void {
    try { worker?.postMessage({ type: "checkpoint_now" }) } catch {}
}
