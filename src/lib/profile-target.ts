import { getPlayerIdByViewerIdSync, getViewerIdByPlayerIdSync } from "../data/domains/follow"

// Compatibility for cached leaderboard responses. New rows use real viewer
// IDs; only old clients may still send this encoded archive-ID namespace.
export const RUSH_PROFILE_ID_BASE = 9_000_000_000

export function toProfileTargetId(playerId: number): number {
    if (!Number.isSafeInteger(playerId) || playerId <= 0
        || !Number.isSafeInteger(RUSH_PROFILE_ID_BASE + playerId)) return 0
    return RUSH_PROFILE_ID_BASE + playerId
}

export function fromProfileTargetId(targetId: number): number | null {
    if (!Number.isSafeInteger(targetId)) return null
    const playerId = targetId - RUSH_PROFILE_ID_BASE
    return playerId > 0 ? playerId : null
}

export function resolveProfileTargetPlayerIdSync(targetId: number): number | null {
    if (!Number.isSafeInteger(targetId) || targetId <= 0) return null
    const legacyPlayerId = fromProfileTargetId(targetId)
    if (legacyPlayerId === null) return getPlayerIdByViewerIdSync(targetId)
    // A legacy profile and its subsequent real-ID follow action must resolve
    // to the same archive. Missing or switched identities are unavailable.
    return getViewerIdByPlayerIdSync(legacyPlayerId) === null ? null : legacyPlayerId
}
