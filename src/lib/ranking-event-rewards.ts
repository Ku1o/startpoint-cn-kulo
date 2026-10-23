import nativeRewards from "../../assets/ranking_event_ranking_reward.json"
import { grantEligibleRankingEventDegreesSync, getRankingPlacementSync } from "./activity-degree-rewards"
import { grantPlayerDegreeSync } from "../data/domains/degree"
import { getPlayerSync } from "../data/domains/player"
import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "../data/domains/player-operation-receipt"
import { runPersistenceTransactionSync } from "./persistence-coordinator"
import { givePlayerRewardsSync } from "./quest"
import { Reward, RewardType } from "./types"

interface NativeReward { kind: number; id: number | null; number: number }
interface RankingReward { id: number; maxPercentile: number; rewards: NativeReward[] }
export interface RankingEventRewardSettlement {
    degreeIds: number[]
    rewardResult: ReturnType<typeof givePlayerRewardsSync>
    userInfo?: { free_mana: number; free_vmoney: number; exp_pool: number }
    received: boolean
    replayed?: boolean
}

const OPERATION = "ranking_event_reward"

/** Permanent original-event receipt: publication or a new session cannot pay it again. */
export function claimRankingEventRewardsSync(playerId: number, eventId: number): RankingEventRewardSettlement {
    return runPersistenceTransactionSync({ domain: "event", playerId, operation: OPERATION }, () => {
        const receipt = getPlayerOperationReceiptSync<RankingEventRewardSettlement>(playerId, OPERATION, String(eventId))
        if (receipt) return { ...receipt.response, replayed: true }
        const placement = getRankingPlacementSync(playerId, eventId)
        if (!placement) return { degreeIds: [], rewardResult: null, received: false }
        const definitions = (nativeRewards.events as Record<string, RankingReward[]>)[String(eventId)]
        const definition = definitions?.filter(rule => Number.isSafeInteger(rule.id) && rule.id > 0
            && Number.isFinite(rule.maxPercentile) && rule.maxPercentile > 0 && rule.maxPercentile <= 1
            && placement.percentile <= rule.maxPercentile).sort((left, right) => left.maxPercentile - right.maxPercentile)[0]
        if (!definition) throw new Error("Missing original ranking reward definition.")
        const rewards: Reward[] = [], nativeDegreeIds: number[] = []
        for (const entry of definition.rewards) {
            if (!Number.isSafeInteger(entry.number) || entry.number <= 0) throw new Error("Invalid original ranking reward amount.")
            if ([0, 1, 6, 7].includes(entry.kind) && (!Number.isSafeInteger(entry.id) || entry.id! <= 0)) {
                throw new Error("Invalid original ranking reward identity.")
            }
            switch (entry.kind) {
                case 0: rewards.push({ type: RewardType.ITEM, id: entry.id!, count: entry.number } as Reward); break
                case 1: rewards.push({ type: RewardType.EQUIPMENT, id: entry.id!, count: entry.number } as Reward); break
                case 2: rewards.push({ type: RewardType.BEADS, count: entry.number } as Reward); break
                case 3: rewards.push({ type: RewardType.MANA, count: entry.number } as Reward); break
                case 4: rewards.push({ type: RewardType.EXP, count: entry.number } as Reward); break
                case 6:
                    for (let count = 0; count < entry.number; count++) rewards.push({ type: RewardType.CHARACTER, id: entry.id! })
                    break
                case 7: nativeDegreeIds.push(entry.id!); break
                default: throw new Error("Unsupported original ranking reward kind.")
            }
        }
        // Existing degree repair remains idempotent. A pre-existing title is not
        // evidence that the formerly missing material rewards were ever paid.
        const degreeIds = grantEligibleRankingEventDegreesSync(playerId, eventId)
        for (const id of nativeDegreeIds) if (grantPlayerDegreeSync(playerId, id)) degreeIds.push(id)
        const rewardResult = rewards.length ? givePlayerRewardsSync(playerId, rewards) : null
        const player = getPlayerSync(playerId)
        if (!player) throw new Error("Ranking reward player disappeared.")
        const result: RankingEventRewardSettlement = { degreeIds: [...new Set(degreeIds)], rewardResult,
            userInfo: { free_mana: player.freeMana, free_vmoney: player.freeVmoney, exp_pool: player.expPool }, received: true }
        insertPlayerOperationReceiptSync({ playerId, operation: OPERATION, requestKey: String(eventId), response: result })
        return result
    })
}
