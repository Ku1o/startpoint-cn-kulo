import { getDb } from "../data/db"
import { getRaidQuestCount, getRaidQuestCounts } from "./raid-event-counts"
import { runPersistenceTransactionSync } from "./persistence-coordinator"
import { cachedStatement } from "./cached-statement"
import { givePlayerRewardsSync } from "./quest"
import { Reward, RewardType } from "./types"
import nativeOverallRewards from "../../assets/raid_event_overall_reward.json"
import {
    getRaidEventIdForQuest,
    getRaidEventProgressRule,
    isSupportedRaidEventId,
    RAID_EVENT_CALCULATION_VERSION,
} from "./raid-event-config"

export interface RaidEventRewardEntry {
    kind: number
    kind_id: number | null
    number: number
}

export interface RaidEventRewardClaimResult {
    receivedUpTo: number
    rewardList: RaidEventRewardEntry[]
    rewardResult: ReturnType<typeof givePlayerRewardsSync>
}

interface OverallReward {
    threshold: number
    rewards: RaidEventRewardEntry[]
}

// event/raid/summary uses the remote reward-kind numbering consumed by
// RaidEventLogic.rewardListToGeneralRewardKinds, not the 0-based kind values
// stored in raid_event_overall_reward.orderedmap.
enum RaidEventResponseRewardKind {
    ITEM = 1,
    FREE_STONE = 3,
    CHARACTER = 5,
    EQUIPMENT = 6,
    MANA = 8,
    POOLED_EXP = 9,
}

export interface RaidEventGlobalBoss {
    hpPercentage: number
    totalKillCount: number
    weightedKillCount: number
    requiredKillCount: number
}

// Raid event 7 (Battle Banquet) total-kill rewards. The 300-kill special
// reward is customized to Abyss ten-pull tickets x25 (250 pulls).
const BATTLE_BANQUET_TOTAL_REWARDS: OverallReward[] = [
    {
        threshold: 50,
        rewards: [
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 49100, number: 10 },
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 10003, number: 1 },
        ],
    },
    {
        threshold: 100,
        rewards: [
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 49100, number: 10 },
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 14040, number: 1 },
        ],
    },
    {
        threshold: 150,
        rewards: [
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 49100, number: 15 },
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 14040, number: 1 },
        ],
    },
    {
        threshold: 200,
        rewards: [
            { kind: RaidEventResponseRewardKind.FREE_STONE, kind_id: null, number: 600 },
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 14040, number: 1 },
        ],
    },
    {
        threshold: 250,
        rewards: [
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 49100, number: 20 },
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 12002, number: 1 },
        ],
    },
    {
        threshold: 300,
        rewards: [
            { kind: RaidEventResponseRewardKind.FREE_STONE, kind_id: null, number: 2000 },
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 999014, number: 25 },
        ],
    },
]

function getBattleBanquetRewardsBetween(
    previousCount: number,
    currentCount: number,
): RaidEventRewardEntry[] {
    const rewards: RaidEventRewardEntry[] = []
    const newKillCount = Math.max(0, currentCount - previousCount)

    // Official repeat reward: every kill grants Mana x500 and item 100000 x25.
    if (newKillCount > 0) {
        rewards.push(
            { kind: RaidEventResponseRewardKind.MANA, kind_id: null, number: 500 * newKillCount },
            { kind: RaidEventResponseRewardKind.ITEM, kind_id: 100000, number: 25 * newKillCount },
        )
    }

    for (const reward of BATTLE_BANQUET_TOTAL_REWARDS) {
        if (reward.threshold > previousCount && reward.threshold <= currentCount) {
            rewards.push(...reward.rewards)
        }
    }

    // Official repeat reward after 300: Star Stones x300 at 400, 500, 600, ...
    let repeatedStoneRewards = 0
    for (let threshold = 400; threshold <= currentCount; threshold += 100) {
        if (threshold > previousCount) repeatedStoneRewards++
    }
    if (repeatedStoneRewards > 0) {
        rewards.push({
            kind: RaidEventResponseRewardKind.FREE_STONE,
            kind_id: null,
            number: 300 * repeatedStoneRewards,
        })
    }

    return rewards
}

/** The original master stores Option.None as a literal string, never zero. */
function originalInteger(value: unknown): number | null {
    if (value === "(None)" || value === "") return null
    if (typeof value !== "string" || !/^\d+$/.test(value)) throw new Error("Invalid original Raid reward integer.")
    const parsed = Number(value)
    if (!Number.isSafeInteger(parsed)) throw new Error("Invalid original Raid reward integer.")
    return parsed
}

export function getRaidEventOverallRewardsBetween(eventId: number, previous: number, current: number): RaidEventRewardEntry[] {
    if (!Number.isSafeInteger(previous) || previous < 0 || !Number.isSafeInteger(current) || current < previous) {
        throw new Error("Invalid Raid reward count.")
    }
    // Preserve the adopted event 7 payouts and its already received cursor.
    if (eventId === 7) return getBattleBanquetRewardsBetween(previous, current)
    const rows = Object.values(nativeOverallRewards.rows as Record<string, string[][]>)
        .map(value => value[0]).filter(row => row?.[0] === String(eventId))
    if (!isSupportedRaidEventId(eventId) || rows.length === 0) throw new Error("Missing original Raid overall rewards.")
    const result: RaidEventRewardEntry[] = []
    for (const row of rows) {
        const target = originalInteger(row[3]), interval = originalInteger(row[4])
        let times: number
        if (row[2] === "0") {
            if (target === null || target <= 0) throw new Error("Invalid original Raid total-kill requirement.")
            times = previous < target && target <= current ? 1 : 0
        } else if (row[2] === "1") {
            if (interval === null || interval <= 0 || (target !== null && target <= 0)) throw new Error("Invalid original Raid each-kill requirement.")
            // None is the per-kill reward description, not a cumulative target.
            // Count actual communal boss kills, just as event 7 does; quest
            // weights affect boss progress and never multiply this payment.
            const count = (value: number) => target === null ? Math.floor(value / interval)
                : value < target ? 0 : Math.floor((value - target) / interval) + 1
            times = count(current) - count(previous)
        } else throw new Error("Unsupported original Raid reward requirement.")
        if (times === 0) continue
        for (let index = 7; index + 2 < row.length; index += 3) {
            const kind = originalInteger(row[index]), number = originalInteger(row[index + 2])
            if (kind === null || number === null) continue
            const amount = number * times
            if (!Number.isSafeInteger(amount) || amount <= 0) throw new Error("Invalid original Raid reward amount.")
            const id = originalInteger(row[index + 1])
            switch (kind) {
                case 0:
                    if (id === null || id <= 0) throw new Error("Invalid original Raid item reward.")
                    result.push({ kind: RaidEventResponseRewardKind.ITEM, kind_id: id, number: amount }); break
                case 2: result.push({ kind: RaidEventResponseRewardKind.FREE_STONE, kind_id: null, number: amount }); break
                case 3: result.push({ kind: RaidEventResponseRewardKind.MANA, kind_id: null, number: amount }); break
                default: throw new Error("Unsupported original Raid overall reward kind.")
            }
        }
    }
    return result
}

function aggregateRewards(rewards: RaidEventRewardEntry[]): RaidEventRewardEntry[] {
    const aggregated = new Map<string, RaidEventRewardEntry>()
    for (const reward of rewards) {
        const key = `${reward.kind}:${reward.kind_id ?? ""}`
        const existing = aggregated.get(key)
        if (existing) {
            existing.number += reward.number
        } else {
            aggregated.set(key, { ...reward })
        }
    }
    return [...aggregated.values()]
}

function applyRewardEntriesSync(
    playerId: number,
    entries: RaidEventRewardEntry[],
): ReturnType<typeof givePlayerRewardsSync> {
    const ordinaryRewards: Reward[] = []
    for (const entry of entries) {
        switch (entry.kind) {
            case RaidEventResponseRewardKind.ITEM:
                if (entry.kind_id !== null) {
                    ordinaryRewards.push({
                        type: RewardType.ITEM,
                        id: entry.kind_id,
                        count: entry.number,
                    } as Reward)
                }
                break
            case RaidEventResponseRewardKind.EQUIPMENT:
                if (entry.kind_id !== null) {
                    ordinaryRewards.push({
                        type: RewardType.EQUIPMENT,
                        id: entry.kind_id,
                        count: entry.number,
                    } as Reward)
                }
                break
            case RaidEventResponseRewardKind.FREE_STONE:
                ordinaryRewards.push({
                    type: RewardType.BEADS,
                    count: entry.number,
                } as Reward)
                break
            case RaidEventResponseRewardKind.MANA:
                ordinaryRewards.push({
                    type: RewardType.MANA,
                    count: entry.number,
                } as Reward)
                break
            case RaidEventResponseRewardKind.POOLED_EXP:
                ordinaryRewards.push({
                    type: RewardType.EXP,
                    count: entry.number,
                } as Reward)
                break
            case RaidEventResponseRewardKind.CHARACTER:
                if (entry.kind_id !== null) {
                    for (let i = 0; i < entry.number; i++) {
                        ordinaryRewards.push({
                            type: RewardType.CHARACTER,
                            id: entry.kind_id,
                        })
                    }
                }
                break
        }
    }
    return ordinaryRewards.length > 0
        ? givePlayerRewardsSync(playerId, ordinaryRewards)
        : null
}

function calculateHpPercentage(weightedKillCount: number, requiredKillCount: number): number {
    if (requiredKillCount <= 0) return 100
    const ratio = Math.max(0, Math.min(1, weightedKillCount / requiredKillCount))
    return Math.ceil((1 - ratio) * 1000) / 10
}

function rebuildRaidEventGlobalStateSync(eventId: number): RaidEventGlobalBoss {
    const rule = getRaidEventProgressRule(eventId)
    const rows = cachedStatement(getDb(), `
        SELECT quest_id
        FROM raid_event_global_kill_ledger
        WHERE event_id = ?
        ORDER BY created_at, rowid
    `).all(eventId) as { quest_id: number }[]

    let weightedKillCount = 0
    let totalKillCount = 0
    for (const row of rows) {
        const questWeight = rule.questWeights[row.quest_id] ?? 0
        weightedKillCount += questWeight
        if (weightedKillCount >= rule.requiredKillCount) {
            weightedKillCount = 0
            totalKillCount++
        }
    }

    cachedStatement(getDb(), `
        INSERT INTO raid_event_global_state
            (
                event_id,
                total_kill_count,
                weighted_kill_count,
                calculation_version,
                updated_at
            )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            total_kill_count = excluded.total_kill_count,
            weighted_kill_count = excluded.weighted_kill_count,
            calculation_version = excluded.calculation_version,
            updated_at = excluded.updated_at
    `).run(
        eventId,
        totalKillCount,
        weightedKillCount,
        RAID_EVENT_CALCULATION_VERSION,
        Date.now(),
    )

    return {
        hpPercentage: calculateHpPercentage(weightedKillCount, rule.requiredKillCount),
        totalKillCount,
        weightedKillCount,
        requiredKillCount: rule.requiredKillCount,
    }
}

export function getRaidEventGlobalBossSync(eventId: number): RaidEventGlobalBoss {
    const rule = getRaidEventProgressRule(eventId)
    const row = cachedStatement(getDb(), `
        SELECT total_kill_count, weighted_kill_count, calculation_version
        FROM raid_event_global_state
        WHERE event_id = ?
    `).get(eventId) as {
        total_kill_count: number
        weighted_kill_count: number
        calculation_version: number
    } | undefined

    if (row && row.calculation_version >= RAID_EVENT_CALCULATION_VERSION) {
        return {
            hpPercentage: calculateHpPercentage(
                row.weighted_kill_count,
                rule.requiredKillCount,
            ),
            totalKillCount: row.total_kill_count,
            weightedKillCount: row.weighted_kill_count,
            requiredKillCount: rule.requiredKillCount,
        }
    }

    const hasLedger = cachedStatement(getDb(), `
        SELECT 1
        FROM raid_event_global_kill_ledger
        WHERE event_id = ?
        LIMIT 1
    `).get(eventId)
    if (row || hasLedger) return rebuildRaidEventGlobalStateSync(eventId)

    return {
        hpPercentage: 100,
        totalKillCount: 0,
        weightedKillCount: 0,
        requiredKillCount: rule.requiredKillCount,
    }
}

export function getRaidEventGlobalKillCountSync(eventId: number): number {
    return getRaidEventGlobalBossSync(eventId).totalKillCount
}

export function getRaidEventQuestKillCountsSync(eventId: number): Record<string, { kill_count: number }> {
    return getRaidQuestCounts(getDb(), eventId)
}

export function getRaidEventQuestKillCountSync(eventId: number, questId: number): number {
    return getRaidQuestCount(getDb(), eventId, questId)
}

export function recordRaidEventClearSync(params: {
    eventId: number
    playId: string
    playerId: number
    questId: number
}): {
    counted: boolean
    questWeight: number
    questKillCount: number
    boss: RaidEventGlobalBoss
} {
    const { eventId, playId, playerId, questId } = params
    const supportedEvent = isSupportedRaidEventId(eventId)
    const questMatchesEvent = supportedEvent && getRaidEventIdForQuest(questId) === eventId
    if (!supportedEvent || !questMatchesEvent || !playId) {
        return {
            counted: false,
            questWeight: 0,
            questKillCount: 0,
            boss: {
                hpPercentage: 100,
                totalKillCount: 0,
                weightedKillCount: 0,
                requiredKillCount: supportedEvent
                    ? getRaidEventProgressRule(eventId).requiredKillCount
                    : 0,
            },
        }
    }

    return runPersistenceTransactionSync({
        domain: "event", playerId, operation: "record_raid_event_clear",
    }, () => {
        const currentBoss = getRaidEventGlobalBossSync(eventId)
        const rule = getRaidEventProgressRule(eventId)
        const questWeight = rule.questWeights[questId] ?? 0
        const ledgerInsert = cachedStatement(getDb(), `
            INSERT OR IGNORE INTO raid_event_global_kill_ledger
                (event_id, play_id, player_id, quest_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        `).run(eventId, playId, playerId, questId, Date.now())

        let boss = currentBoss
        if (ledgerInsert.changes > 0) {
            let weightedKillCount = currentBoss.weightedKillCount + questWeight
            let totalKillCount = currentBoss.totalKillCount
            if (weightedKillCount >= rule.requiredKillCount) {
                weightedKillCount = 0
                totalKillCount++
            }

            cachedStatement(getDb(), `
                INSERT INTO raid_event_global_state
                    (
                        event_id,
                        total_kill_count,
                        weighted_kill_count,
                        calculation_version,
                        updated_at
                    )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    total_kill_count = excluded.total_kill_count,
                    weighted_kill_count = excluded.weighted_kill_count,
                    calculation_version = excluded.calculation_version,
                    updated_at = excluded.updated_at
            `).run(
                eventId,
                totalKillCount,
                weightedKillCount,
                RAID_EVENT_CALCULATION_VERSION,
                Date.now(),
            )

            boss = {
                hpPercentage: calculateHpPercentage(
                    weightedKillCount,
                    rule.requiredKillCount,
                ),
                totalKillCount,
                weightedKillCount,
                requiredKillCount: rule.requiredKillCount,
            }
        }

        return {
            counted: ledgerInsert.changes > 0,
            questWeight,
            questKillCount: getRaidEventQuestKillCountSync(eventId, questId),
            boss,
        }
    })
}

export function claimRaidEventOverallRewardsSync(
    playerId: number,
    eventId: number,
    totalKillCount: number,
): RaidEventRewardClaimResult {
    return runPersistenceTransactionSync({
        domain: "event", playerId, operation: "claim_raid_event_overall_rewards",
    }, () => {
        const receipt = cachedStatement(getDb(), `
            SELECT received_up_to
            FROM players_raid_event_overall_rewards
            WHERE player_id = ? AND event_id = ?
        `).get(playerId, eventId) as { received_up_to: number } | undefined
        const previousCount = receipt?.received_up_to ?? 0

        if (!isSupportedRaidEventId(eventId) || totalKillCount <= previousCount) {
            return {
                receivedUpTo: previousCount,
                rewardList: [],
                rewardResult: null,
            }
        }

        const rewardList = aggregateRewards(
            getRaidEventOverallRewardsBetween(eventId, previousCount, totalKillCount),
        )
        const rewardResult = applyRewardEntriesSync(playerId, rewardList)
        cachedStatement(getDb(), `
            INSERT INTO players_raid_event_overall_rewards
                (player_id, event_id, received_up_to, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(player_id, event_id) DO UPDATE SET
                received_up_to = excluded.received_up_to,
                updated_at = excluded.updated_at
        `).run(playerId, eventId, totalKillCount, Date.now())

        return {
            receivedUpTo: totalKillCount,
            rewardList,
            rewardResult,
        }
    })
}
