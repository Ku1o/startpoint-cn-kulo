import type { FinishContext } from "../quest/finish/types"
import { getPlayerCategoryMissionsSync, updatePlayerCategoryMissionSync } from "../../data/domains/mission"
import { getMissionMasterDefinitions, isMissionDefinitionEnabledAt } from "./master-data"
import { summarizeBattleStatistics } from "./events"
import { matchesActiveMissionQuestRange } from "./active-reconciliation"
import { getMissionFinalTargetProgress } from "./stages"
import { refreshCollectTargetMissionProgressSync } from "./collect-progress"
import { contentDecision } from "../content-operations"

const CONDITIONS = new Set([14, 16, 17, 18, 23, 26, 28, 31])
const battleDefinitions = getMissionMasterDefinitions(4).filter(definition => CONDITIONS.has(Number(definition.row[4])))

function matchesRange(row: readonly unknown[], context: FinishContext): boolean {
    if (row[13] !== undefined && row[13] !== "(None)" && row[13] !== "") return false
    // Both generated types use the same QuestRange constructors, at different
    // CSV offsets. Keep this adapter confined to the four selector columns.
    const range: unknown[] = []
    for (let index = 0; index < 4; index++) range[34 + index] = row[9 + index] === "" ? "(None)" : row[9 + index]
    const category = Number(row[9]) === 5 && context.questCategory === 8 ? 7 : context.questCategory
    return matchesActiveMissionQuestRange(range, category, context.questId)
}

/** Called only by a committed finish transaction; no lifetime counter rebasing. */
export function recordCollectMissionBattleFacts(context: FinishContext, at: Date): number[] {
    if (!context.questAccomplished) return []
    const statistics = summarizeBattleStatistics(context.statistics)
    const stats: Readonly<Record<number, number>> = { 0: statistics.weakPointDestroyCount, 1: statistics.powerFlipCount,
        2: statistics.dashCount, 4: statistics.skillCount, 5: statistics.feverCount, 7: statistics.enemyKillCount }
    let current: ReturnType<typeof getPlayerCategoryMissionsSync> | undefined
    const changed: number[] = []
    const parentGates = new Map<number, boolean | null>()
    const realNow = Date.now()
    for (const definition of battleDefinitions) {
        if (definition.eventId === undefined) continue
        if (!parentGates.has(definition.eventId)) parentGates.set(definition.eventId,
            contentDecision("collect_item_event", definition.eventId, "enter", realNow))
        if (parentGates.get(definition.eventId) === false) continue
        if (!isMissionDefinitionEnabledAt(definition, at, definition.eventId)) continue
        const row = definition.row, condition = Number(row[4])
        if (!matchesRange(row, context)) continue
        if (condition === 14 && context.isMulti === true) continue
        if (condition === 16 && context.isMulti !== true) continue
        if (condition === 17 && (context.isMulti !== true || context.isMultiHost !== true)) continue
        if (condition === 18 && (context.isMulti !== true || context.isMultiHost !== false)) continue
        if ([23, 26, 28].includes(condition)) {
            const kind = Number(row[7])
            if (!(kind === 3 || kind === 2 && context.isMulti === true || kind === 1 && context.isMulti !== true)) continue
        }
        if (condition === 26 && context.clearRank !== 5) continue
        const value = condition === 28 ? stats[Number(row[5])]
            : condition === 31 ? statistics.maxSkillChainCount : 1
        if (!Number.isSafeInteger(value) || value <= 0) continue
        current ??= getPlayerCategoryMissionsSync(context.playerId, 4)
        const before = current[String(definition.missionId)]?.progress ?? 0
        const next = condition === 31 ? Math.max(before, value) : before + value
        const target = getMissionFinalTargetProgress(4, definition.missionId)
        const progress = Math.max(before, Math.min(next, target ?? Number.MAX_SAFE_INTEGER))
        if (!Number.isSafeInteger(progress) || progress === before) continue
        updatePlayerCategoryMissionSync(context.playerId, 4, definition.missionId, progress)
        changed.push(definition.missionId)
    }
    return [...new Set([...changed, ...refreshCollectTargetMissionProgressSync(context.playerId, at)])]
}
