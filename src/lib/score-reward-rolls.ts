import { randomInt } from "crypto"
import type { ScoreReward } from "./types"

export const HALLOWEEN_HELL_QUEST_ID = 300097005
export const HALLOWEEN_HELL_SCORE_GROUP_ID = 30009705
export const HALLOWEEN_CANDY_ITEM_ID = 10009701

/** Integer basis points avoid the inclusive, one-percent legacy roll. */
export function rollExactScoreRewardChance(basisPoints: number, roll: number = randomInt(0, 10000)): boolean {
    if (!Number.isSafeInteger(basisPoints) || basisPoints < 0 || basisPoints > 10000
        || !Number.isSafeInteger(roll) || roll < 0 || roll >= 10000) {
        throw new Error("Invalid exact score reward probability or roll")
    }
    return roll < basisPoints
}

/** Keep distinct master row indices so every candy chest is serialized. */
export function selectScoreRewardRows(
    groupId: number,
    rewards: ScoreReward[],
    questId?: number,
    rollBoxCount: () => number = () => randomInt(9, 12),
    accomplished?: boolean,
): ScoreReward[] {
    if (accomplished !== true && rewards.some(row => row.requires_clear)) {
        return rewards.filter(row => !row.requires_clear)
    }
    if (groupId !== HALLOWEEN_HELL_SCORE_GROUP_ID || questId !== HALLOWEEN_HELL_QUEST_ID) return rewards
    const boxes = rewards.filter(row => row.type === 0
        && "reward_type" in row && row.reward_type === 0
        && "id" in row && row.id === HALLOWEEN_CANDY_ITEM_ID)
    if (boxes.length !== 11 || boxes.some(row => !("count" in row) || row.count !== 20)) {
        throw new Error("Halloween hell requires eleven distinct 20-candy chest rows")
    }
    const count = rollBoxCount()
    if (!Number.isSafeInteger(count) || count < 9 || count > 11) {
        throw new Error("Invalid Halloween candy chest count")
    }
    const omitted = new Set(boxes.slice(count))
    return rewards.filter(row => !omitted.has(row))
}
