"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.installRequestDiagnostics = exports.measureResponseEncoding = exports.recordResponseEncoding = exports.setRequestOutcome = exports.drainAwakeDiagnostics = exports.recordUnownedAwakeMission = void 0;
const perf_hooks_1 = require("perf_hooks");
// Fixed buckets report upper bounds, not exact quantiles or CPU time.
const bounds = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 120000];
const maxRoutes = 256;
const maxSlowSamples = 5;
const states = new WeakMap();
let awakeSkipped = 0;
let awakeExamples = [];
function recordUnownedAwakeMission(missionId, characterId) {
    awakeSkipped++;
    if (awakeExamples.length < 3 && !awakeExamples.some(row => row.missionId === missionId)) {
        awakeExamples.push({ missionId, characterId });
    }
}
exports.recordUnownedAwakeMission = recordUnownedAwakeMission;
function drainAwakeDiagnostics() {
    const result = { skippedUnownedMissions: awakeSkipped, examples: awakeExamples };
    awakeSkipped = 0;
    awakeExamples = [];
    return result;
}
exports.drainAwakeDiagnostics = drainAwakeDiagnostics;
function setRequestOutcome(request, outcome) {
    const state = states.get(request);
    if (state)
        state.outcome = outcome;
}
exports.setRequestOutcome = setRequestOutcome;
/** Record inline in an existing hook; do not add a Promise boundary to sending. */
function recordResponseEncoding(request, durationMs, payload) {
    const state = states.get(request);
    if (!state)
        return;
    state.encodingMs += durationMs;
    state.responseBytes = typeof payload === "string" ? Buffer.byteLength(payload)
        : Buffer.isBuffer(payload) ? payload.length : 0;
}
exports.recordResponseEncoding = recordResponseEncoding;
/** Includes custom encoding/compression and its asynchronous waits, never CPU time. */
function measureResponseEncoding(request, operation) {
    return __awaiter(this, void 0, void 0, function* () {
        const state = states.get(request);
        if (!state)
            return operation();
        const start = perf_hooks_1.performance.now();
        try {
            const result = yield operation();
            state.responseBytes = typeof result === "string" ? Buffer.byteLength(result)
                : Buffer.isBuffer(result) ? result.length : 0;
            return result;
        }
        finally {
            state.encodingMs += perf_hooks_1.performance.now() - start;
        }
    });
}
exports.measureResponseEncoding = measureResponseEncoding;
function timing() { return { n: 0, totalMs: 0, maxMs: 0, buckets: Array(bounds.length + 1).fill(0) }; }
function add(target, ms) {
    ms = Math.max(0, ms);
    target.n++;
    target.totalMs += ms;
    target.maxMs = Math.max(target.maxMs, ms);
    const index = bounds.findIndex(bound => ms <= bound);
    target.buckets[index < 0 ? bounds.length : index]++;
}
function describe(value) {
    const quantile = (ratio) => {
        var _a;
        if (value.n === 0)
            return 0;
        let count = 0;
        for (let i = 0; i < value.buckets.length; i++) {
            count += value.buckets[i];
            if (count >= Math.ceil(value.n * ratio))
                return (_a = bounds[i]) !== null && _a !== void 0 ? _a : ">120000";
        }
        return 0;
    };
    return { n: value.n, avgMs: +(value.totalMs / (value.n || 1)).toFixed(1), maxMs: +value.maxMs.toFixed(1),
        p50UpperMs: quantile(.5), p95UpperMs: quantile(.95), p99UpperMs: quantile(.99) };
}
function increment(target, key) { var _a; target[key] = ((_a = target[key]) !== null && _a !== void 0 ? _a : 0) + 1; }
/** One bounded collector per server; no raw URL, body, IP or player identifiers. */
function installRequestDiagnostics(app, options = {}) {
    var _a, _b;
    const configuredSlowMs = Number((_b = (_a = options.slowMs) !== null && _a !== void 0 ? _a : process.env.ROUTE_PERF_SLOW_MS) !== null && _b !== void 0 ? _b : 2000);
    const slowMs = Number.isFinite(configuredSlowMs) ? Math.max(100, configuredSlowMs) : 2000;
    let routes = new Map();
    let total = timing();
    let statuses = {};
    let outcomes = {};
    let aborted = 0, timeouts = 0, omittedSlowSamples = 0;
    let slow = [];
    const knownErrors = new Set(["SQLITE_CONSTRAINT_FOREIGNKEY", "SQLITE_BUSY", "SQLITE_LOCKED",
        "FST_ERR_CTP_BODY_TOO_LARGE", "FST_ERR_CTP_INVALID_JSON_BODY", "FST_ERR_VALIDATION"]);
    function finish(request, status, kind) {
        var _a, _b, _c, _d, _e, _f;
        var _g;
        const state = states.get(request);
        if (!state)
            return;
        states.delete(request); // close/abort/timeout/response must count once.
        const end = perf_hooks_1.performance.now();
        const ms = end - state.start;
        const method = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"].includes(request.method)
            ? request.method : "OTHER";
        let route = `${method} ${(_b = (_a = request.routeOptions) === null || _a === void 0 ? void 0 : _a.url) !== null && _b !== void 0 ? _b : "<unmatched>"}`;
        if (!routes.has(route) && routes.size >= maxRoutes - 1)
            route = "<overflow>";
        const row = (_c = routes.get(route)) !== null && _c !== void 0 ? _c : Object.assign(Object.assign({}, timing()), { statuses: {}, outcomes: {}, stages: {}, responseBytes: 0, aborted: 0, timeouts: 0 });
        routes.set(route, row);
        add(row, ms);
        add(total, ms);
        const statusKey = kind === "complete" && Number.isInteger(status) && status >= 100 && status <= 599
            ? String(status) : kind;
        increment(row.statuses, statusKey);
        increment(statuses, statusKey);
        if (kind === "aborted") {
            row.aborted++;
            aborted++;
        }
        if (kind === "timeout") {
            row.timeouts++;
            timeouts++;
        }
        if (state.outcome) {
            increment(row.outcomes, state.outcome);
            increment(outcomes, state.outcome);
        }
        const stages = {};
        if (state.parsed !== undefined)
            stages.receiveParse = state.parsed - state.start;
        if (state.parsed !== undefined && ((_d = state.prepared) !== null && _d !== void 0 ? _d : state.sending) !== undefined) {
            stages.application = ((_e = state.prepared) !== null && _e !== void 0 ? _e : state.sending) - state.parsed;
        }
        if (state.prepared !== undefined && state.sending !== undefined)
            stages.serialize = state.sending - state.prepared;
        if (state.sending !== undefined) {
            stages.customEncoding = state.encodingMs;
            stages.sendRemainder = Math.max(0, end - state.sending - state.encodingMs);
        }
        for (const [name, value] of Object.entries(stages))
            add((_f = (_g = row.stages)[name]) !== null && _f !== void 0 ? _f : (_g[name] = timing()), value);
        row.responseBytes += state.responseBytes;
        if (ms >= slowMs || kind !== "complete" || status >= 500) {
            if (slow.length < maxSlowSamples)
                slow.push({ route,
                    requestId: String(request.id).replace(/[^A-Za-z0-9_.:-]/g, "_").slice(0, 64),
                    status: statusKey, ms: +ms.toFixed(1), outcome: state.outcome,
                    stages: Object.fromEntries(Object.entries(stages).map(([key, value]) => [key, +value.toFixed(1)])),
                    responseBytes: state.responseBytes });
            else
                omittedSlowSamples++;
        }
    }
    app.addHook("onRequest", (request, reply, done) => {
        states.set(request, { start: perf_hooks_1.performance.now(), encodingMs: 0, responseBytes: 0 });
        const onClose = () => {
            if (!reply.raw.writableFinished)
                finish(request, reply.statusCode, "aborted");
        };
        reply.raw.once("close", onClose);
        reply.raw.once("finish", () => reply.raw.removeListener("close", onClose));
        done();
    });
    app.addHook("preValidation", (request, _reply, done) => { const s = states.get(request); if (s)
        s.parsed = perf_hooks_1.performance.now(); done(); });
    app.addHook("preSerialization", (request, _reply, payload, done) => {
        const s = states.get(request);
        if (s)
            s.prepared = perf_hooks_1.performance.now();
        done(null, payload);
    });
    app.addHook("onSend", (request, _reply, payload, done) => {
        const s = states.get(request);
        if (s) {
            s.sending = perf_hooks_1.performance.now();
            s.responseBytes = typeof payload === "string" ? Buffer.byteLength(payload) : Buffer.isBuffer(payload) ? payload.length : 0;
        }
        done(null, payload);
    });
    app.addHook("onError", (request, _reply, error, done) => {
        var _a;
        const s = states.get(request);
        if (s && !s.outcome)
            s.outcome = knownErrors.has((_a = error.code) !== null && _a !== void 0 ? _a : "") ? error.code : "unclassified_error";
        done();
    });
    app.addHook("onRequestAbort", (request, done) => { finish(request, 0, "aborted"); done(); });
    app.addHook("onTimeout", (request, _reply, done) => { finish(request, 0, "timeout"); done(); });
    app.addHook("onResponse", (request, reply, done) => { finish(request, reply.statusCode, "complete"); done(); });
    return {
        drain() {
            const snapshot = [...routes].sort(([, a], [, b]) => b.totalMs - a.totalMs);
            const compact = ([route, row]) => (Object.assign(Object.assign({ route }, describe(row)), { statuses: row.statuses, outcomes: row.outcomes, stages: Object.fromEntries(Object.entries(row.stages).map(([key, value]) => [key, describe(value)])), responseBytes: row.responseBytes, aborted: row.aborted, timeouts: row.timeouts }));
            const result = { routes: snapshot, summary: Object.assign(Object.assign({ timestamp: new Date().toISOString() }, describe(total)), { statuses, outcomes, aborted, timeouts, routeCount: routes.size, top: snapshot.slice(0, 12).map(compact), failures: snapshot.filter(([, row]) => row.aborted || row.timeouts || Object.keys(row.statuses).some(code => /^[45]/.test(code)))
                        .sort(([, a], [, b]) => b.n - a.n).slice(0, 12).map(compact), slow, omittedSlowSamples }) };
            routes = new Map();
            total = timing();
            statuses = {};
            outcomes = {};
            aborted = 0;
            timeouts = 0;
            slow = [];
            omittedSlowSamples = 0;
            return result;
        },
    };
}
exports.installRequestDiagnostics = installRequestDiagnostics;
