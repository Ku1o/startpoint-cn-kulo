import {
    getPlayerCategoryMissionsForCategoriesSync,
    getPlayerCategoryMissionsForScopesSync,
    updatePlayerCategoryMissionBatchSync,
    updatePlayerCategoryMissionStageBatchSync,
} from "../../data/domains/mission"
import type { Player } from "../../data/types"
import { getPlayerDegreeIdsSync } from "../../data/domains/degree"
import { getComputer } from "./registry"
import { getCategoryMissionRewardStageDefinition } from "./rewards"
import { getCompletedStageNumbers, getMissionFinalTargetProgress, getMissionIdsByCategory, isMissionProgressComplete } from "./stages"
import { getMissionPattern, isMissionEnabledAt } from "./patterns"
import { MissionRewardGranter } from "./grants"
import { getMissionMasterDefinition } from "./master-data"
import { runPersistenceTransaction, runPersistenceTransactionSync, runWriterCommand } from "../persistence-coordinator"
import { MISSION_SETTLE_CATEGORIES, type MissionSettleCategoriesArgs } from "../persistence/command-names"
import { MissionEvaluationReadContext } from "./evaluation-context"
import { contentMissionDecision } from "../content-operations"

export interface MissionSettlementInfo {
    mission_category_id: number
    mission_id: number
    mission_reward_id: number
}

export interface MissionSettlementResult {
    missionInfo: MissionSettlementInfo[]
    itemList: Record<string, number>
    characterList: Object[]
    equipmentList: Object[]
    degreeIds: number[]
    passCardPoints: Record<string, number>
    userInfo?: Record<string, number>
}

export interface MissionSettlementProgress {
    readonly category: number
    readonly missionId: number
    readonly progress: number
}

export interface MissionSettlementWithProgressResult {
    readonly settlement: MissionSettlementResult
    readonly evaluatedProgress: readonly MissionSettlementProgress[]
}

export interface MissionSettlementScope {
    category: number
    eventId?: number
    /** Restrict evaluation to missions that this mutation can affect. */
    missionIds?: readonly number[]
}

interface EvaluatedMission {
    category: number
    missionId: number
    progress: number
    receivedStages: Record<string, boolean> | unknown[]
    dbProgress: number
    progressEnabled: boolean
}

interface PendingMissionReward {
    readonly mission: EvaluatedMission
    readonly stage: number
    readonly definition: NonNullable<ReturnType<typeof getCategoryMissionRewardStageDefinition>>
}

interface PreparedMissionPersistence {
    readonly progressUpdates: EvaluatedMission[]
    readonly pendingRewards: PendingMissionReward[]
    readonly missingLegacyDegreeIds: number[]
}

function applyDailyCompletionProgress(missions: EvaluatedMission[]): void {
    const dailyMissions = missions.filter(mission => mission.category === 2)
    if (dailyMissions.length === 0) return
    const byId = new Map(dailyMissions.map(mission => [mission.missionId, mission]))

    for (const mission of dailyMissions) {
        if (!mission.progressEnabled) continue
        if (!getMissionPattern(2, mission.missionId).startsWith("daily_quest_all_clear")) continue
        // Each generation declares its own prerequisite IDs. Historical
        // claim-only counters must not stand in for today's required tasks.
        const rawDependencies = getMissionMasterDefinition(2, mission.missionId)?.row[17]
        if (typeof rawDependencies !== "string" || !/^[1-9]\d*(?:,[1-9]\d*)*$/.test(rawDependencies)) continue
        const dependencies = [...new Set(rawDependencies.split(",").map(Number))]
        if (dependencies.some(id => !Number.isSafeInteger(id))) continue
        const completedCount = dependencies.filter(id => {
            const dependency = byId.get(id)
            return dependency?.progressEnabled
                && isMissionProgressComplete(2, id, dependency.progress)
        }).length
        mission.progress = Math.max(mission.dbProgress, completedCount)
    }
}

function evaluateMissionCategories(
    playerId: number,
    categories: readonly (number | MissionSettlementScope)[],
    evaluationTime: Date,
): { player: Player, evaluatedMissions: EvaluatedMission[] } {
    const evaluatedMissions: EvaluatedMission[] = []
    const evaluatedMissionKeys = new Set<string>()
    const scopes = new Map<string, MissionSettlementScope>()
    for (const entry of categories) {
        const scope = typeof entry === "number" ? { category: entry } : entry
        scopes.set(`${scope.category}:${scope.eventId ?? ""}`, scope)
    }
    const preparedScopes = [...scopes.values()].map(scope => ({
        scope,
        candidateMissionIds: scope.missionIds ?? getMissionIdsByCategory(scope.category),
    })).filter(entry => entry.candidateMissionIds.length > 0)
    const persistedByCategory = /^(0|false|no|off)$/i.test(process.env.MISSION_SCOPED_READS ?? "true")
        ? getPlayerCategoryMissionsForCategoriesSync(playerId, preparedScopes.map(entry => entry.scope.category))
        : getPlayerCategoryMissionsForScopesSync(playerId, preparedScopes.map(entry => ({
            category: entry.scope.category, missionIds: entry.candidateMissionIds,
        })))
    const readContext = new MissionEvaluationReadContext(playerId)
    const player = readContext.player

    for (const { scope, candidateMissionIds } of preparedScopes) {
        const { category, eventId } = scope
        const computer = getComputer(category)
        const persisted = persistedByCategory[String(category)] ?? {}
        // Title progress is monotonic and capped at its final target. Completed
        // titles need no fact scan, but still enter persistence preparation so
        // unreceived stages and missing legacy degree ownership can be repaired.
        const progressMissionIds = candidateMissionIds.filter(missionId => isMissionEnabledAt(category, missionId, evaluationTime, eventId))
        const factMissionIds = category === 5 ? progressMissionIds.filter(missionId => {
            if (!isMissionEnabledAt(category, missionId, evaluationTime, eventId)) return false
            const target = getMissionFinalTargetProgress(category, missionId)
            return target === undefined || (persisted[String(missionId)]?.progress ?? 0) < target
        }) : progressMissionIds
        const factMissionIdSet = new Set(factMissionIds)
        const context = factMissionIds.length > 0 ? computer.buildContext(
            playerId,
            category,
            evaluationTime,
            factMissionIds,
            readContext,
        ) : undefined
        for (const missionId of candidateMissionIds) {
            const progressEnabled = isMissionEnabledAt(category, missionId, evaluationTime, eventId)
            const claimOnly = contentMissionDecision(category, missionId, "claim") === true
                && isMissionEnabledAt(category, missionId, evaluationTime, eventId, "claim")
            if (!progressEnabled && !claimOnly) continue
            const missionKey = `${category}:${missionId}`
            if (evaluatedMissionKeys.has(missionKey)) continue
            evaluatedMissionKeys.add(missionKey)
            const current = persisted[String(missionId)]
            const dbProgress = current?.progress ?? 0
            const computed = context && factMissionIdSet.has(missionId)
                ? computer.compute(missionId, context, dbProgress) : dbProgress
            const finalTarget = getMissionFinalTargetProgress(category, missionId)
            const monotonicProgress = Math.max(0, dbProgress, Number.isFinite(computed) ? computed : 0)
            evaluatedMissions.push({
                category,
                missionId,
                progress: !progressEnabled ? dbProgress : finalTarget === undefined
                    ? monotonicProgress
                    // A target limits new progress; it must never lower a saved
                    // counter from an older content definition or active period.
                    : Math.max(dbProgress, Math.min(monotonicProgress, finalTarget)),
                receivedStages: current?.stages ?? [],
                dbProgress,
                progressEnabled,
            })
        }
    }
    applyDailyCompletionProgress(evaluatedMissions)
    return { player, evaluatedMissions }
}

function emptyMissionSettlementResult(): MissionSettlementResult {
    return {
        missionInfo: [],
        itemList: {},
        characterList: [],
        equipmentList: [],
        degreeIds: [],
        passCardPoints: {},
    }
}

function prepareMissionPersistence(
    playerId: number,
    evaluatedMissions: EvaluatedMission[],
): PreparedMissionPersistence {
    const progressUpdates = evaluatedMissions.filter(mission => mission.progress !== mission.dbProgress)
    const pendingRewards: PendingMissionReward[] = []
    const legacyDegreeIds = new Set<number>()
    for (const mission of evaluatedMissions) {
        for (const stage of getCompletedStageNumbers(mission.category, mission.missionId, mission.progress)) {
            const definition = getCategoryMissionRewardStageDefinition(mission.category, mission.missionId, stage)
            if (!definition) continue
            if (!Array.isArray(mission.receivedStages)
                && mission.receivedStages[String(stage)] === true) {
                if (mission.category === 5) {
                    for (const reward of definition.rewards) {
                        if (reward.kind === 6 && reward.degreeId !== undefined) {
                            legacyDegreeIds.add(reward.degreeId)
                        }
                    }
                }
                continue
            }
            if (contentMissionDecision(mission.category, mission.missionId, "claim") !== false) pendingRewards.push({ mission, stage, definition })
        }
    }
    const ownedDegrees = legacyDegreeIds.size > 0
        ? new Set(getPlayerDegreeIdsSync(playerId))
        : new Set<number>()
    return {
        progressUpdates,
        pendingRewards,
        missingLegacyDegreeIds: [...legacyDegreeIds].filter(degreeId => !ownedDegrees.has(degreeId)),
    }
}

function persistMissionEvaluation(
    playerId: number,
    player: Player,
    prepared: PreparedMissionPersistence,
): MissionSettlementResult {
    const granter = new MissionRewardGranter(playerId, player)
    const missionInfo: MissionSettlementInfo[] = []
    updatePlayerCategoryMissionBatchSync(
        playerId,
        prepared.progressUpdates
            .map(mission => ({
                category: mission.category,
                missionId: mission.missionId,
                progress: mission.progress,
            })),
    )
    for (const degreeId of prepared.missingLegacyDegreeIds) {
        granter.grantDegreeOwnershipOnly(degreeId)
    }
    updatePlayerCategoryMissionStageBatchSync(
        playerId,
        prepared.pendingRewards.map(({ mission, stage }) => ({
            category: mission.category,
            missionId: mission.missionId,
            stageId: stage,
            status: true,
        })),
    )
    for (const { mission, definition } of prepared.pendingRewards) {
        const passCardEventId = mission.category >= 6 && mission.category <= 8
            ? getMissionMasterDefinition(mission.category, mission.missionId)?.eventId
            : undefined
        granter.grant(definition.rewards, { passCardEventId })
        missionInfo.push({
            mission_category_id: mission.category,
            mission_id: mission.missionId,
            mission_reward_id: definition.missionRewardId,
        })
    }
    granter.persistPlayer()
    return {
        missionInfo,
        itemList: granter.itemList,
        characterList: granter.characterList,
        equipmentList: granter.equipmentList,
        degreeIds: granter.degreeList,
        passCardPoints: granter.passCardPoints,
        ...(granter.hasPlayerChanges() ? { userInfo: granter.getUserInfo() } : {}),
    }
}

function evaluatedProgressOf(evaluatedMissions: readonly EvaluatedMission[]): MissionSettlementProgress[] {
    return evaluatedMissions.map(mission => ({
        category: mission.category,
        missionId: mission.missionId,
        progress: mission.progress,
    }))
}

export function settleMissionCategoriesWithProgress(
    playerId: number,
    categories: readonly (number | MissionSettlementScope)[],
    evaluationTime: Date,
): MissionSettlementWithProgressResult {
    // Evaluate and authorize inside the same final transaction as grants and stages.
    return runPersistenceTransactionSync({
            domain: "mission", playerId, operation: "settle_categories_sync",
        }, () => {
            const evaluation = evaluateMissionCategories(playerId, categories, evaluationTime)
            const prepared = prepareMissionPersistence(playerId, evaluation.evaluatedMissions)
            const settlement = prepared.progressUpdates.length === 0 && prepared.pendingRewards.length === 0 && prepared.missingLegacyDegreeIds.length === 0
                ? emptyMissionSettlementResult() : persistMissionEvaluation(playerId, evaluation.player, prepared)
            return { settlement, evaluatedProgress: evaluatedProgressOf(evaluation.evaluatedMissions) }
        })
}

export function settleMissionCategories(
    playerId: number,
    categories: readonly (number | MissionSettlementScope)[],
    evaluationTime: Date,
): MissionSettlementResult {
    return settleMissionCategoriesWithProgress(playerId, categories, evaluationTime).settlement
}

export async function settleMissionCategoriesAsync(
    playerId: number,
    categories: readonly (number | MissionSettlementScope)[],
    evaluationTime: Date,
): Promise<MissionSettlementResult> {
    // The whole settlement (context scan plus persistence) is a registered
    // command so it can run inside the SQLite writer thread without holding the
    // main event loop. With the writer disabled the same registry entry runs
    // in-process and keeps the previous behaviour.
    return runWriterCommand<MissionSettleCategoriesArgs, MissionSettlementResult>(
        MISSION_SETTLE_CATEGORIES,
        {
            playerId,
            categories: [...categories],
            evaluationTimeMs: evaluationTime.getTime(),
        },
        { domain: "mission", playerId, operation: "settle_categories" },
    )
}
