import { AsyncLocalStorage } from "node:async_hooks"
import { performance } from "node:perf_hooks"
import { isMainThread } from "node:worker_threads"

interface OperationContext { domain: string; operation: string }
type CpuUsage = { user: number; system: number }
type PhaseKind = "sync" | "wait"
interface Clock {
    now: () => number
    epoch: () => number
    cpu: (() => CpuUsage) | undefined
}
interface Phase {
    phase: string; kind: PhaseKind; context: OperationContext
    start: number; epoch: number; cpu: CpuUsage | undefined
}
interface Sample {
    domain: string; operation: string; phase: string; kind: PhaseKind
    startedAt: string; endedAt: string; wallMs: number
    threadCpuMs: number | null; failed: boolean
}
const MAX_SAMPLES = 16
const FIRST_SAMPLES = 4
const threadCpuUsage = (process as typeof process & { threadCpuUsage?: () => CpuUsage }).threadCpuUsage
const round = (n: number) => Math.round(n * 1000) / 1000
const label = (value: string) => {
    // Existing administrative operation names may append an account ID after ':'.
    if (typeof value !== "string") return "unknown"
    const stable = value.split(":", 1)[0]!
    return /^[a-zA-Z][a-zA-Z0-9_.-]{0,79}$/.test(stable) ? stable : "unknown"
}

/** Bounded metadata only: no SQL, request payload, player ID, file path or error text. */
export function createSlowOperationDiagnostics(options: {
    enabled?: boolean; thresholdMs?: number; clock?: Clock
} = {}) {
    const enabled = options.enabled ?? (isMainThread && process.env.MULTI_REALTIME_OWNER_CHILD !== "1"
        && !/^(0|false|no|off)$/i.test(process.env.SLOW_OPERATION_DIAGNOSTICS ?? "true")
        && !/^(0|false|no|off)$/i.test(process.env.ROUTE_PERF_SUMMARY ?? "true"))
    const configured = options.thresholdMs ?? Number(process.env.SLOW_OPERATION_MS ?? 250)
    const thresholdMs = Number.isFinite(configured) ? Math.max(1, Math.min(60_000, configured)) : 250
    const clock = options.clock ?? {
        now: () => performance.now(), epoch: () => Date.now(),
        cpu: threadCpuUsage ? () => threadCpuUsage.call(process) : undefined,
    }
    const contexts = new AsyncLocalStorage<OperationContext>()
    let samples: Sample[] = [], count = 0, maxWallMs = 0, observerErrors = 0
    function withContext<T>(context: OperationContext, operation: () => T): T {
        if (!enabled) return operation()
        return contexts.run({ domain: label(context.domain), operation: label(context.operation) }, operation)
    }
    function begin(phase: string, kind: PhaseKind = "sync", context?: OperationContext): Phase | undefined {
        if (!enabled) return
        try {
            return {
                phase: label(phase), kind,
                context: context ? { domain: label(context.domain), operation: label(context.operation) }
                    : contexts.getStore() ?? { domain: "unscoped", operation: "unscoped" },
                start: clock.now(), epoch: clock.epoch(),
                // Other work can run during an await; its CPU is not attributable to this wait.
                cpu: kind === "sync" ? clock.cpu?.() : undefined,
            }
        } catch { observerErrors++; return undefined }
    }
    function end(token: Phase | undefined, failed = false): void {
        // Only observation errors are isolated; business exceptions still leave measure unchanged.
        try { recordEnd(token, failed) } catch { observerErrors++ }
    }
    function recordEnd(token: Phase | undefined, failed: boolean): void {
        if (!token) return
        const ended = clock.now(), wallMs = ended - token.start
        if (!Number.isFinite(wallMs) || wallMs < thresholdMs) return
        const cpu = token.cpu ? clock.cpu?.() : undefined
        const sample: Sample = {
            ...token.context, phase: token.phase, kind: token.kind,
            startedAt: new Date(token.epoch).toISOString(),
            endedAt: new Date(token.epoch + wallMs).toISOString(), wallMs: round(wallMs),
            threadCpuMs: cpu && token.cpu
                ? round(Math.max(0, (cpu.user + cpu.system - token.cpu.user - token.cpu.system) / 1000)) : null,
            failed,
        }
        count++
        maxWallMs = Math.max(maxWallMs, wallMs)
        if (samples.length < MAX_SAMPLES) samples.push(sample)
        else {
            // Keep the first four events to preserve onset, plus the twelve longest later events.
            let smallest = FIRST_SAMPLES
            for (let i = FIRST_SAMPLES + 1; i < samples.length; i++) {
                if (samples[i]!.wallMs < samples[smallest]!.wallMs) smallest = i
            }
            if (sample.wallMs > samples[smallest]!.wallMs) samples[smallest] = sample
        }
    }
    function measure<T>(phase: string, operation: () => T): T {
        const token = begin(phase)
        let failed = true
        try { const result = operation(); failed = false; return result }
        finally { end(token, failed) }
    }
    function drain() {
        const result = { count, omitted: Math.max(0, count - samples.length), maxWallMs: round(maxWallMs), observerErrors,
            samples: samples.sort((a, b) => a.startedAt.localeCompare(b.startedAt)) }
        samples = []; count = 0; maxWallMs = 0; observerErrors = 0
        return result
    }
    return { withContext, begin, end, measure, drain,
        configuration: { enabled, thresholdMs, maxSamples: MAX_SAMPLES, threadCpuAvailable: !!clock.cpu } }
}

const diagnostics = createSlowOperationDiagnostics()
export const withSlowOperationContext = diagnostics.withContext
export const beginSlowOperationPhase = diagnostics.begin
export const endSlowOperationPhase = diagnostics.end
export const measureSlowOperation = diagnostics.measure
export const drainSlowOperationDiagnostics = diagnostics.drain
export const slowOperationDiagnosticsConfiguration = diagnostics.configuration
