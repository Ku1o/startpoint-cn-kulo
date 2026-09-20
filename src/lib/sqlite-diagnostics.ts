/// <reference lib="es2021.weakref" />
import type { Database } from "better-sqlite3"
import { performance } from "node:perf_hooks"
import { memoryDiagnosticsEnabled, registerMemoryCounters } from "./memory-diagnostics"

const observed = new WeakSet<Database>()

/** Counts all prepare calls on a connection, including callers outside the LRU. */
export function observeSqliteDatabase(db: Database, name: string): void {
    if (!memoryDiagnosticsEnabled() || observed.has(db)) return
    observed.add(db)
    const stats = { prepareCalls: 0, prepareErrors: 0, sampledPrepareCalls: 0,
        sampledPrepareMs: 0, maxSampledPrepareMs: 0 }
    const settings: Record<string, number | boolean | null> = { nativeBytesAvailable: false }
    for (const pragma of ["cache_size", "page_size", "mmap_size", "temp_store"]) {
        try {
            const value = db.pragma(pragma, { simple: true })
            settings[pragma] = typeof value === "number" ? value : null
        } catch { settings[pragma] = null }
    }
    const prepare = db.prepare
    db.prepare = function (this: Database, sql: string) {
        stats.prepareCalls++
        const sampled = stats.prepareCalls % 64 === 1
        const start = sampled ? performance.now() : 0
        try { return prepare.call(this, sql) }
        catch (error) { stats.prepareErrors++; throw error }
        finally {
            if (sampled) {
                const elapsed = performance.now() - start
                stats.sampledPrepareCalls++
                stats.sampledPrepareMs += elapsed
                stats.maxSampledPrepareMs = Math.max(stats.maxSampledPrepareMs, elapsed)
            }
        }
    } as Database["prepare"]
    // Do not keep the connection alive from the process-wide counter registry.
    const reference = new WeakRef(db)
    const unregister = registerMemoryCounters(`sqlite.${name}`, (): Record<string, number | boolean | null> => {
        const connection = reference.deref()
        if (!connection?.open) { unregister(); return { unavailable: true } }
        return { ...settings, ...stats, inTransaction: connection.inTransaction }
    })
}
