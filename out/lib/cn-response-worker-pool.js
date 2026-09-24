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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.createCnResponseWorkerPool = exports.CnResponseWorkerPool = void 0;
const node_path_1 = __importDefault(require("node:path"));
const node_os_1 = require("node:os");
const node_worker_threads_1 = require("node:worker_threads");
const node_perf_hooks_1 = require("node:perf_hooks");
const cn_response_encoding_1 = require("./cn-response-encoding");
const memory_diagnostics_1 = require("./memory-diagnostics");
const server_work_performance_1 = require("./server-work-performance");
/** Workers own immutable response data only; they never access SQLite or rooms. */
class CnResponseWorkerPool {
    constructor(options) {
        var _a, _b, _c, _d;
        this.options = options;
        this.slots = [];
        this.queue = [];
        this.nextId = 0;
        this.bytes = 0;
        this.closed = false;
        this.cooldownUntil = 0;
        this.counters = { completed: 0, failed: 0, rejected: 0, fallback: 0, timeouts: 0 };
        this.size = Math.min(4, Math.max(0, Math.trunc(options.size) || 0));
        this.maxPending = Math.max(1, (_a = options.maxPending) !== null && _a !== void 0 ? _a : 16);
        this.maxBytes = Math.max(1, (_b = options.maxPendingBytes) !== null && _b !== void 0 ? _b : 32 * 1024 * 1024);
        this.timeoutMs = Math.max(1, (_c = options.timeoutMs) !== null && _c !== void 0 ? _c : 10000);
        this.minimumLength = Math.max(0, (_d = options.minimumLength) !== null && _d !== void 0 ? _d : 512 * 1024);
        this.unregister = (0, memory_diagnostics_1.registerMemoryCounters)("responseWorkers", () => (Object.assign(Object.assign({}, this.counters), { workers: this.slots.length, pending: this.queue.length, active: this.slots.filter(slot => slot.job).length, retainedBytes: this.bytes, maxPending: this.maxPending, maxBytes: this.maxBytes })));
    }
    snapshot() {
        return Object.assign(Object.assign({}, this.counters), { workers: this.slots.length, pending: this.queue.length, active: this.slots.filter(slot => slot.job).length, retainedBytes: this.bytes });
    }
    encode(input) {
        return __awaiter(this, void 0, void 0, function* () {
            let result;
            if (!this.closed && this.size > 0 && typeof input.payload === "string"
                && input.payload.length >= this.minimumLength) {
                try {
                    result = yield this.submit(input);
                }
                catch (_a) {
                    this.counters.fallback++;
                    result = yield (0, cn_response_encoding_1.encodeCnResponse)(input);
                }
            }
            else
                result = yield (0, cn_response_encoding_1.encodeCnResponse)(input);
            (0, server_work_performance_1.recordServerWork)("encode.pack", result.timings.packMs);
            (0, server_work_performance_1.recordServerWork)("encode.fix", result.timings.fixMs);
            (0, server_work_performance_1.recordServerWork)("encode.base64", result.timings.base64Ms);
            if (input.compression)
                (0, server_work_performance_1.recordServerWork)("encode.compressWait", result.timings.compressWaitMs);
            return result;
        });
    }
    submit(input) {
        // UTF-16 retained string plus the in-flight structured-clone copy.
        const bytes = input.payload.length * 4;
        const pending = this.queue.length + this.slots.filter(slot => slot.job).length;
        if (this.closed || Date.now() < this.cooldownUntil
            || pending >= this.maxPending || this.bytes + bytes > this.maxBytes) {
            this.counters.rejected++;
            return Promise.reject(new Error("Response worker capacity unavailable"));
        }
        return new Promise((resolve, reject) => {
            const job = { id: ++this.nextId, input, bytes, queuedAt: node_perf_hooks_1.performance.now(), startedAt: 0,
                timer: setTimeout(() => this.timeout(job), this.timeoutMs), resolve, reject };
            this.bytes += bytes;
            this.queue.push(job);
            this.dispatch();
        });
    }
    createSlot() {
        var _a;
        const worker = new node_worker_threads_1.Worker((_a = this.options.workerPath) !== null && _a !== void 0 ? _a : node_path_1.default.join(__dirname, "../workers/cn-response-worker.js"), {
            resourceLimits: { maxOldGenerationSizeMb: 256 },
        });
        const slot = { worker, failed: false };
        this.slots.push(slot);
        (0, memory_diagnostics_1.observeWorkerMemory)("response-encoder", worker);
        worker.on("message", message => {
            var _a;
            if ((message === null || message === void 0 ? void 0 : message.type) !== "encoded" || slot.failed || message.id !== ((_a = slot.job) === null || _a === void 0 ? void 0 : _a.id))
                return;
            const job = slot.job;
            slot.job = undefined;
            this.release(job);
            (0, server_work_performance_1.recordServerWork)("encode.workerRoundTrip", node_perf_hooks_1.performance.now() - job.startedAt);
            worker.unref();
            if (message.error) {
                this.counters.failed++;
                job.reject(new Error("Response worker encoding failed"));
            }
            else {
                this.counters.completed++;
                const result = message.result;
                // Structured clone turns Buffers into Uint8Arrays.
                if (typeof result.body !== "string")
                    result.body = Buffer.from(result.body);
                job.resolve(result);
            }
            this.dispatch();
        });
        worker.on("error", () => this.failSlot(slot));
        worker.on("exit", () => this.failSlot(slot));
        worker.unref();
        return slot;
    }
    dispatch() {
        if (this.closed)
            return;
        while (this.queue.length > 0) {
            let slot = this.slots.find(candidate => !candidate.job && !candidate.failed);
            if (!slot && this.slots.length < this.size && Date.now() >= this.cooldownUntil) {
                try {
                    slot = this.createSlot();
                }
                catch (_a) {
                    this.cooldownUntil = Date.now() + 30000;
                    this.rejectQueued();
                    return;
                }
            }
            if (!slot)
                return;
            const job = this.queue.shift();
            slot.job = job;
            job.startedAt = node_perf_hooks_1.performance.now();
            (0, server_work_performance_1.recordServerWork)("encode.queue", job.startedAt - job.queuedAt);
            slot.worker.ref();
            const start = node_perf_hooks_1.performance.now();
            try {
                slot.worker.postMessage({ type: "encode", id: job.id, input: job.input });
            }
            catch (_b) {
                this.failSlot(slot);
            }
            finally {
                (0, server_work_performance_1.recordServerWork)("encode.clone", node_perf_hooks_1.performance.now() - start);
            }
        }
    }
    release(job) {
        clearTimeout(job.timer);
        this.bytes -= job.bytes;
    }
    rejectQueued() {
        for (const job of this.queue.splice(0)) {
            this.release(job);
            job.reject(new Error("Response worker unavailable"));
        }
    }
    failSlot(slot) {
        if (slot.failed)
            return;
        slot.failed = true;
        this.counters.failed++;
        this.cooldownUntil = Date.now() + 30000;
        this.slots.splice(this.slots.indexOf(slot), 1);
        if (slot.job) {
            this.release(slot.job);
            slot.job.reject(new Error("Response worker stopped"));
            slot.job = undefined;
        }
        void slot.worker.terminate();
        // Avoid repeated startup failures and an unbounded queue behind them.
        this.rejectQueued();
    }
    timeout(job) {
        this.counters.timeouts++;
        const slot = this.slots.find(candidate => candidate.job === job);
        if (slot) {
            this.failSlot(slot);
            return;
        }
        const index = this.queue.indexOf(job);
        if (index < 0)
            return;
        this.queue.splice(index, 1);
        this.release(job);
        job.reject(new Error("Response worker queue timed out"));
    }
    close() {
        return __awaiter(this, void 0, void 0, function* () {
            if (this.closed)
                return;
            this.closed = true;
            this.unregister();
            this.rejectQueued();
            const slots = [...this.slots];
            for (const slot of slots) {
                slot.failed = true;
                if (slot.job) {
                    this.release(slot.job);
                    slot.job.reject(new Error("Response worker pool closed"));
                    slot.job = undefined;
                }
            }
            this.slots.length = 0;
            yield Promise.all(slots.map(slot => slot.worker.terminate()));
        });
    }
}
exports.CnResponseWorkerPool = CnResponseWorkerPool;
function createCnResponseWorkerPool(environment = process.env) {
    const configured = Number(environment.CN_RESPONSE_WORKERS);
    return new CnResponseWorkerPool({
        size: Number.isFinite(configured) ? configured : Math.min(2, Math.max(0, (0, node_os_1.availableParallelism)() - 1)),
    });
}
exports.createCnResponseWorkerPool = createCnResponseWorkerPool;
