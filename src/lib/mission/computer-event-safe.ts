import { getMissionMasterDefinition, getMissionMasterDefinitions } from "./master-data"
import { MissionEvaluationReadContext } from "./evaluation-context"
import type { CategoryContext, MissionComputer } from "./types"

const GET_ITEM_COUNT_PATTERN_TYPE = 37

export function getEventItemMissionItemId(missionId: number): number | undefined {
    const row = getMissionMasterDefinition(3, missionId)?.row
    if (!row || Number(row[2]) !== GET_ITEM_COUNT_PATTERN_TYPE) return undefined
    const itemId = Number(row[12])
    return Number.isSafeInteger(itemId) && itemId > 0 ? itemId : undefined
}

const eventItemMissionIdsByItemId = new Map<number, number[]>()
for (const definition of getMissionMasterDefinitions(3)) {
    const itemId = getEventItemMissionItemId(definition.missionId)
    if (itemId === undefined) continue
    const missionIds = eventItemMissionIdsByItemId.get(itemId) ?? []
    missionIds.push(definition.missionId)
    eventItemMissionIdsByItemId.set(itemId, missionIds)
}

export function getEventItemMissionIdsForItems(itemIds: readonly number[]): number[] {
    return [...new Set(itemIds.flatMap(itemId => eventItemMissionIdsByItemId.get(itemId) ?? []))]
}

export const EventSafeComputer: MissionComputer = {
    name: "EventSafe",

    buildContext(
        playerId: number,
        category: number,
        _evaluationTime: Date,
        _missionIds?: readonly number[],
        shared: MissionEvaluationReadContext = new MissionEvaluationReadContext(playerId),
    ): CategoryContext {
        const player = shared.player
        return {
            category,
            playerId,
            player,
            questProgress: {},
            totalQuestClears: 0,
            totalStories: 0,
            rankCounts: {},
            collectedItemTotals: shared.collectedItemTotals,
        }
    },

    compute(missionId: number, ctx: CategoryContext, dbProgress: number): number {
        const itemId = getEventItemMissionItemId(missionId)
        if (itemId === undefined) return dbProgress
        return Math.max(dbProgress, ctx.collectedItemTotals?.[String(itemId)] ?? 0)
    },
}
