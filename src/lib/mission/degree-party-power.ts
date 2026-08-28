import { getDb } from "../../data/db"
import { PartyCategory } from "../../data/types"
import { parseGlobalPartyId } from "../special-event-parties"
import { QuestCategory } from "../types"
import type { FinishContext } from "../quest/finish/types"
import { setMissionCounterMaxSync } from "./counters"

interface StoredPartyPowerRow {
    category: number
    current_battle_power: number
    character_id_1: number | null
    character_id_2: number | null
    character_id_3: number | null
    unison_character_1: number | null
    unison_character_2: number | null
    unison_character_3: number | null
    equipment_1: number | null
    equipment_2: number | null
    equipment_3: number | null
}

function partyCategoryForQuest(questCategory: number): PartyCategory {
    switch (questCategory) {
        case QuestCategory.CARNIVAL_EVENT:
            return PartyCategory.CARNIVAL
        case QuestCategory.RAID_EVENT:
            return PartyCategory.RAID
        case QuestCategory.RUSH_EVENT:
            return PartyCategory.RUSH
        default:
            return PartyCategory.NORMAL
    }
}

function partyIds(values: unknown, length: number): (number | null)[] | undefined {
    if (!Array.isArray(values)) return undefined
    return Array.from({ length }, (_, index) => {
        const value = Number((values[index] as { id?: unknown } | null)?.id)
        return Number.isSafeInteger(value) && value > 0 ? value : null
    })
}

function sameIds(actual: readonly (number | null)[], expected: readonly (number | null)[]): boolean {
    return actual.length === expected.length
        && actual.every((value, index) => value === expected[index])
}

function matchesClearedParty(row: StoredPartyPowerRow, party: FinishContext["party"]): boolean {
    const characters = partyIds(party?.characters, 3)
    if (!characters || !sameIds(characters, [
        row.character_id_1,
        row.character_id_2,
        row.character_id_3,
    ])) return false

    const unisons = partyIds(party?.unison_characters, 3)
    if (unisons && !sameIds(unisons, [
        row.unison_character_1,
        row.unison_character_2,
        row.unison_character_3,
    ])) return false

    const equipments = partyIds(party?.equipments, 3)
    if (equipments && !sameIds(equipments, [
        row.equipment_1,
        row.equipment_2,
        row.equipment_3,
    ])) return false

    return true
}

/** Resolves the client-computed power for the exact party that cleared a quest. */
export function getClearedPartyPowerSync(context: FinishContext): number {
    const parsedPartyId = parseGlobalPartyId(context.partySlot ?? context.player.partySlot)
    if (!parsedPartyId) return 0

    const rows = getDb().prepare(`
        SELECT category, current_battle_power,
               character_id_1, character_id_2, character_id_3,
               unison_character_1, unison_character_2, unison_character_3,
               equipment_1, equipment_2, equipment_3
        FROM players_parties
        WHERE player_id = ? AND group_id = ? AND slot = ?
    `).all(
        context.playerId,
        parsedPartyId.groupId,
        parsedPartyId.slot,
    ) as StoredPartyPowerRow[]

    const expectedCategory = partyCategoryForQuest(context.questCategory)
    rows.sort((left, right) => (
        Number(right.category === expectedCategory) - Number(left.category === expectedCategory)
    ))
    const matched = rows.find(row => matchesClearedParty(row, context.party))
    return Math.max(0, Math.trunc(Number(matched?.current_battle_power) || 0))
}

export function recordDegreePartyPowerClearSync(context: FinishContext): number {
    if (!context.questAccomplished) return 0
    const partyPower = getClearedPartyPowerSync(context)
    if (partyPower <= 0) return 0
    return setMissionCounterMaxSync(context.playerId, {
        dimension: "battle.max_party_power",
        scopeType: "lifetime",
        scopeKey: "all",
        qualifier: {},
    }, partyPower)
}
