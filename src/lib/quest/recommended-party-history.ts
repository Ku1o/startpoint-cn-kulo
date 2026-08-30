import { getDb } from "../../data/db"
import { PartyCategory } from "../../data/types"
import { parseGlobalPartyId } from "../special-event-parties"
import { QuestCategory } from "../types"
import type { FinishContext } from "./finish/types"

export interface RecommendedQuestParty {
    party_name: string
    power: number
    character_id_1: number | null
    character_id_2: number | null
    character_id_3: number | null
    evolution_img_level_1: number | null
    evolution_img_level_2: number | null
    evolution_img_level_3: number | null
    unison_character_id_1: number | null
    unison_character_id_2: number | null
    unison_character_id_3: number | null
    unison_evolution_img_level_1: number | null
    unison_evolution_img_level_2: number | null
    unison_evolution_img_level_3: number | null
    equipment_id_1: number | null
    equipment_id_2: number | null
    equipment_id_3: number | null
    ability_soul_id_1: number | null
    ability_soul_id_2: number | null
    ability_soul_id_3: number | null
}

interface StoredPartyRow {
    player_id: number
    party_slot: number
    name: string
    current_battle_power: number
    character_id_1: number | null
    character_id_2: number | null
    character_id_3: number | null
    evolution_img_level_1: number | null
    evolution_img_level_2: number | null
    evolution_img_level_3: number | null
    unison_character_id_1: number | null
    unison_character_id_2: number | null
    unison_character_id_3: number | null
    unison_evolution_img_level_1: number | null
    unison_evolution_img_level_2: number | null
    unison_evolution_img_level_3: number | null
    equipment_id_1: number | null
    equipment_id_2: number | null
    equipment_id_3: number | null
    ability_soul_id_1: number | null
    ability_soul_id_2: number | null
    ability_soul_id_3: number | null
    category: number
}

interface StoredRecommendationRow {
    source_player_id: number
    battle_power: number
    party_payload: string
    cleared_at: number
}

type LegacyPartyRow = StoredPartyRow

interface RankedParty {
    sourcePlayerId: number
    clearedAt: number
    exactSnapshot: boolean
    party: RecommendedQuestParty
}

export interface RecommendedQuestPartyResult {
    parties: RecommendedQuestParty[]
    exactCandidateCount: number
    legacyCandidateCount: number
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

function normalizeId(value: unknown): number | null {
    const id = Number(value)
    return Number.isSafeInteger(id) && id > 0 ? id : null
}

function objectIds(values: unknown, length: number): (number | null)[] | undefined {
    if (!Array.isArray(values)) return undefined
    return Array.from({ length }, (_, index) => (
        normalizeId((values[index] as { id?: unknown } | null)?.id)
    ))
}

function scalarIds(values: unknown, length: number): (number | null)[] | undefined {
    if (!Array.isArray(values)) return undefined
    return Array.from({ length }, (_, index) => normalizeId(values[index]))
}

function sameIds(actual: readonly (number | null)[], expected: readonly (number | null)[]): boolean {
    return actual.length === expected.length
        && actual.every((value, index) => value === expected[index])
}

function matchesFinishedParty(row: StoredPartyRow, party: FinishContext["party"]): boolean {
    const characters = objectIds(party?.characters, 3)
    if (!characters || !sameIds(characters, [
        row.character_id_1,
        row.character_id_2,
        row.character_id_3,
    ])) return false

    const unisons = objectIds(party?.unison_characters, 3)
    if (unisons && !sameIds(unisons, [
        row.unison_character_id_1,
        row.unison_character_id_2,
        row.unison_character_id_3,
    ])) return false

    const equipments = objectIds(party?.equipments, 3)
    if (equipments && !sameIds(equipments, [
        row.equipment_id_1,
        row.equipment_id_2,
        row.equipment_id_3,
    ])) return false

    const abilitySouls = scalarIds((party as any)?.ability_soul_ids, 3)
    if (abilitySouls && !sameIds(abilitySouls, [
        row.ability_soul_id_1,
        row.ability_soul_id_2,
        row.ability_soul_id_3,
    ])) return false

    return true
}

function loadStoredPartiesSync(
    playerId: number,
    partySlot: number,
): StoredPartyRow[] {
    const parsedPartyId = parseGlobalPartyId(partySlot)
    if (!parsedPartyId) return []
    return getDb().prepare(`
        SELECT
            p.player_id,
            p.slot AS party_slot,
            p.name,
            p.current_battle_power,
            p.character_id_1,
            p.character_id_2,
            p.character_id_3,
            c1.evolution_level AS evolution_img_level_1,
            c2.evolution_level AS evolution_img_level_2,
            c3.evolution_level AS evolution_img_level_3,
            p.unison_character_1 AS unison_character_id_1,
            p.unison_character_2 AS unison_character_id_2,
            p.unison_character_3 AS unison_character_id_3,
            u1.evolution_level AS unison_evolution_img_level_1,
            u2.evolution_level AS unison_evolution_img_level_2,
            u3.evolution_level AS unison_evolution_img_level_3,
            p.equipment_1 AS equipment_id_1,
            p.equipment_2 AS equipment_id_2,
            p.equipment_3 AS equipment_id_3,
            p.ability_soul_1 AS ability_soul_id_1,
            p.ability_soul_2 AS ability_soul_id_2,
            p.ability_soul_3 AS ability_soul_id_3,
            p.category
        FROM players_parties p
        LEFT JOIN players_characters c1
            ON c1.player_id = p.player_id AND c1.id = p.character_id_1
        LEFT JOIN players_characters c2
            ON c2.player_id = p.player_id AND c2.id = p.character_id_2
        LEFT JOIN players_characters c3
            ON c3.player_id = p.player_id AND c3.id = p.character_id_3
        LEFT JOIN players_characters u1
            ON u1.player_id = p.player_id AND u1.id = p.unison_character_1
        LEFT JOIN players_characters u2
            ON u2.player_id = p.player_id AND u2.id = p.unison_character_2
        LEFT JOIN players_characters u3
            ON u3.player_id = p.player_id AND u3.id = p.unison_character_3
        WHERE p.player_id = ?
          AND p.group_id = ?
          AND p.slot = ?
    `).all(playerId, parsedPartyId.groupId, parsedPartyId.slot) as StoredPartyRow[]
}

function toRecommendedParty(row: StoredPartyRow): RecommendedQuestParty {
    return {
        party_name: row.name || "推荐编成",
        power: Math.max(0, Math.trunc(Number(row.current_battle_power) || 0)),
        character_id_1: normalizeId(row.character_id_1),
        character_id_2: normalizeId(row.character_id_2),
        character_id_3: normalizeId(row.character_id_3),
        evolution_img_level_1: normalizeEvolutionLevel(row.evolution_img_level_1),
        evolution_img_level_2: normalizeEvolutionLevel(row.evolution_img_level_2),
        evolution_img_level_3: normalizeEvolutionLevel(row.evolution_img_level_3),
        unison_character_id_1: normalizeId(row.unison_character_id_1),
        unison_character_id_2: normalizeId(row.unison_character_id_2),
        unison_character_id_3: normalizeId(row.unison_character_id_3),
        unison_evolution_img_level_1: normalizeEvolutionLevel(row.unison_evolution_img_level_1),
        unison_evolution_img_level_2: normalizeEvolutionLevel(row.unison_evolution_img_level_2),
        unison_evolution_img_level_3: normalizeEvolutionLevel(row.unison_evolution_img_level_3),
        equipment_id_1: normalizeId(row.equipment_id_1),
        equipment_id_2: normalizeId(row.equipment_id_2),
        equipment_id_3: normalizeId(row.equipment_id_3),
        ability_soul_id_1: normalizeId(row.ability_soul_id_1),
        ability_soul_id_2: normalizeId(row.ability_soul_id_2),
        ability_soul_id_3: normalizeId(row.ability_soul_id_3),
    }
}

function normalizeEvolutionLevel(value: unknown): number | null {
    const level = Number(value)
    return Number.isSafeInteger(level) && level >= 0 ? level : null
}

function isCompleteParty(party: RecommendedQuestParty): boolean {
    return party.character_id_1 !== null
        && party.character_id_2 !== null
        && party.character_id_3 !== null
}

function compositionKey(party: RecommendedQuestParty): string {
    return [
        party.character_id_1,
        party.character_id_2,
        party.character_id_3,
        party.unison_character_id_1,
        party.unison_character_id_2,
        party.unison_character_id_3,
        party.equipment_id_1,
        party.equipment_id_2,
        party.equipment_id_3,
        party.ability_soul_id_1,
        party.ability_soul_id_2,
        party.ability_soul_id_3,
    ].join(":")
}

function parseStoredParty(row: StoredRecommendationRow): RecommendedQuestParty | null {
    try {
        const parsed = JSON.parse(row.party_payload) as RecommendedQuestParty
        if (!parsed || typeof parsed !== "object") return null
        const party: RecommendedQuestParty = {
            party_name: parsed.party_name || "推荐编成",
            power: Math.max(0, Math.trunc(Number(row.battle_power) || 0)),
            character_id_1: normalizeId(parsed.character_id_1),
            character_id_2: normalizeId(parsed.character_id_2),
            character_id_3: normalizeId(parsed.character_id_3),
            evolution_img_level_1: normalizeEvolutionLevel(parsed.evolution_img_level_1),
            evolution_img_level_2: normalizeEvolutionLevel(parsed.evolution_img_level_2),
            evolution_img_level_3: normalizeEvolutionLevel(parsed.evolution_img_level_3),
            unison_character_id_1: normalizeId(parsed.unison_character_id_1),
            unison_character_id_2: normalizeId(parsed.unison_character_id_2),
            unison_character_id_3: normalizeId(parsed.unison_character_id_3),
            unison_evolution_img_level_1: normalizeEvolutionLevel(parsed.unison_evolution_img_level_1),
            unison_evolution_img_level_2: normalizeEvolutionLevel(parsed.unison_evolution_img_level_2),
            unison_evolution_img_level_3: normalizeEvolutionLevel(parsed.unison_evolution_img_level_3),
            equipment_id_1: normalizeId(parsed.equipment_id_1),
            equipment_id_2: normalizeId(parsed.equipment_id_2),
            equipment_id_3: normalizeId(parsed.equipment_id_3),
            ability_soul_id_1: normalizeId(parsed.ability_soul_id_1),
            ability_soul_id_2: normalizeId(parsed.ability_soul_id_2),
            ability_soul_id_3: normalizeId(parsed.ability_soul_id_3),
        }
        return isCompleteParty(party) ? party : null
    } catch {
        return null
    }
}

/**
 * Freezes the exact saved party that produced a successful clear. One best
 * (highest clear-power) snapshot is retained per player and quest.
 */
export function recordQuestRecommendedPartySync(context: FinishContext): boolean {
    if (!context.questAccomplished) return false

    const partySlot = context.partySlot ?? context.player.partySlot
    const expectedCategory = partyCategoryForQuest(context.questCategory)
    const rows = loadStoredPartiesSync(context.playerId, partySlot)
    rows.sort((left, right) => (
        Number(right.category === expectedCategory) - Number(left.category === expectedCategory)
    ))
    const matched = rows.find(row => matchesFinishedParty(row, context.party))
    if (!matched) return false

    const party = toRecommendedParty(matched)
    if (!isCompleteParty(party)) return false
    const clearedAt = Date.now()
    const result = getDb().prepare(`
        INSERT INTO quest_npc_party_pool (
            quest_category, quest_id, source_player_id, party_slot,
            battle_power, party_element, party_payload, cleared_at
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
        ON CONFLICT (quest_category, quest_id, source_player_id) DO UPDATE SET
            party_slot = excluded.party_slot,
            battle_power = excluded.battle_power,
            party_element = excluded.party_element,
            party_payload = excluded.party_payload,
            cleared_at = excluded.cleared_at
        WHERE excluded.battle_power > quest_npc_party_pool.battle_power
           OR (
                excluded.battle_power = quest_npc_party_pool.battle_power
                AND excluded.cleared_at >= quest_npc_party_pool.cleared_at
           )
    `).run(
        context.questCategory,
        context.questId,
        context.playerId,
        matched.party_slot,
        party.power,
        JSON.stringify(party),
        clearedAt,
    )
    return result.changes > 0
}

/** Recommendation history must never make an otherwise valid settlement fail. */
export function recordQuestRecommendedPartySafe(context: FinishContext): boolean {
    try {
        return recordQuestRecommendedPartySync(context)
    } catch (error) {
        console.error(
            `[QUEST-RECOMMEND] failed to record clear: player=${context.playerId} `
            + `category=${context.questCategory} quest=${context.questId} `
            + `error=${error instanceof Error ? error.message : String(error)}`,
        )
        return false
    }
}

function compareRankedParties(left: RankedParty, right: RankedParty): number {
    return right.party.power - left.party.power
        || Number(right.exactSnapshot) - Number(left.exactSnapshot)
        || right.clearedAt - left.clearedAt
        || right.sourcePlayerId - left.sourcePlayerId
}

/**
 * Returns real clear parties for one quest. Exact frozen snapshots are used
 * when available. Legacy progress rows only provide a migration fallback, so
 * existing servers stop recommending unrelated high-power players immediately.
 */
export function getRecommendedQuestPartiesSync(
    viewerPlayerId: number,
    questCategory: number,
    questId: number,
    limit = 10,
): RecommendedQuestPartyResult {
    const targetLimit = Math.max(0, Math.min(10, Math.trunc(limit)))
    if (targetLimit === 0) {
        return { parties: [], exactCandidateCount: 0, legacyCandidateCount: 0 }
    }

    const exactRows = getDb().prepare(`
        SELECT source_player_id, battle_power, party_payload, cleared_at
        FROM quest_npc_party_pool
        WHERE quest_category = ?
          AND quest_id = ?
          AND source_player_id <> ?
        ORDER BY battle_power DESC, cleared_at DESC
        LIMIT 200
    `).all(questCategory, questId, viewerPlayerId) as StoredRecommendationRow[]

    const ranked: RankedParty[] = []
    const exactPlayers = new Set<number>()
    for (const row of exactRows) {
        const party = parseStoredParty(row)
        if (!party) continue
        exactPlayers.add(row.source_player_id)
        ranked.push({
            sourcePlayerId: row.source_player_id,
            clearedAt: row.cleared_at,
            exactSnapshot: true,
            party,
        })
    }

    const expectedCategory = partyCategoryForQuest(questCategory)
    const legacyRows = getDb().prepare(`
        SELECT
            saved.player_id,
            saved.slot AS party_slot,
            saved.name,
            saved.current_battle_power,
            saved.character_id_1,
            saved.character_id_2,
            saved.character_id_3,
            c1.evolution_level AS evolution_img_level_1,
            c2.evolution_level AS evolution_img_level_2,
            c3.evolution_level AS evolution_img_level_3,
            saved.unison_character_1 AS unison_character_id_1,
            saved.unison_character_2 AS unison_character_id_2,
            saved.unison_character_3 AS unison_character_id_3,
            u1.evolution_level AS unison_evolution_img_level_1,
            u2.evolution_level AS unison_evolution_img_level_2,
            u3.evolution_level AS unison_evolution_img_level_3,
            saved.equipment_1 AS equipment_id_1,
            saved.equipment_2 AS equipment_id_2,
            saved.equipment_3 AS equipment_id_3,
            saved.ability_soul_1 AS ability_soul_id_1,
            saved.ability_soul_2 AS ability_soul_id_2,
            saved.ability_soul_3 AS ability_soul_id_3,
            saved.category
        FROM players_quest_progress q
        INNER JOIN players p ON p.id = q.player_id
        INNER JOIN players_parties saved
            ON saved.player_id = q.player_id
           AND saved.group_id = CAST((p.party_slot - 1) / 10 AS INTEGER) + 1
           AND saved.slot = ((p.party_slot - 1) % 10) + 1
           AND saved.category IN (?, ?)
        LEFT JOIN players_characters c1
            ON c1.player_id = saved.player_id AND c1.id = saved.character_id_1
        LEFT JOIN players_characters c2
            ON c2.player_id = saved.player_id AND c2.id = saved.character_id_2
        LEFT JOIN players_characters c3
            ON c3.player_id = saved.player_id AND c3.id = saved.character_id_3
        LEFT JOIN players_characters u1
            ON u1.player_id = saved.player_id AND u1.id = saved.unison_character_1
        LEFT JOIN players_characters u2
            ON u2.player_id = saved.player_id AND u2.id = saved.unison_character_2
        LEFT JOIN players_characters u3
            ON u3.player_id = saved.player_id AND u3.id = saved.unison_character_3
        WHERE q.section = ?
          AND q.quest_id = ?
          AND q.finished = 1
          AND q.player_id <> ?
        ORDER BY q.player_id DESC,
                 CASE WHEN saved.category = ? THEN 0 ELSE 1 END,
                 saved.current_battle_power DESC
        LIMIT 400
    `).all(
        expectedCategory,
        PartyCategory.NORMAL,
        questCategory,
        questId,
        viewerPlayerId,
        expectedCategory,
    ) as LegacyPartyRow[]

    let legacyCandidateCount = 0
    const legacyPlayers = new Set<number>()
    for (const row of legacyRows) {
        if (exactPlayers.has(row.player_id) || legacyPlayers.has(row.player_id)) continue
        legacyPlayers.add(row.player_id)
        const party = toRecommendedParty(row)
        if (!isCompleteParty(party)) continue
        legacyCandidateCount += 1
        ranked.push({
            sourcePlayerId: row.player_id,
            clearedAt: 0,
            exactSnapshot: false,
            party,
        })
    }

    ranked.sort(compareRankedParties)
    const seenCompositions = new Set<string>()
    const parties: RecommendedQuestParty[] = []
    for (const candidate of ranked) {
        const key = compositionKey(candidate.party)
        if (seenCompositions.has(key)) continue
        seenCompositions.add(key)
        parties.push(candidate.party)
        if (parties.length >= targetLimit) break
    }

    return {
        parties,
        exactCandidateCount: ranked.filter(candidate => candidate.exactSnapshot).length,
        legacyCandidateCount,
    }
}
