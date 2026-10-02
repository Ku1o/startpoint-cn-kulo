"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.drainSingleSettlementDiagnostics = exports.createSingleSettlementBodyTimer = void 0;
const node_perf_hooks_1 = require("node:perf_hooks");
const timings = new Map();
const rounded = (value) => Math.round(value * 1000) / 1000;
const disabledTimer = { step(_phase) { }, finish(_bodySucceeded) { } };
/** Disjoint transaction-body intervals, bounded to known numeric categories plus two buckets. */
function createSingleSettlementBodyTimer(category, fiveBoss) {
    var _a;
    if (/^(0|false|no|off)$/i.test((_a = process.env.ROUTE_PERF_SUMMARY) !== null && _a !== void 0 ? _a : "true"))
        return disabledTimer;
    const key = fiveBoss ? "five_boss" : Number.isInteger(category) && category >= 0 && category <= 27
        ? String(category) : "other";
    const startedAt = node_perf_hooks_1.performance.now();
    let previousAt = startedAt;
    let phase = "rewards";
    let finished = false;
    const local = {};
    const record = (now) => {
        var _a;
        local[phase] = ((_a = local[phase]) !== null && _a !== void 0 ? _a : 0) + now - previousAt;
        previousAt = now;
    };
    return {
        step(next) {
            if (finished)
                return;
            record(node_perf_hooks_1.performance.now());
            phase = next;
        },
        finish(bodySucceeded) {
            var _a, _b;
            if (finished)
                return;
            finished = true;
            const now = node_perf_hooks_1.performance.now();
            record(now);
            const elapsed = now - startedAt;
            const entry = (_a = timings.get(key)) !== null && _a !== void 0 ? _a : { n: 0, bodyErrors: 0, totalMs: 0, maxMs: 0, phases: {} };
            entry.n++;
            if (!bodySucceeded)
                entry.bodyErrors++;
            entry.totalMs += elapsed;
            entry.maxMs = Math.max(entry.maxMs, elapsed);
            for (const name of Object.keys(local)) {
                const duration = local[name];
                const timing = (_b = entry.phases[name]) !== null && _b !== void 0 ? _b : { n: 0, totalMs: 0, maxMs: 0 };
                timing.n++;
                timing.totalMs += duration;
                timing.maxMs = Math.max(timing.maxMs, duration);
                entry.phases[name] = timing;
            }
            timings.set(key, entry);
        },
    };
}
exports.createSingleSettlementBodyTimer = createSingleSettlementBodyTimer;
function drainSingleSettlementDiagnostics() {
    const result = Object.fromEntries([...timings].map(([key, entry]) => [key, Object.assign(Object.assign({}, entry), { totalMs: rounded(entry.totalMs), maxMs: rounded(entry.maxMs), phases: Object.fromEntries(Object.entries(entry.phases).map(([phase, timing]) => [phase, Object.assign(Object.assign({}, timing), { totalMs: rounded(timing.totalMs), maxMs: rounded(timing.maxMs) })])) })]));
    timings.clear();
    return result;
}
exports.drainSingleSettlementDiagnostics = drainSingleSettlementDiagnostics;
