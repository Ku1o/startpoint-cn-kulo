import type { Database } from "better-sqlite3"
import { multicoreConfig } from "./multicore-config"

function integer(value: string | undefined, fallback: number, min: number, max: number): number {
    if (!value?.trim()) return fallback
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) && parsed >= min && parsed <= max ? parsed : fallback
}

export function sqliteSettings(environment: NodeJS.ProcessEnv = process.env) {
    const multicore = multicoreConfig(environment)
    return {
        // FULL preserves acknowledged commits across power loss. NORMAL is opt-in.
        synchronous: environment.SQLITE_SYNCHRONOUS?.toUpperCase() === "NORMAL" ? "NORMAL" : "FULL",
        cacheKiB: integer(environment.SQLITE_CACHE_KIB, multicore.enabled ? 65536 : 2048, 2048, 262144),
        mmapBytes: integer(environment.SQLITE_MMAP_MIB, multicore.enabled ? 256 : 0, 0, 1024) * 1024 * 1024,
    } as const
}

export function applySqliteSettings(db: Database, readonly = false): void {
    const settings = sqliteSettings()
    db.pragma(`cache_size = -${settings.cacheKiB}`)
    db.pragma(`mmap_size = ${settings.mmapBytes}`)
    if (!readonly) db.pragma(`synchronous = ${settings.synchronous}`)
}
