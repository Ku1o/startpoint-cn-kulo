import type { FastifyInstance } from "fastify"
import { isMainThread, parentPort, Worker } from "worker_threads"
import { performance } from "perf_hooks"
import { getHeapStatistics } from "v8"
import type { Server } from "node:net"
import { ProcessMemoryProbe } from "./process-memory-probe"

type Counters = Record<string, number | boolean | null>
type CounterReader = (detailed: boolean) => Counters
type CounterGroup = "memory" | "sqlite"
type ThreadCpuUsage = { user: number, system: number }
type WorkerCpuSampler = Worker & { cpuUsage?: () => Promise<ThreadCpuUsage> }
const providers = new Map<string, { read: CounterReader, group: CounterGroup }>()
const workers = new Map<Worker, {
    name: string; pending: boolean; requestedAt: number; sampledAt: number | null;
    sample: ReturnType<typeof threadMemory> | null; counters: Counters; diagnostics: Record<string, Counters>;
    cpuPending: boolean; cpuRequestedAt: number; cpuSampledAt: number | null;
    cpuTotal: ThreadCpuUsage | null; cpuDelta: ThreadCpuUsage | null;
}>()
const installed = new WeakSet<FastifyInstance>()
const betterSqlite3Version: string = require("better-sqlite3/package.json").version
const observedServers = new WeakSet<Server>()
let processProbe: ProcessMemoryProbe | null = null
let processCpuTotal: ThreadCpuUsage | null = null
let processCpuSampledAt: number | null = null
let processCpuDelta: ThreadCpuUsage | null = null
let monitorUsers = 0
export function memoryDiagnosticsEnabled(): boolean {
    return !/^(0|false|no|off)$/i.test(process.env.MEMORY_DIAGNOSTICS ?? "true")
}
export function sqliteDiagnosticsEnabled(): boolean {
    return !/^(0|false|no|off)$/i.test(process.env.SQLITE_DIAGNOSTICS ?? "false")
}
export function detailedMemoryDiagnosticsEnabled(): boolean {
    return memoryDiagnosticsEnabled() && /^(1|true|yes|on)$/i.test(process.env.MEMORY_DIAGNOSTICS_DETAIL ?? "false")
}
function samplingEnabled(): boolean { return memoryDiagnosticsEnabled() || sqliteDiagnosticsEnabled() }
function threadMemory(detailed: boolean) {
    const { rss: _rss, ...memory } = process.memoryUsage()
    if (!detailed) return memory
    const heap = getHeapStatistics()
    return { ...memory, totalPhysicalHeap: heap.total_physical_size,
        mallocedMemory: heap.malloced_memory, nativeContexts: heap.number_of_native_contexts,
        detachedContexts: heap.number_of_detached_contexts }
}
export function registerMemoryCounters(name: string, read: CounterReader, group: CounterGroup = "memory"): () => void {
    const enabled = group === "sqlite" ? sqliteDiagnosticsEnabled() : memoryDiagnosticsEnabled()
    if (!enabled || (!providers.has(name) && providers.size >= 32)) return () => {}
    const provider = { read, group }
    providers.set(name, provider)
    return () => { if (providers.get(name) === provider) providers.delete(name) }
}
function readCounters(detailed: boolean): Record<string, Counters> {
    const counters: Record<string, Counters> = {}
    for (const [name, { read, group }] of providers) {
        if (!(group === "sqlite" ? sqliteDiagnosticsEnabled() : memoryDiagnosticsEnabled())) continue
        try { counters[name] = read(detailed) } catch { counters[name] = { unavailable: true } }
    }
    return counters
}
export function installWorkerMemoryProbe(read: CounterReader): void {
    if (isMainThread || !samplingEnabled()) return
    parentPort?.on("message", message => {
        if (message?.type !== "memory_probe") return
        const memory = memoryDiagnosticsEnabled(), detailed = detailedMemoryDiagnosticsEnabled()
        parentPort?.postMessage({ type: "memory_sample", memory: memory ? threadMemory(detailed) : null,
            counters: memory ? read(detailed) : {}, diagnostics: readCounters(detailed) })
    })
}
export function observeWorkerMemory(name: string, worker: Worker): void {
    if (!samplingEnabled() || workers.size >= 16) return
    const state = { name, pending: false, requestedAt: 0, sampledAt: null as number | null,
        sample: null as ReturnType<typeof threadMemory> | null, counters: {} as Counters,
        diagnostics: {} as Record<string, Counters>, cpuPending: false, cpuRequestedAt: 0,
        cpuSampledAt: null as number | null, cpuTotal: null as ThreadCpuUsage | null,
        cpuDelta: null as ThreadCpuUsage | null }
    workers.set(worker, state)
    const receive = (message: any) => {
        if (message?.type !== "memory_sample") return
        state.sample = message.memory
        state.counters = message.counters
        state.diagnostics = message.diagnostics ?? {}
        state.sampledAt = performance.now()
        state.pending = false
    }
    worker.on("message", receive)
    worker.once("exit", () => { workers.delete(worker); worker.off("message", receive) })
}
function sampleWorkerCpu(worker: Worker, state: {
    cpuPending: boolean; cpuRequestedAt: number; cpuSampledAt: number | null;
    cpuTotal: ThreadCpuUsage | null; cpuDelta: ThreadCpuUsage | null;
}): void {
    const cpuUsage = (worker as WorkerCpuSampler).cpuUsage
    if (typeof cpuUsage !== "function" || state.cpuPending) return
    state.cpuPending = true
    state.cpuRequestedAt = performance.now()
    void cpuUsage.call(worker).then(current => {
        const previous = state.cpuTotal
        state.cpuTotal = current
        state.cpuDelta = previous === null ? null : {
            user: Math.max(0, current.user - previous.user),
            system: Math.max(0, current.system - previous.system),
        }
        state.cpuSampledAt = performance.now()
    }).catch(() => {
        // Node versions before 24.6 and workers that are exiting may reject this probe.
        state.cpuDelta = null
    }).finally(() => { state.cpuPending = false })
}
function sampleProcessCpu(): void {
    const current = process.cpuUsage()
    const previous = processCpuTotal
    processCpuTotal = current
    processCpuDelta = previous === null ? null : {
        user: Math.max(0, current.user - previous.user),
        system: Math.max(0, current.system - previous.system),
    }
    processCpuSampledAt = performance.now()
}
export function observeServerConnections(name: string, server: Server): void {
    if (!memoryDiagnosticsEnabled() || observedServers.has(server)) return
    observedServers.add(server)
    let connections: number | null = null, pending = false, closed = false
    let sampledAt: number | null = null
    const unregister = registerMemoryCounters(`connections.${name}`, () => {
        const ageMs = sampledAt === null ? null : Math.round(performance.now() - sampledAt)
        if (!pending && !closed) {
            pending = true
            server.getConnections((error, count) => {
                pending = false
                if (closed) return
                if (error) { connections = null; return }
                connections = count; sampledAt = performance.now()
            })
        }
        return { connections, ageMs, unavailable: connections === null || ageMs === null || ageMs > 120_000 }
    })
    server.once("close", () => { closed = true; unregister(); observedServers.delete(server) })
}
/** Constant retained state: one sample and at most one outstanding request per worker. */
export function collectMemoryDiagnostics() {
    const now = performance.now()
    const memory = memoryDiagnosticsEnabled(), detailed = detailedMemoryDiagnosticsEnabled()
    sampleProcessCpu()
    const counters = readCounters(detailed)
    const workerSamples = [...workers].map(([worker, state]) => {
        sampleWorkerCpu(worker, state)
        const sample = { name: state.name, threadId: worker.threadId,
            ageMs: state.sampledAt === null ? null : Math.round(now - state.sampledAt),
            stale: state.sampledAt === null || now - state.sampledAt > 120_000,
            pendingMs: state.pending ? Math.round(now - state.requestedAt) : 0,
            memory: state.sample, counters: state.counters, diagnostics: state.diagnostics,
            cpu: {
                supported: typeof (worker as WorkerCpuSampler).cpuUsage === "function",
                ageMs: state.cpuSampledAt === null ? null : Math.round(now - state.cpuSampledAt),
                pendingMs: state.cpuPending ? Math.round(now - state.cpuRequestedAt) : 0,
                totalUserUs: state.cpuTotal?.user ?? null,
                totalSystemUs: state.cpuTotal?.system ?? null,
                deltaUserUs: state.cpuDelta?.user ?? null,
                deltaSystemUs: state.cpuDelta?.system ?? null,
            }, }
        if (samplingEnabled() && !state.pending) {
            try {
                worker.postMessage({ type: "memory_probe" })
                state.pending = true
                state.requestedAt = now
            } catch { /* Exiting worker: exit listener removes its sample. */ }
        }
        return sample
    })
    if (detailed) {
        const activeResources: Record<string, number> = Object.create(null)
        let resourceTypes = 0
        for (const type of process.getActiveResourcesInfo()) {
            if (type in activeResources) activeResources[type]++
            else if (resourceTypes < 64) { activeResources[type] = 1; resourceTypes++ }
        }
        counters.activeResources = activeResources
    }
    if (memory) counters.stdio = { stdoutQueuedBytes: process.stdout.writableLength, stderrQueuedBytes: process.stderr.writableLength }
    const osProcess = memory ? processProbe?.snapshot() ?? null : undefined
    if (memory) processProbe?.request()
    return { timestamp: new Date().toISOString(), pid: process.pid, uptimeSeconds: Math.floor(process.uptime()),
        memoryMode: memory ? detailed ? "detailed" : "basic" : "off",
        runtime: { node: process.versions.node, v8: process.versions.v8, betterSqlite3: betterSqlite3Version,
            platform: process.platform, arch: process.arch },
        cpu: {
            ageMs: processCpuSampledAt === null ? null : Math.round(now - processCpuSampledAt),
            totalUserUs: processCpuTotal?.user ?? null,
            totalSystemUs: processCpuTotal?.system ?? null,
            deltaUserUs: processCpuDelta?.user ?? null,
            deltaSystemUs: processCpuDelta?.system ?? null,
        },
        rss: memory ? process.memoryUsage.rss() : undefined, main: memory ? threadMemory(detailed) : undefined,
        osProcess, workers: workerSamples, counters }
}
export function installMemoryDiagnostics(fastify: FastifyInstance): void {
    if (!samplingEnabled() || installed.has(fastify)) return
    installed.add(fastify)
    monitorUsers++
    if (memoryDiagnosticsEnabled() && !processProbe) { processProbe = new ProcessMemoryProbe(); processProbe.request() }
    if (fastify.server) observeServerConnections("http", fastify.server)
    console.warn(`[DIAGNOSTICS] ${JSON.stringify({
        memory: memoryDiagnosticsEnabled() ? detailedMemoryDiagnosticsEnabled() ? "detailed" : "basic" : "off",
        sqlite: sqliteDiagnosticsEnabled(), nativeMemory: processProbe?.enabled ?? false, intervalMs: 60_000,
    })}`)
    const timer = setInterval(() => {
        const tag = memoryDiagnosticsEnabled() ? "MEM" : "SQLITE-PERF"
        try {
            const sample = collectMemoryDiagnostics()
            // SQLite sampling remains usable with memory collection switched off.
            console.warn(`[${tag}] ${JSON.stringify(tag === "MEM" ? sample : {
                timestamp: sample.timestamp, pid: sample.pid, cpu: sample.cpu, counters: sample.counters,
                workers: sample.workers.filter(worker => Object.keys(worker.diagnostics).length > 0).map(worker => ({
                    name: worker.name, threadId: worker.threadId, ageMs: worker.ageMs,
                    stale: worker.stale, pendingMs: worker.pendingMs, diagnostics: worker.diagnostics,
                })),
            })}`)
        }
        catch { console.warn(`[${tag}] sample unavailable`) }
    }, 60_000)
    timer.unref()
    fastify.addHook("onClose", async () => {
        clearInterval(timer); installed.delete(fastify)
        if (--monitorUsers === 0) {
            processProbe?.close(); processProbe = null
            processCpuTotal = null; processCpuSampledAt = null; processCpuDelta = null
        }
    })
}
