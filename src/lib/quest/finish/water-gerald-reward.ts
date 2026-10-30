import { getDb } from "../../../data/db"
import { givePlayerRewardsSync } from "../../quest"
import { QuestCategory, RewardType } from "../../types"
import type { PlayerRewardResult } from "../../types"

export const WATER_GERALD_CHARACTER_ID = 129989

/** Runs only for a newly settled successful EX30; historical clear flags are irrelevant. */
export function grantWaterGeraldEx30Sync(input: {
    playerId: number; questCategory: number; questId: number; questAccomplished: boolean
    questData: { rushEventId?: number; rushEventFolderId?: number; rushEventRound?: number }
}): PlayerRewardResult | null {
    if (!input.questAccomplished || input.questCategory !== QuestCategory.RUSH_EVENT
        || input.questId !== 700100030 || input.questData.rushEventId !== 700100
        || input.questData.rushEventFolderId !== 1 || input.questData.rushEventRound !== 30) return null
    const db = getDb()
    return db.transaction(() => {
        const claimed = db.prepare(`INSERT OR IGNORE INTO players_water_gerald_claims(player_id,claimed_at)
            VALUES(?,?)`).run(input.playerId, Date.now())
        if (claimed.changes === 0) return null
        const reward = givePlayerRewardsSync(input.playerId, [{ type: RewardType.CHARACTER, id: WATER_GERALD_CHARACTER_ID }])
        if (reward === null || !reward.character_list.some(character =>
            (character as { character_id?: number }).character_id === WATER_GERALD_CHARACTER_ID)) {
            throw new Error("Water Gerald reward could not be granted")
        }
        // The generic grant currently leaves this presentation list empty.
        // Only a newly inserted character carries entry_count; duplicate stack
        // updates must not replay the first-acquisition animation.
        reward.joined_character_id_list = reward.character_list.some(character =>
            (character as { entry_count?: number }).entry_count !== undefined) ? [WATER_GERALD_CHARACTER_ID] : []
        return reward
    })()
}
