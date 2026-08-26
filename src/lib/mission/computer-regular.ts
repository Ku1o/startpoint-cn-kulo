import { getRankDegree } from "../stamina"
import { makeMissionCounterKey, type MissionCounterQuery } from "./counters"
import { MissionEvaluationReadContext } from "./evaluation-context"
import { getMissionPattern } from "./patterns"
import type { MissionComputer, CategoryContext } from "./types"

function rescueRankQuery(rank: number): MissionCounterQuery {
    return {
        dimension: "battle.multi_rescue_clear",
        scopeType: "lifetime",
        scopeKey: "all",
        qualifier: { questRank: rank },
    }
}

function buildStats(
    playerId: number,
    category: number,
    missionIds?: readonly number[],
    shared: MissionEvaluationReadContext = new MissionEvaluationReadContext(playerId),
): CategoryContext {
    const player = shared.player
    // Regular/daily/weekly/pass computers only consume player totals, battle
    // counters and periodic snapshots. Loading every quest row here made one
    // battle finish deserialize the same quest history up to five times.
    const totalQuestClears = category === 7
        ? shared.totalQuestClears
        : 0

    const snapshot = category === 2 || category === 6
        ? shared.snapshot("daily")
        : category === 7 || category === 10
            ? shared.snapshot("weekly")
            : null
    const rescueRanks = category !== 1
        ? []
        : missionIds === undefined
            ? [1, 2, 3, 4, 5]
            : [...new Set(missionIds.flatMap(missionId => {
                const match = getMissionPattern(category, missionId).match(/^boss_battle_attention_rank([1-5])$/)
                return match ? [Number(match[1])] : []
            }))]
    const rescueQueries = rescueRanks.map(rescueRankQuery)

    return {
        category,
        playerId,
        player,
        questProgress: {},
        totalQuestClears,
        totalStories: 0,
        rankCounts: {},
        battleCounters: shared.battleCounters,
        missionCounterValues: shared.missionCounters(rescueQueries),
        snapshot,
    }
}

function periodValue(current: number, baseline: number | undefined): number {
    return Math.max(0, current - (baseline ?? 0))
}

function computeLifetime(pattern: string, ctx: CategoryContext, dbProgress: number): number {
    const counters = ctx.battleCounters!
    if (pattern === "max_combo") return Math.max(dbProgress, ctx.player.maxComboAchieved ?? 0)
    if (pattern === "rank_ss") return Math.max(dbProgress, counters.rankSsCount)
    if (pattern === "use_dash") return Math.max(dbProgress, ctx.player.totalDashes ?? 0)
    if (pattern === "single_battle_play") return Math.max(dbProgress, counters.singleClearCount)
    if (pattern === "use_power_flip") return Math.max(dbProgress, ctx.player.totalPowerflips ?? 0)
    if (pattern === "user_rank") return Math.max(dbProgress, getRankDegree(ctx.player.rankPoint))
    if (pattern === "total_login") return Math.max(dbProgress, ctx.player.totalLoginDays ?? 0)
    if (pattern === "multi_battle_play") return Math.max(dbProgress, counters.multiClearCount)
    if (pattern === "multi_play_host") return Math.max(dbProgress, counters.multiHostClearCount)
    if (pattern === "multi_play_guest") return Math.max(dbProgress, counters.multiGuestClearCount)
    const rescueRankMatch = pattern.match(/^boss_battle_attention_rank([1-5])$/)
    if (rescueRankMatch) {
        const query = rescueRankQuery(Number(rescueRankMatch[1]))
        return Math.max(dbProgress, ctx.missionCounterValues?.get(makeMissionCounterKey(query)) ?? 0)
    }
    return dbProgress
}

function computeDaily(pattern: string, ctx: CategoryContext, dbProgress: number): number {
    const snapshot = ctx.snapshot
    const counters = ctx.battleCounters!
    if (/^single_battle_play(?:_[23])?$/.test(pattern)) {
        return Math.max(dbProgress, periodValue(counters.singleClearCount, snapshot?.singleClearCount))
    }
    if (/^multi_battle_play(?:_[23])?$/.test(pattern)) {
        return Math.max(dbProgress, periodValue(counters.multiClearCount, snapshot?.multiClearCount))
    }
    if (/^use_dash(?:_[23])?$/.test(pattern)) {
        return Math.max(dbProgress, periodValue(ctx.player.totalDashes ?? 0, snapshot?.dashCount))
    }
    if (pattern === "daily_quest_stamina_use_2024_02") {
        return Math.max(dbProgress, periodValue(ctx.player.totalStaminaUsed ?? 0, snapshot?.staminaUsed))
    }
    return dbProgress
}

function computeWeekly(pattern: string, ctx: CategoryContext, dbProgress: number): number {
    const snapshot = ctx.snapshot
    const counters = ctx.battleCounters!
    if (pattern === "weekly_mission_1") {
        return Math.max(dbProgress, periodValue(ctx.player.totalLoginDays ?? 0, snapshot?.loginDays))
    }
    if (pattern === "weekly_mission_2") {
        return Math.max(dbProgress, periodValue(counters.multiClearCount, snapshot?.multiClearCount))
    }
    return dbProgress
}

export const RegularComputer: MissionComputer = {
    name: "Regular",

    buildContext(
        playerId: number,
        category: number,
        _evaluationTime: Date,
        missionIds?: readonly number[],
        readContext?: MissionEvaluationReadContext,
    ): CategoryContext {
        return buildStats(playerId, category, missionIds, readContext)
    },

    compute(missionId: number, ctx: CategoryContext, dbProgress: number): number {
        const pattern = getMissionPattern(ctx.category, missionId)
        if (ctx.category === 1) return computeLifetime(pattern, ctx, dbProgress)
        if (ctx.category === 2) return computeDaily(pattern, ctx, dbProgress)
        if (ctx.category === 10) return computeWeekly(pattern, ctx, dbProgress)
        return dbProgress
    },
}
