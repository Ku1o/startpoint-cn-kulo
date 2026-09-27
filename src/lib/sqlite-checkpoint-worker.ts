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
    lastDurationMs: number | null
    lastLogFrames: number | null
    lastCheckpointedFrames: number | null
    lastError: string | null
}

let worker: Worker | null = null
const state: CheckpointState = {
    enabled: false, started: false, completed: 0, errors: 0, busy: 0,
    lastDurationMs: null, lastLogFrames: null, lastCheckpointedFrames: null,
    lastError: null,
}

registerMemoryCounters("sqliteCheckpoint", () => ({
    enabled: state.enabled, started: state.started, completed: state.completed,
    errors: state.errors, busy: state.busy, lastDurationMs: state.lastDurationMs,
    lastLogFrames: state.lastLogFrames,
    lastCheckpointedFrames: state.lastCheckpointedFrames,
    lastError: state.lastError !== null,
    lastErrorLength: state.lastError?.length ?? 0,
}), "sqlite")

function enabled(environment: NodeJS.ProcessEnv = process.env): boolean {
    return /^(1|true|yes|on)$/i.test(environment.SQLITE_CHECKPOINT_WORKER ?? "")
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
    const current = new Worker(location.filename, {
        ...(location.execArgv ? { execArgv: location.execArgv } : {}),
        workerData: { databasePath, intervalMs },
    })
    worker = current
    observeWorkerMemory("sqlite-checkpoint", current)
    current.on("online", () => { state.started = true })
    current.on("message", message => {
        if (worker !== current) return
        if (message?.type === "checkpoint") {
            state.completed++
            state.busy += message.busy === 1 ? 1 : 0
            state.lastDurationMs = Number(message.durationMs) || 0
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
    console.log(`[DB] sqlite checkpoint worker enabled intervalMs=${intervalMs}`)
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
