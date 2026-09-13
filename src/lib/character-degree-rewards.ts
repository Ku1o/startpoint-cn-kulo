import { readFileSync } from "node:fs"
import path from "node:path"
import { getDb } from "../data/db"
import { grantPlayerDegreeSync } from "../data/domains/degree"
import { getCharacterDataSync, getPracticeQuestSync } from "./assets"
import { QuestCategory } from "./types"
import type { BattleFinishMissionEvent } from "./mission/events"
import {
    CHARACTER_DEGREE_CATALOG,
    isCharacterDegreeActivation,
    isCharacterDegreeEligible,
} from "./character-degree-catalog"

export const CHARACTER_DEGREE_CONFIG_PATH = path.resolve(
    __dirname, "..", "..", "assets", "character_degree_rewards.json",
)

interface RewardOptions {
    /** Isolated verification only; request handlers never supply this option. */
    configPath?: string
}

/** Deploy the matching .108 resources before enabling this configuration. */
export function characterDegreeRewardsEnabled(configPath = CHARACTER_DEGREE_CONFIG_PATH): boolean {
    try {
        const value: unknown = JSON.parse(readFileSync(configPath, "utf8"))
        return isCharacterDegreeActivation(value) && value.enabled
    } catch {
        return false
    }
}

/** Grant both cosmetic variants from persisted ownership, EXP and limit breaks. */
export function grantCharacterDegreeRewardsSync(
    playerId: number,
    characterIds?: readonly number[],
    options: RewardOptions = {},
): number[] {
    if (!Number.isSafeInteger(playerId) || playerId <= 0) return []
    const requested = characterIds === undefined ? null : new Set(characterIds)
    const targets = CHARACTER_DEGREE_CATALOG.filter(entry =>
        requested === null || requested.has(entry.character_id))
    if (targets.length === 0 || !characterDegreeRewardsEnabled(options.configPath)) return []

    const db = getDb()
    if (!db.prepare("SELECT id FROM players WHERE id = ?").get(playerId)) return []
    return db.transaction(() => {
        const newlyGranted: number[] = []
        const owned = db.prepare(`SELECT exp, over_limit_step FROM players_characters
            WHERE player_id = ? AND id = ?`)
        const acquiredAt = Date.now()
        for (const entry of targets) {
            if (getCharacterDataSync(entry.character_id)?.rarity !== 5) continue
            const character = owned.get(playerId, entry.character_id) as
                { exp: number; over_limit_step: number } | undefined
            if (!character || !isCharacterDegreeEligible(character)) continue
            for (const degreeId of entry.degree_ids) {
                // The shared writer supplies acquired_at and preserves duplicate ownership.
                if (grantPlayerDegreeSync(playerId, degreeId, acquiredAt)) newlyGranted.push(degreeId)
            }
        }
        return newlyGranted
    })()
}

/** Backfill the entire owned roster after a successful native single-player practice. */
export function grantPracticeCharacterDegreeRewardsSync(
    event: BattleFinishMissionEvent,
    options: RewardOptions = {},
): number[] {
    if (event.type !== "battle_finish" || event.accomplished !== true
        || event.mode !== "single" || event.questCategory !== QuestCategory.PRACTICE
        || !Number.isSafeInteger(event.questId) || event.questId <= 0
        || getPracticeQuestSync(event.questId) === null) return []
    return grantCharacterDegreeRewardsSync(event.playerId, undefined, options)
}
