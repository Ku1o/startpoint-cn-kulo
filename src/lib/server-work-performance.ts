import { performance } from "node:perf_hooks"

// Fixed names keep telemetry bounded even when request IDs are unbounded.
export type ServerWorkPhase = "encode.pack" | "encode.fix" | "encode.base64"
    | "encode.compressWait" | "encode.clone" | "encode.queue" | "encode.workerRoundTrip"
    | "db.single.body" | "db.single.commit" | "db.begin" | "db.body" | "db.commit" | "db.playerQueue"

const timings = new Map<ServerWorkPhase, { n: number, totalMs: number, maxMs: number }>()

export function recordServerWork(phase: ServerWorkPhase, elapsedMs: number): void {
    if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return
    const value = timings.get(phase) ?? { n: 0, totalMs: 0, maxMs: 0 }
    value.n++
    value.totalMs += elapsedMs
    value.maxMs = Math.max(value.maxMs, elapsedMs)
    timings.set(phase, value)
}

export function measureServerWork<T>(phase: ServerWorkPhase, operation: () => T): T {
    const start = performance.now()
    try { return operation() } finally { recordServerWork(phase, performance.now() - start) }
}

export function drainServerWorkPerformance() {
    const snapshot = Object.fromEntries([...timings].map(([phase, value]) => [phase, {
        n: value.n,
        avgMs: Math.round(value.totalMs / value.n * 1000) / 1000,
        maxMs: Math.round(value.maxMs * 1000) / 1000,
        totalMs: Math.round(value.totalMs * 1000) / 1000,
    }]))
    timings.clear()
    return snapshot
}
