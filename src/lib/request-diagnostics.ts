import type { FastifyInstance, FastifyRequest } from "fastify"
import { performance } from "perf_hooks"

// Fixed buckets report upper bounds, not exact quantiles or CPU time.
const bounds = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 120000]
const maxRoutes = 256
const maxSlowSamples = 5
export type RequestOutcome = "rush_invalid_body" | "rush_invalid_session" | "rush_missing_player"
    | "rush_missing_event" | "rush_invalid_folder" | "rush_different_folder"
    | "rush_same_folder" | "rush_selected" | "rush_endless_compat" | "rush_ex_locked"

interface Timing { n: number; totalMs: number; maxMs: number; buckets: number[] }
interface RouteTiming extends Timing {
    statuses: Record<string, number>
    outcomes: Record<string, number>
    stages: Record<string, Timing>
    responseBytes: number
    aborted: number
    timeouts: number
}
interface RequestState {
    start: number
    parsed?: number
    prepared?: number
    sending?: number
    encodingMs: number
    responseBytes: number
    outcome?: string
}
const states = new WeakMap<FastifyRequest, RequestState>()
let awakeSkipped = 0
let awakeExamples: { missionId: number; characterId: number }[] = []

export function recordUnownedAwakeMission(missionId: number, characterId: number): void {
    awakeSkipped++
    if (awakeExamples.length < 3 && !awakeExamples.some(row => row.missionId === missionId)) {
        awakeExamples.push({ missionId, characterId })
    }
}

export function drainAwakeDiagnostics() {
    const result = { skippedUnownedMissions: awakeSkipped, examples: awakeExamples }
    awakeSkipped = 0
    awakeExamples = []
    return result
}

export function setRequestOutcome(request: FastifyRequest, outcome: RequestOutcome): void {
    const state = states.get(request)
    if (state) state.outcome = outcome
}

/** Record inline in an existing hook; do not add a Promise boundary to sending. */
export function recordResponseEncoding(request: FastifyRequest, durationMs: number, payload: unknown): void {
    const state = states.get(request)
    if (!state) return
    state.encodingMs += durationMs
    state.responseBytes = typeof payload === "string" ? Buffer.byteLength(payload)
        : Buffer.isBuffer(payload) ? payload.length : 0
}

/** Includes custom encoding/compression and its asynchronous waits, never CPU time. */
export async function measureResponseEncoding<T>(request: FastifyRequest, operation: () => Promise<T>): Promise<T> {
    const state = states.get(request)
    if (!state) return operation()
    const start = performance.now()
    try {
        const result = await operation()
        state.responseBytes = typeof result === "string" ? Buffer.byteLength(result)
            : Buffer.isBuffer(result) ? result.length : 0
        return result
    } finally {
        state.encodingMs += performance.now() - start
    }
}

function timing(): Timing { return { n: 0, totalMs: 0, maxMs: 0, buckets: Array(bounds.length + 1).fill(0) } }
function add(target: Timing, ms: number): void {
    ms = Math.max(0, ms)
    target.n++
    target.totalMs += ms
    target.maxMs = Math.max(target.maxMs, ms)
    const index = bounds.findIndex(bound => ms <= bound)
    target.buckets[index < 0 ? bounds.length : index]++
}
function describe(value: Timing) {
    const quantile = (ratio: number): number | string => {
        if (value.n === 0) return 0
        let count = 0
        for (let i = 0; i < value.buckets.length; i++) {
            count += value.buckets[i]!
            if (count >= Math.ceil(value.n * ratio)) return bounds[i] ?? ">120000"
        }
        return 0
    }
    return { n: value.n, avgMs: +(value.totalMs / (value.n || 1)).toFixed(1), maxMs: +value.maxMs.toFixed(1),
        p50UpperMs: quantile(.5), p95UpperMs: quantile(.95), p99UpperMs: quantile(.99) }
}
function increment(target: Record<string, number>, key: string): void { target[key] = (target[key] ?? 0) + 1 }

/** One bounded collector per server; no raw URL, body, IP or player identifiers. */
export function installRequestDiagnostics(app: FastifyInstance, options: { slowMs?: number } = {}) {
    const configuredSlowMs = Number(options.slowMs ?? process.env.ROUTE_PERF_SLOW_MS ?? 2000)
    const slowMs = Number.isFinite(configuredSlowMs) ? Math.max(100, configuredSlowMs) : 2000
    let routes = new Map<string, RouteTiming>()
    let total = timing()
    let statuses: Record<string, number> = {}
    let outcomes: Record<string, number> = {}
    let aborted = 0, timeouts = 0, omittedSlowSamples = 0
    let slow: Record<string, unknown>[] = []
    const knownErrors = new Set(["SQLITE_CONSTRAINT_FOREIGNKEY", "SQLITE_BUSY", "SQLITE_LOCKED",
        "FST_ERR_CTP_BODY_TOO_LARGE", "FST_ERR_CTP_INVALID_JSON_BODY", "FST_ERR_VALIDATION"])

    function finish(request: FastifyRequest, status: number, kind: "complete" | "aborted" | "timeout") {
        const state = states.get(request)
        if (!state) return
        states.delete(request) // close/abort/timeout/response must count once.
        const end = performance.now()
        const ms = end - state.start
        const method = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"].includes(request.method)
            ? request.method : "OTHER"
        let route = `${method} ${request.routeOptions?.url ?? "<unmatched>"}`
        if (!routes.has(route) && routes.size >= maxRoutes - 1) route = "<overflow>"
        const row = routes.get(route) ?? { ...timing(), statuses: {}, outcomes: {}, stages: {},
            responseBytes: 0, aborted: 0, timeouts: 0 }
        routes.set(route, row)
        add(row, ms); add(total, ms)
        const statusKey = kind === "complete" && Number.isInteger(status) && status >= 100 && status <= 599
            ? String(status) : kind
        increment(row.statuses, statusKey); increment(statuses, statusKey)
        if (kind === "aborted") { row.aborted++; aborted++ }
        if (kind === "timeout") { row.timeouts++; timeouts++ }
        if (state.outcome) { increment(row.outcomes, state.outcome); increment(outcomes, state.outcome) }
        const stages: Record<string, number> = {}
        if (state.parsed !== undefined) stages.receiveParse = state.parsed - state.start
        if (state.parsed !== undefined && (state.prepared ?? state.sending) !== undefined) {
            stages.application = (state.prepared ?? state.sending)! - state.parsed
        }
        if (state.prepared !== undefined && state.sending !== undefined) stages.serialize = state.sending - state.prepared
        if (state.sending !== undefined) {
            stages.customEncoding = state.encodingMs
            stages.sendRemainder = Math.max(0, end - state.sending - state.encodingMs)
        }
        for (const [name, value] of Object.entries(stages)) add(row.stages[name] ??= timing(), value)
        row.responseBytes += state.responseBytes
        if (ms >= slowMs || kind !== "complete" || status >= 500) {
            if (slow.length < maxSlowSamples) slow.push({ route,
                requestId: String(request.id).replace(/[^A-Za-z0-9_.:-]/g, "_").slice(0, 64),
                status: statusKey, ms: +ms.toFixed(1), outcome: state.outcome,
                stages: Object.fromEntries(Object.entries(stages).map(([key, value]) => [key, +value.toFixed(1)])),
                responseBytes: state.responseBytes })
            else omittedSlowSamples++
        }
    }

    app.addHook("onRequest", (request, reply, done) => {
        states.set(request, { start: performance.now(), encodingMs: 0, responseBytes: 0 })
        const onClose = () => {
            if (!reply.raw.writableFinished) finish(request, reply.statusCode, "aborted")
        }
        reply.raw.once("close", onClose)
        reply.raw.once("finish", () => reply.raw.removeListener("close", onClose))
        done()
    })
    app.addHook("preValidation", (request, _reply, done) => { const s = states.get(request); if (s) s.parsed = performance.now(); done() })
    app.addHook("preSerialization", (request, _reply, payload, done) => {
        const s = states.get(request); if (s) s.prepared = performance.now(); done(null, payload)
    })
    app.addHook("onSend", (request, _reply, payload, done) => {
        const s = states.get(request)
        if (s) {
            s.sending = performance.now()
            s.responseBytes = typeof payload === "string" ? Buffer.byteLength(payload) : Buffer.isBuffer(payload) ? payload.length : 0
        }
        done(null, payload)
    })
    app.addHook("onError", (request, _reply, error, done) => {
        const s = states.get(request)
        if (s && !s.outcome) s.outcome = knownErrors.has(error.code ?? "") ? error.code! : "unclassified_error"
        done()
    })
    app.addHook("onRequestAbort", (request, done) => { finish(request, 0, "aborted"); done() })
    app.addHook("onTimeout", (request, _reply, done) => { finish(request, 0, "timeout"); done() })
    app.addHook("onResponse", (request, reply, done) => { finish(request, reply.statusCode, "complete"); done() })

    return {
        drain() {
            const snapshot = [...routes].sort(([, a], [, b]) => b.totalMs - a.totalMs)
            const compact = ([route, row]: [string, RouteTiming]) => ({ route, ...describe(row), statuses: row.statuses,
                outcomes: row.outcomes, stages: Object.fromEntries(Object.entries(row.stages).map(([key, value]) => [key, describe(value)])),
                responseBytes: row.responseBytes, aborted: row.aborted, timeouts: row.timeouts })
            const result = { routes: snapshot, summary: { timestamp: new Date().toISOString(), ...describe(total),
                statuses, outcomes, aborted, timeouts, routeCount: routes.size, top: snapshot.slice(0, 12).map(compact),
                failures: snapshot.filter(([, row]) => row.aborted || row.timeouts || Object.keys(row.statuses).some(code => /^[45]/.test(code)))
                    .sort(([, a], [, b]) => b.n - a.n).slice(0, 12).map(compact), slow, omittedSlowSamples } }
            routes = new Map(); total = timing(); statuses = {}; outcomes = {}; aborted = 0; timeouts = 0; slow = []; omittedSlowSamples = 0
            return result
        },
    }
}
