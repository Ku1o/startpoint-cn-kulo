import { existsSync, readdirSync, statSync } from "fs"
import path from "path"

const ZIP_SUMMARY_CACHE_TTL_MS = 15_000
const ZIP_CATALOG_CACHE_TTL_MS = 5_000

export interface ZipArchiveMetadata {
    readonly filename: string
    readonly size: number
}

export interface ZipSummary {
    exists: boolean
    count: number
    latestMtime: string | null
    totalBytes: number
}

type ZipCacheEntry =
    | { readonly kind: "summary", readonly expiresAt: number, readonly summary: ZipSummary }
    | {
        readonly kind: "catalog"
        readonly expiresAt: number
        readonly directoryMtimeMs: number
        readonly archives: readonly ZipArchiveMetadata[]
    }

const zipCache = new Map<string, ZipCacheEntry>()
const cacheKey = (kind: ZipCacheEntry["kind"], directory: string) => (
    `${kind}:${path.resolve(directory)}`
)

export function invalidateZipCache(directory?: string): void {
    if (directory === undefined) {
        zipCache.clear()
        return
    }
    const resolved = path.resolve(directory)
    zipCache.delete(`summary:${resolved}`)
    zipCache.delete(`catalog:${resolved}`)
}

export function invalidateZipSummaryCache(directory?: string): void {
    invalidateZipCache(directory)
}

/** Reads flat ZIP names and sizes; callers build request-specific URLs later. */
export function getZipArchiveMetadata(directory: string): readonly ZipArchiveMetadata[] {
    const resolved = path.resolve(directory)
    const key = cacheKey("catalog", resolved)
    const now = Date.now()
    const directoryMtimeMs = statSync(resolved).mtimeMs
    const cached = zipCache.get(key)
    if (cached?.kind === "catalog"
        && cached.expiresAt > now
        && cached.directoryMtimeMs === directoryMtimeMs) {
        return cached.archives
    }
    const archives = readdirSync(resolved)
        .filter(filename => filename.endsWith(".zip"))
        .map(filename => ({
            filename,
            size: statSync(path.join(resolved, filename)).size,
        }))
    zipCache.set(key, {
        kind: "catalog",
        expiresAt: now + ZIP_CATALOG_CACHE_TTL_MS,
        directoryMtimeMs,
        archives,
    })
    return archives
}

/** Recursively summarizes ZIP files, reusing the result briefly for admin polling. */
export function getZipFileSummary(dir: string): ZipSummary {
    const resolved = path.resolve(dir)
    const key = cacheKey("summary", resolved)
    const now = Date.now()
    const cached = zipCache.get(key)
    if (cached?.kind === "summary" && cached.expiresAt > now) return cached.summary
    if (!existsSync(resolved)) {
        const summary = { exists: false, count: 0, latestMtime: null, totalBytes: 0 }
        zipCache.set(key, { kind: "summary", expiresAt: now + ZIP_SUMMARY_CACHE_TTL_MS, summary })
        return summary
    }
    let count = 0
    let totalBytes = 0
    let latest = 0
    const stack = [resolved]
    while (stack.length) {
        const current = stack.pop()!
        for (const name of readdirSync(current)) {
            const filePath = path.join(current, name)
            const stats = statSync(filePath)
            if (stats.isDirectory()) {
                stack.push(filePath)
                continue
            }
            if (!name.endsWith(".zip")) continue
            count += 1
            totalBytes += stats.size
            latest = Math.max(latest, stats.mtimeMs)
        }
    }
    const summary = {
        exists: true,
        count,
        latestMtime: latest ? new Date(latest).toISOString() : null,
        totalBytes,
    }
    zipCache.set(key, { kind: "summary", expiresAt: now + ZIP_SUMMARY_CACHE_TTL_MS, summary })
    return summary
}
