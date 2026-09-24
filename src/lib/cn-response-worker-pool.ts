import path from "node:path"
import { availableParallelism } from "node:os"
import { Worker } from "node:worker_threads"
import { performance } from "node:perf_hooks"
import { pack } from "msgpackr"
import { encodeCnResponse, type ResponseEncodingInput, type ResponseEncodingResult } from "./cn-response-encoding"
import { observeWorkerMemory, registerMemoryCounters } from "./memory-diagnostics"
import { recordServerWork } from "./server-work-performance"

interface Job {
    id: number
    input: ResponseEncodingInput
    objectPayload: boolean
    bytes: number
    queuedAt: number
    startedAt: number
    timer: NodeJS.Timeout
    resolve: (result: ResponseEncodingResult) => void
    reject: (error: Error) => void
}

interface Slot { worker: Worker, job?: Job, failed: boolean }

export interface ResponseWorkerOptions {
    size: number
    maxPending?: number
    maxPendingBytes?: number
    timeoutMs?: number
    minimumLength?: number
    minimumObjectBytes?: number
    workerPath?: string
}

/** Workers own response snapshots only; they never access SQLite or rooms. */
export class CnResponseWorkerPool {
    private readonly slots: Slot[] = []
    private readonly queue: Job[] = []
    private nextId = 0
    private bytes = 0
    private closed = false
    private cooldownUntil = 0
    private readonly unregister: () => void
    private readonly counters = { completed: 0, completedObjects: 0, submitted: 0,
        failed: 0, rejected: 0, fallback: 0, timeouts: 0,
        localDisabled: 0, localSmall: 0, localIneligible: 0 }
    private readonly size: number
    private readonly maxPending: number
    private readonly maxBytes: number
    private readonly timeoutMs: number
    private readonly minimumLength: number
    private readonly minimumObjectBytes: number

    constructor(private readonly options: ResponseWorkerOptions) {
        this.size = Math.min(4, Math.max(0, Math.trunc(options.size) || 0))
        this.maxPending = Math.max(1, options.maxPending ?? 16)
        this.maxBytes = Math.max(1, options.maxPendingBytes ?? 32 * 1024 * 1024)
        this.timeoutMs = Math.max(1, options.timeoutMs ?? 10_000)
        this.minimumLength = Math.max(0, options.minimumLength ?? 512 * 1024)
        this.minimumObjectBytes = Math.max(0, options.minimumObjectBytes ?? 32 * 1024)
        this.unregister = registerMemoryCounters("responseWorkers", () => ({
            ...this.counters, workers: this.slots.length, pending: this.queue.length,
            active: this.slots.filter(slot => slot.job).length, retainedBytes: this.bytes,
            maxPending: this.maxPending, maxBytes: this.maxBytes,
            configuredWorkers: this.size, minimumObjectBytes: this.minimumObjectBytes,
        }))
    }

    snapshot() {
        return { ...this.counters, workers: this.slots.length, pending: this.queue.length,
            active: this.slots.filter(slot => slot.job).length, retainedBytes: this.bytes }
    }

    async encode(input: ResponseEncodingInput, options: { offloadObject?: boolean } = {}): Promise<ResponseEncodingResult> {
        let result: ResponseEncodingResult
        const objectPayload = options.offloadObject === true && input.payload !== null && typeof input.payload === "object"
        const eligible = objectPayload || (typeof input.payload === "string" && input.payload.length >= this.minimumLength)
        if (!this.closed && this.size > 0 && eligible) {
            let snapshot: ResponseEncodingInput | undefined
            let packMs = 0
            try {
                // Avoid copying a large load response when the pool is already full.
                this.checkCapacity(0)
                const start = performance.now()
                try {
                    // MessagePack is faster to snapshot than a general object clone,
                    // and preserves the exact wire types (including Buffers/Dates).
                    // msgpackr reuses its buffer: own a copy before the next request.
                    const packedPayload = objectPayload ? Buffer.from(pack(input.payload)) : undefined
                    snapshot = { payload: objectPayload ? undefined : input.payload, packedPayload,
                        ...(input.compression ? { compression: {
                            config: { ...input.compression.config },
                            acceptEncoding: Array.isArray(input.compression.acceptEncoding)
                                ? [...input.compression.acceptEncoding] : input.compression.acceptEncoding,
                        } } : {}) }
                }
                finally { recordServerWork("encode.snapshot", performance.now() - start) }
                packMs = objectPayload ? performance.now() - start : 0
                if (objectPayload && snapshot.packedPayload!.byteLength < this.minimumObjectBytes) {
                    this.counters.localSmall++
                    result = await encodeCnResponse(snapshot)
                } else result = await this.submit(snapshot, objectPayload)
            }
            catch {
                this.counters.fallback++
                // A queued response must keep its send-time values on failure too.
                result = await encodeCnResponse(snapshot ?? input)
            }
            result.timings.packMs += packMs
        } else {
            if (this.closed || this.size === 0) this.counters.localDisabled++
            else if (typeof input.payload === "string") this.counters.localSmall++
            else this.counters.localIneligible++
            result = await encodeCnResponse(input)
        }
        recordServerWork("encode.pack", result.timings.packMs)
        recordServerWork("encode.fix", result.timings.fixMs)
        recordServerWork("encode.base64", result.timings.base64Ms)
        if (input.compression) recordServerWork("encode.compressWait", result.timings.compressWaitMs)
        return result
    }

    private checkCapacity(bytes: number): void {
        const pending = this.queue.length + this.slots.filter(slot => slot.job).length
        if (this.closed || Date.now() < this.cooldownUntil
            || pending >= this.maxPending || this.bytes + bytes > this.maxBytes) {
            this.counters.rejected++
            throw new Error("Response worker capacity unavailable")
        }
    }

    private submit(input: ResponseEncodingInput, objectPayload: boolean): Promise<ResponseEncodingResult> {
        // Budget retained/copy buffers and decoded working data conservatively.
        // This is an input budget, not a measurement of the V8 heap.
        const bytes = input.packedPayload ? input.packedPayload.byteLength * 4 : (input.payload as string).length * 4
        this.checkCapacity(bytes)
        return new Promise((resolve, reject) => {
            const job: Job = { id: ++this.nextId, input, objectPayload, bytes, queuedAt: performance.now(), startedAt: 0,
                timer: setTimeout(() => this.timeout(job), this.timeoutMs), resolve, reject }
            this.bytes += bytes
            this.counters.submitted++
            this.queue.push(job)
            this.dispatch()
        })
    }

    private createSlot(): Slot {
        const worker = new Worker(this.options.workerPath ?? path.join(__dirname, "../workers/cn-response-worker.js"), {
            resourceLimits: { maxOldGenerationSizeMb: 256 },
        })
        const slot: Slot = { worker, failed: false }
        this.slots.push(slot)
        observeWorkerMemory("response-encoder", worker)
        worker.on("message", message => {
            if (message?.type !== "encoded" || slot.failed || message.id !== slot.job?.id) return
            const job = slot.job!
            slot.job = undefined
            this.release(job)
            recordServerWork("encode.workerRoundTrip", performance.now() - job.startedAt)
            worker.unref()
            if (message.error) {
                this.counters.failed++
                job.reject(new Error("Response worker encoding failed"))
            } else {
                this.counters.completed++
                if (job.objectPayload) this.counters.completedObjects++
                const result = message.result as ResponseEncodingResult
                // Structured clone turns Buffers into Uint8Arrays.
                if (typeof result.body !== "string") result.body = Buffer.from(result.body)
                job.resolve(result)
            }
            this.dispatch()
        })
        worker.on("error", () => this.failSlot(slot))
        worker.on("exit", () => this.failSlot(slot))
        worker.unref()
        return slot
    }

    private dispatch(): void {
        if (this.closed) return
        while (this.queue.length > 0) {
            let slot = this.slots.find(candidate => !candidate.job && !candidate.failed)
            if (!slot && this.slots.length < this.size && Date.now() >= this.cooldownUntil) {
                try { slot = this.createSlot() }
                catch { this.cooldownUntil = Date.now() + 30_000; this.rejectQueued(); return }
            }
            if (!slot) return
            const job = this.queue.shift()!
            slot.job = job
            job.startedAt = performance.now()
            recordServerWork("encode.queue", job.startedAt - job.queuedAt)
            slot.worker.ref()
            const start = performance.now()
            try { slot.worker.postMessage({ type: "encode", id: job.id, input: job.input }) }
            catch { this.failSlot(slot) }
            finally { recordServerWork("encode.clone", performance.now() - start) }
        }
    }

    private release(job: Job): void {
        clearTimeout(job.timer)
        this.bytes -= job.bytes
    }

    private rejectQueued(): void {
        for (const job of this.queue.splice(0)) {
            this.release(job)
            job.reject(new Error("Response worker unavailable"))
        }
    }

    private failSlot(slot: Slot): void {
        if (slot.failed) return
        slot.failed = true
        this.counters.failed++
        this.cooldownUntil = Date.now() + 30_000
        this.slots.splice(this.slots.indexOf(slot), 1)
        if (slot.job) {
            this.release(slot.job)
            slot.job.reject(new Error("Response worker stopped"))
            slot.job = undefined
        }
        void slot.worker.terminate()
        // Avoid repeated startup failures and an unbounded queue behind them.
        this.rejectQueued()
    }

    private timeout(job: Job): void {
        this.counters.timeouts++
        const slot = this.slots.find(candidate => candidate.job === job)
        if (slot) { this.failSlot(slot); return }
        const index = this.queue.indexOf(job)
        if (index < 0) return
        this.queue.splice(index, 1)
        this.release(job)
        job.reject(new Error("Response worker queue timed out"))
    }

    async close(): Promise<void> {
        if (this.closed) return
        this.closed = true
        this.unregister()
        this.rejectQueued()
        const slots = [...this.slots]
        for (const slot of slots) {
            slot.failed = true
            if (slot.job) {
                this.release(slot.job)
                slot.job.reject(new Error("Response worker pool closed"))
                slot.job = undefined
            }
        }
        this.slots.length = 0
        await Promise.all(slots.map(slot => slot.worker.terminate()))
    }
}

export function createCnResponseWorkerPool(environment: NodeJS.ProcessEnv = process.env): CnResponseWorkerPool {
    const configured = Number(environment.CN_RESPONSE_WORKERS)
    return new CnResponseWorkerPool({
        size: Number.isFinite(configured) ? configured : Math.min(2, Math.max(0, availableParallelism() - 1)),
    })
}
