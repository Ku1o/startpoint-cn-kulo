// Compute awake mission summary for /load response
// Returns active_mission_list (Array format for data.active_mission_list)

import { getPlayerCategoryMissionsSync } from "../../data/domains/mission"
import { getPlayerCharactersSync } from "../../data/domains/character"
import { getPlayerCharacterAwakeUnlocksSync } from "../../data/domains/character_awake"
import { getMissionIdsByCategory, getMissionStageIds } from "./stages"
import { getCharacterIdFromMission } from "./character-queries"
import type { CategoryContext } from "./types"
import { getServerDate } from "../../utils"
import type { Player, PlayerActiveMission, PlayerCharacter, PlayerQuestProgress } from "../../data/types"
import { AwakeComputer, buildAwakeContext } from "./computer-awake"

export interface AwakeMissionEntry {
    mission_id: number
    progress_value: number
    stages: { stage: number; received: boolean }[]
}

export interface AwakeSummary {
    activeMissionList: AwakeMissionEntry[]
    manaBoardAwakeMap: Map<string, Record<number, number>>
}

const awakeMissionIds = Object.freeze(getMissionIdsByCategory(9))
const awakeMissionIdsByCharacter = new Map<string, readonly number[]>()
const awakeStageIdsByMission = new Map<number, readonly number[]>()
for (const missionId of awakeMissionIds) {
    const characterId = getCharacterIdFromMission(missionId)
    const missionIds = awakeMissionIdsByCharacter.get(characterId) ?? []
    awakeMissionIdsByCharacter.set(characterId, Object.freeze([...missionIds, missionId]))
    awakeStageIdsByMission.set(missionId, Object.freeze(getMissionStageIds(9, missionId)))
}

export function computeAwakeSummary(
    playerId: number,
    snapshot: {
        readonly player?: Player
        readonly characterList?: Record<string, PlayerCharacter>
        readonly questProgress?: Record<string, PlayerQuestProgress[]>
        readonly activeMissions?: Record<string, PlayerActiveMission>
    } = {},
): AwakeSummary {
    const activeMissions = snapshot.activeMissions ?? getPlayerCategoryMissionsSync(playerId, 9)
    const playerChars = snapshot.characterList ?? getPlayerCharactersSync(playerId)
    const ctx = buildAwakeContext(playerId, undefined, {
        player: snapshot.player,
        characterList: playerChars,
        questProgress: snapshot.questProgress,
        persistedMissions: activeMissions,
    }) as CategoryContext

    const activeMissionList: AwakeMissionEntry[] = []
    const manaBoardAwakeMap = getPlayerCharacterAwakeUnlocksSync(playerId)

    for (const [charKId, missionIds] of awakeMissionIdsByCharacter) {
        if (!playerChars[charKId]) continue

        for (const missionId of missionIds) {
            const dbProgress = activeMissions[String(missionId)]?.progress ?? 0
            const progress = AwakeComputer.compute(missionId, ctx, dbProgress)
            const allStageIds = awakeStageIdsByMission.get(missionId) ?? []
            const persistedStages = activeMissions[String(missionId)]?.stages

            const stages = allStageIds.map(sid => ({
                stage: sid,
                received: !Array.isArray(persistedStages) && persistedStages?.[String(sid)] === true,
            }))

            activeMissionList.push({
                mission_id: missionId,
                progress_value: progress,
                stages,
            })
        }
    }

    return { activeMissionList, manaBoardAwakeMap }
}
