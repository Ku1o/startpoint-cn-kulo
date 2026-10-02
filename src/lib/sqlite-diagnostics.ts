/// <reference lib="es2021.weakref" />
import type { Database } from "better-sqlite3"
import { performance } from "node:perf_hooks"
import { sqliteDiagnosticsEnabled, registerMemoryCounters } from "./memory-diagnostics"

const observed = new WeakSet<Database>()

/** Counts all prepare calls on a connection, including callers outside the LRU. */
export function observeSqliteDatabase(db: Database, name: string): void {
    if (!sqliteDiagnosticsEnabled() || observed.has(db)) return
    observed.add(db)
    const stats = { prepareCalls: 0, prepareErrors: 0, sampledPrepareCalls: 0,
        sampledPrepareMs: 0, maxSampledPrepareMs: 0,
        executeCalls: 0, executeErrors: 0, busyErrors: 0, sampledExecuteCalls: 0,
        sampledExecuteMs: 0, maxSampledExecuteMs: 0 }
    const readSettings = (): Record<string, number | boolean | null> => {
        const settings: Record<string, number | boolean | null> = { nativeBytesAvailable: false }
        for (const pragma of ["cache_size", "page_size", "mmap_size", "temp_store", "busy_timeout", "synchronous", "wal_autocheckpoint"]) {
            try {
                const value = db.pragma(pragma, { simple: true })
                settings[pragma] = typeof value === "number" ? value : null
            } catch { settings[pragma] = null }
        }
        return settings
    }
    const prepare = db.prepare
    db.prepare = function (this: Database, sql: string) {
        stats.prepareCalls++
        const sampled = stats.prepareCalls % 64 === 1
        const start = sampled ? performance.now() : 0
        try {
            const statement = prepare.call(this, sql)
            const methods = statement as unknown as Record<"get" | "all" | "run", (...args: unknown[]) => unknown>
            for (const method of ["get", "all", "run"] as const) {
                const execute = methods[method]
                methods[method] = function (this: typeof statement, ...args: unknown[]) {
                    stats.executeCalls++
                    const sampled = stats.executeCalls % 64 === 1
                    const start = sampled ? performance.now() : 0
                    try { return execute.apply(this, args) }
                    catch (error) {
                        stats.executeErrors++
                        if (String((error as { code?: string })?.code).startsWith("SQLITE_BUSY")) stats.busyErrors++
                        throw error
                    } finally {
                        if (sampled) {
                            const elapsed = performance.now() - start
                            stats.sampledExecuteCalls++
                            stats.sampledExecuteMs += elapsed
                            stats.maxSampledExecuteMs = Math.max(stats.maxSampledExecuteMs, elapsed)
                        }
                    }
                }
            }
            return statement
        }
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
        return { ...readSettings(), ...stats, inTransaction: connection.inTransaction }
    }, "sqlite")
}
