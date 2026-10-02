import { PartyCategory } from "../data/types"

export const FANTASY_RUSH_EVENT_ID = 700098

/**
 * Resolve the persisted party category used by a Rush event.
 *
 * Legacy clients omit event_id and continue to use PartyCategory.RUSH.  New
 * clients send the event id and get a dedicated category for each activity.
 */
export function partyCategoryForRushEvent(eventId: unknown): PartyCategory {
    switch (Number(eventId)) {
        case 700099:
            return PartyCategory.ABYSS_NORMAL
        case 700100:
            return PartyCategory.ABYSS_EX
        case FANTASY_RUSH_EVENT_ID:
            return PartyCategory.FANTASY
        default:
            return PartyCategory.RUSH
    }
}

