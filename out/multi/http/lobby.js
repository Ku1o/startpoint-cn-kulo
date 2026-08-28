"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.registerLobbyRoutes = void 0;
const player_1 = require("../../data/domains/player");
const follow_1 = require("../../data/domains/follow");
const assets_1 = require("../../lib/assets");
const utils_1 = require("../../utils");
const profileFavorite_1 = require("../../lib/profileFavorite");
const manager_1 = require("../room/manager");
const serializer_1 = require("../room/serializer");
const sharing_1 = require("../room/sharing");
const SessionManager_1 = require("../state/SessionManager");
const recruitment_1 = require("../recruitment");
const game_logging_1 = require("../../lib/game-logging");
const newbie_1 = require("../../lib/newbie");
const mode15_optional_1 = require("../../lib/mode15-optional");
const mode15_room_gate_1 = require("../mode15-room-gate");
const admission_1 = require("../room/admission");
const select_denial_1 = require("../room/select-denial");
const embedded_1 = require("../coordinator/embedded");
const player_context_1 = require("../player-context");
const ROOM_CAPACITY = 3;
function isReturningMember(room, viewerId) {
    return room.host_viewer_id === viewerId
        || room.expected_real_viewer_ids.includes(viewerId)
        || room.mates.some(mate => mate.viewer_id === viewerId);
}
function getCurrentLobbyViewerIds(room) {
    var _a;
    const viewerIds = new Set((_a = room.member_viewer_ids) !== null && _a !== void 0 ? _a : [room.host_viewer_id]);
    for (const client of SessionManager_1.sessionManager.getClientsInRoom(room.room_number, room.lobby_generation)) {
        if (client.isBattle
            || client.socket.destroyed
            || !client.socket.readable
            || !client.socket.writable)
            continue;
        viewerIds.add(client.viewerId);
    }
    return viewerIds;
}
function getCurrentLobbyOccupancy(room) {
    return admission_1.roomAdmissionRegistry.getOccupancy(room.room_number, room.lobby_generation, getCurrentLobbyViewerIds(room));
}
function canEnterMode15Room(playerId, room) {
    if (!(0, mode15_optional_1.isMode15Quest)(room.category, room.quest_id))
        return true;
    return (0, mode15_optional_1.canStartMode15QuestSync)(playerId, room.category, room.quest_id).allowed;
}
function canJoinRoomAsGuest(playerId, room) {
    if (!(0, mode15_optional_1.isMode15Quest)(room.category, room.quest_id))
        return true;
    return (0, mode15_optional_1.canJoinMode15RescueSync)(playerId, room.category, room.quest_id).allowed;
}
function registerLobbyRoutes(fastify) {
    // The legacy client posts this telemetry endpoint after handling native
    // create-room error 4507.  A successful empty response is required; a 404
    // is promoted by the client to a fatal H404 screen.
    fastify.post("/create_room_failure", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        var _a;
        const body = request.body;
        const viewerId = Number((_a = body === null || body === void 0 ? void 0 : body.viewer_id) !== null && _a !== void 0 ? _a : 0);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: Number.isFinite(viewerId) ? viewerId : 0 }),
            data: {},
        });
    }));
    fastify.post("/get_rooms", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewerId);
        if (!ctx)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id or no player bound."
            });
        const viewerPlayerId = ctx.playerId;
        const requestedCategories = body.category_id === 7 || body.category_id === 8
            ? [7, 8]
            : [body.category_id];
        const rooms = requestedCategories
            .flatMap(categoryId => (0, manager_1.getRooms)(categoryId, body.event_id))
            .filter(r => r.host_viewer_id !== viewerId)
            .filter(r => (0, sharing_1.isRoomSharedWithPlayer)(r, viewerPlayerId))
            .filter(r => !r.is_npc_mode
            && !["STARTING", "BATTLE"].includes(embedded_1.embeddedMultiCoordinator.ensureLifecycle(r).phase))
            .filter(r => !(0, mode15_room_gate_1.isMode15RoomClosed)(r))
            .filter(r => SessionManager_1.sessionManager.isHostOnline(r.host_viewer_id, r.room_number, r.lobby_generation))
            .filter(r => getCurrentLobbyOccupancy(r) < ROOM_CAPACITY)
            // Every non-host entrant to a Mode15 boss room is a helper.  Room
            // code, follow sharing and random recruitment must therefore use
            // the same repeatable rescue gate instead of the helper's own run
            // position.
            .filter(r => canJoinRoomAsGuest(viewerPlayerId, r))
            .map(r => (0, serializer_1.serializeRoom)(r, viewerPlayerId));
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": { "rooms": rooms }
        });
    }));
    fastify.post("/create_room", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        var _b, _c;
        const body = request.body;
        const { viewer_id, category, quest_id, party_id } = body;
        if (!viewer_id || isNaN(viewer_id))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewer_id);
        if (!ctx)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id or no player bound."
            });
        const quest = (0, assets_1.getQuestFromCategorySync)(category, quest_id);
        if (!quest)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Quest doesn't exist."
            });
        if ((0, mode15_optional_1.isMode15Quest)(category, quest_id)) {
            const gate = (0, mode15_optional_1.canStartMode15QuestSync)(ctx.playerId, category, quest_id);
            if (!gate.allowed) {
                // The legacy client treats a non-2xx response as a fatal HTTP
                // error (H409).  Result code 4507 is its native
                // create-room-failure branch, which closes the processing
                // dialog normally while still creating no room.
                console.log(`[MODE15] create_room denied: player=${ctx.playerId} requested=${gate.stage} expected=${gate.expectedStage} result=4507`);
                reply.header("content-type", "application/x-msgpack");
                return reply.status(200).send({
                    data_headers: (0, utils_1.generateDataHeaders)({ viewer_id, result_code: 4507 }),
                    data: {},
                });
            }
        }
        const favorite = (0, profileFavorite_1.getFavoritePartySelectionSync)(ctx.playerId, ctx.player.leaderCharacterId);
        const profileMainCharacterId = (_c = (_b = favorite.characterIds[0]) !== null && _b !== void 0 ? _b : ctx.player.leaderCharacterId) !== null && _c !== void 0 ? _c : 1;
        const room = (0, manager_1.createRoom)(viewer_id, ctx.playerId, party_id, category, quest_id, 0, profileMainCharacterId);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id }),
            "data": {
                "access_token": room.access_token,
                "room_number": room.room_number,
                "room_url": ""
            }
        });
    }));
    fastify.post("/search_room", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        var _d;
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewerId);
        if (!ctx)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id or no player bound."
            });
        const viewerPlayerId = ctx.playerId;
        const room = (0, manager_1.getRoom)(body.room_number);
        const returningMember = !!room && isReturningMember(room, viewerId);
        const roomVisible = !!room
            && !(0, mode15_room_gate_1.isMode15RoomClosed)(room)
            && !SessionManager_1.sessionManager.isRoomRestoreBlocked(room.room_number, viewerId)
            && (returningMember || (canJoinRoomAsGuest(viewerPlayerId, room)
                && !["STARTING", "BATTLE"].includes(embedded_1.embeddedMultiCoordinator.ensureLifecycle(room).phase)
                && !(0, manager_1.isRoomWaitingForExpectedMember)(room)
                && getCurrentLobbyOccupancy(room) < ROOM_CAPACITY));
        const followState = roomVisible
            ? (0, follow_1.getFollowRelationSync)(viewerPlayerId, room.host_player_id).state
            : 0;
        (0, game_logging_1.gameVerboseLog)(() => {
            var _a, _b;
            return `[MULTI] search_room: viewer=${viewerId} room=${body.room_number}`
                + ` found=${!!room} visible=${roomVisible}`
                + ` category=${(_a = room === null || room === void 0 ? void 0 : room.category) !== null && _a !== void 0 ? _a : 0} quest=${(_b = room === null || room === void 0 ? void 0 : room.quest_id) !== null && _b !== void 0 ? _b : 0}`;
        });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                "room_exists": roomVisible,
                "category_id": roomVisible ? room.category : 0,
                "quest_id": roomVisible ? room.quest_id : 0,
                "room_number": (_d = room === null || room === void 0 ? void 0 : room.room_number) !== null && _d !== void 0 ? _d : body.room_number,
                "establisher_viewer_id": roomVisible ? room.host_viewer_id : 0,
                "establisher_follow": followState
            }
        });
    }));
    fastify.post("/select_room", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewerId);
        if (!ctx)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id or no player bound."
            });
        const room = body.room_number ? (0, manager_1.getRoom)(body.room_number) : (0, manager_1.getRoomByToken)(body.access_token || "");
        if (room && (room.category !== Number(body.category) || room.quest_id !== Number(body.quest_id))) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Room quest mismatch."
            });
        }
        const returningMember = !!room && isReturningMember(room, viewerId);
        const rescueSelection = Number(body.accepted_type) === 2;
        const randomRescue = !!room
            && !returningMember
            && rescueSelection
            && (0, recruitment_1.wasRandomRecruitmentDeliveredTo)(room.room_number, viewerId);
        const mode15Blocked = !!room
            && !returningMember
            && !canJoinRoomAsGuest(ctx.playerId, room);
        const mode15RoomClosed = !!room && (0, mode15_room_gate_1.isMode15RoomClosed)(room);
        // A rescue notice remains visible on the client for roughly 30 seconds.
        // If the host enabled AI or started/stopped recruitment after delivery,
        // reject only that stale notice recipient. Direct room-code entrants are
        // unaffected and may still replace one COM slot normally.
        const staleRescueNotice = !!room
            && !returningMember
            && rescueSelection
            && (0, recruitment_1.wasStoppedRandomRecruitmentDeliveredTo)(room.room_number, viewerId)
            && (room.is_npc_mode || !(0, recruitment_1.isRandomRecruiting)(room.room_number));
        const battleStarted = !!room
            && !returningMember
            && ["STARTING", "BATTLE"].includes(embedded_1.embeddedMultiCoordinator.ensureLifecycle(room).phase);
        const waitingForExpectedMember = !!room
            && !returningMember
            && (0, manager_1.isRoomWaitingForExpectedMember)(room);
        const isUnavailableWithoutCapacity = !!room && (mode15RoomClosed
            || (!returningMember && (battleStarted
                || waitingForExpectedMember
                || staleRescueNotice
                || mode15Blocked)));
        const restoreBlocked = !!room && SessionManager_1.sessionManager.isRoomRestoreBlocked(room.room_number, viewerId);
        const capacityDenied = !!room
            && !returningMember
            && !isUnavailableWithoutCapacity
            && !restoreBlocked
            && !admission_1.roomAdmissionRegistry.reserve(room.room_number, room.lobby_generation, viewerId, getCurrentLobbyViewerIds(room), ROOM_CAPACITY);
        if (!room || isUnavailableWithoutCapacity || restoreBlocked || capacityDenied) {
            if (room && !returningMember) {
                admission_1.roomAdmissionRegistry.release(room.room_number, viewerId);
            }
            if (mode15RoomClosed) {
                console.log(`[MODE15] select_room denied: completed host room=${room === null || room === void 0 ? void 0 : room.room_number} viewer=${viewerId}`);
            }
            if (capacityDenied) {
                console.log(`[MULTI] select_room denied before TCP: viewer=${viewerId}`
                    + ` room=${room === null || room === void 0 ? void 0 : room.room_number} reason=capacity_reserved`);
            }
            const denialRaisingState = (0, select_denial_1.getSelectRoomDenialRaisingState)({
                battleStarted,
                // A disconnected expected member still owns that seat, so the
                // room is full from a new entrant's point of view.
                roomFull: capacityDenied || waitingForExpectedMember,
            });
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
                "data": {
                    application_update_url: "",
                    category_id: 0,
                    host_entry_time: 0,
                    ip_address: "",
                    port: 0,
                    quest_id: 0,
                    raising_state: denialRaisingState,
                    room_number: (room === null || room === void 0 ? void 0 : room.room_number) || body.room_number || "",
                    room_sequence: 0,
                    share_room_options: 0,
                    is_pickup: null
                }
            });
        }
        // A Fantasy room-code/follow entrant is also a helper for lifecycle
        // and progression purposes, but only a delivered rescue selection is
        // eligible for the repeatable fragment reward.
        if (randomRescue || (!returningMember && (0, mode15_optional_1.isMode15Quest)(room.category, room.quest_id))) {
            const host = (0, player_1.getPlayerSync)(room.host_player_id);
            SessionManager_1.sessionManager.markRescueGuest(room.room_number, viewerId, (0, newbie_1.isNewbiePlayerSync)(room.host_player_id, host), randomRescue);
        }
        if (randomRescue)
            (0, recruitment_1.acceptRandomRecruitmentForViewer)(room.room_number, viewerId);
        const selectData = (0, serializer_1.serializeRoomConnection)(room);
        if (viewerId === room.host_viewer_id) {
            selectData.raising_state = 1;
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] select_room: host override raising_state → 1`);
        }
        else if (!SessionManager_1.sessionManager.isHostOnline(room.host_viewer_id, room.room_number, room.lobby_generation)) {
            selectData.raising_state = 2;
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] select_room: host offline, guest polls raising_state → 2`);
        }
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": selectData
        });
    }));
}
exports.registerLobbyRoutes = registerLobbyRoutes;
