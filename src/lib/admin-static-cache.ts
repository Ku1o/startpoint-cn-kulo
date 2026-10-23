/** A single bounded admin-only cache; live server metrics never pass through it. */
export function createAdminStaticCache<T>(ttlMs: number, now: () => number = Date.now) {
    let entry: { key: string; source: unknown; expires: number; value: T } | undefined
    return {
        get(key: string, source: unknown, load: () => T): T {
            const time = now()
            if (entry && entry.key === key && entry.source === source && entry.expires > time) return entry.value
            const value = load()
            entry = { key, source, expires: time + ttlMs, value }
            return value
        },
    }
}
