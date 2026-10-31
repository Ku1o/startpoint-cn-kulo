import type { ContentOperationsSnapshot, ContentOperationsStore } from "./content-operations-store"

interface CachedSnapshot {
    store: ContentOperationsStore
    computedAtMs: number
    validUntilMs: number
    snapshot: ContentOperationsSnapshot
}
let cached: CachedSnapshot | null = null

function freezeSnapshot(value: unknown): void {
    if (!value || typeof value !== "object" || Object.isFrozen(value)) return
    Object.freeze(value)
    for (const child of Object.values(value)) freezeSnapshot(child)
}

function nextDeadline(snapshot: ContentOperationsSnapshot, nowMs: number): number {
    let next = Infinity
    for (const state of snapshot.states) {
        const actions = state.actions
        if (!actions || typeof actions !== "object") continue
        for (const action of Object.values(actions as Record<string, { ends_at_ms?: unknown }>)) {
            const end = action?.ends_at_ms
            if (typeof end === "number" && end >= nowMs && end < next) next = end
        }
    }
    return next
}

/** Production wire responses only. Definitions are captured by the store at startup;
 * supported content writes advance its revision. Business authorization continues
 * to read fresh state through the store, never through this response cache.
 * Nested response data is shared read-only; callers own only the returned root.
 */
export function cachedContentOperationsSnapshot(store: ContentOperationsStore, nowMs: number): ContentOperationsSnapshot {
    if (store.db.inTransaction || !Number.isFinite(nowMs)) return store.snapshot(nowMs)
    let entry = cached
    if (!entry || entry.store !== store || nowMs < entry.computedAtMs || nowMs > entry.validUntilMs
        || store.revision() !== entry.snapshot.revision) {
        // Clone once on rebuild: capability lists can be borrowed from the store.
        // Freezing the wire copy must not freeze the original mutable interfaces.
        const snapshot = structuredClone(store.snapshot(nowMs))
        freezeSnapshot(snapshot)
        entry = { store, computedAtMs: nowMs, validUntilMs: nextDeadline(snapshot, nowMs), snapshot }
        cached = entry
    }
    // Expiry is inclusive in stateAllows; rebuild on the first request after it.
    return { ...entry.snapshot, server_time_ms: nowMs }
}

export function contentOperationsSnapshot(nowMs = Date.now()): ContentOperationsSnapshot {
    const { contentOperations } = require("./content-operations") as { contentOperations(): ContentOperationsStore }
    return cachedContentOperationsSnapshot(contentOperations(), nowMs)
}

/** Release the retained response in isolated tests/tools. */
export function clearContentOperationsSnapshotCache(): void {
    cached = null
}
