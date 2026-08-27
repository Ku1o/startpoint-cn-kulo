"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.updateHostEntryTime = exports.disbandRoom = exports.setRoomBattle = exports.getRoomMemberPlayerId = exports.removeRoomMember = exports.addRoomMember = exports.isRoomMember = exports.getRooms = exports.getRoomByToken = exports.getRoom = exports.createRoom = exports.isRoomWaitingForExpectedMember = exports.generateRoomAccessToken = exports.generateRoomNumber = void 0;
const crypto_1 = require("crypto");
const types_1 = require("../../lib/types");
const utils_1 = require("../../utils");
const SessionManager_1 = require("../state/SessionManager");
const game_logging_1 = require("../../lib/game-logging");
const admission_1 = require("./admission");
const embedded_1 = require("../coordinator/embedded");
const assets_1 = require("../../lib/assets");
const rooms = new Map();
let roomSequence = 1;
const INCOMPLETE_EXPIRY_MS = parseInt(process.env.MULTI_ROOM_INCOMPLETE_EXPIRY_MS || "900000"); // 15min, mates < 3
const FULL_ROOM_EXPIRY_MS = parseInt(process.env.MULTI_ROOM_FULL_EXPIRY_MS || "1800000"); // 30min, mates >= 3
const CLEAN_INTERVAL_MS = parseInt(process.env.MULTI_ROOM_CLEAN_INTERVAL_MS || "60000");
const REMAINING_NOTIFY_MS = 30000; // send RemainingTime float 30s before disband
// Track which rooms have already been notified (to avoid repeat floats)
const notifiedRooms = new Set();
function cleanExpiredRooms() {
    for (const [roomNumber, room] of rooms) {
        const lifecycle = embedded_1.embeddedMultiCoordinator.ensureLifecycle(room);
        // Battle and settlement rooms are governed by their own watchdogs.
        // Skip them before allocating a Promise chain every cleanup tick.
        if (lifecycle.phase !== "LOBBY")
            continue;
        const instanceId = lifecycle.instanceId;
        const lifecycleVersion = lifecycle.version;
        void embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(roomNumber, () => {
            const current = rooms.get(roomNumber);
            if (!embedded_1.embeddedMultiCoordinator.isCurrentInstance(current, instanceId)
                || current.lifecycle.version !== lifecycleVersion)
                return;
            // Only an ordinary lobby uses idle expiry. Battle and settlement
            // phases have their own watchdogs and grace periods.
            if (current.lifecycle.phase !== "LOBBY")
                return;
            const now = Date.now();
            const timeOffset = now - (0, utils_1.getServerTime)() * 1000;
            const idleAge = now - (current.host_entry_time * 1000 + timeOffset);
            const timeout = current.mates.length < 3 ? INCOMPLETE_EXPIRY_MS : FULL_ROOM_EXPIRY_MS;
            const remaining = timeout - idleAge;
            if (remaining > 0 && remaining <= REMAINING_NOTIFY_MS && !notifiedRooms.has(roomNumber)) {
                SessionManager_1.sessionManager.broadcastToRoom(roomNumber, [1, [7, Math.ceil(remaining / 1000)]]);
                notifiedRooms.add(roomNumber);
                (0, game_logging_1.gameVerboseLog)(() => `[MULTI] RemainingTime sent: room=${roomNumber} seconds=${Math.ceil(remaining / 1000)}`);
            }
            if (idleAge > timeout && SessionManager_1.sessionManager.commitRoomDisband(roomNumber, "room_expired")) {
                notifiedRooms.delete(roomNumber);
            }
        }).catch(error => console.error(`[MULTI] room cleanup failed: room=${roomNumber}`, error));
    }
}
setInterval(cleanExpiredRooms, CLEAN_INTERVAL_MS);
function generateRoomNumber() {
    for (let attempt = 0; attempt < 100; attempt += 1) {
        const roomNumber = String((0, crypto_1.randomInt)(100000, 1000000));
        if (!rooms.has(roomNumber))
            return roomNumber;
    }
    throw new Error("Unable to allocate a unique multiplayer room number");
}
exports.generateRoomNumber = generateRoomNumber;
function generateRoomAccessToken() {
    for (let attempt = 0; attempt < 100; attempt += 1) {
        const token = (0, crypto_1.randomBytes)(24).toString("base64url");
        if (!getRoomByToken(token))
            return token;
    }
    throw new Error("Unable to allocate a unique multiplayer room token");
}
exports.generateRoomAccessToken = generateRoomAccessToken;
function isRoomWaitingForExpectedMember(room) {
    if (room.lobby_generation <= 0 || room.expected_real_viewer_ids.length === 0) {
        return false;
    }
    const liveViewerIds = new Set(SessionManager_1.sessionManager.getClientsInRoom(room.room_number, room.lobby_generation)
        .filter(client => !client.isBattle
        && !client.socket.destroyed
        && client.socket.readable
        && client.socket.writable)
        .map(client => client.viewerId));
    return room.expected_real_viewer_ids.some(viewerId => !liveViewerIds.has(viewerId));
}
exports.isRoomWaitingForExpectedMember = isRoomWaitingForExpectedMember;
function createRoom(hostViewerId, hostPlayerId, hostPartyId, category, questId, acceptedType, hostMainCharacterId, isNpcMode = false) {
    const roomNumber = generateRoomNumber();
    const room = {
        room_number: roomNumber,
        access_token: generateRoomAccessToken(),
        category,
        quest_id: questId,
        host_viewer_id: hostViewerId,
        host_player_id: hostPlayerId,
        host_party_id: hostPartyId,
        host_main_character_id: hostMainCharacterId,
        accepted_type: acceptedType,
        created_at: Date.now(),
        raising_state: 2,
        room_sequence: roomSequence++,
        host_entry_time: (0, utils_1.getServerTime)(),
        member_viewer_ids: [hostViewerId],
        member_player_ids: { [hostViewerId]: hostPlayerId },
        mates: [],
        share_room_options: 0,
        is_npc_mode: isNpcMode,
        npc_count: 0,
        expected_real_viewer_ids: [],
        lobby_generation: 0,
        rematch_wait_started_at: null,
        settlement_return_pending: false,
        lifecycle: embedded_1.embeddedMultiCoordinator.createLifecycle(),
    };
    rooms.set(roomNumber, room);
    (0, game_logging_1.gameVerboseLog)(() => `[MULTI] room created: ${roomNumber} host=${hostViewerId} category=${category} quest=${questId}`);
    return room;
}
exports.createRoom = createRoom;
function getRoom(roomNumber) {
    const room = rooms.get(roomNumber);
    if (!room)
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] room not found: ${roomNumber}`);
    return room;
}
exports.getRoom = getRoom;
function getRoomByToken(token) {
    for (const room of rooms.values()) {
        if (room.access_token === token)
            return room;
    }
    return undefined;
}
exports.getRoomByToken = getRoomByToken;
function getRoomEventId(room) {
    const quest = (0, assets_1.getQuestFromCategorySync)(room.category, room.quest_id);
    if ((quest === null || quest === void 0 ? void 0 : quest.eventId) !== undefined)
        return quest.eventId;
    if ((room.category === types_1.QuestCategory.ADVENT_EVENT_SINGLE
        || room.category === types_1.QuestCategory.ADVENT_EVENT_MULTI)
        && Number.isSafeInteger(room.quest_id)
        && room.quest_id >= 1000) {
        return Math.trunc(room.quest_id / 1000);
    }
    return undefined;
}
function getRooms(categoryId, eventId) {
    const result = [];
    for (const room of rooms.values()) {
        if (room.category !== categoryId)
            continue;
        if (eventId !== undefined) {
            const roomEventId = getRoomEventId(room);
            // Legacy advent tables encode the event in the quest's thousands
            // group instead of storing eventId explicitly. Other old tables
            // without either form remain visible for backward compatibility.
            if (roomEventId !== undefined && roomEventId !== Number(eventId))
                continue;
        }
        result.push(room);
    }
    return result;
}
exports.getRooms = getRooms;
function isRoomMember(room, viewerId) {
    var _a;
    if ((_a = room.member_viewer_ids) === null || _a === void 0 ? void 0 : _a.includes(viewerId))
        return true;
    if (room.host_viewer_id === viewerId)
        return true;
    if (room.expected_real_viewer_ids.includes(viewerId))
        return true;
    if (room.mates.some(mate => mate.viewer_id === viewerId))
        return true;
    return SessionManager_1.sessionManager.getClientsInRoom(room.room_number, room.lobby_generation)
        .some(client => !client.isBattle && client.viewerId === viewerId);
}
exports.isRoomMember = isRoomMember;
function addRoomMember(roomNumber, viewerId, playerId) {
    const room = rooms.get(roomNumber);
    if (!room)
        return false;
    if (!room.member_viewer_ids.includes(viewerId))
        room.member_viewer_ids.push(viewerId);
    room.member_player_ids[viewerId] = playerId;
    return true;
}
exports.addRoomMember = addRoomMember;
function removeRoomMember(roomNumber, viewerId) {
    const room = rooms.get(roomNumber);
    if (!room || viewerId === room.host_viewer_id)
        return false;
    const index = room.member_viewer_ids.indexOf(viewerId);
    if (index < 0)
        return false;
    room.member_viewer_ids.splice(index, 1);
    delete room.member_player_ids[viewerId];
    return true;
}
exports.removeRoomMember = removeRoomMember;
function getRoomMemberPlayerId(room, viewerId) {
    var _a, _b;
    const recordedMemberPlayerId = (_a = room.member_player_ids) === null || _a === void 0 ? void 0 : _a[viewerId];
    if (recordedMemberPlayerId)
        return recordedMemberPlayerId;
    if (room.host_viewer_id === viewerId)
        return room.host_player_id;
    const recordedMate = room.mates.find(mate => mate.viewer_id === viewerId);
    if (recordedMate === null || recordedMate === void 0 ? void 0 : recordedMate.player_id)
        return recordedMate.player_id;
    const liveClient = SessionManager_1.sessionManager.getClientsInRoom(room.room_number, room.lobby_generation)
        .find(client => !client.isBattle && client.viewerId === viewerId);
    return (_b = liveClient === null || liveClient === void 0 ? void 0 : liveClient.playerId) !== null && _b !== void 0 ? _b : null;
}
exports.getRoomMemberPlayerId = getRoomMemberPlayerId;
function setRoomBattle(roomNumber) {
    const room = rooms.get(roomNumber);
    if (!room)
        return false;
    const lifecycle = embedded_1.embeddedMultiCoordinator.ensureLifecycle(room);
    if (lifecycle.phase === "BATTLE")
        return true;
    return embedded_1.embeddedMultiCoordinator.commitBattleStart(room).ok;
}
exports.setRoomBattle = setRoomBattle;
function disbandRoom(roomNumber, reason = "room_manager_delete") {
    const room = rooms.get(roomNumber);
    if (room)
        embedded_1.embeddedMultiCoordinator.commitDisband(room, reason);
    const deleted = rooms.delete(roomNumber);
    if (deleted) {
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] room deleted: ${roomNumber}`);
        admission_1.roomAdmissionRegistry.clearRoom(roomNumber);
        try {
            const { stopRandomRecruitment } = require("../recruitment");
            stopRandomRecruitment(roomNumber);
        }
        catch (e) { }
        SessionManager_1.sessionManager.removeRoomState(roomNumber);
        notifiedRooms.delete(roomNumber);
    }
    return deleted;
}
exports.disbandRoom = disbandRoom;
function updateHostEntryTime(roomNumber) {
    const room = rooms.get(roomNumber);
    if (!room)
        return false;
    room.host_entry_time = (0, utils_1.getServerTime)();
    return true;
}
exports.updateHostEntryTime = updateHostEntryTime;
