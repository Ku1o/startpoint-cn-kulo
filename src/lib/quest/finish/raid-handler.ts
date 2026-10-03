import { RushEventBattleType } from "../../../data/types"
import { QuestCategory } from "../../types"
import {
    getRaidEventGlobalBossSync,
    getRaidEventQuestKillCountSync,
    recordRaidEventClearSync,
} from "../../raidEventGlobal"
import { grantEligibleRaidEventDegreesSync } from "../../activity-degree-rewards"
import { gameVerboseLog } from "../../game-logging"
import { measureServerWork } from "../../server-work-performance"

export interface RaidEventFinishData {
    auto_start_point: number
    is_out_of_period: boolean
    quest_boss: {
        kill_count: number
    }
    raid_boss: {
        hp_percentage: number
        total_kill_count: number
    }
    new_degree_ids: number[]
}

export function handleRaidEventFinish(params: {
    questCategory: number
    questAccomplished: boolean
    activeEventId: number | undefined
    playId: string
    party: { characters: ({ id: number | null } | null)[], unison_characters: ({ id: number | null } | null)[], equipments: ({ id: number | null } | null)[], ability_soul_ids: (number | null)[] }
    playerId: number
    questId: number
    getEvoLevelsFn: (playerId: number, charIds: (number | null)[]) => (number | null)[]
    insertPartyFn: (playerId: number, eventId: number, partyData: {
        characterIds: (number | null)[]
        unisonCharacterIds: (number | null)[]
        equipmentIds: (number | null)[]
        abilitySoulIds: (number | null)[]
        evolutionImgLevels: (number | null)[]
        unisonEvolutionImgLevels: (number | null)[]
        battleType: RushEventBattleType
        round: number
    }) => void
}): RaidEventFinishData | null {
    const {
        questCategory,
        questAccomplished,
        activeEventId,
        playId,
        party,
        playerId,
        questId,
        getEvoLevelsFn,
        insertPartyFn,
    } = params

    if (questCategory !== QuestCategory.RAID_EVENT || !activeEventId) return null

    const characterIds = party.characters.map(val => val?.id ?? null)
    const unisonCharacterIds = party.unison_characters.map(val => val?.id ?? null)
    const evolutionImgLevels = getEvoLevelsFn(playerId, characterIds)
    const unisonEvolutionImgLevels = getEvoLevelsFn(playerId, unisonCharacterIds)

    insertPartyFn(playerId, activeEventId, {
        characterIds, unisonCharacterIds,
        equipmentIds: party.equipments.map(val => val?.id ?? null),
        abilitySoulIds: party.ability_soul_ids,
        evolutionImgLevels,
        unisonEvolutionImgLevels,
        battleType: RushEventBattleType.FOLDER,
        round: questId
    })

    // A successful clear gets both values from the atomic ledger update below.
    // Avoid reading the global state and the quest count once before entering
    // that transaction and then reading them again inside it. Failed battles
    // still use the read-only path because no ledger update is needed.
    let boss: ReturnType<typeof getRaidEventGlobalBossSync>
    let questKillCount: number
    let newDegreeIds: number[] = []
    if (questAccomplished) {
        const result = measureServerWork("raid.finish", () => recordRaidEventClearSync({
            eventId: activeEventId,
            playId,
            playerId,
            questId,
        }))
        boss = result.boss
        questKillCount = result.questKillCount
        newDegreeIds = measureServerWork(
            "raid.degree",
            () => grantEligibleRaidEventDegreesSync(playerId, activeEventId),
        )
        gameVerboseLog(() =>
            `[RAID] clear: eventId=${activeEventId} questId=${questId} `
            + `playId=${playId} counted=${result.counted} weight=${result.questWeight} `
            + `weighted=${boss.weightedKillCount}/${boss.requiredKillCount} `
            + `hp=${boss.hpPercentage} total=${boss.totalKillCount}`
        )
    } else {
        boss = getRaidEventGlobalBossSync(activeEventId)
        questKillCount = getRaidEventQuestKillCountSync(activeEventId, questId)
    }

    return {
        auto_start_point: 0,
        is_out_of_period: false,
        quest_boss: {
            kill_count: questKillCount,
        },
        raid_boss: {
            hp_percentage: boss.hpPercentage,
            total_kill_count: boss.totalKillCount,
        },
        new_degree_ids: newDegreeIds,
    }
}
