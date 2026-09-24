import path from "node:path"
import { availableParallelism } from "node:os"
import { Worker } from "node:worker_threads"
import { performance } from "node:perf_hooks"
import { encodeCnResponse, type ResponseEncodingInput, type ResponseEncodingResult } from "./cn-response-encoding"
import { observeWorkerMemory, registerMemoryCounters } from "./memory-diagnostics"
import { recordServerWork } from "./server-work-performance"

interface Job {
    id: number
    input: ResponseEncodingInput
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
    workerPath?: string
}

/** Workers own immutable response data only; they never access SQLite or rooms. */
export class CnResponseWorkerPool {
    private readonly slots: Slot[] = []
    private readonly queue: Job[] = []
    private nextId = 0
    private bytes = 0
    private closed = false
    private cooldownUntil = 0
    private readonly unregister: () => void
    private readonly counters = { completed: 0, failed: 0, rejected: 0, fallback: 0, timeouts: 0 }
    private readonly size: number
    private readonly maxPending: number
    private readonly maxBytes: number
    private readonly timeoutMs: number
    private readonly minimumLength: number

    constructor(private readonly options: ResponseWorkerOptions) {
        this.size = Math.min(4, Math.max(0, Math.trunc(options.size) || 0))
        this.maxPending = Math.max(1, options.maxPending ?? 16)
        this.maxBytes = Math.max(1, options.maxPendingBytes ?? 32 * 1024 * 1024)
        this.timeoutMs = Math.max(1, options.timeoutMs ?? 10_000)
        this.minimumLength = Math.max(0, options.minimumLength ?? 512 * 1024)
        this.unregister = registerMemoryCounters("responseWorkers", () => ({
            ...this.counters, workers: this.slots.length, pending: this.queue.length,
            active: this.slots.filter(slot => slot.job).length, retainedBytes: this.bytes,
            maxPending: this.maxPending, maxBytes: this.maxBytes,
        }))
    }

    snapshot() {
        return { ...this.counters, workers: this.slots.length, pending: this.queue.length,
            active: this.slots.filter(slot => slot.job).length, retainedBytes: this.bytes }
    }

    async encode(input: ResponseEncodingInput): Promise<ResponseEncodingResult> {
        let result: ResponseEncodingResult
        if (!this.closed && this.size > 0 && typeof input.payload === "string"
            && input.payload.length >= this.minimumLength) {
            try { result = await this.submit(input) }
            catch {
                this.counters.fallback++
                result = await encodeCnResponse(input)
            }
        } else result = await encodeCnResponse(input)
        recordServerWork("encode.pack", result.timings.packMs)
        recordServerWork("encode.fix", result.timings.fixMs)
        recordServerWork("encode.base64", result.timings.base64Ms)
        if (input.compression) recordServerWork("encode.compressWait", result.timings.compressWaitMs)
        return result
    }

    private submit(input: ResponseEncodingInput): Promise<ResponseEncodingResult> {
        // UTF-16 retained string plus the in-flight structured-clone copy.
        const bytes = (input.payload as string).length * 4
        const pending = this.queue.length + this.slots.filter(slot => slot.job).length
        if (this.closed || Date.now() < this.cooldownUntil
            || pending >= this.maxPending || this.bytes + bytes > this.maxBytes) {
            this.counters.rejected++
            return Promise.reject(new Error("Response worker capacity unavailable"))
        }
        return new Promise((resolve, reject) => {
            const job: Job = { id: ++this.nextId, input, bytes, queuedAt: performance.now(), startedAt: 0,
                timer: setTimeout(() => this.timeout(job), this.timeoutMs), resolve, reject }
            this.bytes += bytes
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
