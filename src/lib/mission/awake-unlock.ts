import { getPlayerCharacterAwakeUnlocksSync, upsertPlayerCharacterAwakeUnlockSync } from "../../data/domains/character_awake"
import type { CharacterAwakeUnlockMap } from "../../data/domains/character_awake"
import { getPlayerCharactersByIdsSync } from "../../data/domains/character"
import { getDb } from "../../data/db"
import { getCharacterIdFromMission } from "./character-queries"
import { getComputer } from "./registry"
import { getAwakeMissionRewardStageDefinition } from "./rewards"
import { getCompletedStageNumbers, getMissionIdsByCategory, getMissionStageIds } from "./stages"
import { getServerDate } from "../../utils"

export interface AwakeUnlockReconciliationResult {
    all: CharacterAwakeUnlockMap
    changed: CharacterAwakeUnlockMap
}

export interface AwakeUnlockProgress {
    missionId: number
    progress: number
}

export function reconcileAwakeUnlocksFromProgress(
    playerId: number,
    progressList: AwakeUnlockProgress[],
    persistedUnlocks: CharacterAwakeUnlockMap = getPlayerCharacterAwakeUnlocksSync(playerId),
): AwakeUnlockReconciliationResult {
    const changed: CharacterAwakeUnlockMap = new Map()
    const missing = progressList.flatMap(entry => {
        const characterId = getCharacterIdFromMission(entry.missionId)
        return getCompletedStageNumbers(9, entry.missionId, entry.progress).flatMap(stage => {
            const reward = getAwakeMissionRewardStageDefinition(entry.missionId, stage)?.specialReward
            return reward && String(reward.characterId) === characterId
                && (persistedUnlocks.get(characterId)?.[reward.boardIndex] ?? 0) < reward.awakeLevel
                ? [reward] : []
        })
    })
    if (missing.length === 0) return { all: persistedUnlocks, changed }

    getDb().transaction(() => {
        for (const reward of missing) {
            if (!upsertPlayerCharacterAwakeUnlockSync(
                playerId, reward.characterId, reward.boardIndex, reward.awakeLevel,
            )) continue
            const characterId = String(reward.characterId)
            const levels = changed.get(characterId) ?? {}
            levels[reward.boardIndex] = Math.max(levels[reward.boardIndex] ?? 0, reward.awakeLevel)
            changed.set(characterId, levels)
        }
    })()

    return {
        all: getPlayerCharacterAwakeUnlocksSync(playerId),
        changed,
    }
}

export function reconcileAwakeUnlocks(
    playerId: number,
    candidateCharacterIds?: number[]
): AwakeUnlockReconciliationResult {
    const all = getPlayerCharacterAwakeUnlocksSync(playerId)
    const candidateIds = candidateCharacterIds ? new Set(candidateCharacterIds.map(String)) : null
    // This function repairs unlock state, not consumable mission rewards.
    // A character already holding every configured level needs no fact reads.
    const missingMissionIds = getMissionIdsByCategory(9).filter(missionId => {
        const characterId = getCharacterIdFromMission(missionId)
        if (candidateIds && !candidateIds.has(characterId)) return false
        return getMissionStageIds(9, missionId).some(stage => {
            const reward = getAwakeMissionRewardStageDefinition(missionId, stage)?.specialReward
            return reward && String(reward.characterId) === characterId
                && (all.get(characterId)?.[reward.boardIndex] ?? 0) < reward.awakeLevel
        })
    })
    if (missingMissionIds.length === 0) return { all, changed: new Map() }
    const ownedCharacters = getPlayerCharactersByIdsSync(
        playerId, missingMissionIds.map(getCharacterIdFromMission).map(Number),
    )
    const ownedMissionIds = missingMissionIds.filter(id => ownedCharacters[getCharacterIdFromMission(id)])
    if (ownedMissionIds.length === 0) return { all, changed: new Map() }
    const computer = getComputer(9)
    const context = computer.buildContext(playerId, 9, getServerDate(), ownedMissionIds)
    const progressList: AwakeUnlockProgress[] = []

    for (const missionId of ownedMissionIds) {
        const dbProgress = context.persistedMissions?.[String(missionId)]?.progress ?? 0
        progressList.push({
            missionId,
            progress: computer.compute(missionId, context, dbProgress),
        })
    }

    return reconcileAwakeUnlocksFromProgress(playerId, progressList, all)
}
