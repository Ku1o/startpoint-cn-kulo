import type { FastifyInstance } from "fastify"
import { isMainThread, parentPort, Worker } from "worker_threads"
import { performance } from "perf_hooks"
import { getHeapStatistics } from "v8"

type Counters = Record<string, number | boolean | null>
const providers = new Map<string, () => Counters>()
const workers = new Map<Worker, {
    name: string; pending: boolean; requestedAt: number; sampledAt: number | null;
    sample: ReturnType<typeof threadMemory> | null; counters: Counters;
}>()
const installed = new WeakSet<FastifyInstance>()
export function memoryDiagnosticsEnabled(): boolean {
    return !/^(0|false|no|off)$/i.test(process.env.MEMORY_DIAGNOSTICS ?? "true")
}
function threadMemory() {
    const { rss: _rss, ...memory } = process.memoryUsage()
    const heap = getHeapStatistics()
    return { ...memory, totalPhysicalHeap: heap.total_physical_size,
        mallocedMemory: heap.malloced_memory, nativeContexts: heap.number_of_native_contexts,
        detachedContexts: heap.number_of_detached_contexts }
}
export function registerMemoryCounters(name: string, read: () => Counters): () => void {
    if (!memoryDiagnosticsEnabled() || (!providers.has(name) && providers.size >= 32)) return () => {}
    providers.set(name, read)
    return () => { if (providers.get(name) === read) providers.delete(name) }
}
export function installWorkerMemoryProbe(read: () => Counters): void {
    if (isMainThread || !memoryDiagnosticsEnabled()) return
    parentPort?.on("message", message => {
        if (message?.type !== "memory_probe") return
        parentPort?.postMessage({ type: "memory_sample", memory: threadMemory(), counters: read() })
    })
}
export function observeWorkerMemory(name: string, worker: Worker): void {
    if (!memoryDiagnosticsEnabled() || workers.size >= 16) return
    const state = { name, pending: false, requestedAt: 0, sampledAt: null as number | null,
        sample: null as ReturnType<typeof threadMemory> | null, counters: {} as Counters }
    workers.set(worker, state)
    const receive = (message: any) => {
        if (message?.type !== "memory_sample") return
        state.sample = message.memory
        state.counters = message.counters
        state.sampledAt = performance.now()
        state.pending = false
    }
    worker.on("message", receive)
    worker.once("exit", () => { workers.delete(worker); worker.off("message", receive) })
}
/** Constant retained state: one sample and at most one outstanding request per worker. */
export function collectMemoryDiagnostics() {
    const now = performance.now()
    const counters: Record<string, Counters> = {}
    for (const [name, read] of providers) {
        try { counters[name] = read() } catch { counters[name] = { unavailable: true } }
    }
    const workerSamples = [...workers].map(([worker, state]) => {
        const sample = { name: state.name, threadId: worker.threadId,
            ageMs: state.sampledAt === null ? null : Math.round(now - state.sampledAt),
            stale: state.sampledAt === null || now - state.sampledAt > 120_000,
            pendingMs: state.pending ? Math.round(now - state.requestedAt) : 0,
            memory: state.sample, counters: state.counters }
        if (!state.pending) {
            try {
                worker.postMessage({ type: "memory_probe" })
                state.pending = true
                state.requestedAt = now
            } catch { /* Exiting worker: exit listener removes its sample. */ }
        }
        return sample
    })
    return { timestamp: new Date().toISOString(), pid: process.pid, uptimeSeconds: Math.floor(process.uptime()),
        rss: process.memoryUsage.rss(), main: threadMemory(), workers: workerSamples, counters }
}
export function installMemoryDiagnostics(fastify: FastifyInstance): void {
    if (!memoryDiagnosticsEnabled() || installed.has(fastify)) return
    installed.add(fastify)
    const timer = setInterval(() => {
        try { console.warn(`[MEM] ${JSON.stringify(collectMemoryDiagnostics())}`) }
        catch { console.warn("[MEM] sample unavailable") }
    }, 60_000)
    timer.unref()
    fastify.addHook("onClose", async () => { clearInterval(timer); installed.delete(fastify) })
}
