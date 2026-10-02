import { QuestCategory } from "./types"

/**
 * Carnival, Raid, and Rush use their own persisted party categories.  The
 * legacy players.party_slot field remains the NORMAL/home-party pointer and
 * must not be overwritten by those event selections.
 */
export function usesNormalCurrentPartySlot(category: QuestCategory | number): boolean {
    const normalizedCategory = Number(category)
    return normalizedCategory !== QuestCategory.CARNIVAL_EVENT
        && normalizedCategory !== QuestCategory.RAID_EVENT
        && normalizedCategory !== QuestCategory.RUSH_EVENT
}
