import {
    getPlayerCharactersManaNodesSync,
    getPlayerCharactersSync,
} from "../../data/domains/character"
import type { CharacterAwakeUnlockMap } from "../../data/domains/character_awake"
import { buildManaBoardAwakeCharacterList, buildScopedManaBoardAwakeCharacterList } from "../character-helpers"
import { reconcileAwakeUnlocks } from "./awake-unlock"

function mergeManaBoardAwake(...values: unknown[]): Record<number, number> {
    const merged: Record<number, number> = {}

    for (const value of values) {
        if (!value || typeof value !== "object" || Array.isArray(value)) continue

        for (const [boardIndex, awakeLevel] of Object.entries(value)) {
            const index = Number(boardIndex)
            if (!Number.isSafeInteger(index) || index <= 0) continue
            if (typeof awakeLevel !== "number"
                || !Number.isSafeInteger(awakeLevel)
                || awakeLevel < 0) continue
            merged[index] = Math.max(merged[index] ?? 0, awakeLevel)
        }
    }

    return merged
}

export function reconcileAwakeUnlockCharacterList(
    playerId: number,
    existing: Object[]
): Record<string, unknown>[] {
    try {
        const changed = reconcileAwakeUnlocks(playerId).changed
        if (changed.size === 0) return existing as Record<string, unknown>[]

        const updates = buildManaBoardAwakeCharacterList(
            getPlayerCharactersSync(playerId),
            changed,
            getPlayerCharactersManaNodesSync(playerId),
        )
        return mergeAwakeCharacterUpdates(existing, updates)
    } catch (cause) {
        const error = cause instanceof Error
            ? cause
            : new Error("Unknown awake unlock publication error")
        console.error("[awake-unlock] Failed to publish character unlocks.", error)
        return existing as Record<string, unknown>[]
    }
}

/**
 * Re-publishes already-persisted Awake unlocks for the requested characters.
 *
 * Mission progress pages are allowed to be retried after the original unlock
 * response was lost.  Scope the refresh to the page's character IDs so the
 * recovery path never scans every owned character or mana node.
 */
export function refreshAwakeUnlockCharacterList(
    playerId: number,
    existing: Object[],
    unlocks: CharacterAwakeUnlockMap,
    candidateCharacterIds: readonly number[],
): Record<string, unknown>[] {
    const selectedUnlocks: CharacterAwakeUnlockMap = new Map()

    for (const characterId of new Set(candidateCharacterIds)) {
        if (!Number.isSafeInteger(characterId) || characterId <= 0) continue
        const key = String(characterId)
        const awakeLevels = unlocks.get(key)
        if (!awakeLevels) continue
        selectedUnlocks.set(key, awakeLevels)
    }

    if (selectedUnlocks.size === 0) {
        return existing as Record<string, unknown>[]
    }

    const updates = buildScopedManaBoardAwakeCharacterList(playerId, selectedUnlocks)
    return mergeAwakeCharacterUpdates(existing, updates)
}

function mergeAwakeCharacterUpdates(
    existing: Object[],
    updates: Record<string, unknown>[],
): Record<string, unknown>[] {
    const merged: Record<string, unknown>[] = []
    const indexByCharacterId = new Map<string, number>()

    for (const rawEntry of existing) {
        const entry = rawEntry as Record<string, unknown>
        const characterId = entry.character_id
        if (typeof characterId !== "number" && typeof characterId !== "string") {
            merged.push({ ...entry })
            continue
        }

        const key = String(characterId)
        const index = indexByCharacterId.get(key)
        if (index === undefined) {
            indexByCharacterId.set(key, merged.length)
            merged.push({ ...entry })
            continue
        }

        const previous = merged[index]
        merged[index] = {
            ...previous,
            ...entry,
            ...((previous.mana_board_awake !== undefined || entry.mana_board_awake !== undefined) ? {
                mana_board_awake: mergeManaBoardAwake(
                    previous.mana_board_awake,
                    entry.mana_board_awake
                ),
            } : {}),
        }
    }

    for (const update of updates) {
        const key = String(update.character_id)
        const index = indexByCharacterId.get(key)
        if (index === undefined) {
            indexByCharacterId.set(key, merged.length)
            merged.push(update)
            continue
        }

        merged[index] = {
            ...update,
            ...merged[index],
            mana_board_awake: mergeManaBoardAwake(
                merged[index].mana_board_awake,
                update.mana_board_awake
            ),
        }
    }

    return merged
}
