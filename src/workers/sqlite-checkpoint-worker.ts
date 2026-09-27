import Database from "better-sqlite3"
import fs from "node:fs"
import { parentPort, workerData } from "node:worker_threads"
import { performance } from "node:perf_hooks"

interface WorkerInput {
    databasePath: string
    intervalMs: number
    truncateFrames: number
    truncateBytes: number
    truncateCooldownMs: number
}

const input = workerData as WorkerInput
const database = new Database(input.databasePath)
database.pragma("journal_mode = WAL")
database.pragma("synchronous = NORMAL")
database.pragma("busy_timeout = 250")
database.pragma("wal_autocheckpoint = 0")

let closed = false
// Allow the first oversized WAL to be reclaimed immediately after startup.
let lastTruncateAt = Number.NEGATIVE_INFINITY

function walBytes(): number | null {
    try { return fs.statSync(`${input.databasePath}-wal`).size }
    catch { return null }
}

function numberValue(value: unknown): number {
    return Number.isFinite(Number(value)) ? Number(value) : 0
}

function checkpoint(): void {
    if (closed) return
    const startedAt = performance.now()
    try {
        const passiveResult = database.pragma("wal_checkpoint(PASSIVE)") as Array<Record<string, unknown>>
        const passiveState = passiveResult[0] ?? {}
        const passiveLogFrames = numberValue(passiveState.log)
        const passiveCheckpointedFrames = numberValue(passiveState.checkpointed)
        const currentWalBytes = walBytes()
        const truncateDue = (
            passiveLogFrames >= input.truncateFrames
            || (currentWalBytes !== null && currentWalBytes >= input.truncateBytes)
        ) && performance.now() - lastTruncateAt >= input.truncateCooldownMs
        let state = passiveState
        let mode = "passive"
        let truncateAttempted = false
        let truncateBusy = 0
        if (truncateDue) {
            truncateAttempted = true
            lastTruncateAt = performance.now()
            const truncateResult = database.pragma("wal_checkpoint(TRUNCATE)") as Array<Record<string, unknown>>
            state = truncateResult[0] ?? {}
            truncateBusy = numberValue(state.busy)
            mode = "truncate"
        }
        parentPort?.postMessage({
            type: "checkpoint",
            durationMs: performance.now() - startedAt,
            mode,
            busy: Math.max(numberValue(passiveState.busy), truncateBusy),
            logFrames: numberValue(state.log),
            checkpointedFrames: numberValue(state.checkpointed),
            passiveLogFrames,
            passiveCheckpointedFrames,
            truncateAttempted,
            truncateBusy,
            walBytes: walBytes(),
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
