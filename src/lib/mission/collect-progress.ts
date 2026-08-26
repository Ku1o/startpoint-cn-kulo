import { getMissionMasterDefinition } from "./master-data"
import { MissionEvaluationReadContext } from "./evaluation-context"
import type { CategoryContext, MissionComputer } from "./types"

export function getCollectMissionItemId(missionId: number): number | undefined {
    const rawItemId = getMissionMasterDefinition(4, missionId)?.row[14]
    const itemId = Number(rawItemId)
    return Number.isSafeInteger(itemId) && itemId > 0 ? itemId : undefined
}

export const CollectComputer: MissionComputer = {
    name: "CollectItemEvent",

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
        const itemId = getCollectMissionItemId(missionId)
        if (itemId === undefined) return dbProgress
        return Math.max(dbProgress, ctx.collectedItemTotals?.[String(itemId)] ?? 0)
    },
}
