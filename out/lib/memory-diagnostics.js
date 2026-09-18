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
var __rest = (this && this.__rest) || function (s, e) {
    var t = {};
    for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
        t[p] = s[p];
    if (s != null && typeof Object.getOwnPropertySymbols === "function")
        for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
            if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i]))
                t[p[i]] = s[p[i]];
        }
    return t;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.installMemoryDiagnostics = exports.collectMemoryDiagnostics = exports.observeWorkerMemory = exports.installWorkerMemoryProbe = exports.registerMemoryCounters = exports.memoryDiagnosticsEnabled = void 0;
const worker_threads_1 = require("worker_threads");
const perf_hooks_1 = require("perf_hooks");
const v8_1 = require("v8");
const providers = new Map();
const workers = new Map();
const installed = new WeakSet();
function memoryDiagnosticsEnabled() {
    var _a;
    return !/^(0|false|no|off)$/i.test((_a = process.env.MEMORY_DIAGNOSTICS) !== null && _a !== void 0 ? _a : "true");
}
exports.memoryDiagnosticsEnabled = memoryDiagnosticsEnabled;
function threadMemory() {
    const _a = process.memoryUsage(), { rss: _rss } = _a, memory = __rest(_a, ["rss"]);
    const heap = (0, v8_1.getHeapStatistics)();
    return Object.assign(Object.assign({}, memory), { totalPhysicalHeap: heap.total_physical_size, mallocedMemory: heap.malloced_memory, nativeContexts: heap.number_of_native_contexts, detachedContexts: heap.number_of_detached_contexts });
}
function registerMemoryCounters(name, read) {
    if (!memoryDiagnosticsEnabled() || (!providers.has(name) && providers.size >= 32))
        return () => { };
    providers.set(name, read);
    return () => { if (providers.get(name) === read)
        providers.delete(name); };
}
exports.registerMemoryCounters = registerMemoryCounters;
function installWorkerMemoryProbe(read) {
    if (worker_threads_1.isMainThread || !memoryDiagnosticsEnabled())
        return;
    worker_threads_1.parentPort === null || worker_threads_1.parentPort === void 0 ? void 0 : worker_threads_1.parentPort.on("message", message => {
        if ((message === null || message === void 0 ? void 0 : message.type) !== "memory_probe")
            return;
        worker_threads_1.parentPort === null || worker_threads_1.parentPort === void 0 ? void 0 : worker_threads_1.parentPort.postMessage({ type: "memory_sample", memory: threadMemory(), counters: read() });
    });
}
exports.installWorkerMemoryProbe = installWorkerMemoryProbe;
function observeWorkerMemory(name, worker) {
    if (!memoryDiagnosticsEnabled() || workers.size >= 16)
        return;
    const state = { name, pending: false, requestedAt: 0, sampledAt: null,
        sample: null, counters: {} };
    workers.set(worker, state);
    const receive = (message) => {
        if ((message === null || message === void 0 ? void 0 : message.type) !== "memory_sample")
            return;
        state.sample = message.memory;
        state.counters = message.counters;
        state.sampledAt = perf_hooks_1.performance.now();
        state.pending = false;
    };
    worker.on("message", receive);
    worker.once("exit", () => { workers.delete(worker); worker.off("message", receive); });
}
exports.observeWorkerMemory = observeWorkerMemory;
/** Constant retained state: one sample and at most one outstanding request per worker. */
function collectMemoryDiagnostics() {
    const now = perf_hooks_1.performance.now();
    const counters = {};
    for (const [name, read] of providers) {
        try {
            counters[name] = read();
        }
        catch (_a) {
            counters[name] = { unavailable: true };
        }
    }
    const workerSamples = [...workers].map(([worker, state]) => {
        const sample = { name: state.name, threadId: worker.threadId,
            ageMs: state.sampledAt === null ? null : Math.round(now - state.sampledAt),
            stale: state.sampledAt === null || now - state.sampledAt > 120000,
            pendingMs: state.pending ? Math.round(now - state.requestedAt) : 0,
            memory: state.sample, counters: state.counters };
        if (!state.pending) {
            try {
                worker.postMessage({ type: "memory_probe" });
                state.pending = true;
                state.requestedAt = now;
            }
            catch ( /* Exiting worker: exit listener removes its sample. */_a) { /* Exiting worker: exit listener removes its sample. */ }
        }
        return sample;
    });
    return { timestamp: new Date().toISOString(), pid: process.pid, uptimeSeconds: Math.floor(process.uptime()),
        rss: process.memoryUsage.rss(), main: threadMemory(), workers: workerSamples, counters };
}
exports.collectMemoryDiagnostics = collectMemoryDiagnostics;
function installMemoryDiagnostics(fastify) {
    if (!memoryDiagnosticsEnabled() || installed.has(fastify))
        return;
    installed.add(fastify);
    const timer = setInterval(() => {
        try {
            console.warn(`[MEM] ${JSON.stringify(collectMemoryDiagnostics())}`);
        }
        catch (_a) {
            console.warn("[MEM] sample unavailable");
        }
    }, 60000);
    timer.unref();
    fastify.addHook("onClose", () => __awaiter(this, void 0, void 0, function* () { clearInterval(timer); installed.delete(fastify); }));
}
exports.installMemoryDiagnostics = installMemoryDiagnostics;
