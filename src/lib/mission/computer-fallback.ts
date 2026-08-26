// Fallback computer — returns DB-stored progress for unhandled categories

import { MissionEvaluationReadContext } from "./evaluation-context"
import type { MissionComputer, CategoryContext } from "./types"

function buildMinimal(
    playerId: number,
    category: number,
    shared: MissionEvaluationReadContext,
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
    }
}

export const FallbackComputer: MissionComputer = {
    name: "Fallback",

    buildContext(
        playerId: number,
        category: number,
        _evaluationTime: Date,
        _missionIds?: readonly number[],
        shared: MissionEvaluationReadContext = new MissionEvaluationReadContext(playerId),
    ): CategoryContext {
        return buildMinimal(playerId, category, shared)
    },

    compute(_missionId: number, _ctx: CategoryContext, dbProgress: number): number {
        return dbProgress
    },
}
