import { getPlayerCategoryMissionsSync, incrementPlayerCategoryMissionSync, updatePlayerCategoryMissionSync } from "../../data/domains/mission"
import type { FinishContext } from "../quest/finish/types"
import { getMissionMasterDefinitions, isMissionDefinitionEnabledAt } from "./master-data"
import { summarizeBattleStatistics } from "./events"
import { contentMissionDecision } from "../content-operations"
import { getMissionFinalTargetProgress } from "./stages"

const QUEST_CATEGORY_BY_RANGE_KIND: Readonly<Record<number, number | readonly number[]>> = Object.freeze({
    2: 2,
    5: [7, 8],
    7: 13,
    8: 11,
    10: 19,
    15: 22,
    16: 23,
    17: 24,
})

function parseSelector(value: unknown): ReadonlySet<number> | null {
    if (value === undefined || value === null || value === "" || value === "(None)") return null
    const values = String(value).split(",").map(Number)
    if (values.some(value => !Number.isSafeInteger(value))) return new Set()
    return new Set(values)
}

function matchesSelector(selector: ReadonlySet<number> | null, value: number): boolean {
    return selector === null || selector.has(value)
}

function matchesQuestRange(row: readonly unknown[], questCategory: number, questId: number): boolean {
    const rangeKind = Number(row[8])
    const categories = QUEST_CATEGORY_BY_RANGE_KIND[rangeKind]
    if (!(Array.isArray(categories) ? categories.includes(questCategory) : categories === questCategory)) return false
    if (row[12] !== undefined && row[12] !== "" && row[12] !== "(None)") return false

    if (rangeKind === 2) {
        const first = Math.floor(questId / 1_000_000)
        const remainder = questId % 1_000_000
        const second = Math.floor(remainder / 1_000)
        const third = remainder % 1_000
        return matchesSelector(parseSelector(row[9]), first)
            && matchesSelector(parseSelector(row[10]), second)
            && matchesSelector(parseSelector(row[11]), third)
    }

    const first = Math.floor(questId / 1_000)
    const second = questId % 1_000
    return matchesSelector(parseSelector(row[9]), first)
        && matchesSelector(parseSelector(row[11]), second)
}

/** Count accepted finish statistics in the active week, including failed battles.
 * The enclosing finish transaction owns replay prevention and rollback.
 */
export function recordPassWeeklyEmotionFacts(context: FinishContext, evaluationTime: Date): void {
    const count = summarizeBattleStatistics(context.statistics).emotionCount
    if (count <= 0) return
    for (const definition of getMissionMasterDefinitions(7)) {
        if (definition.patternType === 85 && isMissionDefinitionEnabledAt(definition, evaluationTime)) {
            incrementPlayerCategoryMissionSync(context.playerId, 7, definition.missionId, count)
        }
    }
}

export function recordPassMissionBattleFacts(
    context: FinishContext,
    evaluationTime: Date,
): number[] {
    if (!context.questAccomplished) return []

    recordPassCompletedRescueBattleFact(context, evaluationTime)
    const dashCount = summarizeBattleStatistics(context.statistics).dashCount
    for (const category of [6, 7]) {
        let current: ReturnType<typeof getPlayerCategoryMissionsSync> | undefined
        for (const definition of getMissionMasterDefinitions(category)) {
            const pattern = definition.patternType
            const amount = pattern === 16 ? (context.isMulti === true ? 1 : 0)
                : category === 6 && pattern === 14 ? (context.isMulti === true ? 0 : 1)
                : category === 6 && pattern === 28 ? dashCount : 0
            if (!Number.isSafeInteger(amount) || amount <= 0
                || contentMissionDecision(category, definition.missionId, "enter") !== true
                || !isMissionDefinitionEnabledAt(definition, evaluationTime)) continue
            current ??= getPlayerCategoryMissionsSync(context.playerId, category)
            const before = current[String(definition.missionId)]?.progress ?? 0
            const target = getMissionFinalTargetProgress(category, definition.missionId)
            const progress = Math.max(before, Math.min(before + amount, target ?? Number.MAX_SAFE_INTEGER))
            if (!Number.isSafeInteger(progress) || progress === before) continue
            updatePlayerCategoryMissionSync(context.playerId, category, definition.missionId, progress)
        }
    }

    const matchedMissionIds: number[] = []
    for (const definition of getMissionMasterDefinitions(8)) {
        const patternType = definition.patternType
        if (patternType !== 16 && patternType !== 23) continue
        if (patternType === 16 && context.isMulti !== true) continue
        if (patternType === 23) {
            const battleKind = Number(definition.row[6])
            if (battleKind !== 3
                && !(battleKind === 2 && context.isMulti === true)
                && !(battleKind === 1 && context.isMulti !== true)) continue
        }
        if (!isMissionDefinitionEnabledAt(definition, evaluationTime)
            || !matchesQuestRange(definition.row, context.questCategory, context.questId)) continue
        incrementPlayerCategoryMissionSync(context.playerId, 8, definition.missionId, 1)
        matchedMissionIds.push(definition.missionId)
    }
    return matchedMissionIds
}

/** Also used by the custom five-boss final reward callback, never its phase signals. */
export function recordPassCompletedRescueBattleFact(
    context: Pick<FinishContext, "playerId" | "questAccomplished" | "isMulti" | "isMultiHost" | "isRegisteredRescue">,
    evaluationTime: Date,
): void {
    if (!context.questAccomplished || context.isMulti !== true
        || context.isMultiHost !== false || context.isRegisteredRescue !== true) return
    let current: ReturnType<typeof getPlayerCategoryMissionsSync> | undefined
    for (const definition of getMissionMasterDefinitions(7)) {
        if (definition.patternType !== 20
            || contentMissionDecision(7, definition.missionId, "enter") !== true
            || !isMissionDefinitionEnabledAt(definition, evaluationTime)) continue
        current ??= getPlayerCategoryMissionsSync(context.playerId, 7)
        const before = current[String(definition.missionId)]?.progress ?? 0
        const target = getMissionFinalTargetProgress(7, definition.missionId)
        const progress = Math.max(before, Math.min(before + 1, target ?? Number.MAX_SAFE_INTEGER))
        if (Number.isSafeInteger(progress) && progress > before) updatePlayerCategoryMissionSync(context.playerId, 7, definition.missionId, progress)
    }
}
