"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.isRoomSharedWithPlayer = exports.hasRoomShareType = exports.encodeRoomShareOptions = exports.normalizeRoomShareTypes = exports.RANDOM_RECRUITMENT_SHARE_TYPE = exports.AI_RECRUITMENT_SHARE_TYPE = exports.MUTUAL_FOLLOW_SHARE_TYPE = void 0;
const follow_1 = require("../../data/domains/follow");
exports.MUTUAL_FOLLOW_SHARE_TYPE = 1;
exports.AI_RECRUITMENT_SHARE_TYPE = 2;
exports.RANDOM_RECRUITMENT_SHARE_TYPE = 3;
function normalizeRoomShareTypes(shareTypes) {
    if (!Array.isArray(shareTypes))
        return [];
    return [...new Set(shareTypes.filter(type => Number.isInteger(type)
            && type >= exports.MUTUAL_FOLLOW_SHARE_TYPE
            && type <= exports.RANDOM_RECRUITMENT_SHARE_TYPE))];
}
exports.normalizeRoomShareTypes = normalizeRoomShareTypes;
function encodeRoomShareOptions(shareTypes) {
    return shareTypes.reduce((options, type) => options | (1 << (type - 1)), 0);
}
exports.encodeRoomShareOptions = encodeRoomShareOptions;
function hasRoomShareType(room, shareType) {
    return (room.share_room_options & (1 << (shareType - 1))) !== 0;
}
exports.hasRoomShareType = hasRoomShareType;
function isRoomSharedWithPlayer(room, viewerPlayerId) {
    if (!hasRoomShareType(room, exports.MUTUAL_FOLLOW_SHARE_TYPE))
        return false;
    // The client-side one-way-follow button is repurposed for AI recruitment,
    // so the remaining follow share option covers everyone the viewer follows:
    // both mutual follows and viewer-to-host one-way follows.
    return (0, follow_1.getFollowRelationSync)(viewerPlayerId, room.host_player_id).followTime !== null;
}
exports.isRoomSharedWithPlayer = isRoomSharedWithPlayer;
