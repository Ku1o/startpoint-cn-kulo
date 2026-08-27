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
const player_1 = require("../../data/domains/player");
const character_1 = require("../../data/domains/character");
const follow_1 = require("../../data/domains/follow");
const utils_1 = require("../../utils");
const attention_rank_1 = require("../../lib/attention-rank");
const profileFavorite_1 = require("../../lib/profileFavorite");
const manager_1 = require("../../multi/room/manager");
const SessionManager_1 = require("../../multi/state/SessionManager");
const recruitment_1 = require("../../multi/recruitment");
const game_logging_1 = require("../../lib/game-logging");
const newbie_1 = require("../../lib/newbie");
const admission_1 = require("../../multi/room/admission");
const player_context_1 = require("../../multi/player-context");
const attention_config_1 = require("../../multi/attention-config");
const mode15_room_gate_1 = require("../../multi/mode15-room-gate");
const mode15_optional_1 = require("../../lib/mode15-optional");
const embedded_1 = require("../../multi/coordinator/embedded");
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/check", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            });
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewerId);
        if (!ctx)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid viewer id or no player bound."
            });
        const { playerId } = ctx;
        const requested = Number.isFinite(body.request_number) ? body.request_number : 3;
        const holding = Number.isFinite(body.holding_number) ? body.holding_number : 0;
        const availableSlots = Math.max(0, Math.min(3, requested) - Math.max(0, holding));
        const recruitments = (0, recruitment_1.takeRandomRecruitments)(viewerId, availableSlots, recruitment => {
            var _a;
            const room = (0, manager_1.getRoom)(recruitment.roomNumber);
            if (!room || room.host_viewer_id === viewerId)
                return false;
            if (room.is_npc_mode || (0, mode15_room_gate_1.isMode15RoomClosed)(room))
                return false;
            if (["STARTING", "BATTLE"].includes(embedded_1.embeddedMultiCoordinator.ensureLifecycle(room).phase))
                return false;
            if ((0, mode15_optional_1.isMode15Quest)(room.category, room.quest_id)
                && !(0, mode15_optional_1.canJoinMode15RescueSync)(playerId, room.category, room.quest_id).allowed)
                return false;
            if (!SessionManager_1.sessionManager.isHostOnline(room.host_viewer_id, room.room_number, room.lobby_generation))
                return false;
            if ((0, manager_1.isRoomWaitingForExpectedMember)(room))
                return false;
            const occupiedViewerIds = new Set((_a = room.member_viewer_ids) !== null && _a !== void 0 ? _a : [room.host_viewer_id]);
            for (const client of SessionManager_1.sessionManager.getClientsInRoom(room.room_number, room.lobby_generation)) {
                if (client.isBattle
                    || client.socket.destroyed
                    || !client.socket.readable
                    || !client.socket.writable)
                    continue;
                occupiedViewerIds.add(client.viewerId);
            }
            return admission_1.roomAdmissionRegistry.getOccupancy(room.room_number, room.lobby_generation, occupiedViewerIds) < 3;
        });
        const multi = recruitments.flatMap(recruitment => {
            var _a, _b, _c, _d;
            const room = (0, manager_1.getRoom)(recruitment.roomNumber);
            if (!room)
                return [];
            const host = (0, player_1.getPlayerSync)(room.host_player_id);
            if (!host)
                return [];
            // Rescue cards must use the same avatar source as the public
            // profile. The legacy leaderCharacterId is still character 1
            // (Arcl) on many old saves, even after the player edits favorites.
            const favorite = (0, profileFavorite_1.getFavoritePartySelectionSync)(room.host_player_id, host.leaderCharacterId);
            const profileLeaderId = (_c = (_b = (_a = favorite.characterIds[0]) !== null && _a !== void 0 ? _a : room.host_main_character_id) !== null && _b !== void 0 ? _b : host.leaderCharacterId) !== null && _c !== void 0 ? _c : 1;
            const leader = (0, character_1.getPlayerCharacterSync)(room.host_player_id, profileLeaderId);
            const isNewbie = (0, newbie_1.isNewbiePlayerSync)(room.host_player_id, host);
            return [{
                    "attention_key": recruitment.attentionKey,
                    "quest_info": {
                        "category_id": room.category,
                        "establisher_character": profileLeaderId,
                        "establisher_character_evolution_img_level": (_d = leader === null || leader === void 0 ? void 0 : leader.evolutionLevel) !== null && _d !== void 0 ? _d : 0,
                        "establisher_follow": (0, follow_1.getFollowRelationSync)(playerId, room.host_player_id).state,
                        "establisher_rank": (0, attention_rank_1.resolveAttentionEstablisherRank)(host.rankPoint || 0),
                        "host_entry_time": room.host_entry_time,
                        "is_newbie": isNewbie,
                        "quest_id": room.quest_id,
                        "room_number": room.room_number,
                    }
                }];
        });
        if (multi.length > 0) {
            (0, game_logging_1.gameVerboseLog)(() => `[ATTENTION] check: viewer=${viewerId} delivered=${multi.length} rooms=${multi.map(item => item.quest_info.room_number).join(",")}`);
        }
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": {
                "config": (0, attention_config_1.getAttentionConfig)(),
                "multi": multi.length > 0 ? multi : null,
            }
        });
    }));
    // ---- action (stub: NPC-only, no real matching) ----
    fastify.post("/action", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!(yield (0, player_context_1.resolveMultiPlayerContext)(viewerId))) {
            console.log(`[ATTENTION] action: 400 invalid viewer_id=${viewerId}`);
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        (0, game_logging_1.gameVerboseLog)(() => { var _a, _b; return `[ATTENTION] action: viewer=${viewerId} factors=${(_b = (_a = body.priority_factors) === null || _a === void 0 ? void 0 : _a.length) !== null && _b !== void 0 ? _b : 0}`; });
        (0, game_logging_1.gameVerboseLog)(() => `[ATTENTION] action: factors_detail=${JSON.stringify(body.priority_factors)}`);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                "priority_action_score": 0,
                "priority_playing_score": 0
            }
        });
    }));
    // ---- logger ----
    fastify.post("/logger", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!(yield (0, player_context_1.resolveMultiPlayerContext)(viewerId))) {
            console.log(`[ATTENTION] logger: 400 invalid viewer_id=${viewerId}`);
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        (0, game_logging_1.gameVerboseLog)(() => { var _a, _b; return `[ATTENTION] logger: viewer=${viewerId} logs=${(_b = (_a = body.client_logs) === null || _a === void 0 ? void 0 : _a.length) !== null && _b !== void 0 ? _b : 0}`; });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {}
        });
    }));
});
exports.default = routes;
