interface PhaseTiming {
    count: number
    totalMs: number
    maxMs: number
}

const timings = new Map<string, PhaseTiming>()
const gachaRequests = {
    character: { requests: 0, pulls: 0 },
    equipment: { requests: 0, pulls: 0 },
}

export function recordGachaRequest(kind: "character" | "equipment", pulls: number): void {
    if (!Number.isSafeInteger(pulls) || pulls <= 0) return
    gachaRequests[kind].requests += 1
    gachaRequests[kind].pulls += pulls
}

export function drainGachaRequestSummary(): string {
    return Object.entries(gachaRequests).map(([kind, counters]) => {
        const text = `${kind}{requests=${counters.requests},pulls=${counters.pulls}}`
        counters.requests = 0
        counters.pulls = 0
        return text
    }).join("; ")
}

export function recordSettlementPhase(kind: "single" | "multi" | "gacha", phase: string, elapsedMs: number): void {
    if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return
    const key = `${kind}.${phase}`
    const timing = timings.get(key) ?? { count: 0, totalMs: 0, maxMs: 0 }
    timing.count += 1
    timing.totalMs += elapsedMs
    timing.maxMs = Math.max(timing.maxMs, elapsedMs)
    timings.set(key, timing)
}

export function measureSettlementPhase<T>(
    kind: "single" | "multi" | "gacha",
    phase: string,
    operation: () => T,
): T {
    const startedAt = process.hrtime.bigint()
    try {
        return operation()
    } finally {
        recordSettlementPhase(kind, phase, Number(process.hrtime.bigint() - startedAt) / 1_000_000)
    }
}

export async function measureSettlementPhaseAsync<T>(
    kind: "single" | "multi" | "gacha",
    phase: string,
    operation: () => Promise<T>,
): Promise<T> {
    const startedAt = process.hrtime.bigint()
    try {
        return await operation()
    } finally {
        recordSettlementPhase(kind, phase, Number(process.hrtime.bigint() - startedAt) / 1_000_000)
    }
}

export function drainSettlementPerformanceSummary(limit = 12): string {
    if (timings.size === 0) return "none"
    const snapshot = [...timings.entries()]
    timings.clear()
    return snapshot
        .sort(([, left], [, right]) => right.totalMs - left.totalMs)
        .slice(0, limit)
        .map(([phase, timing]) => (
            `${phase}{n=${timing.count},avg=${(timing.totalMs / timing.count).toFixed(1)}ms,max=${timing.maxMs.toFixed(1)}ms}`
        ))
        .join("; ")
}
