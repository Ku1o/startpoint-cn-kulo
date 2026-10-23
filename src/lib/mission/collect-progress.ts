import { getMissionMasterDefinition, getMissionMasterDefinitions, isMissionDefinitionEnabledAt } from "./master-data"
import { MissionEvaluationReadContext } from "./evaluation-context"
import type { CategoryContext, MissionComputer } from "./types"
import { getPlayerCategoryMissionsSync, updatePlayerCategoryMissionSync } from "../../data/domains/mission"
import { getMissionFinalTargetProgress } from "./stages"
import { contentDecision } from "../content-operations"

interface CollectContext extends CategoryContext { collectProgress: Record<string, number> }

export function getCollectMissionItemId(missionId: number): number | undefined {
    const row = getMissionMasterDefinition(4, missionId)?.row
    if (!row || Number(row[4]) !== 37) return undefined
    const rawItemId = row[14]
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
    ): CollectContext {
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
            collectProgress: Object.fromEntries(Object.entries(getPlayerCategoryMissionsSync(playerId, 4))
                .map(([id, state]) => [id, state.progress])),
        }
    },

    compute(missionId: number, ctx: CategoryContext, dbProgress: number): number {
        const progress = (id: number, stored: number, seen: Set<number>): number => {
            if (seen.has(id)) return stored
            const definition = getMissionMasterDefinition(4, id)
            if (!definition) return stored
            const itemId = getCollectMissionItemId(id)
            if (itemId !== undefined) return Math.max(stored, ctx.collectedItemTotals?.[String(itemId)] ?? 0)
            if (Number(definition.row[4]) !== 13) return stored
            const raw = definition.row[19]
            if (typeof raw !== "string" || !/^\d+(,\d+)*$/.test(raw)) return stored
            const next = new Set(seen).add(id)
            const count = [...new Set(raw.split(",").map(Number))].filter(dependency => {
                if (getMissionMasterDefinition(4, dependency)?.eventId !== definition.eventId) return false
                const target = getMissionFinalTargetProgress(4, dependency)
                return target !== undefined && progress(dependency, (ctx as CollectContext).collectProgress?.[String(dependency)] ?? 0, next) >= target
            }).length
            return Math.max(stored, count)
        }
        return progress(missionId, dbProgress, new Set())
    },
}

/** Persist earned all-task progress before a publication change can close it. */
export function refreshCollectTargetMissionProgressSync(playerId: number, at: Date): number[] {
    const parentGates = new Map<number, boolean | null>()
    const realNow = Date.now()
    const definitions = getMissionMasterDefinitions(4).filter(definition => {
        if (Number(definition.row[4]) !== 13 || definition.eventId === undefined) return false
        if (!parentGates.has(definition.eventId)) parentGates.set(definition.eventId,
            contentDecision("collect_item_event", definition.eventId, "enter", realNow))
        return parentGates.get(definition.eventId) !== false && isMissionDefinitionEnabledAt(definition, at, definition.eventId)
    })
    if (definitions.length === 0) return []
    const context = CollectComputer.buildContext(playerId, 4, at, definitions.map(definition => definition.missionId)) as CollectContext
    const changed: number[] = []
    for (const definition of definitions) {
        const before = context.collectProgress[String(definition.missionId)] ?? 0
        const computed = CollectComputer.compute(definition.missionId, context, before)
        const progress = Math.max(before, Math.min(computed, getMissionFinalTargetProgress(4, definition.missionId) ?? Number.MAX_SAFE_INTEGER))
        if (progress <= before || !Number.isSafeInteger(progress)) continue
        updatePlayerCategoryMissionSync(playerId, 4, definition.missionId, progress)
        context.collectProgress[String(definition.missionId)] = progress
        changed.push(definition.missionId)
    }
    return changed
}
