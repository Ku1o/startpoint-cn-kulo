import { givePlayerItemSync as givePlayerItemSyncDefault } from "../../data/domains/item"
import {
    FiveBossAdditionalRewardDrop,
    buildFiveBossAdditionalRewardDrops,
    buildFiveBossGauntletRewardPlan,
} from "./rewards"

export interface FiveBossSoloRewardResult {
    /** item id -> 发放后的持有总数(直接并进 finish 的 item_list) */
    items: Record<number, number>
    /** 结算页展示用 additional_reward 引用 */
    dropAdditionalRewardIds: FiveBossAdditionalRewardDrop[]
    granted: Array<{ itemId: number, amount: number }>
}

export interface GrantFiveBossSoloRewardsInput {
    playerId: number
    firstClear: boolean
    rewardMultiplier?: 1 | 2
    randomFloat?: () => number
    givePlayerItemSync?: (playerId: number, itemId: number, amount: number) => number
}

/**
 * 单人打五重决战(2026-09-05 作者:"单人那还是有奖励")的结算发放。
 *
 * 单人 start/finish 走 singleBattleQuest 的普通领主战链路,不经过 five-boss runtime,
 * 按整轮 AUTO 记录决定模式材料倍率；图纸和首通凭证仍遵循固定奖励口径。
 */
export function grantFiveBossSoloRewardsSync(input: GrantFiveBossSoloRewardsInput): FiveBossSoloRewardResult {
    const give = input.givePlayerItemSync ?? givePlayerItemSyncDefault
    const plan = buildFiveBossGauntletRewardPlan({
        firstClear: input.firstClear,
        rewardMultiplier: input.rewardMultiplier ?? 1,
        randomFloat: input.randomFloat,
    })
    const items: Record<number, number> = {}
    const granted: Array<{ itemId: number, amount: number }> = []
    for (const item of plan.items) {
        if (item.amount <= 0) continue
        items[item.itemId] = give(input.playerId, item.itemId, item.amount)
        granted.push({ itemId: item.itemId, amount: item.amount })
    }
    return {
        items,
        dropAdditionalRewardIds: buildFiveBossAdditionalRewardDrops(granted),
        granted,
    }
}
