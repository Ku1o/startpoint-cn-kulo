"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.installRoutePerformanceMonitor = void 0;
const perf_hooks_1 = require("perf_hooks");
const settlement_performance_1 = require("./settlement-performance");
const admission_1 = require("../multi/room/admission");
function isEnabled() {
    var _a;
    return !/^(0|false|no|off)$/i.test((_a = process.env.ROUTE_PERF_SUMMARY) !== null && _a !== void 0 ? _a : "true");
}
/**
 * Adds constant-space, per-route request timing.  It emits one compact line
 * per interval instead of logging every request, so it can remain enabled on
 * production servers while still exposing the routes consuming the CPU core.
 */
function installRoutePerformanceMonitor(fastify) {
    var _a;
    if (!isEnabled())
        return;
    const starts = new WeakMap();
    const timings = new Map();
    const intervalMs = Math.max(10000, Number.parseInt((_a = process.env.ROUTE_PERF_INTERVAL_MS) !== null && _a !== void 0 ? _a : "60000", 10) || 60000);
    const eventLoopDelay = (0, perf_hooks_1.monitorEventLoopDelay)({ resolution: 20 });
    eventLoopDelay.enable();
    let previousElu = perf_hooks_1.performance.eventLoopUtilization();
    let previousCpu = process.cpuUsage();
    fastify.addHook("onRequest", (request, _reply, done) => {
        starts.set(request, process.hrtime.bigint());
        done();
    });
    fastify.addHook("onResponse", (request, _reply, done) => {
        var _a, _b;
        const startedAt = starts.get(request);
        if (startedAt !== undefined) {
            const elapsedMs = Number(process.hrtime.bigint() - startedAt) / 1000000;
            const route = ((_a = request.routeOptions) === null || _a === void 0 ? void 0 : _a.url) || request.url.split("?", 1)[0];
            const key = `${request.method} ${route}`;
            const current = (_b = timings.get(key)) !== null && _b !== void 0 ? _b : { count: 0, totalMs: 0, maxMs: 0 };
            current.count += 1;
            current.totalMs += elapsedMs;
            current.maxMs = Math.max(current.maxMs, elapsedMs);
            timings.set(key, current);
        }
        done();
    });
    const timer = setInterval(() => {
        const snapshot = [...timings.entries()];
        timings.clear();
        const requestCount = snapshot.reduce((total, [, timing]) => total + timing.count, 0);
        const top = snapshot
            .sort(([, left], [, right]) => right.totalMs - left.totalMs)
            .slice(0, 6)
            .map(([route, timing]) => (`${route}{n=${timing.count},avg=${(timing.totalMs / timing.count).toFixed(1)}ms,max=${timing.maxMs.toFixed(1)}ms}`))
            .join("; ");
        const elu = perf_hooks_1.performance.eventLoopUtilization(previousElu);
        previousElu = perf_hooks_1.performance.eventLoopUtilization();
        const cpu = process.cpuUsage(previousCpu);
        previousCpu = process.cpuUsage();
        const cpuMs = (cpu.user + cpu.system) / 1000;
        const loopP99Ms = eventLoopDelay.percentile(99) / 1000000;
        const loopMaxMs = eventLoopDelay.max / 1000000;
        eventLoopDelay.reset();
        const phases = (0, settlement_performance_1.drainSettlementPerformanceSummary)();
        const gacha = (0, settlement_performance_1.drainGachaRequestSummary)();
        const admission = (0, admission_1.drainRoomAdmissionPerformanceSummary)();
        if (requestCount === 0 && phases === "none" && admission === "none")
            return;
        console.warn(`[PERF] interval=${intervalMs}ms requests=${requestCount} cpu=${cpuMs.toFixed(0)}ms `
            + `elu=${(elu.utilization * 100).toFixed(1)}% loopP99=${loopP99Ms.toFixed(1)}ms `
            + `loopMax=${loopMaxMs.toFixed(1)}ms top=${top || "none"}`
            + ` phases=${phases} gacha=${gacha} admission=${admission}`);
    }, intervalMs);
    timer.unref();
}
exports.installRoutePerformanceMonitor = installRoutePerformanceMonitor;
