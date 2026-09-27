import Database from "better-sqlite3"
import { parentPort, workerData } from "node:worker_threads"
import { performance } from "node:perf_hooks"

interface WorkerInput {
    databasePath: string
    intervalMs: number
}

const input = workerData as WorkerInput
const database = new Database(input.databasePath)
database.pragma("journal_mode = WAL")
database.pragma("synchronous = NORMAL")
database.pragma("busy_timeout = 250")
database.pragma("wal_autocheckpoint = 0")

let closed = false

function checkpoint(): void {
    if (closed) return
    const startedAt = performance.now()
    try {
        const result = database.pragma("wal_checkpoint(PASSIVE)") as Array<Record<string, unknown>>
        const state = result[0] ?? {}
        parentPort?.postMessage({
            type: "checkpoint",
            durationMs: performance.now() - startedAt,
            busy: Number(state.busy) || 0,
            logFrames: Number(state.log) || 0,
            checkpointedFrames: Number(state.checkpointed) || 0,
        })
    } catch (error) {
        parentPort?.postMessage({
            type: "checkpoint_error",
            durationMs: performance.now() - startedAt,
            error: error instanceof Error ? error.message : String(error),
        })
    }
}

const interval = setInterval(checkpoint, Math.max(250, input.intervalMs))
interval.unref()
checkpoint()

parentPort?.on("message", message => {
    if (message?.type === "checkpoint_now") checkpoint()
    if (message?.type !== "close" || closed) return
    closed = true
    clearInterval(interval)
    try { database.close() } catch {}
    parentPort?.postMessage({ type: "closed" })
})
