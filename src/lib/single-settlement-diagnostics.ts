import { performance } from "node:perf_hooks"

export type SingleSettlementPhase = "rewards" | "battle_facts" | "experience" | "mode_rewards"
    | "missions" | "awake" | "active" | "response"
interface Timing { n: number; totalMs: number; maxMs: number }
interface CategoryTiming {
    n: number
    bodyErrors: number
    totalMs: number
    maxMs: number
    phases: Partial<Record<SingleSettlementPhase, Timing>>
}
const timings = new Map<string, CategoryTiming>()
const rounded = (value: number) => Math.round(value * 1000) / 1000
const disabledCollector = {
    step(_phase: SingleSettlementPhase) {},
    result(_bodySucceeded: boolean): SingleSettlementBodyTiming | null { return null },
}

/**
 * One completed transaction-body measurement.
 *
 * The finish settlement can run in the SQLite writer thread, so the phases
 * travel back with the command result and are merged into the main-thread
 * aggregate instead of being recorded where the body executed.
 */
export interface SingleSettlementBodyTiming {
    category: number
    fiveBoss: boolean
    succeeded: boolean
    totalMs: number
    phases: Partial<Record<SingleSettlementPhase, number>>
}

function keyOf(category: number, fiveBoss: boolean): string {
    return fiveBoss ? "five_boss" : Number.isInteger(category) && category >= 0 && category <= 27
        ? String(category) : "other"
}

/** Merge one completed body measurement into the per-category aggregate. */
export function recordSingleSettlementBodyTiming(timing: SingleSettlementBodyTiming): void {
    const entry = timings.get(keyOf(timing.category, timing.fiveBoss))
        ?? { n: 0, bodyErrors: 0, totalMs: 0, maxMs: 0, phases: {} }
    entry.n++
    if (!timing.succeeded) entry.bodyErrors++
    entry.totalMs += timing.totalMs
    entry.maxMs = Math.max(entry.maxMs, timing.totalMs)
    for (const name of Object.keys(timing.phases) as SingleSettlementPhase[]) {
        const duration = timing.phases[name]!
        const phaseTiming = entry.phases[name] ?? { n: 0, totalMs: 0, maxMs: 0 }
        phaseTiming.n++
        phaseTiming.totalMs += duration
        phaseTiming.maxMs = Math.max(phaseTiming.maxMs, duration)
        entry.phases[name] = phaseTiming
    }
    timings.set(keyOf(timing.category, timing.fiveBoss), entry)
}

/**
 * Disjoint transaction-body intervals, bounded to known numeric categories
 * plus two buckets. `result` returns the sample without touching the local
 * aggregate, which is what a command executed in another thread needs.
 */
export function createSingleSettlementBodyTimingCollector(category: number, fiveBoss: boolean) {
    if (/^(0|false|no|off)$/i.test(process.env.ROUTE_PERF_SUMMARY ?? "true")) return disabledCollector
    const startedAt = performance.now()
    let previousAt = startedAt
    let phase: SingleSettlementPhase = "rewards"
    let finished = false
    const local: Partial<Record<SingleSettlementPhase, number>> = {}
    const record = (now: number) => {
        local[phase] = (local[phase] ?? 0) + now - previousAt
        previousAt = now
    }
    return {
        step(next: SingleSettlementPhase) {
            if (finished) return
            record(performance.now())
            phase = next
        },
        result(bodySucceeded: boolean): SingleSettlementBodyTiming | null {
            if (finished) return null
            finished = true
            const now = performance.now()
            record(now)
            return {
                category, fiveBoss, succeeded: bodySucceeded,
                totalMs: now - startedAt,
                phases: { ...local },
            }
        },
    }
}

/** In-process timer: records the finished body into the local aggregate. */
export function createSingleSettlementBodyTimer(category: number, fiveBoss: boolean) {
    const collector = createSingleSettlementBodyTimingCollector(category, fiveBoss)
    return {
        step: collector.step,
        finish(bodySucceeded: boolean) {
            const timing = collector.result(bodySucceeded)
            if (timing !== null) recordSingleSettlementBodyTiming(timing)
        },
    }
}

export function drainSingleSettlementDiagnostics() {
    const result = Object.fromEntries([...timings].map(([key, entry]) => [key, {
        ...entry, totalMs: rounded(entry.totalMs), maxMs: rounded(entry.maxMs),
        phases: Object.fromEntries(Object.entries(entry.phases).map(([phase, timing]) => [phase, {
            ...timing, totalMs: rounded(timing.totalMs), maxMs: rounded(timing.maxMs),
        }])),
    }]))
    timings.clear()
    return result
}
