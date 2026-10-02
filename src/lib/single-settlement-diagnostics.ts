import { performance } from "node:perf_hooks"

type Phase = "rewards" | "battle_facts" | "experience" | "mode_rewards"
    | "missions" | "awake" | "active" | "response"
interface Timing { n: number; totalMs: number; maxMs: number }
interface CategoryTiming {
    n: number
    bodyErrors: number
    totalMs: number
    maxMs: number
    phases: Partial<Record<Phase, Timing>>
}
const timings = new Map<string, CategoryTiming>()
const rounded = (value: number) => Math.round(value * 1000) / 1000
const disabledTimer = { step(_phase: Phase) {}, finish(_bodySucceeded: boolean) {} }

/** Disjoint transaction-body intervals, bounded to known numeric categories plus two buckets. */
export function createSingleSettlementBodyTimer(category: number, fiveBoss: boolean) {
    if (/^(0|false|no|off)$/i.test(process.env.ROUTE_PERF_SUMMARY ?? "true")) return disabledTimer
    const key = fiveBoss ? "five_boss" : Number.isInteger(category) && category >= 0 && category <= 27
        ? String(category) : "other"
    const startedAt = performance.now()
    let previousAt = startedAt
    let phase: Phase = "rewards"
    let finished = false
    const local: Partial<Record<Phase, number>> = {}
    const record = (now: number) => {
        local[phase] = (local[phase] ?? 0) + now - previousAt
        previousAt = now
    }
    return {
        step(next: Phase) {
            if (finished) return
            record(performance.now())
            phase = next
        },
        finish(bodySucceeded: boolean) {
            if (finished) return
            finished = true
            const now = performance.now()
            record(now)
            const elapsed = now - startedAt
            const entry = timings.get(key) ?? { n: 0, bodyErrors: 0, totalMs: 0, maxMs: 0, phases: {} }
            entry.n++
            if (!bodySucceeded) entry.bodyErrors++
            entry.totalMs += elapsed
            entry.maxMs = Math.max(entry.maxMs, elapsed)
            for (const name of Object.keys(local) as Phase[]) {
                const duration = local[name]!
                const timing = entry.phases[name] ?? { n: 0, totalMs: 0, maxMs: 0 }
                timing.n++
                timing.totalMs += duration
                timing.maxMs = Math.max(timing.maxMs, duration)
                entry.phases[name] = timing
            }
            timings.set(key, entry)
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
