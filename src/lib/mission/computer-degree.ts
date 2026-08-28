// Degree mission computer (category 5)

import { getDb } from "../../data/db"
import {
    getPlayerCharactersByIdsSync,
    getPlayerCharactersManaNodesByIdsSync,
    getPlayerCharactersManaNodesSync,
    getPlayerCharactersSync,
} from "../../data/domains/character"
import { getPlayerEquipmentListSync } from "../../data/domains/equipment"
import {
    getPlayerCollectedItemTotalsByIdsSync,
    getPlayerItemsByIdsSync,
} from "../../data/domains/item"
import { countEquippedAbilitySoulSlotsSync } from "../../data/domains/party"
import { getPlayerShopPurchasesMapSync } from "../../data/domains/shopPurchase"
import {
    countFinishedPlayerQuestsByCategorySync,
} from "../../data/domains/quest"
import type { PlayerCharacter, PlayerEquipment } from "../../data/types"
import { getCharacterDataSync, getCharacterManaNodesSync } from "../assets"
import { characterExpCaps } from "../character"
import { getRankDegree } from "../stamina"
import { getMissionMasterDefinition, getMissionMasterDefinitions } from "./master-data"
import { getMissionPattern } from "./patterns"
import type { MissionComputer, CategoryContext, PlayerQuestProgressEntry } from "./types"
import { MissionEvaluationReadContext } from "./evaluation-context"

type DegreeRow = readonly unknown[]

interface DegreeDefinition {
    conditionType: number
    row: DegreeRow
    description: string
    pattern: string
}

interface DegreeQuestProgressEntry extends PlayerQuestProgressEntry {
    section: number
    hostFinished?: boolean
    highScore?: number
}

interface QuestFilter {
    categories: number[]
    exactQuestIds?: Set<number>
    eventPrefix?: number
    bossId?: number
}

interface DegreeContext extends CategoryContext {
    characters: Record<string, PlayerCharacter>
    manaNodes: Record<string, number[]>
    equipment: Record<string, PlayerEquipment>
    items: Record<string, number>
    collectedItemTotals: Record<string, number>
    flatQuestProgress: DegreeQuestProgressEntry[]
    questProgressBySection: ReadonlyMap<number, readonly DegreeQuestProgressEntry[]>
    questProgressByQuestId: ReadonlyMap<number, readonly DegreeQuestProgressEntry[]>
    finishedQuestKeys: ReadonlySet<string>
    questMetricCache: Map<string, number | undefined>
    completedSecondBoards: Set<number>
    questClearCounters: Map<string, number>
    counterValues: Map<string, number>
    treasureShopPurchaseCount: number
    equippedAbilitySoulCount: number
}

// Degree mission target lookup
const degreeTargetMap: Record<number, number> = {}
{
    // Note: this import is resolved at module load time via the patterns file's data
    // but we use the same degreeDefs. For simplicity, inline the regex.
    const degreeDefs = require("../../../assets/mission_degree.json")
    const descRegex = /玩家(?:达到|级别达到)\s*(\d+)/
    for (const [mid, rows] of Object.entries(degreeDefs as Record<string, any>)) {
        const row = (rows as any[])[0]
        if (!row || !row[2]) continue
        const match = descRegex.exec(String(row[2]))
        if (match) degreeTargetMap[parseInt(mid)] = parseInt(match[1])
    }
}

export function getTargetDegree(missionId: number): number | undefined {
    return degreeTargetMap[missionId]
}

const degreeDefinitions = new Map<number, DegreeDefinition>()
const degreeMissionIdsByConditionType = new Map<number, number[]>()
const degreeMissionOrder = new Map<number, number>()
const mainQuestIdsByChapter = new Map<number, number[]>()
const exQuestIdsByChapter = new Map<number, number[]>()
const bossQuestIdsByBoss = new Map<number, number[]>()
const hardMultiQuestIdsByChallenge = new Map<number, number[]>()
const treasureShopItemIds = new Set(
    Object.keys(require("../../../assets/treasure_shop.json") as Record<string, unknown>),
)

function optionalNumber(value: unknown): number | undefined {
    if (value === undefined || value === null) return undefined
    const text = String(value).trim()
    if (!text || text === "(None)") return undefined
    const parsed = Number(text)
    return Number.isFinite(parsed) ? parsed : undefined
}

function numberList(value: unknown): number[] {
    if (value === undefined || value === null) return []
    const text = String(value).trim()
    if (!text || text === "(None)") return []
    return text
        .split(",")
        .map(item => Number(item.trim()))
        .filter(Number.isFinite)
}

function addQuestIdByChapter(target: Map<number, number[]>, questIdText: string): void {
    const questId = Number(questIdText)
    if (!Number.isFinite(questId)) return
    const chapter = Math.floor(questId / 1_000_000)
    if (chapter <= 0) return
    const bucket = target.get(chapter) ?? []
    bucket.push(questId)
    target.set(chapter, bucket)
}

{
    for (const definition of getMissionMasterDefinitions(5)) {
        const conditionType = optionalNumber(definition.row[3])
        if (conditionType === undefined) continue
        degreeDefinitions.set(definition.missionId, {
            conditionType,
            row: definition.row,
            description: String(definition.row[2] ?? ""),
            pattern: definition.pattern,
        })
        degreeMissionOrder.set(definition.missionId, degreeMissionOrder.size)
        const missionIds = degreeMissionIdsByConditionType.get(conditionType) ?? []
        missionIds.push(definition.missionId)
        degreeMissionIdsByConditionType.set(conditionType, missionIds)
    }

    const mainQuests = require("../../../assets/main_quest.json") as Record<string, unknown>
    const exQuests = require("../../../assets/ex_quest.json") as Record<string, unknown>
    const bossQuests = require("../../../assets/boss_battle_quest.json") as Record<string, unknown>
    for (const questId of Object.keys(mainQuests)) addQuestIdByChapter(mainQuestIdsByChapter, questId)
    for (const questId of Object.keys(exQuests)) addQuestIdByChapter(exQuestIdsByChapter, questId)
    for (const questIdText of Object.keys(bossQuests)) {
        const questId = Number(questIdText)
        if (!Number.isFinite(questId) || questId < 1_000_000) continue
        const bossId = Math.floor((questId - 1_000_000) / 1_000)
        const bucket = bossQuestIdsByBoss.get(bossId) ?? []
        bucket.push(questId)
        bossQuestIdsByBoss.set(bossId, bucket)
    }
    for (const questIds of bossQuestIdsByBoss.values()) questIds.sort((a, b) => a - b)

    const hardMultiQuests = require("../../../assets/hard_multi_event_quest.json") as Record<
        string,
        { name?: string }
    >
    const normalizeQuestName = (value: unknown): string => String(value ?? "")
        .replace(/\s*::quest_rank::\s*/g, "")
        .trim()
    for (const definition of degreeDefinitions.values()) {
        if (optionalNumber(definition.row[8]) !== 19) continue
        const challengeId = optionalNumber(definition.row[9])
        if (challengeId === undefined) continue
        const questIds = Object.entries(hardMultiQuests)
            .filter(([, quest]) => {
                const questName = normalizeQuestName(quest.name)
                return questName.length > 0 && definition.description.includes(questName)
            })
            .map(([questId]) => Number(questId))
            .filter(Number.isSafeInteger)
            .sort((left, right) => left - right)
        if (questIds.length > 0) hardMultiQuestIdsByChallenge.set(challengeId, questIds)
    }
}

function estimateCharacterLevel(characterId: number, exp: number): number {
    const rarity = getCharacterDataSync(characterId)?.rarity
    if (rarity === undefined) return 0
    const caps = characterExpCaps[rarity]
    if (!caps || caps.length === 0) return 0
    const baseLevel = 40 + (rarity - 1) * 10
    // The cap table only proves five-level milestones; it is not a per-level
    // curve. Starting at baseLevel - 1 made a zero-EXP 4*/5* character look
    // like level 69/79 and granted level titles immediately.
    let level = 0
    for (let index = 0; index < caps.length; index++) {
        if (exp < caps[index]) break
        level = baseLevel + index * 5
    }
    return level
}

function counterKey(dimension: string, qualifier: Record<string, unknown> = {}): string {
    const normalized: Record<string, unknown> = {}
    for (const key of Object.keys(qualifier).sort()) {
        const value = qualifier[key]
        if (value !== undefined && value !== null && value !== "" && value !== "(None)") {
            normalized[key] = value
        }
    }
    return `${dimension}|${JSON.stringify(normalized)}`
}

const COUNTER_DIMENSIONS_BY_CONDITION_TYPE: Readonly<Record<number, readonly string[]>> = {
    3: ["shop.treasure_mana_spent"],
    14: ["battle.quest_clear"],
    15: ["battle.best_clear_time_ms"],
    16: ["battle.clear"],
    17: ["battle.multi_role_clear"],
    19: ["battle.multi_mvp"],
    20: ["battle.multi_rescue_clear"],
    23: ["battle.quest_clear"],
    25: ["battle.max_score"],
    26: ["battle.rank_clear", "battle.quest_rank_clear"],
    27: ["battle.max_party_power"],
    28: ["battle.stat"],
    29: ["battle.max_damage", "battle.max_revival_coffin"],
    30: ["battle.max_combo"],
    31: ["battle.max_skill_chain"],
    34: ["equipment.awakening"],
    35: ["party.ability_soul_equip"],
    36: ["equipment.lv5_count"],
    45: ["shop.treasure_purchase"],
    92: ["battle.multi_newbie_rescue_clear"],
}

function loadCounterMaps(playerId: number, conditionTypes: ReadonlySet<number>): {
    questClearCounters: Map<string, number>
    counterValues: Map<string, number>
} {
    const dimensions = [...new Set([...conditionTypes]
        .flatMap(conditionType => COUNTER_DIMENSIONS_BY_CONDITION_TYPE[conditionType] ?? []))]
    if (dimensions.length === 0) {
        return { questClearCounters: new Map(), counterValues: new Map() }
    }
    const placeholders = dimensions.map(() => "?").join(", ")
    const rows = getDb().prepare(`
        SELECT dimension, qualifier_json, value
        FROM players_mission_counters
        WHERE player_id = ?
          AND scope_type = 'lifetime'
          AND scope_key = 'all'
          AND dimension IN (${placeholders})
    `).all(playerId, ...dimensions) as { dimension: string; qualifier_json: string; value: number }[]

    const questClearCounters = new Map<string, number>()
    const counterValues = new Map<string, number>()
    for (const row of rows) {
        let qualifier: Record<string, unknown> = {}
        try {
            qualifier = JSON.parse(row.qualifier_json || "{}")
        } catch {
            qualifier = {}
        }
        counterValues.set(counterKey(row.dimension, qualifier), Number(row.value) || 0)
        if (row.dimension !== "battle.quest_clear") continue
        const questCategory = optionalNumber(qualifier.questCategory)
        const questId = optionalNumber(qualifier.questId)
        const mode = String(qualifier.mode ?? "any")
        if (questCategory !== undefined && questId !== undefined) {
            questClearCounters.set(
                `${questCategory}:${questId}:${mode}`,
                Number(row.value) || 0,
            )
        }
    }
    return { questClearCounters, counterValues }
}

function buildStats(
    playerId: number,
    category: number,
    missionIds?: readonly number[],
    shared: MissionEvaluationReadContext = new MissionEvaluationReadContext(playerId),
): DegreeContext {
    const selectedDefinitions = missionIds === undefined
        ? [...degreeDefinitions.values()]
        : missionIds
            .map(missionId => degreeDefinitions.get(missionId))
            .filter((definition): definition is DegreeDefinition => definition !== undefined)
    const conditionTypes = new Set(selectedDefinitions.map(definition => definition.conditionType))
    const specificCharacterIds = [...new Set(selectedDefinitions
        .filter(definition => definition.conditionType === 44 || definition.conditionType === 48)
        .map(definition => optionalNumber(definition.row[15]))
        .filter((characterId): characterId is number => characterId !== undefined))]
    const targetItemIds = [...new Set(selectedDefinitions
        .filter(definition => definition.conditionType === 37)
        .map(definition => optionalNumber(definition.row[13]))
        .filter((itemId): itemId is number => itemId !== undefined))]
    const needsQuestProgress = [14, 15, 16, 22, 23, 25, 26]
        .some(conditionType => conditionTypes.has(conditionType))
    const needsAllCharacters = [4, 5, 8, 9].some(conditionType => conditionTypes.has(conditionType))
        || selectedDefinitions.some(definition => (
            (definition.conditionType === 44 || definition.conditionType === 48)
            && optionalNumber(definition.row[15]) === undefined
        ))
    const needsAllManaNodes = conditionTypes.has(7)
        || selectedDefinitions.some(definition => (
            definition.conditionType === 48
            && optionalNumber(definition.row[15]) === undefined
        ))
    const needsCounters = [3, 14, 15, 16, 17, 19, 20, 23, 25, 26, 27, 28, 29, 30, 31, 34, 35, 36, 45, 92]
        .some(conditionType => conditionTypes.has(conditionType))
    const needsBattleCounters = conditionTypes.has(16)
        || conditionTypes.has(17)
        || conditionTypes.has(26)
    const player = shared.player
    const characters = needsAllCharacters
        ? getPlayerCharactersSync(playerId)
        : specificCharacterIds.length > 0
            ? getPlayerCharactersByIdsSync(playerId, specificCharacterIds)
            : {}
    const manaNodes = needsAllManaNodes
        ? getPlayerCharactersManaNodesSync(playerId)
        : conditionTypes.has(48) && specificCharacterIds.length > 0
            ? getPlayerCharactersManaNodesByIdsSync(playerId, specificCharacterIds)
            : {}
    const battleCounters = needsBattleCounters
        ? shared.battleCounters
        : {
            singlePlayCount: 0,
            singleClearCount: 0,
            multiPlayCount: 0,
            multiClearCount: 0,
            multiHostClearCount: 0,
            multiGuestClearCount: 0,
            singleRankSsCount: 0,
            rankSsCount: 0,
            rankSCount: 0,
            rankACount: 0,
            rankBCount: 0,
        }
    const rawQuestProgress = needsQuestProgress ? shared.questProgress : {}
    const questProgress: Record<string, PlayerQuestProgressEntry[]> = {}
    const flatQuestProgress: DegreeQuestProgressEntry[] = []
    const questProgressBySection = new Map<number, DegreeQuestProgressEntry[]>()
    const questProgressByQuestId = new Map<number, DegreeQuestProgressEntry[]>()
    const finishedQuestKeys = new Set<string>()
    for (const [sectionText, entries] of Object.entries(rawQuestProgress)) {
        const section = Number(sectionText)
        questProgress[sectionText] = entries.map(entry => ({
            questId: entry.questId,
            finished: entry.finished,
            clearRank: entry.clearRank,
            bestElapsedTimeMs: entry.bestElapsedTimeMs,
            leaderCharacterId: entry.leaderCharacterId,
            multiClearCount: entry.multiClearCount,
        }))
        for (const entry of entries) {
            const flattened = {
                section,
                questId: entry.questId,
                finished: entry.finished,
                hostFinished: entry.hostFinished,
                highScore: entry.highScore,
                clearRank: entry.clearRank,
                bestElapsedTimeMs: entry.bestElapsedTimeMs,
                leaderCharacterId: entry.leaderCharacterId,
                multiClearCount: entry.multiClearCount,
            }
            flatQuestProgress.push(flattened)
            const sectionEntries = questProgressBySection.get(section) ?? []
            sectionEntries.push(flattened)
            questProgressBySection.set(section, sectionEntries)
            const questEntries = questProgressByQuestId.get(entry.questId) ?? []
            questEntries.push(flattened)
            questProgressByQuestId.set(entry.questId, questEntries)
            if (entry.finished) finishedQuestKeys.add(`${section}:${entry.questId}`)
        }
    }
    const characterLevels = new Map<number, number>()
    const completedSecondManaBoardCharacterIds = new Set<number>()
    for (const [characterIdValue, character] of Object.entries(characters)) {
        const characterId = Number(characterIdValue)
        characterLevels.set(characterId, estimateCharacterLevel(characterId, character.exp))

        const secondBoard = getCharacterManaNodesSync(characterId, 2)
        if (!secondBoard) continue
        const requiredNodes = Object.keys(secondBoard).map(Number)
        if (requiredNodes.length === 0) continue
        const unlockedNodes = new Set(manaNodes[characterIdValue] ?? [])
        if (requiredNodes.every(nodeId => unlockedNodes.has(nodeId))) {
            completedSecondManaBoardCharacterIds.add(characterId)
        }
    }
    const counters = needsCounters
        ? loadCounterMaps(playerId, conditionTypes)
        : { questClearCounters: new Map<string, number>(), counterValues: new Map<string, number>() }
    const shopPurchases = conditionTypes.has(45) ? getPlayerShopPurchasesMapSync(playerId) : {}
    return {
        category,
        playerId,
        player,
        questProgress,
        totalQuestClears: 0,
        totalStories: 0,
        rankCounts: {},
        characters,
        manaNodes,
        equipment: conditionTypes.has(34) || conditionTypes.has(36)
            ? getPlayerEquipmentListSync(playerId)
            : {},
        items: conditionTypes.has(37) ? getPlayerItemsByIdsSync(playerId, targetItemIds) : {},
        collectedItemTotals: conditionTypes.has(37)
            ? getPlayerCollectedItemTotalsByIdsSync(playerId, targetItemIds)
            : {},
        flatQuestProgress,
        questProgressBySection,
        questProgressByQuestId,
        finishedQuestKeys,
        questMetricCache: new Map(),
        completedSecondBoards: completedSecondManaBoardCharacterIds,
        ...counters,
        treasureShopPurchaseCount: [...treasureShopItemIds].reduce(
            (total, shopItemId) => total + Math.max(0, shopPurchases[Number(shopItemId)] ?? 0),
            0,
        ),
        equippedAbilitySoulCount: conditionTypes.has(35)
            ? countEquippedAbilitySoulSlotsSync(playerId)
            : 0,
        battleCounters,
        degreeStats: {
            companionCount: Object.keys(characters).length,
            maxCharacterLevel: Math.max(0, ...characterLevels.values()),
            overLimitCount: Object.values(characters)
                .reduce((total, character) => total + character.overLimitStep, 0),
            manaBoardCount: Object.values(manaNodes)
                .reduce((total, nodes) => total + nodes.length, 0),
            secondManaBoardCompleteCount: completedSecondManaBoardCharacterIds.size,
            bondTokenCount: Object.values(characters)
                .reduce((total, character) => total
                    + character.bondTokenList.filter(token => token.status >= 2).length, 0),
            singleSsCount: battleCounters.singleRankSsCount,
            multiClearCount: battleCounters.multiClearCount,
            multiHostClearCount: battleCounters.multiHostClearCount,
            episodeClearCount: conditionTypes.has(21)
                ? countFinishedPlayerQuestsByCategorySync(playerId, 3)
                : 0,
            level100BondedCharacterIds: new Set(Object.entries(characters)
                .filter(([characterId, character]) => (
                    (characterLevels.get(Number(characterId)) ?? 0) >= 100
                    && character.bondTokenList.some(token => token.status >= 2)
                ))
                .map(([characterId]) => Number(characterId))),
            completedSecondManaBoardCharacterIds,
        },
    }
}

function getCharacterFavorProgress(
    characterId: number,
    character: PlayerCharacter | undefined,
): number {
    if (!character) return 0
    const asset = getCharacterDataSync(characterId)
    const expCaps = asset ? characterExpCaps[asset.rarity] : undefined
    const level100Exp = expCaps?.[expCaps.length - 1]
    const reachedLevel100 = level100Exp !== undefined && character.exp >= level100Exp
    const receivedBondToken = character.bondTokenList.some(token => token.status >= 2)
    return Number(reachedLevel100) + Number(receivedBondToken)
}

function questCategoriesForKind(kind: number | undefined): number[] {
    switch (kind) {
        case 0: return [1]
        case 1: return [4]
        case 2: return [2]
        case 3: return [6]
        case 4: return [14]
        case 5: return [7, 8]
        case 6: return [10]
        case 7: return [13]
        case 8: return [11]
        case 9: return [18]
        case 10: return [19]
        case 11: return [15]
        case 12: return [13, 14, 20]
        case 13: return [20]
        case 14: return [21]
        case 15: return [22]
        case 16: return [23]
        case 17: return [24]
        case 18: return [25]
        case 19: return [26]
        case 20: return [27]
        default: return []
    }
}

function resolveQuestFilter(row: DegreeRow): QuestFilter {
    const kind = optionalNumber(row[8])
    const eventOrChapter = optionalNumber(row[9])
    const bossId = optionalNumber(row[10])
    const questRankOrId = optionalNumber(row[11])
    const difficultyId = optionalNumber(row[12])
    const filter: QuestFilter = { categories: questCategoriesForKind(kind) }

    if (kind === 2) {
        if (bossId !== undefined && difficultyId !== undefined) {
            const requestedQuestId = 1_000_000 + bossId * 1_000 + difficultyId
            const availableQuestIds = bossQuestIdsByBoss.get(bossId) ?? []
            const resolvedQuestId = availableQuestIds.includes(requestedQuestId)
                ? requestedQuestId
                : availableQuestIds[availableQuestIds.length - 1]
            if (resolvedQuestId !== undefined) {
                filter.exactQuestIds = new Set([resolvedQuestId])
            } else {
                filter.bossId = bossId
            }
        } else if (bossId !== undefined) {
            filter.bossId = bossId
        }
        return filter
    }

    if (kind === 11) {
        const practiceIds = numberList(row[11])
        if (practiceIds.length > 0) filter.exactQuestIds = new Set(practiceIds)
        return filter
    }

    if (kind === 19 && eventOrChapter !== undefined) {
        filter.exactQuestIds = new Set(
            hardMultiQuestIdsByChallenge.get(eventOrChapter) ?? [eventOrChapter],
        )
        return filter
    }

    if (eventOrChapter !== undefined && questRankOrId !== undefined) {
        filter.exactQuestIds = new Set([eventOrChapter * 1_000 + questRankOrId])
    } else if (eventOrChapter !== undefined) {
        filter.eventPrefix = eventOrChapter
    }
    return filter
}

function matchesQuest(filter: QuestFilter, section: number, questId: number): boolean {
    if (filter.categories.length > 0 && !filter.categories.includes(section)) return false
    if (filter.exactQuestIds && !filter.exactQuestIds.has(questId)) return false
    if (filter.bossId !== undefined) {
        const actualBossId = Math.floor((questId - 1_000_000) / 1_000)
        if (actualBossId !== filter.bossId) return false
    }
    if (
        filter.eventPrefix !== undefined
        && Math.floor(questId / 1_000) !== filter.eventPrefix
    ) {
        return false
    }
    return true
}

function requestedBattleMode(row: DegreeRow): "single" | "multi" | "any" {
    const battleKind = optionalNumber(row[6])
    if (battleKind === 1) return "single"
    if (battleKind === 2) return "multi"
    return "any"
}

function matchingQuestProgress(
    ctx: DegreeContext,
    filter: QuestFilter,
): readonly DegreeQuestProgressEntry[] {
    let candidates: readonly DegreeQuestProgressEntry[]
    if (filter.exactQuestIds && filter.exactQuestIds.size > 0) {
        candidates = [...filter.exactQuestIds]
            .flatMap(questId => ctx.questProgressByQuestId.get(questId) ?? [])
    } else if (filter.categories.length > 0) {
        candidates = filter.categories.flatMap(section => ctx.questProgressBySection.get(section) ?? [])
    } else {
        candidates = ctx.flatQuestProgress
    }
    return candidates.filter(entry => matchesQuest(filter, entry.section, entry.questId))
}

function countQuestClears(
    ctx: DegreeContext,
    filter: QuestFilter,
    mode: "single" | "multi" | "any",
): number {
    let storedProgressCount = 0
    for (const entry of matchingQuestProgress(ctx, filter)) {
        if (!entry.finished) continue
        if (mode === "any" || (mode === "single" && isHistoricallySingleOnly(entry.section))) {
            storedProgressCount += 1
        }
    }

    let counterCount = 0
    for (const [key, value] of ctx.questClearCounters) {
        const [categoryText, questIdText, counterMode] = key.split(":")
        if (counterMode !== mode) continue
        const section = Number(categoryText)
        const questId = Number(questIdText)
        if (matchesQuest(filter, section, questId)) counterCount += value
    }
    return Math.max(storedProgressCount, counterCount)
}

function isHistoricallySingleOnly(section: number): boolean {
    return ![2, 8, 19, 26].includes(section)
}

function readCounter(
    ctx: DegreeContext,
    dimension: string,
    qualifier: Record<string, unknown> = {},
): number {
    return ctx.counterValues.get(counterKey(dimension, qualifier)) ?? 0
}

function completedChapter(ctx: DegreeContext, chapter: number): boolean {
    const requiredMain = mainQuestIdsByChapter.get(chapter) ?? []
    const requiredEx = exQuestIdsByChapter.get(chapter) ?? []
    if (requiredMain.length === 0 || requiredEx.length === 0) return false
    return requiredMain.every(id => ctx.finishedQuestKeys.has(`1:${id}`))
        && requiredEx.every(id => ctx.finishedQuestKeys.has(`4:${id}`))
}

function bestSingleClearTimeMs(ctx: DegreeContext): number | undefined {
    if (ctx.questMetricCache.has("bestSingleClearTimeMs")) {
        return ctx.questMetricCache.get("bestSingleClearTimeMs")
    }
    const counter = readCounter(ctx, "battle.best_clear_time_ms", { mode: "single" })
    const times = ctx.flatQuestProgress
        .filter(entry => entry.finished
            && isHistoricallySingleOnly(entry.section)
            && entry.bestElapsedTimeMs !== undefined)
        .map(entry => Number(entry.bestElapsedTimeMs))
        .filter(value => Number.isFinite(value) && value > 0)
    if (counter > 0) times.push(counter)
    const result = times.length > 0 ? Math.min(...times) : undefined
    ctx.questMetricCache.set("bestSingleClearTimeMs", result)
    return result
}

function maxHighScore(ctx: DegreeContext): number {
    const cached = ctx.questMetricCache.get("maxHighScore")
    if (cached !== undefined) return cached
    const result = Math.max(
        readCounter(ctx, "battle.max_score", { mode: "single" }),
        0,
        ...ctx.flatQuestProgress
            .filter(entry => isHistoricallySingleOnly(entry.section))
            .map(entry => Number(entry.highScore) || 0),
    )
    ctx.questMetricCache.set("maxHighScore", result)
    return result
}

function maxClearRankCount(ctx: DegreeContext, rank: number, mode: "single" | "any" = "any"): number {
    const cacheKey = `maxClearRankCount:${rank}:${mode}`
    const cached = ctx.questMetricCache.get(cacheKey)
    if (cached !== undefined) return cached
    const historical = ctx.flatQuestProgress
        .filter(entry => entry.finished
            && entry.clearRank === rank
            && (mode === "any" || isHistoricallySingleOnly(entry.section)))
        .length
    const counter = readCounter(ctx, "battle.rank_clear", { rank, mode })
    const result = Math.max(historical, counter)
    ctx.questMetricCache.set(cacheKey, result)
    return result
}

function countQuestRankClears(
    ctx: DegreeContext,
    filter: QuestFilter,
    rank: number,
    mode: "single" | "multi" | "any",
): number {
    let historical = 0
    let counter = 0
    for (const entry of matchingQuestProgress(ctx, filter)) {
        if (entry.finished
            && entry.clearRank === rank
            && (mode === "any" || (mode === "single" && isHistoricallySingleOnly(entry.section)))) {
            historical++
        }
        counter += readCounter(ctx, "battle.quest_rank_clear", {
            questCategory: entry.section,
            questId: entry.questId,
            rank,
            mode,
        })
    }
    return Math.max(historical, counter)
}

const SUPPORTED_FAMILIES = {
    playerRank: "degree_player_rank_growth_",
    companionCount: "degree_companion_add_",
    characterLevel: "degree_character_lv_growth_",
    overLimitCount: "degree_overlimit_growth_",
    manaBoardCount: "degree_manaboard_growth_",
    secondManaBoardCompleteCount: "degree_manaboard_all_growth_",
    bondTokenCount: "degree_proof_of_bond_get_",
    singleSsCount: "degree_rank_ss_clear_single_",
    multiClearCount: "degree_multi_battle_clear_",
    multiHostClearCount: "degree_multi_battle_by_host_clear_",
    episodeClearCount: "degree_character_episode_read_",
} as const

const SERVER_COMPUTED_CONDITION_TYPES = new Set([
    0, 1, 3, 4, 5, 7, 8, 9, 14, 15, 16, 17, 19, 20, 21, 22, 23, 25, 26,
    27, 28, 29, 30, 31, 34, 35, 36, 37, 39, 44, 45, 48, 92,
])

const CLIENT_REPORTED_CONDITION_TYPES = new Set([40, 41, 42, 43])

export function getDegreeMissionCoverageReport() {
    const definitions = getMissionMasterDefinitions(5)
    const conditionTypeCounts: Record<number, number> = {}
    for (const definition of definitions) {
        const conditionType = optionalNumber(definition.row[3])
        if (conditionType === undefined) continue
        conditionTypeCounts[conditionType] = (conditionTypeCounts[conditionType] ?? 0) + 1
    }
    const serverComputed = definitions.filter(definition => (
        SERVER_COMPUTED_CONDITION_TYPES.has(Number(definition.row[3]))
        || (
            Number(definition.row[3]) === 28
            && [0, 2, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16].includes(Number(definition.row[4]))
        )
    )).length
    const clientReported = definitions.filter(definition => (
        CLIENT_REPORTED_CONDITION_TYPES.has(Number(definition.row[3]))
    )).length
    return {
        total: definitions.length,
        serverComputed,
        clientReported,
        persistedOnly: definitions.length - serverComputed - clientReported,
        conditionTypeCounts,
    }
}

/** Reverse-index title missions by the master-data condition they use. */
export function getDegreeMissionIdsForConditionTypes(
    conditionTypes: readonly number[],
    characterIds?: readonly number[],
    itemIds?: readonly number[],
): number[] {
    const requested = new Set(conditionTypes)
    const requestedCharacters = characterIds === undefined
        ? undefined
        : new Set(characterIds.filter(characterId => Number.isFinite(characterId) && characterId > 0))
    const requestedItems = itemIds === undefined
        ? undefined
        : new Set(itemIds.filter(itemId => Number.isFinite(itemId) && itemId > 0))
    if (requested.size === 0) return []
    return [...new Set([...requested]
        .flatMap(conditionType => degreeMissionIdsByConditionType.get(conditionType) ?? []))]
        .filter(missionId => {
            const definition = degreeDefinitions.get(missionId)
            if (!definition) return false
            if (
                requestedCharacters !== undefined
                && (definition.conditionType === 44 || definition.conditionType === 48)
            ) {
                const targetCharacterId = optionalNumber(definition.row[15])
                return targetCharacterId === undefined || requestedCharacters.has(targetCharacterId)
            }
            if (requestedItems !== undefined && definition.conditionType === 37) {
                const targetItemId = optionalNumber(definition.row[13])
                return targetItemId === undefined || requestedItems.has(targetItemId)
            }
            return true
        })
        .sort((left, right) => (
            (degreeMissionOrder.get(left) ?? 0) - (degreeMissionOrder.get(right) ?? 0)
        ))
}

export interface DegreeBattleTrigger {
    readonly questCategory: number
    readonly questId: number
    readonly mode: "single" | "multi"
    readonly isHost?: boolean
    readonly accomplished: boolean
    readonly clearRank?: number | null
}

const BATTLE_CLEAR_ONLY_DEGREE_CONDITION_TYPES = new Set([
    14, 15, 16, 17, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29, 30, 31, 92,
])

/**
 * Narrows quest-specific title families to the quest fact that just changed.
 * Generic cumulative title families remain candidates because the same battle
 * can update their counters or grant character/item rewards.
 */
export function getDegreeMissionIdsForBattle(
    conditionTypes: readonly number[],
    trigger: DegreeBattleTrigger,
    characterIds: readonly number[] = [],
    itemIds: readonly number[] = [],
): number[] {
    return getDegreeMissionIdsForConditionTypes(conditionTypes, characterIds, itemIds)
        .filter(missionId => {
            const definition = degreeDefinitions.get(missionId)
            if (!definition) return false
            const { conditionType, row, pattern } = definition
            if (!trigger.accomplished && BATTLE_CLEAR_ONLY_DEGREE_CONDITION_TYPES.has(conditionType)) {
                return false
            }
            if (conditionType === 15 || conditionType === 25) return trigger.mode === "single"
            if (conditionType === 16) return trigger.mode === "multi"
            if (conditionType === 17) return trigger.mode === "multi" && trigger.isHost === true
            if (conditionType === 19 || conditionType === 20 || conditionType === 92) {
                return trigger.mode === "multi"
            }
            if (conditionType === 21) return trigger.questCategory === 3
            if (conditionType === 14) {
                return trigger.accomplished
                    && trigger.mode === "single"
                    && matchesQuest(resolveQuestFilter(row), trigger.questCategory, trigger.questId)
            }
            if (conditionType === 22) {
                const chapter = optionalNumber(row[9])
                return trigger.accomplished
                    && (trigger.questCategory === 1 || trigger.questCategory === 4)
                    && chapter !== undefined
                    && Math.floor(trigger.questId / 1_000_000) === chapter
            }
            if (conditionType === 23) {
                const requestedMode = requestedBattleMode(row)
                return trigger.accomplished
                    && (requestedMode === "any" || requestedMode === trigger.mode)
                    && matchesQuest(resolveQuestFilter(row), trigger.questCategory, trigger.questId)
            }
            if (conditionType === 26) {
                if (!trigger.accomplished || trigger.clearRank !== 5) return false
                if (pattern.startsWith(SUPPORTED_FAMILIES.singleSsCount)) {
                    return trigger.mode === "single"
                }
                const filter = resolveQuestFilter(row)
                if (filter.exactQuestIds && filter.exactQuestIds.size > 0) {
                    const requestedMode = requestedBattleMode(row)
                    return (requestedMode === "any" || requestedMode === trigger.mode)
                        && matchesQuest(filter, trigger.questCategory, trigger.questId)
                }
                return trigger.mode === "single"
            }
            if (conditionType === 28) {
                const requestedMode = requestedBattleMode(row)
                return requestedMode === "any" || requestedMode === trigger.mode
            }
            return true
        })
}

export function getSpecificCharacterId(
    missionId: number,
    missionType: 44 | 48,
): number | undefined {
    const definition = getMissionMasterDefinition(5, missionId)
    if (!definition || Number(definition.row[3]) !== missionType) return undefined
    const characterId = Number(definition.row[15])
    return Number.isSafeInteger(characterId) && characterId > 0 ? characterId : undefined
}

function computeRecoverableProgress(
    definition: DegreeDefinition,
    ctx: DegreeContext,
): number | undefined {
    const { conditionType, row, description, pattern } = definition
    const stats = ctx.degreeStats
    switch (conditionType) {
        case 0:
            return ctx.player.totalLoginDays
        case 1:
            return getRankDegree(ctx.player.rankPoint)
        case 3:
            return readCounter(ctx, "shop.treasure_mana_spent")
        case 4:
            return stats?.companionCount
        case 5:
            return stats?.maxCharacterLevel
        case 7:
            return stats?.manaBoardCount
        case 8:
            return stats?.bondTokenCount
        case 9:
            return stats?.overLimitCount
        case 14:
            return countQuestClears(ctx, resolveQuestFilter(row), "single")
        case 15: {
            const secondsMatch = description.match(/(\d+)/)
            const seconds = secondsMatch ? Number(secondsMatch[1]) : undefined
            const bestMs = bestSingleClearTimeMs(ctx)
            return seconds !== undefined && bestMs !== undefined && bestMs <= seconds * 1000
                ? 1
                : 0
        }
        case 16: {
            return Math.max(
                stats?.multiClearCount ?? 0,
                readCounter(ctx, "battle.clear", { mode: "multi" }),
            )
        }
        case 17:
            return Math.max(
                stats?.multiHostClearCount ?? 0,
                readCounter(ctx, "battle.multi_role_clear", { role: "host" }),
            )
        case 19:
            return readCounter(ctx, "battle.multi_mvp")
        case 20:
            return readCounter(ctx, "battle.multi_rescue_clear")
        case 92:
            return readCounter(ctx, "battle.multi_newbie_rescue_clear")
        case 21:
            return stats?.episodeClearCount
        case 22: {
            const chapter = optionalNumber(row[9])
            return chapter !== undefined && completedChapter(ctx, chapter) ? 1 : 0
        }
        case 23:
            return countQuestClears(ctx, resolveQuestFilter(row), requestedBattleMode(row))
        case 25:
            return maxHighScore(ctx)
        case 26: {
            if (pattern.startsWith(SUPPORTED_FAMILIES.singleSsCount)) {
                return stats?.singleSsCount
            }
            const filter = resolveQuestFilter(row)
            if (filter.exactQuestIds && filter.exactQuestIds.size > 0) {
                return Number(countQuestRankClears(ctx, filter, 5, requestedBattleMode(row)) > 0)
            }
            return maxClearRankCount(ctx, 5, "single")
        }
        case 27:
            return readCounter(ctx, "battle.max_party_power")
        case 28: {
            const statisticKind = optionalNumber(row[4])
            const mode = requestedBattleMode(row)
            const kindByStatistic: Readonly<Record<number, string>> = {
                0: "weak_point",
                2: "dash",
                4: "skill",
                5: "fever",
                7: "enemy_kill",
                8: "emotion",
                9: "buff_companion",
                10: "heal_companion",
                11: "coffin_reduce",
                12: "clear_debuff_self",
                13: "debuff_enemy",
                14: "clear_buff_enemy",
                15: "fever_time_ms",
                16: "power_flip_lv3",
            }
            const kind = statisticKind === undefined ? undefined : kindByStatistic[statisticKind]
            if (!kind) return undefined
            const currentCounter = readCounter(ctx, "battle.stat", { kind, mode })
            const legacyCounter = mode === "any"
                ? readCounter(ctx, "battle.stat", { kind })
                : 0
            if (statisticKind === 2 && mode === "any") {
                return Math.max(
                    ctx.player.totalDashes,
                    currentCounter,
                    legacyCounter,
                )
            }
            // Fever-time counters and targets stay in milliseconds; the client converts them only for display.
            return Math.max(currentCounter, legacyCounter)
        }
        case 29: {
            const statisticKind = optionalNumber(row[5])
            if (statisticKind === 0) return readCounter(ctx, "battle.max_damage")
            if (statisticKind === 1) return readCounter(ctx, "battle.max_revival_coffin")
            return undefined
        }
        case 30:
            return Math.max(ctx.player.maxComboAchieved, readCounter(ctx, "battle.max_combo"))
        case 31:
            return readCounter(ctx, "battle.max_skill_chain")
        case 34:
            return Math.max(
                Object.values(ctx.equipment).reduce(
                    (sum, equipment) => sum + Math.max(0, equipment.level - 1),
                    0,
                ),
                readCounter(ctx, "equipment.awakening"),
            )
        case 35:
            return Math.max(
                ctx.equippedAbilitySoulCount,
                readCounter(ctx, "party.ability_soul_equip"),
            )
        case 36:
            return Math.max(
                Object.values(ctx.equipment)
                    .filter(equipment => equipment.level >= 5)
                    .length,
                readCounter(ctx, "equipment.lv5_count"),
            )
        case 37: {
            const itemId = optionalNumber(row[13])
            if (itemId === undefined) return undefined
            return Math.max(
                ctx.items[String(itemId)] ?? 0,
                ctx.collectedItemTotals[String(itemId)] ?? 0,
            )
        }
        case 39:
            return ctx.player.totalStaminaUsed
        case 44: {
            const characterId = optionalNumber(row[15])
            if (characterId === undefined) return 0
            return getCharacterFavorProgress(characterId, ctx.characters[String(characterId)])
        }
        case 45:
            return Math.max(
                ctx.treasureShopPurchaseCount,
                readCounter(ctx, "shop.treasure_purchase"),
            )
        case 48: {
            const characterId = optionalNumber(row[15])
            return characterId === undefined
                ? ctx.completedSecondBoards.size
                : Number(ctx.completedSecondBoards.has(characterId))
        }
        default:
            return undefined
    }
}

export const DegreeComputer: MissionComputer = {
    name: "Degree",

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
        const definition = degreeDefinitions.get(missionId)
        if (definition) {
            const recoverable = computeRecoverableProgress(definition, ctx as DegreeContext)
            if (recoverable !== undefined) return Math.max(dbProgress, recoverable)
        }

        const pattern = getMissionPattern(5, missionId)
        const stats = ctx.degreeStats
        if (pattern.startsWith(SUPPORTED_FAMILIES.playerRank)) return getRankDegree(ctx.player.rankPoint)
        if (!stats) return dbProgress
        const bondCharacterId = getSpecificCharacterId(missionId, 44)
        if (bondCharacterId !== undefined) {
            return Math.max(dbProgress, stats.level100BondedCharacterIds.has(bondCharacterId) ? 1 : 0)
        }
        const secondManaBoardCharacterId = getSpecificCharacterId(missionId, 48)
        if (secondManaBoardCharacterId !== undefined) {
            return Math.max(
                dbProgress,
                stats.completedSecondManaBoardCharacterIds.has(secondManaBoardCharacterId) ? 1 : 0,
            )
        }
        if (pattern.startsWith(SUPPORTED_FAMILIES.companionCount)) return stats.companionCount
        if (pattern.startsWith(SUPPORTED_FAMILIES.characterLevel)) {
            return Math.max(dbProgress, stats.maxCharacterLevel)
        }
        if (pattern.startsWith(SUPPORTED_FAMILIES.overLimitCount)) return stats.overLimitCount
        if (pattern.startsWith(SUPPORTED_FAMILIES.manaBoardCount)) return stats.manaBoardCount
        if (pattern.startsWith(SUPPORTED_FAMILIES.secondManaBoardCompleteCount)) {
            return Math.max(dbProgress, stats.secondManaBoardCompleteCount)
        }
        if (pattern.startsWith(SUPPORTED_FAMILIES.bondTokenCount)) return stats.bondTokenCount
        if (pattern.startsWith(SUPPORTED_FAMILIES.singleSsCount)) return stats.singleSsCount
        if (pattern.startsWith(SUPPORTED_FAMILIES.multiClearCount)) {
            return Math.max(dbProgress, stats.multiClearCount)
        }
        if (pattern.startsWith(SUPPORTED_FAMILIES.multiHostClearCount)) {
            return Math.max(dbProgress, stats.multiHostClearCount)
        }
        if (pattern.startsWith(SUPPORTED_FAMILIES.episodeClearCount)) {
            return Math.max(dbProgress, stats.episodeClearCount)
        }
        return dbProgress
    },
}
