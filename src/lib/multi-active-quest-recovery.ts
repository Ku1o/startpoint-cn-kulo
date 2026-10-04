import type { PlayerActiveQuest } from "../data/types"
import type { MultiRoom } from "./types"

export type MultiActiveQuestRecoveryReason =
    | "single"
    | "recoverable"
    | "missing_room_number"
    | "room_missing"
    | "room_not_in_battle"
    | "quest_mismatch"
    | "member_not_in_battle"

export interface MultiActiveQuestRecoveryDecision {
    recoverable: boolean
    reason: MultiActiveQuestRecoveryReason
}

/**
 * Only publish a multiplayer unfinished quest when the exact room battle can
 * still accept this viewer. Anything else is an orphan that makes the client
 * retry restore on every login.
 */
export function classifyMultiActiveQuestRecovery(
    quest: Pick<PlayerActiveQuest, "isMulti" | "roomNumber" | "category" | "questId">,
    room: MultiRoom | undefined,
    viewerId: number,
    battleSeatRetired = false,
): MultiActiveQuestRecoveryDecision {
    if (!quest.isMulti) return { recoverable: true, reason: "single" }
    if (typeof quest.roomNumber !== "string" || quest.roomNumber.trim().length === 0) {
        return { recoverable: false, reason: "missing_room_number" }
    }
    if (!room) return { recoverable: false, reason: "room_missing" }
    if (room.lifecycle?.phase !== "BATTLE") {
        return { recoverable: false, reason: "room_not_in_battle" }
    }
    if (Number(room.category) !== Number(quest.category)
        || Number(room.quest_id) !== Number(quest.questId)) {
        return { recoverable: false, reason: "quest_mismatch" }
    }
    const expectedViewerIds = room.expected_real_viewer_ids.length > 0
        ? room.expected_real_viewer_ids
        : room.member_viewer_ids
    if (!expectedViewerIds.includes(Number(viewerId))) {
        return { recoverable: false, reason: "member_not_in_battle" }
    }
    if (battleSeatRetired) {
        return { recoverable: false, reason: "member_not_in_battle" }
    }
    return { recoverable: true, reason: "recoverable" }
}
