import { givePlayerItemSync as givePlayerItemSyncDefault } from "../../data/domains/item"
import { givePlayerEquipmentSync as givePlayerEquipmentSyncDefault } from "../../lib/equipment"
import {
    FiveBossAdditionalRewardDrop,
    buildFiveBossAdditionalRewardDrops,
    buildFiveBossCursedWeaponDropPlan,
    buildFiveBossSoloGauntletRewardPlan,
    buildFiveBossWeaponAdditionalRewardDrops,
    FIVE_BOSS_SOLO_CURSED_WEAPON_DROP_RATE,
    getFiveBossCursedWeaponPool,
} from "./rewards"

export interface FiveBossSoloRewardResult {
    /** item id -> 发放后的持有总数(直接并进 finish 的 item_list) */
    items: Record<number, number>
    /** 结算页展示用 additional_reward 引用 */
    dropAdditionalRewardIds: FiveBossAdditionalRewardDrop[]
    granted: Array<{ itemId: number, amount: number }>
    /** 命中武器的当前持有状态，按 id 去重后随单人 finish 返回。 */
    equipment_list: Object[]
    /** 命中武器 id 原序列，供 receipt/展示行重放使用。 */
    grantedEquipment: number[]
}

export interface GrantFiveBossSoloRewardsInput {
    playerId: number
    firstClear: boolean
    rewardMultiplier?: 1 | 2
    randomFloat?: () => number
    givePlayerItemSync?: (playerId: number, itemId: number, amount: number) => number
    givePlayerEquipmentSync?: (playerId: number, equipmentId: number, amount: number) => Object
    cursedWeaponPool?: readonly number[]
}

/**
 * 单人打五重决战(2026-09-05 作者:"单人那还是有奖励")的结算发放。
 *
 * 单人 start/finish 走 singleBattleQuest 的普通领主战链路,不经过 five-boss runtime,
 * 按整轮 AUTO 记录决定模式倍率；单人数量型奖励按多人二分之一向上取整，
 * 图纸、心核和诅咒武器本体使用单人专用概率，首通凭证保持固定奖励口径。
 */
export function grantFiveBossSoloRewardsSync(input: GrantFiveBossSoloRewardsInput): FiveBossSoloRewardResult {
    const give = input.givePlayerItemSync ?? givePlayerItemSyncDefault
    const giveEquipment = input.givePlayerEquipmentSync ?? givePlayerEquipmentSyncDefault
    const rewardMultiplier = input.rewardMultiplier ?? 1
    const plan = buildFiveBossSoloGauntletRewardPlan({
        firstClear: input.firstClear,
        rewardMultiplier,
        randomFloat: input.randomFloat,
    })
    const items: Record<number, number> = {}
    const granted: Array<{ itemId: number, amount: number }> = []
    for (const item of plan.items) {
        if (item.amount <= 0) continue
        items[item.itemId] = give(input.playerId, item.itemId, item.amount)
        granted.push({ itemId: item.itemId, amount: item.amount })
    }
    const weaponPlan = buildFiveBossCursedWeaponDropPlan({
        rewardMultiplier,
        dropRate: FIVE_BOSS_SOLO_CURSED_WEAPON_DROP_RATE,
        availableEquipmentIds: input.cursedWeaponPool ?? getFiveBossCursedWeaponPool(),
        randomFloat: input.randomFloat,
    })
    const latestEquipmentStateById = new Map<number, Object>()
    for (const equipmentId of weaponPlan.equipmentIds) {
        latestEquipmentStateById.set(equipmentId, giveEquipment(input.playerId, equipmentId, 1))
    }
    return {
        items,
        dropAdditionalRewardIds: [
            ...buildFiveBossAdditionalRewardDrops(granted),
            ...buildFiveBossWeaponAdditionalRewardDrops(weaponPlan.equipmentIds),
        ],
        granted,
        equipment_list: Array.from(latestEquipmentStateById.values()),
        grantedEquipment: weaponPlan.equipmentIds,
    }
}
