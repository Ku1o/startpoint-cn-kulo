import type { FastifyInstance } from "fastify"
import { monitorEventLoopDelay, performance } from "perf_hooks"
import { drainGachaRequestSummary, drainSettlementPerformanceSummary } from "./settlement-performance"
import { drainRoomAdmissionPerformanceSummary } from "../multi/room/admission"
import { installMemoryDiagnostics } from "./memory-diagnostics"
import { drainAwakeDiagnostics, installRequestDiagnostics } from "./request-diagnostics"
import { drainServerWorkPerformance } from "./server-work-performance"
import { drainSqliteCommitDiagnostics } from "./sqlite-commit-diagnostics"
import { drainSingleSettlementDiagnostics } from "./single-settlement-diagnostics"

function isEnabled(): boolean {
    return !/^(0|false|no|off)$/i.test(process.env.ROUTE_PERF_SUMMARY ?? "true")
}

/**
 * Adds constant-space, per-route request timing.  It emits one compact line
 * per interval instead of logging every request, so it can remain enabled on
 * production servers while still exposing the routes consuming the CPU core.
 */
export function installRoutePerformanceMonitor(fastify: FastifyInstance): void {
    installMemoryDiagnostics(fastify)
    if (!isEnabled()) return

    const diagnostics = installRequestDiagnostics(fastify)
    const intervalMs = Math.max(
        10_000,
        Number.parseInt(process.env.ROUTE_PERF_INTERVAL_MS ?? "60000", 10) || 60_000,
    )
    const eventLoopDelay = monitorEventLoopDelay({ resolution: 20 })
    eventLoopDelay.enable()
    let previousElu = performance.eventLoopUtilization()
    let previousCpu = process.cpuUsage()
    let previousSampleAt = performance.now()

    const timer = setInterval(() => {
        const sampledAt = performance.now()
        const actualIntervalMs = sampledAt - previousSampleAt
        previousSampleAt = sampledAt
        const { routes: snapshot, summary } = diagnostics.drain()
        const awake = drainAwakeDiagnostics()
        const requestCount = summary.n
        const top = snapshot
            .sort(([, left], [, right]) => right.totalMs - left.totalMs)
            .slice(0, 6)
            .map(([route, timing]) => (
                `${route}{n=${timing.n},avg=${(timing.totalMs / timing.n).toFixed(1)}ms,max=${timing.maxMs.toFixed(1)}ms}`
            ))
            .join("; ")
        const elu = performance.eventLoopUtilization(previousElu)
        previousElu = performance.eventLoopUtilization()
        const cpu = process.cpuUsage(previousCpu)
        previousCpu = process.cpuUsage()
        const cpuMs = (cpu.user + cpu.system) / 1000
        const loopP99Ms = eventLoopDelay.percentile(99) / 1_000_000
        const loopMaxMs = eventLoopDelay.max / 1_000_000
        eventLoopDelay.reset()
        const phases = drainSettlementPerformanceSummary()
        const gacha = drainGachaRequestSummary()
        const admission = drainRoomAdmissionPerformanceSummary()
        const work = drainServerWorkPerformance()
        const commits = drainSqliteCommitDiagnostics()
        const settlements = drainSingleSettlementDiagnostics()
        if (requestCount === 0 && phases === "none" && admission === "none"
            && awake.skippedUnownedMissions === 0 && commits.n === 0
            && gacha === "none" && Object.keys(work).length === 0
            && Object.keys(settlements).length === 0) return
        console.warn(
            `[PERF] interval=${intervalMs}ms requests=${requestCount} cpu=${cpuMs.toFixed(0)}ms `
            + `actualInterval=${actualIntervalMs.toFixed(1)}ms `
            + `elu=${(elu.utilization * 100).toFixed(1)}% loopP99=${loopP99Ms.toFixed(1)}ms `
            + `loopMax=${loopMaxMs.toFixed(1)}ms top=${top || "none"}`
            + ` phases=${phases} gacha=${gacha} admission=${admission}`,
        )
        console.warn(`[REQUEST-PERF] ${JSON.stringify({ ...summary, awake })}`)
        if (Object.keys(work).length > 0) console.warn(`[WORK-PERF] ${JSON.stringify(work)}`)
        if (commits.n > 0) console.warn(`[SQLITE-COMMIT] ${JSON.stringify(commits)}`)
        if (Object.keys(settlements).length > 0) console.warn(`[SINGLE-SETTLEMENT] ${JSON.stringify(settlements)}`)
    }, intervalMs)
    timer.unref()
    fastify.addHook("onClose", async () => { clearInterval(timer); eventLoopDelay.disable() })
}
