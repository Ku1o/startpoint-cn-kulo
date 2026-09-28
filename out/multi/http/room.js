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
exports.registerRoomRoutes = void 0;
const utils_1 = require("../../utils");
const manager_1 = require("../room/manager");
const serializer_1 = require("../room/serializer");
const SessionManager_1 = require("../state/SessionManager");
const builder_1 = require("../npc/builder");
const recruitment_1 = require("../recruitment");
const lobby_1 = require("../tcp/lobby");
const sharing_1 = require("../room/sharing");
const game_logging_1 = require("../../lib/game-logging");
const mode15_room_gate_1 = require("../mode15-room-gate");
const embedded_1 = require("../coordinator/embedded");
const player_context_1 = require("../player-context");
const attention_config_1 = require("../attention-config");
function hasValidViewer(viewerId) {
    return __awaiter(this, void 0, void 0, function* () {
        return (yield (0, player_context_1.resolveMultiPlayerContext)(viewerId)) !== null;
    });
}
function forbidden(reply) {
    return reply.status(403).send({
        "error": "Forbidden",
        "message": "Room permission denied.",
    });
}
function registerRoomRoutes(fastify) {
    // ---- prepare ----
    fastify.post("/prepare", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] prepare: viewer=${viewerId} room=${body.room_number}`);
        if (!(yield hasValidViewer(viewerId))) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const room = body.room_number
            ? (0, manager_1.getRoom)(body.room_number)
            : (0, manager_1.getRoomByToken)(body.access_token || "");
        const mode15RoomClosed = !!room && (0, mode15_room_gate_1.isMode15RoomClosed)(room);
        if (!room || mode15RoomClosed || SessionManager_1.sessionManager.isRoomRestoreBlocked(room.room_number, viewerId)) {
            if (mode15RoomClosed) {
                console.log(`[MODE15] prepare denied: completed host room=${room === null || room === void 0 ? void 0 : room.room_number} viewer=${viewerId}`);
            }
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
                    raising_state: 9,
                    room_number: (room === null || room === void 0 ? void 0 : room.room_number) || body.room_number || "",
                    room_sequence: 0,
                    share_room_options: 0,
                    is_pickup: null,
                }
            });
        }
        if (room.category !== Number(body.category) || room.quest_id !== Number(body.quest_id)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Room quest mismatch."
            });
        }
        if (viewerId === room.host_viewer_id)
            (0, manager_1.updateHostEntryTime)(room.room_number);
        const data = (0, serializer_1.serializeRoomConnection)(room);
        if (viewerId === room.host_viewer_id) {
            data.raising_state = 1;
        }
        else if (!SessionManager_1.sessionManager.isHostOnline(room.host_viewer_id, room.room_number, room.lobby_generation)) {
            data.raising_state = 2;
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] prepare: host offline, guest polls raising_state → 2`);
        }
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": data,
        });
    }));
    // ---- summon ----
    fastify.post("/summon", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] summon: viewer=${viewerId} room=${body.room_number}`);
        if (!(yield hasValidViewer(viewerId))) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const room = (0, manager_1.getRoom)(body.room_number);
        if (!room || (0, mode15_room_gate_1.isMode15RoomClosed)(room) || SessionManager_1.sessionManager.isRoomRestoreBlocked(body.room_number, viewerId)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Room doesn't exist."
            });
        }
        if (room.host_viewer_id !== viewerId)
            return forbidden(reply);
        if (room.category !== Number(body.category_id) || room.quest_id !== Number(body.quest_id)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Room quest mismatch."
            });
        }
        // Random recruitment is a real-player broadcast.  The client still calls
        // /summon after its legacy COM timeout, so only return COM data for rooms
        // that explicitly selected the second (AI) share option.
        const mates = room.is_npc_mode
            ? (0, builder_1.buildNpcMates)(body.quest_id, room.category)
            : { mate1: null, mate2: null };
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                "mate1": mates.mate1,
                "mate2": mates.mate2,
            }
        });
    }));
    // ---- restore_room ----
    fastify.post("/restore_room", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] restore_room: viewer=${viewerId} room=${body.room_number}`);
        if (!(yield hasValidViewer(viewerId))) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const room = (0, manager_1.getRoom)(body.room_number);
        const mode15RoomClosed = !!room && (0, mode15_room_gate_1.isMode15RoomClosed)(room);
        if (!room || mode15RoomClosed || SessionManager_1.sessionManager.isRoomRestoreBlocked(body.room_number, viewerId)) {
            if (mode15RoomClosed) {
                console.log(`[MODE15] restore_room denied: completed host room=${body.room_number} viewer=${viewerId}`);
            }
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
                    raising_state: 9,
                    room_number: body.room_number,
                    room_sequence: 0,
                    share_room_options: 0,
                    is_pickup: null,
                    is_same_room: true,
                }
            });
        }
        if (!(0, manager_1.isRoomMember)(room, viewerId)) {
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
                "data": {
                    application_update_url: "",
                    category_id: room.category,
                    host_entry_time: room.host_entry_time,
                    ip_address: "",
                    port: 0,
                    quest_id: room.quest_id,
                    raising_state: 13,
                    room_number: room.room_number,
                    room_sequence: room.room_sequence,
                    share_room_options: room.share_room_options,
                    is_pickup: null,
                    is_same_room: true,
                }
            });
        }
        const data = Object.assign(Object.assign({}, (0, serializer_1.serializeRoomConnection)(room)), { is_same_room: true });
        if (viewerId === room.host_viewer_id) {
            data.raising_state = 1;
        }
        else if (!SessionManager_1.sessionManager.isHostOnline(room.host_viewer_id, room.room_number, room.lobby_generation)) {
            data.raising_state = 2;
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] restore_room: host offline, guest polls raising_state → 2`);
        }
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": data,
        });
    }));
    // ---- share_room ----
    fastify.post("/share_room", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] share_room: viewer=${viewerId} room=${body.room_number}`);
        if (!(yield hasValidViewer(viewerId))) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const room = (0, manager_1.getRoom)(body.room_number);
        if (!room) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Room doesn't exist."
            });
        }
        if (room.host_viewer_id !== viewerId)
            return forbidden(reply);
        if ((body.category !== undefined && room.category !== Number(body.category))
            || (body.quest_id !== undefined && room.quest_id !== Number(body.quest_id))) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Room quest mismatch."
            });
        }
        if ((0, mode15_room_gate_1.isMode15RoomClosed)(room)) {
            (0, recruitment_1.stopRandomRecruitment)(room.room_number);
            console.log(`[MODE15] share_room ignored: completed host room=${room.room_number} viewer=${viewerId}`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
                "data": { "config": (0, attention_config_1.getAttentionConfig)() }
            });
        }
        const shareTypes = (0, sharing_1.normalizeRoomShareTypes)(body.share_type_list);
        const aiSelected = shareTypes.includes(sharing_1.AI_RECRUITMENT_SHARE_TYPE);
        const aiAlreadyActive = room.is_npc_mode;
        if (aiAlreadyActive && !aiSelected)
            shareTypes.push(sharing_1.AI_RECRUITMENT_SHARE_TYPE);
        room.share_room_options = (0, sharing_1.encodeRoomShareOptions)(shareTypes);
        // Option 2 is intentionally repurposed as the private-server AI switch.
        // Once AI has been selected, keep it authoritative for this room. The
        // client may send several share_room refreshes with stale subsets
        // while the three checkboxes are enabled; treating a later [1, 3]
        // refresh as a cancellation leaves the delayed AI reconcile stranded.
        if (aiSelected || aiAlreadyActive) {
            room.is_npc_mode = true;
            (0, recruitment_1.stopRandomRecruitment)(room.room_number);
            (0, lobby_1.recruitNpcMatesForRoom)(room.room_number);
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] share_room: AI recruitment enabled/preserved room=${room.room_number}`);
        }
        else if (shareTypes.includes(sharing_1.RANDOM_RECRUITMENT_SHARE_TYPE)) {
            const recruitment = (0, recruitment_1.publishRandomRecruitment)(room.room_number);
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] share_room: random recruitment published room=${room.room_number} key=${recruitment.attentionKey}`);
        }
        else {
            (0, recruitment_1.stopRandomRecruitment)(room.room_number);
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] share_room: scoped visibility updated room=${room.room_number} options=${room.share_room_options}`);
        }
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": { "config": (0, attention_config_1.getAttentionConfig)() }
        });
    }));
    // ---- disband_room ----
    fastify.post("/disband_room", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body === null || body === void 0 ? void 0 : body.viewer_id;
        const roomNumber = body === null || body === void 0 ? void 0 : body.room_number;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] disband_room: viewer=${viewerId} room=${roomNumber}`);
        if (typeof roomNumber !== "string" || !roomNumber
            || !(yield hasValidViewer(viewerId))) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const room = (0, manager_1.getRoom)(roomNumber);
        // Settlement or disconnect cleanup may already have removed the room
        // before the client returns to the quest selector. Repeated cleanup
        // must succeed; a 400 here makes the CN client show H400 and log out.
        if (room) {
            if (room.host_viewer_id !== viewerId)
                return forbidden(reply);
            const generation = room.lobby_generation;
            yield embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(roomNumber, () => {
                // A queued request belongs only to the room and round that
                // passed the ownership check, even if its number is reused.
                if ((0, manager_1.getRoom)(roomNumber) !== room || room.lobby_generation !== generation)
                    return;
                if (SessionManager_1.sessionManager.commitRoomDisband(roomNumber, `viewer_${viewerId}_requested`)) {
                    (0, game_logging_1.gameVerboseLog)(() => `[MULTI] room ${roomNumber} disbanded by viewer ${viewerId}`);
                }
            });
        }
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {}
        });
    }));
}
exports.registerRoomRoutes = registerRoomRoutes;
