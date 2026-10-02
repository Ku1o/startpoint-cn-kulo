import { resolvePlayerIdSync } from "../data/activeAccount"
import { getPlayerSync } from "../data/domains/player"
import { getSession } from "../data/domains/session"
import type { Player } from "../data/types"
import { registerMemoryCounters } from "../lib/memory-diagnostics"

export interface MultiPlayerContext {
    playerId: number
    player: Player
}

export interface MultiPlayerContextDependencies {
    getSession: (viewerId: string) => Promise<{ accountId: number } | null>
    resolvePlayerIdSync: (accountId: number) => number | null
    getPlayerSync: (playerId: number) => Player | null
}

interface ContextCacheEntry {
    context: MultiPlayerContext
    expiresAt: number
}

const CONTEXT_CACHE_TTL_MS = Math.max(
    5_000,
    Number.parseInt(process.env.MULTI_CONTEXT_CACHE_TTL_MS ?? "10000", 10) || 10_000,
)
const CONTEXT_CACHE_MAX_ENTRIES = Math.max(
    100,
    Number.parseInt(process.env.MULTI_CONTEXT_CACHE_MAX_ENTRIES ?? "1000", 10) || 1_000,
)
const contextCache = new Map<number, ContextCacheEntry>()
let contextCacheHits = 0
let contextCacheMisses = 0

registerMemoryCounters("multiPlayerContext", _detailed => ({
    entries: contextCache.size,
    hits: contextCacheHits,
    misses: contextCacheMisses,
    ttlMs: CONTEXT_CACHE_TTL_MS,
    maxEntries: CONTEXT_CACHE_MAX_ENTRIES,
}))

function readCachedContext(viewerId: number): MultiPlayerContext | null {
    const entry = contextCache.get(viewerId)
    if (!entry) return null
    if (entry.expiresAt <= Date.now()) {
        contextCache.delete(viewerId)
        return null
    }
    contextCacheHits++
    return entry.context
}

/** Cache only after an HTTP route has authenticated the viewer. */
export function cacheMultiPlayerContext(viewerId: number, context: MultiPlayerContext): void {
    if (!Number.isSafeInteger(viewerId) || viewerId <= 0) return
    if (!contextCache.has(viewerId) && contextCache.size >= CONTEXT_CACHE_MAX_ENTRIES) {
        const oldest = contextCache.keys().next().value
        if (Number.isSafeInteger(oldest)) contextCache.delete(oldest)
    }
    contextCache.set(viewerId, { context, expiresAt: Date.now() + CONTEXT_CACHE_TTL_MS })
}

export function getCachedMultiPlayerContext(viewerId: number): MultiPlayerContext | null {
    return readCachedContext(viewerId)
}

export function invalidateMultiPlayerContext(viewerId: number): void {
    contextCache.delete(viewerId)
}

/** Resolve a multiplayer viewer token to that account's selected save. */
export async function resolveMultiPlayerContext(
    viewerId: number,
    dependencies: Partial<MultiPlayerContextDependencies> = {},
): Promise<MultiPlayerContext | null> {
    if (!Number.isSafeInteger(viewerId) || viewerId <= 0) return null

    const session = await (dependencies.getSession ?? getSession)(String(viewerId))
    if (!session) return null

    const playerId = (dependencies.resolvePlayerIdSync ?? resolvePlayerIdSync)(session.accountId)
    if (!playerId) return null

    const player = (dependencies.getPlayerSync ?? getPlayerSync)(playerId)
    if (!player) return null

    const context = { playerId, player }
    contextCacheMisses++
    return context
}
