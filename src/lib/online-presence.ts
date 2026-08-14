const ONLINE_WINDOW_MS = 5 * 60 * 1000
const CLEANUP_INTERVAL_MS = 60 * 1000

const lastSeenByViewerId = new Map<number, number>()
let nextCleanupAt = 0

function normalizeViewerId(value: unknown): number | null {
    if (typeof value !== "number" && typeof value !== "string") return null
    const viewerId = Number(value)
    if (!Number.isSafeInteger(viewerId) || viewerId <= 0) return null
    return viewerId
}

function cleanupExpired(now: number): void {
    const cutoff = now - ONLINE_WINDOW_MS
    for (const [viewerId, lastSeen] of lastSeenByViewerId) {
        if (lastSeen < cutoff) lastSeenByViewerId.delete(viewerId)
    }
    nextCleanupAt = now + CLEANUP_INTERVAL_MS
}

/**
 * Records one player as recently active. This is deliberately memory-only:
 * no SQLite writes, timers, logs, or additional client requests are involved.
 */
export function markPlayerOnline(value: unknown, now = Date.now()): boolean {
    const viewerId = normalizeViewerId(value)
    if (viewerId === null) return false

    lastSeenByViewerId.set(viewerId, now)
    if (now >= nextCleanupAt) cleanupExpired(now)
    return true
}

/** Returns the number of unique players active during the last five minutes. */
export function getOnlinePlayerCount(now = Date.now()): number {
    // The management page only calls this every 30 seconds. Cleaning here keeps
    // the displayed number exact without adding a background timer.
    cleanupExpired(now)
    return lastSeenByViewerId.size
}

export const ONLINE_PLAYER_WINDOW_MS = ONLINE_WINDOW_MS

/** Test helper; not used by runtime code. */
export function clearOnlinePlayers(): void {
    lastSeenByViewerId.clear()
    nextCleanupAt = 0
}
