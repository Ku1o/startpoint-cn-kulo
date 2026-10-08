import {
    getMode15ExclusiveItemIds,
    isMode15EquipmentAllowedQuest,
} from "../../lib/mode15-optional"

const PARTY_ITEM_FIELDS = [
    "equipments",
    "equipmentIds",
    "equipment_ids",
    "abilitySoulIds",
    "ability_soul_ids",
] as const

const FANTASY_ITEM_IDS = new Set(
    Array.from({ length: 11 }, (_, index) => 100013 + index),
)

function itemId(raw: any): unknown {
    const value = Array.isArray(raw)
        ? (raw[0] === 0 ? raw[1] : null)
        : raw
    if (!value || typeof value !== "object") return value
    return value.equipmentId
        ?? value.equipment_id
        ?? value.abilitySoulId
        ?? value.ability_soul_id
        ?? value.id
}

function isFantasyItem(raw: any): boolean {
    const id = Number(itemId(raw))
    return FANTASY_ITEM_IDS.has(id)
        || getMode15ExclusiveItemIds([id]).length > 0
}

/**
 * Reject a complete AI party if it carries Fantasy-only equipment outside a
 * Fantasy quest. The party must never enter a room in a silently altered form.
 */
export function isNpcPartyAllowedInRoom(
    category: number | undefined,
    questId: number | undefined,
    party: any,
): boolean {
    if (!party || typeof party !== "object") return false
    if (category !== undefined && questId !== undefined
        && isMode15EquipmentAllowedQuest(category, questId)) return true
    for (const field of PARTY_ITEM_FIELDS) {
        const values = party[field]
        if (!Array.isArray(values)) continue
        if (values.some(isFantasyItem)) return false
    }
    return true
}
