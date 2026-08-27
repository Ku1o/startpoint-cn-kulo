import rushEventRankingRewards from "../../assets/rush_event_ranking_reward.json"
import { getDb } from "../data/db"
import { grantPlayerDegreeSync } from "../data/domains/degree"

export const rankingEventIdQuestMap: Readonly<Record<number, number>> = {
    1: 1001,
    2: 2001,
    3: 3001,
    4: 4001,
    5: 5001,
    1000: 1000001,
    1001: 1001001,
}

const RANKING_TIME_DEGREES: Readonly<Record<number, readonly {
    degreeId: number
    maxElapsedTimeMs: number
}[]>> = {
    2: [
        { degreeId: 54050, maxElapsedTimeMs: Number.MAX_SAFE_INTEGER },
        { degreeId: 54060, maxElapsedTimeMs: 280_000 },
        { degreeId: 54070, maxElapsedTimeMs: 150_000 },
        { degreeId: 54080, maxElapsedTimeMs: 80_000 },
        { degreeId: 54090, maxElapsedTimeMs: 42_000 },
    ],
    3: [
        { degreeId: 54100, maxElapsedTimeMs: Number.MAX_SAFE_INTEGER },
        { degreeId: 54110, maxElapsedTimeMs: 240_000 },
        { degreeId: 54120, maxElapsedTimeMs: 120_000 },
        { degreeId: 54130, maxElapsedTimeMs: 35_000 },
        { degreeId: 54140, maxElapsedTimeMs: 23_000 },
    ],
    4: [
        { degreeId: 54150, maxElapsedTimeMs: Number.MAX_SAFE_INTEGER },
        { degreeId: 54160, maxElapsedTimeMs: 420_000 },
        { degreeId: 54170, maxElapsedTimeMs: 150_000 },
        { degreeId: 54180, maxElapsedTimeMs: 70_000 },
        { degreeId: 54190, maxElapsedTimeMs: 45_000 },
    ],
}

const RANKING_PERCENTILE_DEGREES: Readonly<Record<number, readonly {
    degreeId: number
    maxPercentile: number
}[]>> = {
    1: [
        { degreeId: 54040, maxPercentile: 0.03 },
        { degreeId: 54030, maxPercentile: 0.10 },
        { degreeId: 54020, maxPercentile: 0.30 },
        { degreeId: 54010, maxPercentile: 0.50 },
        { degreeId: 54000, maxPercentile: 1.00 },
    ],
    5: [
        { degreeId: 54240, maxPercentile: 0.03 },
        { degreeId: 54230, maxPercentile: 0.10 },
        { degreeId: 54220, maxPercentile: 0.30 },
        { degreeId: 54210, maxPercentile: 0.50 },
        { degreeId: 54200, maxPercentile: 1.00 },
    ],
}

export interface RankingPlacement {
    bestElapsedTimeMs: number
    participantCount: number
    rankNumber: number
    percentile: number
}

export function getRankingPlacementSync(playerId: number, eventId: number): RankingPlacement | null {
    const questId = rankingEventIdQuestMap[eventId]
    if (questId === undefined) return null
    const own = getDb().prepare(`
        SELECT best_elapsed_time_ms
        FROM players_quest_progress
        WHERE player_id = ? AND section = 11 AND quest_id = ?
          AND finished = 1 AND best_elapsed_time_ms > 0
    `).get(playerId, questId) as { best_elapsed_time_ms: number } | undefined
    if (!own) return null
    const placement = getDb().prepare(`
        SELECT
            COUNT(*) AS participant_count,
            1 + SUM(CASE WHEN best_elapsed_time_ms < ? THEN 1 ELSE 0 END) AS rank_number
        FROM players_quest_progress
        WHERE section = 11 AND quest_id = ?
          AND finished = 1 AND best_elapsed_time_ms > 0
    `).get(own.best_elapsed_time_ms, questId) as {
        participant_count: number
        rank_number: number
    }
    const participantCount = Math.max(1, Number(placement.participant_count) || 0)
    const rankNumber = Math.max(1, Number(placement.rank_number) || 1)
    return {
        bestElapsedTimeMs: own.best_elapsed_time_ms,
        participantCount,
        rankNumber,
        percentile: rankNumber / participantCount,
    }
}

export function getEligibleRankingDegreeIdsSync(playerId: number, eventId: number): number[] {
    const placement = getRankingPlacementSync(playerId, eventId)
    if (!placement) return []
    const timeRules = RANKING_TIME_DEGREES[eventId]
    if (timeRules) {
        return timeRules
            .filter(rule => placement.bestElapsedTimeMs <= rule.maxElapsedTimeMs)
            .map(rule => rule.degreeId)
    }
    const percentileRules = RANKING_PERCENTILE_DEGREES[eventId]
    const matched = percentileRules?.find(rule => placement.percentile <= rule.maxPercentile)
    return matched ? [matched.degreeId] : []
}

function grantDegreeIds(playerId: number, degreeIds: readonly number[]): number[] {
    const granted: number[] = []
    for (const degreeId of degreeIds) {
        if (grantPlayerDegreeSync(playerId, degreeId)) granted.push(degreeId)
    }
    return granted
}

export function grantEligibleRankingEventDegreesSync(playerId: number, eventId: number): number[] {
    return grantDegreeIds(playerId, getEligibleRankingDegreeIdsSync(playerId, eventId))
}

type RaidDifficulty = "beginner" | "advanced" | "super" | "hell"

export function getRaidQuestDifficulty(questId: number): RaidDifficulty | null {
    if (questId === 7001) return "super"
    if (questId === 7002) return "hell"
    if (questId < 7003 || questId > 7026) return null
    return (["beginner", "advanced", "super", "hell"] as const)[(questId - 7003) % 4]
}

const RAID_DEGREE_RULES: readonly { difficulty: RaidDifficulty; count: number; offset: number }[] = [
    { difficulty: "hell", count: 700, offset: 0 },
    { difficulty: "hell", count: 300, offset: 1 },
    { difficulty: "hell", count: 100, offset: 2 },
    { difficulty: "hell", count: 10, offset: 3 },
    { difficulty: "super", count: 200, offset: 4 },
    { difficulty: "super", count: 100, offset: 5 },
    { difficulty: "super", count: 50, offset: 6 },
    { difficulty: "super", count: 10, offset: 7 },
    { difficulty: "advanced", count: 100, offset: 8 },
    { difficulty: "advanced", count: 50, offset: 9 },
    { difficulty: "advanced", count: 10, offset: 10 },
    { difficulty: "beginner", count: 100, offset: 11 },
    { difficulty: "beginner", count: 10, offset: 12 },
]

export function getEligibleRaidDegreeIdsSync(playerId: number, eventId: number): number[] {
    if (!Number.isInteger(eventId) || eventId < 1 || eventId > 7) return []
    const rows = getDb().prepare(`
        SELECT quest_id, COUNT(*) AS clear_count
        FROM raid_event_global_kill_ledger
        WHERE player_id = ? AND event_id = ?
        GROUP BY quest_id
    `).all(playerId, eventId) as { quest_id: number; clear_count: number }[]
    const counts: Record<RaidDifficulty, number> = {
        beginner: 0,
        advanced: 0,
        super: 0,
        hell: 0,
    }
    for (const row of rows) {
        const difficulty = getRaidQuestDifficulty(row.quest_id)
        if (difficulty) counts[difficulty] += Math.max(0, Number(row.clear_count) || 0)
    }
    const baseDegreeId = 63000 + (eventId - 1) * 13
    return RAID_DEGREE_RULES
        .filter(rule => counts[rule.difficulty] >= rule.count)
        .map(rule => baseDegreeId + rule.offset)
}

export function grantEligibleRaidEventDegreesSync(playerId: number, eventId: number): number[] {
    return grantDegreeIds(playerId, getEligibleRaidDegreeIdsSync(playerId, eventId))
}

interface RushRewardEntry {
    fromRank: number
    toRank: number
    kind: number
    kindId: number
    number: number
}

const rushRewards = rushEventRankingRewards as Record<string, Record<string, RushRewardEntry[]>>

export function getEligibleRushDegreeIds(eventId: number, maxRound: number | null | undefined): number[] {
    if (!Number.isFinite(maxRound) || Number(maxRound) <= 0) return []
    const eventRewards = rushRewards[String(eventId)] ?? {}
    const degreeIds: number[] = []
    for (const entries of Object.values(eventRewards)) {
        for (const entry of entries) {
            if (entry.kind === 7
                && maxRound! >= entry.fromRank
                && maxRound! <= entry.toRank) {
                degreeIds.push(entry.kindId)
            }
        }
    }
    return degreeIds
}

export function grantEligibleRushEventDegreesSync(
    playerId: number,
    eventId: number,
    maxRound?: number | null,
): number[] {
    const resolvedMaxRound = maxRound ?? (getDb().prepare(`
        SELECT endless_battle_max_round
        FROM players_rush_events
        WHERE player_id = ? AND event_id = ?
    `).get(playerId, eventId) as { endless_battle_max_round: number | null } | undefined)
        ?.endless_battle_max_round
    return grantDegreeIds(playerId, getEligibleRushDegreeIds(eventId, resolvedMaxRound))
}

/** Restores activity titles from authoritative persisted results when profile data is opened. */
export function ensurePlayerActivityDegreesSync(playerId: number): number[] {
    const granted: number[] = []
    for (const eventId of [1, 2, 3, 4, 5]) {
        granted.push(...grantEligibleRankingEventDegreesSync(playerId, eventId))
    }
    const raidEvents = getDb().prepare(`
        SELECT DISTINCT event_id
        FROM raid_event_global_kill_ledger
        WHERE player_id = ?
    `).all(playerId) as { event_id: number }[]
    for (const row of raidEvents) {
        granted.push(...grantEligibleRaidEventDegreesSync(playerId, row.event_id))
    }
    const rushEvents = getDb().prepare(`
        SELECT event_id, endless_battle_max_round
        FROM players_rush_events
        WHERE player_id = ? AND endless_battle_max_round IS NOT NULL
    `).all(playerId) as { event_id: number; endless_battle_max_round: number }[]
    for (const row of rushEvents) {
        granted.push(...grantEligibleRushEventDegreesSync(
            playerId,
            row.event_id,
            row.endless_battle_max_round,
        ))
    }
    return granted
}
