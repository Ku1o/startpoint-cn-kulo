import type { Database } from "better-sqlite3"
import { cachedStatement } from "../../lib/cached-statement"
import { deserializeBoolean, deserializeNumberList } from "../utils/primitives"
import { gameVerboseLog } from "../../lib/game-logging"
import { PartyCategory, PlayerCharacter, PlayerCharacterBondToken, PlayerCharacterExBoost, RawPlayerCharacter, RawPlayerCharacterBondToken, RawPlayerCharacterManaNode, PlayerParty, PlayerPartyGroup, RawPlayerParty, RawPlayerPartyGroup, PlayerQuestProgress, RawPlayerQuestProgress } from "../types"

export function buildCharacterBondToken(
    rawBondToken: RawPlayerCharacterBondToken
): PlayerCharacterBondToken {
    return {
        manaBoardIndex: rawBondToken.mana_board_index,
        status: rawBondToken.status
    }
}
export function buildPlayerCharacterExBoost(
    exBoostStatusId: number | null,
    exBoostAbilityIdList: string | null
): PlayerCharacterExBoost | undefined {
    if (exBoostStatusId === null || exBoostAbilityIdList === null) return undefined
    return {
        statusId: exBoostStatusId,
        abilityIdList: deserializeNumberList(exBoostAbilityIdList)
    }
}
export function buildPlayerCharacter(
    rawCharacter: RawPlayerCharacter,
    bondTokens: PlayerCharacterBondToken[]
): PlayerCharacter {
    return {
        entryCount: rawCharacter.entry_count,
        evolutionLevel: rawCharacter.evolution_level,
        overLimitStep: rawCharacter.over_limit_step,
        protection: deserializeBoolean(rawCharacter.protection),
        joinTime: new Date(rawCharacter.join_time),
        updateTime: new Date(rawCharacter.update_time),
        exp: rawCharacter.exp,
        stack: rawCharacter.stack,
        manaBoardIndex: rawCharacter.mana_board_index,
        exBoost: buildPlayerCharacterExBoost(rawCharacter.ex_boost_status_id, rawCharacter.ex_boost_ability_id_list),
        illustrationSettings: rawCharacter.illustration_settings === null ? undefined : deserializeNumberList(rawCharacter.illustration_settings),
        bondTokenList: bondTokens
    }
}
export function readPlayerCharactersSync(
    database: Database,
    playerId: number
): Record<string, PlayerCharacter> {

    const rawCharacters = cachedStatement(database, `
    SELECT id, entry_count, evolution_level, over_limit_step, protection,
        join_time, update_time, exp, stack, mana_board_index, ex_boost_status_id,
        ex_boost_ability_id_list, illustration_settings
    FROM players_characters
    WHERE player_id = ?
    `).all(playerId) as RawPlayerCharacter[]

    // get bond tokens
    const rawBondTokens = cachedStatement(database, `
    SELECT mana_board_index, status, character_id
    FROM players_characters_bond_tokens
    WHERE player_id = ?
    ORDER BY character_id, mana_board_index
    `).all(playerId) as RawPlayerCharacterBondToken[]

    const bondBuckets: Record<string, PlayerCharacterBondToken[]> = {}

    for (const rawBondToken of rawBondTokens) {
        const characterId = rawBondToken.character_id.toString()
        let bucket = bondBuckets[characterId]
        if (!bucket) {
            bucket = []
            bondBuckets[characterId] = bucket
        }

        bucket.push(buildCharacterBondToken(rawBondToken))
    }

    const out: Record<string, PlayerCharacter> = {}

    for (const rawCharacter of rawCharacters) {
        const id = rawCharacter.id.toString()
        out[id] = buildPlayerCharacter(
            rawCharacter,
            bondBuckets[id] || []
        )
    }

    return out
}
export function readPlayerCharactersManaNodesSync(
    database: Database,
    playerId: number
): Record<string, number[]> {

    const rawNodes = cachedStatement(database, `
    SELECT value, character_id
    FROM players_characters_mana_nodes
    WHERE player_id = ?
    `).all(playerId) as RawPlayerCharacterManaNode[]

    const buckets: Record<string, number[]> = {}

    for (const rawNode of rawNodes) {
        const characterId = rawNode.character_id.toString()
        let bucket: number[] = buckets[characterId]
        if (!bucket) {
            bucket = []
            buckets[characterId] = bucket
        }

        bucket.push(rawNode.value)
    }

    return buckets
}
export function readPlayerPartyGroupListSync(
    database: Database,
    playerId: number,
    category: PartyCategory = PartyCategory.NORMAL
): Record<string, PlayerPartyGroup> {
    const db = database;
    const rawPartyGroups = cachedStatement(db, `
    SELECT id, color_id, category
    FROM players_party_groups
    WHERE player_id = ? AND category = ?
    `).all(playerId, category) as RawPlayerPartyGroup[]

    const rawParties = cachedStatement(db, `
    SELECT slot, name, character_id_1, character_id_2, character_id_3, unison_character_1,
        unison_character_2, unison_character_3, equipment_1, equipment_2, equipment_3,
        ability_soul_1, ability_soul_2, ability_soul_3, edited, group_id, category,
        current_battle_power, before_battle_power
    FROM players_parties
    WHERE player_id = ? AND category = ?
    `).all(playerId, category) as RawPlayerParty[]

    const groupLists: Record<string, Record<string, PlayerParty>> = {}
    for (const rawParty of rawParties) {
        const groupId = rawParty.group_id.toString()
        let bucket: Record<string, PlayerParty> = groupLists[groupId]
        if (!bucket) {
            bucket = {}
            groupLists[groupId] = bucket
        }
        bucket[rawParty.slot.toString()] = {
            name: rawParty.name,
            characterIds: [rawParty.character_id_1, rawParty.character_id_2, rawParty.character_id_3],
            unisonCharacterIds: [rawParty.unison_character_1, rawParty.unison_character_2, rawParty.unison_character_3],
            equipmentIds: [rawParty.equipment_1, rawParty.equipment_2, rawParty.equipment_3],
            abilitySoulIds: [rawParty.ability_soul_1, rawParty.ability_soul_2, rawParty.ability_soul_3],
            edited: deserializeBoolean(rawParty.edited),
            options: {
                allowOtherPlayersToHealMe: true
            },
            category: rawParty.category,
            currentBattlePower: rawParty.current_battle_power ?? 0,
            beforeBattlePower: rawParty.before_battle_power ?? 0
        }
    }

    const final: Record<string, PlayerPartyGroup> = {}
    for (const rawPartyGroup of rawPartyGroups) {
        const id = rawPartyGroup.id.toString()
        final[id] = {
            list: groupLists[id] || [],
            colorId: rawPartyGroup.color_id,
            category: rawPartyGroup.category
        }
    }
    // Log group summary
    gameVerboseLog(() => `[PARTY-READ] player=${playerId} groups=${Object.keys(final).length} totalParties=${rawParties.length}`)
    return final
}
export function buildPlayerQuestProgress(
    raw: RawPlayerQuestProgress
): PlayerQuestProgress {
    return {
        questId: raw.quest_id,
        finished: deserializeBoolean(raw.finished),
        hostFinished: deserializeBoolean(raw.host_finished ?? 0),
        unlocked: deserializeBoolean(raw.unlocked),
        highScore: raw.high_score,
        clearRank: raw.clear_rank,
        bestElapsedTimeMs: raw.best_elapsed_time_ms,
        leaderCharacterId: raw.leader_character_id,
        multiClearCount: raw.multi_clear_count,
        sPlusRewardReceived: deserializeBoolean(raw.s_plus_reward_received ?? 0)
    }
}
export function readPlayerQuestProgressSync(
    database: Database,
    playerId: number
): Record<string, PlayerQuestProgress[]> {
    const rawProgress = cachedStatement(database, `
    SELECT section, quest_id, finished, host_finished, unlocked, high_score, clear_rank, best_elapsed_time_ms, leader_character_id, multi_clear_count, s_plus_reward_received
    FROM players_quest_progress
    WHERE player_id = ?
    `).all(playerId) as RawPlayerQuestProgress[]

    const mapped: Record<string, PlayerQuestProgress[]> = {}

    for (const raw of rawProgress) {
        const section = raw.section.toString()
        let bucket: PlayerQuestProgress[] = mapped[section]
        if (!bucket) {
            bucket = []
            mapped[section] = bucket
        }
        bucket.push(buildPlayerQuestProgress(raw))
    }

    return mapped
}

export function readLoadSnapshot(database: Database, playerId: number) {
    return database.transaction(() => ({
        characterList: readPlayerCharactersSync(database, playerId),
        characterManaNodeList: readPlayerCharactersManaNodesSync(database, playerId),
        partyGroupList: readPlayerPartyGroupListSync(database, playerId),
        questProgress: readPlayerQuestProgressSync(database, playerId),
    }))()
}
export type LoadSnapshot = ReturnType<typeof readLoadSnapshot>
