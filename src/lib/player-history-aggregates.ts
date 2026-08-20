import charactersAsset from "../../assets/character.json"
import encyclopediaAsset from "../../assets/encyclopedia.json"
import mainQuestAsset from "../../assets/main_quest.json"
import scoreAttackBorderRewardAsset from "../../assets/score_attack_border_reward.json"
import scoreAttackQuestAsset from "../../assets/score_attack_event_quest.json"
import storyEventSingleQuestAsset from "../../assets/story_event_single_quest.json"
import worldStoryEventQuestAsset from "../../assets/world_story_event_quest.json"
import { getDb } from "../data/db"
import { getActiveMissionCountersSync } from "../data/domains/active_mission_counters"
import { getPlayerCharactersSync } from "../data/domains/character"
import { getPlayerDegreeIdsSync } from "../data/domains/degree"
import { getPlayerEquipmentListSync } from "../data/domains/equipment"
import { getMissionBattleCountersSync } from "../data/domains/mission_battle_facts"
import { Player } from "../data/types"
import { getEquipmentDissolveSync, getEquipmentMaxLevel } from "./assets"
import { characterExpCaps } from "./character"
import { getMissionCounterValueSync } from "./mission/counters"
import { PlayerHistoryTopicValueList } from "./player-history-catalog"
import { ScoreAttackBorderTier } from "./quest/finish/score-attack-handler"
import { getRankDegree } from "./stamina"

export type PlayerHistoryTopicAggregates = Record<
    number,
    Partial<PlayerHistoryTopicValueList>
>

interface QuestProgressRow {
    section: number
    quest_id: number
    high_score: number | null
}

interface RushRecordRow {
    event_id: number
    endless_battle_max_round: number
    endless_battle_max_round_character_id_1: number | null
    endless_battle_max_round_character_id_2: number | null
    endless_battle_max_round_character_id_3: number | null
}

interface CarnivalRecordRow {
    event_id: number
    total_score: number
}

interface ExpertBossDegreeRow {
    degree_id: number
    acquired_at: number
}

interface CharacterMasterEntry {
    rarity: number
}

interface ScoreAttackQuestEntry {
    eventId: number
    scoreAttackQuestId: number
}

const MAIN_QUEST_IDS_BY_CHAPTER = Array.from({ length: 12 }, () => new Set<number>())
for (const questIdText of Object.keys(mainQuestAsset)) {
    const questId = Number(questIdText)
    const chapter = Math.floor(questId / 1_000_000)
    if (chapter >= 1 && chapter <= 12) MAIN_QUEST_IDS_BY_CHAPTER[chapter - 1].add(questId)
}

function buildSideStoryGroups(asset: Record<string, unknown>): number[][] {
    const groups = new Map<number, number[]>()
    for (const questIdText of Object.keys(asset)) {
        const questId = Number(questIdText)
        const groupId = Math.floor(questId / 1000)
        const group = groups.get(groupId) ?? []
        group.push(questId)
        groups.set(groupId, group)
    }
    return [...groups.values()]
}

const SIDE_STORY_GROUPS = [
    { section: 10, groups: buildSideStoryGroups(storyEventSingleQuestAsset) },
    { section: 18, groups: buildSideStoryGroups(worldStoryEventQuestAsset) },
] as const

const SPECIAL_EQUIPMENT_IDS = [5010045, 5040020, 5100011, 5030028, 5010032, 5010056]
const SOLO_TIME_ATTACK_MASTERY_DEGREES = new Set([54500, 54520, 54540, 54560, 54580, 54600])
const SOLO_TIME_ATTACK_VICTORY_DEGREES = new Set([54510, 54530, 54550, 54570, 54590, 54610])
const EXPERT_BOSS_DEGREE_TO_BOSS_ID = new Map([
    [57020, 1],
    [57040, 2],
    [57060, 3],
    [57080, 4],
    [57100, 5],
    [57120, 6],
])
const BASE_READ_ENCYCLOPEDIA_COUNT = Object.values(
    encyclopediaAsset as Record<string, { read: boolean }>,
).filter(entry => entry.read).length
const BASE_ENCYCLOPEDIA_IDS = new Set(Object.keys(encyclopediaAsset).map(Number))

function pad(value: number): string {
    return String(value).padStart(2, "0")
}

/** Convert a real database timestamp to the virtual server's JST display time. */
export function formatPlayerHistoryJstDate(date: Date, offsetMs: number): string {
    const jst = new Date(date.getTime() + offsetMs + 9 * 60 * 60 * 1000)
    return `${jst.getUTCFullYear()}-${pad(jst.getUTCMonth() + 1)}-${pad(jst.getUTCDate())}`
        + ` ${pad(jst.getUTCHours())}:${pad(jst.getUTCMinutes())}:${pad(jst.getUTCSeconds())}`
}

function exactLevel100CharacterCount(
    characters: ReturnType<typeof getPlayerCharactersSync>,
): number {
    const master = charactersAsset as Record<string, CharacterMasterEntry>
    let count = 0
    for (const [characterId, character] of Object.entries(characters)) {
        const rarity = master[characterId]?.rarity
        const caps = characterExpCaps[rarity]
        const level100Exp = caps?.[caps.length - 1]
        if (level100Exp !== undefined && character.exp >= level100Exp) count++
    }
    return count
}

function completedSideStoryCount(finishedBySection: Map<number, Set<number>>): number {
    let count = 0
    for (const { section, groups } of SIDE_STORY_GROUPS) {
        const finished = finishedBySection.get(section) ?? new Set<number>()
        count += groups.filter(group => group.every(questId => finished.has(questId))).length
    }
    return count
}

function scoreAttackBorderCounts(rows: QuestProgressRow[]): [number, number] {
    const quests = scoreAttackQuestAsset as Record<string, ScoreAttackQuestEntry>
    const tiers = scoreAttackBorderRewardAsset as Record<string, ScoreAttackBorderTier[]>
    let best = 0
    let total = 0

    for (const row of rows) {
        if (row.section !== 27 || row.high_score === null) continue
        const quest = quests[String(row.quest_id)]
        if (!quest) continue
        const questTiers = tiers[`${quest.eventId}_${quest.scoreAttackQuestId}`] ?? []
        const achieved = questTiers.filter(tier => tier.score <= row.high_score!).length
        best = Math.max(best, achieved)
        total += achieved
    }
    return [best, total]
}

function formatAchievementDate(acquiredAt: number, fallbackDate: string, offsetMs: number): string {
    if (!Number.isFinite(acquiredAt) || acquiredAt <= 0) return fallbackDate
    const date = new Date(acquiredAt)
    return Number.isFinite(date.getTime())
        ? formatPlayerHistoryJstDate(date, offsetMs)
        : fallbackDate
}

/**
 * Build the current player-history snapshot from already persisted gameplay data.
 * This endpoint is opened manually, so the aggregation stays read-only and does
 * not add work to battle settlement, gacha, or multiplayer room handling.
 */
export function buildPlayerHistoryTopicAggregatesSync(
    playerId: number,
    player: Player,
    startGameDate: string,
    fallbackAchievementDate: string,
    offsetMs: number,
): PlayerHistoryTopicAggregates {
    const db = getDb()
    const questRows = db.prepare(`
        SELECT section, quest_id, high_score
        FROM players_quest_progress
        WHERE player_id = ? AND finished = 1
          AND section IN (1, 10, 18, 20, 21, 27)
    `).all(playerId) as QuestProgressRow[]

    const finishedBySection = new Map<number, Set<number>>()
    for (const row of questRows) {
        const finished = finishedBySection.get(row.section) ?? new Set<number>()
        finished.add(row.quest_id)
        finishedBySection.set(row.section, finished)
    }

    const finishedMainQuests = finishedBySection.get(1) ?? new Set<number>()
    const chapterDates = MAIN_QUEST_IDS_BY_CHAPTER.map(questIds => (
        questIds.size > 0 && [...questIds].every(questId => finishedMainQuests.has(questId))
            ? fallbackAchievementDate
            : null
    ))

    const characters = getPlayerCharactersSync(playerId)
    const completedSecondBoards = Object.entries(characters)
        .filter(([, character]) => character.bondTokenList.some(token => (
            token.manaBoardIndex === 2 && token.status >= 2
        )))
        .sort(([, left], [, right]) => left.updateTime.getTime() - right.updateTime.getTime())
    const firstSecondBoard = completedSecondBoards[0]
    const firstSecondBoardDate = firstSecondBoard
        && Number.isFinite(firstSecondBoard[1].updateTime.getTime())
        ? formatPlayerHistoryJstDate(firstSecondBoard[1].updateTime, offsetMs)
        : null

    const equipment = getPlayerEquipmentListSync(playerId)
    const equipmentEntries = Object.entries(equipment)
    const fullyAwakenedEquipmentCount = equipmentEntries.filter(([equipmentId, entry]) => {
        const dissolve = getEquipmentDissolveSync(equipmentId)
        return dissolve !== null && entry.level >= dissolve.max_level
    }).length
    const fullyEnhancedEquipmentCount = equipmentEntries.filter(([equipmentId, entry]) => (
        entry.enhancementLevel >= getEquipmentMaxLevel(Number(equipmentId))
    )).length
    const specialEquipmentLevels: Array<number | null> = []
    for (const equipmentId of SPECIAL_EQUIPMENT_IDS) {
        const entry = equipment[String(equipmentId)]
        specialEquipmentLevels.push(entry?.level ?? null, entry?.enhancementLevel ?? null)
    }

    const battleCounters = getMissionBattleCountersSync(playerId)
    const activeMissionCounters = getActiveMissionCountersSync(playerId)
    const degreeIds = getPlayerDegreeIdsSync(playerId)
    const degreeSet = new Set(degreeIds)

    const regularMissionCount = (db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_cleared_regular_missions
        WHERE player_id = ?
    `).get(playerId) as { count: number }).count
    const eventMissionCount = (db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_category_mission_stages
        WHERE player_id = ? AND status = 1
    `).get(playerId) as { count: number }).count
    const mvpCount = getMissionCounterValueSync(playerId, {
        dimension: "battle.multi_mvp",
        scopeType: "lifetime",
        scopeKey: "all",
    })

    const rushRecord = db.prepare(`
        SELECT event_id, endless_battle_max_round,
               endless_battle_max_round_character_id_1,
               endless_battle_max_round_character_id_2,
               endless_battle_max_round_character_id_3
        FROM players_rush_events
        WHERE player_id = ? AND endless_battle_max_round IS NOT NULL
        ORDER BY endless_battle_max_round DESC, event_id DESC
        LIMIT 1
    `).get(playerId) as RushRecordRow | undefined
    const rushCharacters: Array<number | null> = rushRecord
        ? [
            rushRecord.endless_battle_max_round_character_id_1,
            rushRecord.endless_battle_max_round_character_id_2,
            rushRecord.endless_battle_max_round_character_id_3,
            null, null, null, null,
        ]
        : [null, null, null, null, null, null, null]

    const carnivalRecord = db.prepare(`
        SELECT event_id, SUM(MAX(COALESCE(best_score, 0), 0)) AS total_score
        FROM players_carnival_event_records
        WHERE player_id = ?
        GROUP BY event_id
        ORDER BY total_score DESC, event_id DESC
        LIMIT 1
    `).get(playerId) as CarnivalRecordRow | undefined

    const [scoreAttackBestBorder, scoreAttackTotalBorders] = scoreAttackBorderCounts(questRows)
    const playerReadEncyclopediaIds = db.prepare(`
        SELECT encyclopedia_id
        FROM players_encyclopedia_keywords
        WHERE player_id = ? AND read = 1
    `).all(playerId) as { encyclopedia_id: number }[]
    const readEncyclopediaCount = BASE_READ_ENCYCLOPEDIA_COUNT
        + playerReadEncyclopediaIds.filter(row => !BASE_ENCYCLOPEDIA_IDS.has(row.encyclopedia_id)).length

    const expertBossDegree = db.prepare(`
        SELECT degree_id, acquired_at
        FROM players_degrees
        WHERE player_id = ? AND degree_id IN (57020, 57040, 57060, 57080, 57100, 57120)
        ORDER BY CASE WHEN acquired_at > 0 THEN acquired_at ELSE 9223372036854775807 END,
                 degree_id
        LIMIT 1
    `).get(playerId) as ExpertBossDegreeRow | undefined
    const expertBossId = expertBossDegree
        ? EXPERT_BOSS_DEGREE_TO_BOSS_ID.get(expertBossDegree.degree_id) ?? null
        : null

    return {
        0: { date_values: [startGameDate] },
        1: { int_values: [Math.max(0, player.totalLoginDays)] },
        2: { date_values: chapterDates.slice(0, 6) },
        3: { date_values: chapterDates.slice(6, 12) },
        4: {
            date_values: [firstSecondBoardDate],
            character_id_values: [firstSecondBoard ? Number(firstSecondBoard[0]) : null],
        },
        5: { int_values: [exactLevel100CharacterCount(characters)] },
        6: { int_values: [Math.max(0, player.bondToken)] },
        7: { date_values: [Object.keys(characters).length >= 100 ? fallbackAchievementDate : null] },
        8: { date_values: [getRankDegree(player.rankPoint) >= 100 ? fallbackAchievementDate : null] },
        9: { int_values: [regularMissionCount] },
        10: { int_values: [eventMissionCount] },
        11: { int_values: [mvpCount] },
        12: { int_values: [battleCounters.multiHostClearCount, battleCounters.multiGuestClearCount] },
        13: { int_values: [equipmentEntries.length] },
        14: { int_values: [fullyAwakenedEquipmentCount] },
        15: { int_values: [fullyEnhancedEquipmentCount] },
        16: { int_values: specialEquipmentLevels },
        17: {
            int_values: rushRecord
                ? [rushRecord.event_id, rushRecord.endless_battle_max_round]
                : [null, null],
            character_id_values: rushCharacters,
        },
        18: {
            int_values: carnivalRecord
                ? [carnivalRecord.event_id, carnivalRecord.total_score]
                : [null, null],
        },
        19: {
            int_values: [
                degreeIds.filter(id => SOLO_TIME_ATTACK_VICTORY_DEGREES.has(id)).length,
                degreeIds.filter(id => SOLO_TIME_ATTACK_MASTERY_DEGREES.has(id)).length,
            ],
        },
        20: { int_values: [scoreAttackBestBorder, scoreAttackTotalBorders] },
        21: { int_values: [(finishedBySection.get(21) ?? new Set()).size] },
        22: { int_values: [completedSideStoryCount(finishedBySection)] },
        23: { int_values: [(finishedBySection.get(20) ?? new Set()).size] },
        24: { int_values: [activeMissionCounters.totalUsedManaCount] },
        25: { int_values: [readEncyclopediaCount] },
        26: {
            date_values: [expertBossDegree
                ? formatAchievementDate(expertBossDegree.acquired_at, fallbackAchievementDate, offsetMs)
                : null],
            boss_id_values: [expertBossId],
        },
    }
}
