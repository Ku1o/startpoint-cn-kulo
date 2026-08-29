import { cdnCharacters as characterMaster } from "../content-master"
import { getPlayerSync } from "../../data/domains/player"
import {
    countLeaderboardRanksSync,
    getLeaderboardPlayerRankSync,
    getLeaderboardRankPageSync,
    getLeaderboardRunRoundsSync,
    LeaderboardRankRecord,
} from "../../data/domains/leaderboard"
import { serializePlayerRushEventPlayedParty } from "../../data/domains/rushEvent"
import { getRankDegree } from "../stamina"
import {
    getLeaderboardCompetitionSeasonSync,
    LeaderboardCompetition,
} from "./competition"
import { LeaderboardRewardTier } from "./rewards"
import { getLeaderboardSettlementConfigSync } from "./settlement"

export interface OfficialLeaderboardRow {
    rank_number: number
    best_round: number
    elapsed_time_ms: number
    name: string
    party_member_list: { character_id: number, evolution_img_level: number }[]
    user_rank: number
}

export interface NativeLeaderboardRow {
    rank: string
    visible: boolean
    level: string
    name: string
    count: string
    time: string
    a: string | null
    b: string | null
    c: string | null
    id: number
}

function officialRow(record: LeaderboardRankRecord): OfficialLeaderboardRow {
    return {
        rank_number: record.rankNumber,
        best_round: record.totalRounds,
        elapsed_time_ms: record.clientBattleMs,
        name: record.displayName,
        party_member_list: record.characterIds.flatMap((characterId, slot) =>
            characterId === null ? [] : [{
                character_id: characterId,
                evolution_img_level: record.evolutionImgLevels[slot] ?? 0,
            }]),
        user_rank: getRankDegree(record.rankPoint),
    }
}

function formatTime(ms: number): string {
    const value = Math.max(0, Math.trunc(ms))
    const minutes = Math.floor(value / 60_000)
    const seconds = Math.floor(value / 1_000) % 60
    const centiseconds = Math.floor(value / 10) % 100
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(centiseconds).padStart(2, "0")}`
}

function thumbnailPath(characterId: number | null, evolutionLevel: number | null): string | null {
    if (characterId === null || (characterId >= 700000 && characterId <= 700099)) return null
    const entry = (characterMaster as Record<string, unknown>)[String(characterId)]
    const row = Array.isArray(entry) && Array.isArray(entry[0]) ? entry[0] : entry
    const codeName = Array.isArray(row) && typeof row[0] === "string" ? row[0] : null
    if (codeName === null || codeName === "") return null
    const level = Math.max(0, Math.min(1, Math.trunc(evolutionLevel ?? 0)))
    return `character/${codeName}/ui/thumb_party_unison_${level}`
}

export function nativeRow(record: LeaderboardRankRecord): NativeLeaderboardRow {
    const paths = record.characterIds.map((id, slot) =>
        thumbnailPath(id, record.evolutionImgLevels[slot] ?? 0))
    return {
        rank: `${record.rankNumber}位`,
        visible: true,
        level: `RANK${getRankDegree(record.rankPoint)}`,
        name: record.displayName,
        count: `BEST RECORD: ${record.totalRounds}战`,
        time: `TIME: ${formatTime(record.clientBattleMs)}`,
        a: paths[0] ?? null,
        b: paths[1] ?? null,
        c: paths[2] ?? null,
        id: record.playerId,
    }
}

function outOfRankRow(playerId: number): NativeLeaderboardRow | null {
    const player = getPlayerSync(playerId)
    if (player === null) return null
    return {
        rank: "排名外",
        visible: false,
        level: `RANK${getRankDegree(player.rankPoint)}`,
        name: player.name,
        count: "BEST RECORD: 0战",
        time: "TIME: --:--.--",
        a: null,
        b: null,
        c: null,
        id: playerId,
    }
}

export function getOfficialLeaderboardPageSync(input: {
    competition: LeaderboardCompetition
    playerId: number
    page: number
}): {
    currentPage: number
    pageMax: number
    total: number
    myData: OfficialLeaderboardRow | null
    rows: OfficialLeaderboardRow[]
} {
    const season = getSeason(input.competition.key)
    const total = countLeaderboardRanksSync(input.competition.key, season)
    const visibleTotal = Math.min(total, input.competition.displayLimit)
    const pageMax = Math.max(1, Math.ceil(visibleTotal / input.competition.pageSize))
    const requestedPage = Number.isFinite(input.page) ? Math.trunc(input.page) : 0
    const page = Math.max(0, Math.min(requestedPage, pageMax - 1))
    const rows = getLeaderboardRankPageSync({
        competitionKey: input.competition.key,
        season,
        offset: page * input.competition.pageSize,
        limit: Math.min(
            input.competition.pageSize,
            Math.max(0, input.competition.displayLimit - page * input.competition.pageSize),
        ),
    })
    const mine = getLeaderboardPlayerRankSync(
        input.competition.key,
        season,
        input.playerId,
    )
    return {
        currentPage: page + 1,
        pageMax,
        total,
        myData: mine === null ? null : officialRow(mine),
        rows: rows.map(officialRow),
    }
}

export function getLeaderboardPlayedPartiesSync(input: {
    competition: LeaderboardCompetition
    rankNumber: number
}): Record<number, ReturnType<typeof serializePlayerRushEventPlayedParty>> {
    const season = getSeason(input.competition.key)
    if (!Number.isInteger(input.rankNumber) || input.rankNumber < 1) return {}
    const [record] = getLeaderboardRankPageSync({
        competitionKey: input.competition.key,
        season,
        offset: input.rankNumber - 1,
        limit: 1,
    })
    if (record === undefined) return {}
    return Object.fromEntries(getLeaderboardRunRoundsSync(record.id).map(round => [
        round.roundNumber,
        serializePlayerRushEventPlayedParty({
            characterIds: round.characterIds,
            unisonCharacterIds: round.unisonCharacterIds,
            equipmentIds: round.equipmentIds,
            abilitySoulIds: round.abilitySoulIds,
            evolutionImgLevels: round.evolutionImgLevels,
            unisonEvolutionImgLevels: round.unisonEvolutionImgLevels,
            round: round.roundNumber,
            battleType: 1,
        }),
    ]))
}

export function buildNativeLeaderboardPayload(
    competition: LeaderboardCompetition,
    playerId: number | null,
): {
    enabled: true
    name: string
    rows: NativeLeaderboardRow[]
    item: NativeLeaderboardRow | null
    page: number
    row: number
    index: number
    time: string
    total: number
    reward: readonly LeaderboardRewardTier[]
} {
    const season = getSeason(competition.key)
    const total = countLeaderboardRanksSync(competition.key, season)
    const records = getLeaderboardRankPageSync({
        competitionKey: competition.key,
        season,
        offset: 0,
        limit: competition.displayLimit,
    })
    const mine = playerId === null
        ? null
        : getLeaderboardPlayerRankSync(competition.key, season, playerId)
    const index = mine === null ? -1 : mine.rankNumber - 1
    const visibleIndex = index >= 0 && index < records.length ? index : -1
    return {
        enabled: true,
        name: competition.displayName,
        rows: records.map(nativeRow),
        item: mine === null
            ? (playerId === null ? null : outOfRankRow(playerId))
            : nativeRow(mine),
        page: visibleIndex < 0 ? 0 : Math.floor(visibleIndex / competition.pageSize),
        row: visibleIndex < 0 ? -1 : visibleIndex % competition.pageSize,
        index,
        time: "实时更新",
        total,
        reward: getLeaderboardSettlementConfigSync(competition.key).rewardTiers,
    }
}

export function buildUnavailableNativeLeaderboardPayload(): {
    enabled: false
    name: string
    rows: NativeLeaderboardRow[]
    item: null
    page: number
    row: number
    index: number
    time: string
    total: number
    reward: readonly LeaderboardRewardTier[]
} {
    return {
        enabled: false,
        name: "连战",
        rows: [],
        item: null,
        page: 0,
        row: -1,
        index: -1,
        time: "排行榜暂未开放",
        total: 0,
        reward: [],
    }
}

function getSeason(competitionKey: string): number {
    return getLeaderboardCompetitionSeasonSync(competitionKey)
}

export function buildLeaderboardTermsText(competition: LeaderboardCompetition): string {
    const tiers = getLeaderboardSettlementConfigSync(competition.key).rewardTiers
    const lines = tiers.map(tier => {
        const range = tier.toRank === null
            ? `第${tier.fromRank}名起`
            : tier.fromRank === tier.toRank
                ? `第${tier.fromRank}名`
                : `第${tier.fromRank}～${tier.toRank}名`
        const rewards = [
            tier.itemId === null ? null : `${tier.itemName} × ${tier.itemCount}`,
            tier.degreeId === null ? null : `称号「${tier.degreeName}」`,
        ].filter((value): value is string => value !== null)
        return `<p><b>${range}</b>　${rewards.join(" + ")}</p>`
    })
    return `<h2>${competition.displayName} 排行报酬</h2>${lines.join("")}<p>排行榜按本期完整通关的 client_battle_ms 总和升序排列；每位玩家只保留最佳成绩。</p>`
}
