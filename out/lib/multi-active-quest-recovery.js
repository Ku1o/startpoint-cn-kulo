"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.classifyMultiActiveQuestRecovery = void 0;
/**
 * Only publish a multiplayer unfinished quest when the exact room battle can
 * still accept this viewer. Anything else is an orphan that makes the client
 * retry restore on every login.
 */
function classifyMultiActiveQuestRecovery(quest, room, viewerId, battleSeatRetired = false) {
    var _a;
    if (!quest.isMulti)
        return { recoverable: true, reason: "single" };
    if (typeof quest.roomNumber !== "string" || quest.roomNumber.trim().length === 0) {
        return { recoverable: false, reason: "missing_room_number" };
    }
    if (!room)
        return { recoverable: false, reason: "room_missing" };
    if (((_a = room.lifecycle) === null || _a === void 0 ? void 0 : _a.phase) !== "BATTLE") {
        return { recoverable: false, reason: "room_not_in_battle" };
    }
    if (Number(room.category) !== Number(quest.category)
        || Number(room.quest_id) !== Number(quest.questId)) {
        return { recoverable: false, reason: "quest_mismatch" };
    }
    const expectedViewerIds = room.expected_real_viewer_ids.length > 0
        ? room.expected_real_viewer_ids
        : room.member_viewer_ids;
    if (!expectedViewerIds.includes(Number(viewerId))) {
        return { recoverable: false, reason: "member_not_in_battle" };
    }
    if (battleSeatRetired) {
        return { recoverable: false, reason: "member_not_in_battle" };
    }
    return { recoverable: true, reason: "recoverable" };
}
exports.classifyMultiActiveQuestRecovery = classifyMultiActiveQuestRecovery;
