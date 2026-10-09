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
exports.registerBattleRoutes = void 0;
const lobby_runtime_1 = require("../five-boss/lobby-runtime");
const entry_response_1 = require("../five-boss/entry-response");
const continue_runtime_1 = require("../five-boss/continue-runtime");
const active_quest_resolver_1 = require("../../lib/quest/finish/active-quest-resolver");
const contract_1 = require("../five-boss/contract");
const five_boss_battle_1 = require("./five-boss-battle");
const utils_1 = require("../../utils");
const manager_1 = require("../room/manager");
const SessionManager_1 = require("../state/SessionManager");
const singleBattleQuest_1 = require("../../routes/api/singleBattleQuest");
const quest_active_1 = require("../../data/domains/quest_active");
const player_1 = require("../../data/domains/player");
const quest_1 = require("../../data/domains/quest");
const assets_1 = require("../../lib/assets");
const character_1 = require("../../lib/character");
const quest_2 = require("../../lib/quest");
const stamina_1 = require("../../lib/stamina");
const types_1 = require("../../lib/types");
const mission_1 = require("../../lib/mission");
const steam_robot_challenge_1 = require("../../lib/mission/steam-robot-challenge");
const mission_2 = require("../../lib/mission");
const battle_facts_1 = require("../../lib/mission/battle-facts");
const active_reconciliation_1 = require("../../lib/mission/active-reconciliation");
const content_snapshot_1 = require("../../content/runtime/content-snapshot");
const game_logging_1 = require("../../lib/game-logging");
const mail_1 = require("../../data/domains/mail");
const follow_1 = require("../../lib/follow");
const settlement_1 = require("../settlement");
const settlement_performance_1 = require("../../lib/settlement-performance");
const finish_response_cache_1 = require("../../lib/finish-response-cache");
const rescue_fragment_reward_1 = require("../rescue-fragment-reward");
const mode15_room_gate_1 = require("../mode15-room-gate");
const equipment_ready_1 = require("../room/equipment-ready");
const mode15_optional_1 = require("../../lib/mode15-optional");
const player_party_pool_1 = require("../npc/player-party-pool");
const quest_party_pool_shared_1 = require("../npc/quest-party-pool-shared");
const persistence_coordinator_1 = require("../../lib/persistence-coordinator");
const command_names_1 = require("../../lib/persistence/command-names");
const settlement_snapshot_1 = require("../settlement-snapshot");
const embedded_1 = require("../coordinator/embedded");
const mana_1 = require("../../lib/mana");
const player_context_1 = require("../player-context");
const recruitment_1 = require("../recruitment");
const party_1 = require("../../data/domains/party");
const party_current_slot_1 = require("../../lib/party-current-slot");
function buildFinishFollowInfo(requesterPlayerId_1, viewerId_1, mateResults_1) {
    return __awaiter(this, arguments, void 0, function* (requesterPlayerId, viewerId, mateResults, fallbackMateIds = []) {
        const ids = new Set();
        for (const result of mateResults) {
            const mateViewerId = Number(result === null || result === void 0 ? void 0 : result.viewer_id);
            if (Number.isFinite(mateViewerId))
                ids.add(mateViewerId);
        }
        for (const mateViewerId of fallbackMateIds) {
            if (Number.isFinite(mateViewerId))
                ids.add(Number(mateViewerId));
        }
        const followInfo = [];
        for (const mateViewerId of ids) {
            if (mateViewerId === viewerId || mateViewerId >= 900000000)
                continue;
            const mateCtx = yield (0, player_context_1.resolveMultiPlayerContext)(mateViewerId);
            if (!mateCtx)
                continue;
            const info = (0, follow_1.buildFollowUserInfoSync)(requesterPlayerId, mateCtx.playerId);
            if (info)
                followInfo.push(info);
        }
        return followInfo;
    });
}
function sendMultiStartUnavailable(reply, viewerId, reason) {
    console.warn(`[MULTI] start acknowledged as unavailable: viewer=${viewerId} reason=${reason}`);
    reply.header("content-type", "application/x-msgpack");
    return reply.status(200).send({
        data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId, result_code: 4050 }),
        data: {},
    });
}
function buildTerminalMultiFinishAcknowledgement(player, body) {
    var _a, _b;
    const dataHeaders = (0, utils_1.generateDataHeaders)({ viewer_id: body.viewer_id });
    return {
        data_headers: dataHeaders,
        data: {
            user_info: {
                free_mana: player.freeMana,
                exp_pool: player.expPool,
                exp_pooled_time: (0, utils_1.getServerTime)(player.expPooledTime),
                free_vmoney: player.freeVmoney,
                rank_point: player.rankPoint,
                degree_id: (_a = player.degreeId) !== null && _a !== void 0 ? _a : 1,
                stamina: player.stamina,
                stamina_heal_time: (0, utils_1.realToVirtual)(player.staminaHealTime),
                boost_point: player.boostPoint,
                boss_boost_point: player.bossBoostPoint,
            },
            add_exp_list: [],
            character_list: [],
            bond_token_status_list: [],
            rewards: {
                overflow_pool_exp: 0,
                converted_pool_exp: 0,
                reward_pool_exp: 0,
                reward_mana: 0,
                field_mana: 0,
            },
            old_high_score: 0,
            joined_character_id_list: [],
            before_rank_point: player.rankPoint,
            clear_rank: 0,
            drop_score_reward_ids: [],
            drop_rare_reward_ids: [],
            drop_additional_reward_ids: [],
            drop_periodic_reward_ids: [],
            equipment_list: [],
            category_id: Number(body.category) || 0,
            start_time: dataHeaders.servertime,
            is_multi: "multi",
            quest_name: "",
            item_list: {},
            presigned_quest_category: [],
            mate_player_result: (_b = body.mate_player_result) !== null && _b !== void 0 ? _b : [],
            follow_info: [],
            contribution_score: Number(body.contribution_score) || 0,
            host_finished: false,
            aborted_play_id: null,
            unfinished_play_id: null,
            mail_arrived: (0, mail_1.getPlayerMailCountSync)(player.id, true) > 0,
        },
    };
}
function activeQuestFromPersistent(quest) {
    var _a, _b, _c, _d, _e, _f;
    return {
        questId: quest.questId,
        category: quest.category,
        useBossBoostPoint: quest.useBossBoostPoint,
        useBoostPoint: quest.useBoostPoint,
        isAutoStartMode: quest.isAutoStartMode,
        isMulti: quest.isMulti,
        isMultiHost: quest.isMultiHost,
        roomNumber: (_a = quest.roomNumber) !== null && _a !== void 0 ? _a : undefined,
        entryItemId: (_b = quest.entryItemId) !== null && _b !== void 0 ? _b : undefined,
        eventId: (_c = quest.eventId) !== null && _c !== void 0 ? _c : undefined,
        partySlot: (_d = quest.partySlot) !== null && _d !== void 0 ? _d : undefined,
        playId: quest.playId,
        continueCount: quest.continueCount,
        startedAtMs: (_e = quest.startedAtMs) !== null && _e !== void 0 ? _e : undefined,
        questTimeRevision: (_f = quest.questTimeRevision) !== null && _f !== void 0 ? _f : null,
    };
}
function clearMatchingMultiActiveQuest(playerId, playId, operation) {
    return __awaiter(this, void 0, void 0, function* () {
        var _a, _b;
        if (typeof playId !== "string" || playId.length === 0)
            return false;
        let deleted = false;
        yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "multi-settlement",
            playerId,
            operation,
        }, () => {
            const persisted = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
            if ((persisted === null || persisted === void 0 ? void 0 : persisted.isMulti) && persisted.playId === playId) {
                deleted = (0, quest_active_1.deletePlayerActiveQuestIfPlayIdSync)(playerId, playId);
            }
        });
        if (((_a = singleBattleQuest_1.activeQuests[playerId]) === null || _a === void 0 ? void 0 : _a.isMulti) && ((_b = singleBattleQuest_1.activeQuests[playerId]) === null || _b === void 0 ? void 0 : _b.playId) === playId) {
            delete singleBattleQuest_1.activeQuests[playerId];
            deleted = true;
        }
        return deleted;
    });
}
function registerBattleRoutes(fastify) {
    // ---- start ----
    fastify.post("/start", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        var _a;
        const body = request.body;
        const { viewer_id, quest_id, category, party_id, use_boost_point, use_boss_boost_point, is_auto_start_mode, room_number, mate_player_ids, play_id } = body;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] start: viewer=${viewer_id} quest=${quest_id} category=${category} party=${party_id} room=${room_number}`);
        if (isNaN(viewer_id) || isNaN(party_id) || isNaN(quest_id) || isNaN(category) || use_boost_point === undefined || use_boss_boost_point === undefined || is_auto_start_mode === undefined) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewer_id);
        if (!ctx) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id or no player bound."
            });
        }
        // A rescue guest who already entered the room keeps the client-side
        // attention key, but the key's stopped-notice grace can expire during
        // a long lobby wait. Room membership is the stronger proof at this
        // point, so only validate the key for viewers who are not members yet.
        const attentionRoom = room_number ? (0, manager_1.getRoom)(room_number) : undefined;
        const alreadyRoomMember = !!attentionRoom && (0, manager_1.isRoomMember)(attentionRoom, viewer_id);
        if (body.attention_key
            && !alreadyRoomMember
            && !(0, recruitment_1.validateRandomRecruitmentAttention)(room_number, viewer_id, body.attention_key)) {
            return sendMultiStartUnavailable(reply, viewer_id, "attention_expired");
        }
        if ((0, contract_1.isFiveBossHiddenQuest)(category, quest_id)) {
            return reply.status(400).send({ error: "Bad Request", message: "Internal five-boss scene is not an entry quest." });
        }
        const questData = (0, assets_1.getQuestFromCategorySync)(category, quest_id);
        if (questData === null || !('rankPointReward' in questData)) {
            return sendMultiStartUnavailable(reply, viewer_id, "quest_missing");
        }
        const roomStart = yield embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(room_number, () => {
            var _a, _b, _c;
            const currentRoom = (0, manager_1.getRoom)(room_number);
            if (!currentRoom)
                return { status: "missing" };
            if (currentRoom.category !== category || currentRoom.quest_id !== quest_id) {
                return { status: "quest_mismatch" };
            }
            if (!(0, manager_1.isRoomMember)(currentRoom, viewer_id)) {
                return { status: "forbidden" };
            }
            const recordedPlayerId = (0, manager_1.getRoomMemberPlayerId)(currentRoom, viewer_id);
            if (recordedPlayerId !== null && recordedPlayerId !== ctx.playerId) {
                return { status: "player_mismatch" };
            }
            if ((0, mode15_room_gate_1.isMode15RoomClosed)(currentRoom)) {
                return { status: "mode15_closed", room: currentRoom };
            }
            if (currentRoom.lifecycle.phase === "LOBBY") {
                // Validate the entire roster before HTTP can beat TCP to BATTLE.
                if (!(0, equipment_ready_1.enforceRoomEquipmentReady)(currentRoom))
                    return { status: "unavailable" };
                const peers = SessionManager_1.sessionManager.getClientsInRoom(room_number, currentRoom.lobby_generation)
                    .filter(peer => !peer.isBattle && peer.enterData !== null && peer.yourself);
                if (peers.some(peer => { var _a; return ((_a = peer.yourself.state) === null || _a === void 0 ? void 0 : _a[0]) !== 1; })) {
                    return { status: "unavailable" };
                }
                const requester = peers.find(peer => peer.viewerId === viewer_id);
                if (requester && (0, equipment_ready_1.selectedPartyId)(requester) !== party_id) {
                    return { status: "unavailable" };
                }
            }
            if (!(0, mode15_optional_1.isMode15EquipmentAllowedQuest)(category, quest_id)) {
                const frozenPartyId = (_a = currentRoom.equipmentPartyIds) === null || _a === void 0 ? void 0 : _a[viewer_id];
                // A later save must not invalidate a battle already approved
                // for the same selection. Explicit request forgery still fails.
                if ((frozenPartyId !== undefined && frozenPartyId !== party_id)
                    || (0, equipment_ready_1.exclusiveWirePartyItems)(body.client_battle_party).length > 0
                    || ((_b = body.mate_party_ids) === null || _b === void 0 ? void 0 : _b.some(party => (0, equipment_ready_1.exclusiveWirePartyItems)(party).length > 0))
                    || (frozenPartyId === undefined
                        && (0, mode15_optional_1.getMode15ExclusiveGlobalPartyItemsSync)(ctx.playerId, 1, party_id).length > 0)) {
                    return { status: "unavailable" };
                }
            }
            if (!(0, lobby_runtime_1.freezeFiveBossLobby)(currentRoom))
                return { status: "unavailable" };
            const sourceGeneration = currentRoom.lifecycle.phase === "BATTLE"
                ? Math.max(0, currentRoom.lobby_generation - 1) : currentRoom.lobby_generation;
            if (!(0, manager_1.setRoomBattle)(room_number)) {
                return { status: "unavailable" };
            }
            if (!currentRoom.equipmentPartyIds)
                (0, equipment_ready_1.freezeEquipmentSelections)(currentRoom, sourceGeneration);
            // Take owned copies inside the room queue. Persistence below can
            // yield while this room returns to LOBBY or starts another battle.
            const npcPartySnapshot = (_c = currentRoom.npcPartySnapshots) === null || _c === void 0 ? void 0 : _c[viewer_id];
            return {
                status: "ready",
                room: currentRoom,
                roomGeneration: currentRoom.lobby_generation,
                mateComIds: currentRoom.mates.map(mate => mate.com_id),
                participants: currentRoom.mates
                    .map(mate => ({ viewerId: Number(mate.viewer_id), comId: Number(mate.com_id || 0) }))
                    .filter(mate => Number.isFinite(mate.viewerId) && mate.viewerId > 0),
                expectedRealViewerIds: currentRoom.expected_real_viewer_ids
                    .map(Number).filter(id => Number.isFinite(id) && id > 0),
                isHost: currentRoom.host_viewer_id === viewer_id,
                isRescueGuest: SessionManager_1.sessionManager.isRescueGuest(room_number, viewer_id),
                isRescueFragmentEligible: SessionManager_1.sessionManager.isRescueFragmentEligibleGuest(room_number, viewer_id),
                isNewbieRescueGuest: SessionManager_1.sessionManager.isNewbieRescueGuest(room_number, viewer_id),
                npcPartySnapshot: questData.fixedParty === undefined
                    && (npcPartySnapshot === null || npcPartySnapshot === void 0 ? void 0 : npcPartySnapshot.partySlot) === party_id
                    && npcPartySnapshot.sourcePlayerId === ctx.playerId
                    ? (0, quest_party_pool_shared_1.cloneQuestNpcPartySnapshot)(npcPartySnapshot) : undefined,
            };
        });
        if (roomStart.status === "forbidden") {
            return reply.status(403).send({
                error: "Forbidden",
                message: "Room permission denied.",
            });
        }
        if (roomStart.status === "player_mismatch") {
            return reply.status(400).send({
                error: "Bad Request",
                message: "Room player mismatch.",
            });
        }
        if (roomStart.status === "missing"
            || roomStart.status === "unavailable"
            || roomStart.status === "quest_mismatch") {
            return sendMultiStartUnavailable(reply, viewer_id, roomStart.status);
        }
        // The host's first successful settlement advances Mode15 immediately.
        // A legacy client may keep the old room and request another battle, so
        // validate the room owner again at the final HTTP start boundary.
        if (roomStart.status === "mode15_closed") {
            console.log(`[MODE15] multi start denied: completed host room=${room_number} host=${roomStart.room.host_player_id}`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id, result_code: 4507 }),
                "data": {},
            });
        }
        const room = roomStart.room;
        if ((0, five_boss_battle_1.shouldHandleFiveBossStart)(body)) {
            try {
                return yield (0, five_boss_battle_1.handleFiveBossStart)(body, ctx.playerId, reply);
            }
            catch (error) {
                if (!(0, five_boss_battle_1.isFiveBossBattleRequestError)(error))
                    throw error;
                (0, five_boss_battle_1.logFiveBossRequestFailure)("start", body, ctx.playerId, error);
                if ((0, entry_response_1.isFiveBossTicketShortage)(error))
                    return (0, entry_response_1.sendFiveBossTicketShortage)(reply, viewer_id);
                return sendMultiStartUnavailable(reply, viewer_id, `five_boss_${(_a = error.code) !== null && _a !== void 0 ? _a : "rejected"}`);
            }
        }
        const mateComIds = roomStart.mateComIds;
        const activeQuest = {
            questId: quest_id,
            category,
            useBoostPoint: use_boost_point,
            useBossBoostPoint: use_boss_boost_point,
            isAutoStartMode: is_auto_start_mode,
            isMulti: true,
            isMultiHost: roomStart.isHost,
            roomNumber: room_number,
            matePlayerIds: mate_player_ids,
            mateComIds,
            partySlot: party_id,
            playId: play_id,
            continueCount: 0,
        };
        // The active quest is part of the same durable start command as the
        // selected party. Keeping this write outside the coordinator lets a
        // busy settlement or checkpoint race it and surface SQLITE_BUSY on
        // /multi_battle_quest/start.
        const previousActiveQuest = singleBattleQuest_1.activeQuests[ctx.playerId];
        try {
            yield (0, persistence_coordinator_1.runPersistenceTransaction)({
                domain: "multi-settlement", playerId: ctx.playerId, operation: "start",
            }, () => {
                (0, singleBattleQuest_1.insertActiveQuest)(ctx.playerId, activeQuest);
                if (questData.fixedParty === undefined
                    && (0, party_current_slot_1.usesNormalCurrentPartySlot)(category)
                    && (0, party_1.isValidNormalPartySlotSync)(ctx.playerId, party_id)) {
                    (0, player_1.updatePlayerSync)({ id: ctx.playerId, partySlot: party_id });
                }
            });
        }
        catch (error) {
            if (previousActiveQuest)
                singleBattleQuest_1.activeQuests[ctx.playerId] = previousActiveQuest;
            else
                delete singleBattleQuest_1.activeQuests[ctx.playerId];
            throw error;
        }
        (0, settlement_snapshot_1.registerMultiSettlementSnapshot)({
            battleInstanceId: (0, settlement_snapshot_1.buildBattleInstanceId)(room_number, roomStart.roomGeneration, category, quest_id),
            playerId: ctx.playerId,
            viewerId: viewer_id,
            playId: play_id,
            roomNumber: room_number,
            roomGeneration: roomStart.roomGeneration,
            activeQuest,
            participants: roomStart.participants,
            expectedRealViewerIds: roomStart.expectedRealViewerIds,
            npcPartySnapshot: roomStart.npcPartySnapshot,
            isHost: roomStart.isHost,
            isRescueGuest: roomStart.isRescueGuest,
            isRescueFragmentEligible: roomStart.isRescueFragmentEligible,
            isNewbieRescueGuest: roomStart.isNewbieRescueGuest,
        });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id }),
            "data": {
                "is_multi": "multi",
                "play_id": play_id,
                "client_checks": (0, steam_robot_challenge_1.getSteamRobotMissionClientChecks)(category, quest_id),
            }
        });
    }));
    // ---- finish ----
    fastify.post("/finish", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        var _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q, _r, _s, _t, _u, _v, _w, _x, _y, _z, _0, _1, _2, _3, _4, _5, _6, _7;
        const finishHandlerStartedAt = process.hrtime.bigint();
        const body = request.body;
        const viewerId = body.viewer_id;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] finish: viewer=${viewerId} quest=${body.quest_id} category=${body.category} room=${body.room_number}`);
        if (!viewerId || isNaN(viewerId)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewerId);
        if (!ctx || !ctx.player) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id."
            });
        }
        const { playerId, player } = ctx;
        if ((0, five_boss_battle_1.shouldHandleFiveBossMemberRequest)(body, playerId)) {
            try {
                return yield (0, five_boss_battle_1.handleFiveBossFinish)(body, playerId, reply, (viewer, mates, fallback) => buildFinishFollowInfo(playerId, viewer, mates, fallback));
            }
            catch (error) {
                if (!(0, five_boss_battle_1.isFiveBossBattleRequestError)(error))
                    throw error;
                (0, five_boss_battle_1.logFiveBossRequestFailure)("finish", body, playerId, error);
                return reply.status(400).send({ error: "Bad Request", message: error.message });
            }
        }
        const finishCacheKey = (0, finish_response_cache_1.buildFinishResponseCacheKey)("multi", viewerId, body);
        const cachedFinishResponse = (0, finish_response_cache_1.getCachedFinishResponse)(finishCacheKey);
        if (cachedFinishResponse !== undefined) {
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send(cachedFinishResponse);
        }
        const executionWaitStartedAt = process.hrtime.bigint();
        const releaseFinishExecution = yield (0, finish_response_cache_1.acquireFinishExecution)(finishCacheKey);
        (0, settlement_performance_1.recordSettlementPhase)("multi", "finish_execution_wait", Number(process.hrtime.bigint() - executionWaitStartedAt) / 1000000);
        reply.raw.once("finish", releaseFinishExecution);
        reply.raw.once("close", releaseFinishExecution);
        // A matching request may have completed while this one waited.
        const coalescedFinishResponse = (0, finish_response_cache_1.getCachedFinishResponse)(finishCacheKey);
        if (coalescedFinishResponse !== undefined) {
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send(coalescedFinishResponse);
        }
        const settlementSnapshot = (0, settlement_snapshot_1.getMultiSettlementSnapshot)(playerId, body.play_id);
        const currentActiveQuest = singleBattleQuest_1.activeQuests[playerId];
        const persistentActiveQuest = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
        // A delayed finish from the previous generation must use its frozen
        // snapshot. Taking the current active quest first can settle or clear a
        // rematch that merely happens to belong to the same player.
        const persistentMatches = (persistentActiveQuest === null || persistentActiveQuest === void 0 ? void 0 : persistentActiveQuest.isMulti)
            && persistentActiveQuest.playId === body.play_id;
        const activeQuestData = (_b = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.activeQuest) !== null && _b !== void 0 ? _b : (persistentMatches
            ? activeQuestFromPersistent(persistentActiveQuest)
            : persistentActiveQuest === null
                && (currentActiveQuest === null || currentActiveQuest === void 0 ? void 0 : currentActiveQuest.playId) === body.play_id
                ? currentActiveQuest
                : undefined);
        if (activeQuestData === undefined) {
            const terminal = buildTerminalMultiFinishAcknowledgement(player, body);
            (0, finish_response_cache_1.cacheFinishResponse)(finishCacheKey, terminal);
            console.warn(`[MULTI] stale finish acknowledged: viewer=${viewerId}`
                + ` play=${body.play_id} reason=active_quest_missing`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send(terminal);
        }
        const finishRoom = activeQuestData.roomNumber
            ? (0, manager_1.getRoom)(activeQuestData.roomNumber)
            : undefined;
        const settlementGeneration = (_d = (_c = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.roomGeneration) !== null && _c !== void 0 ? _c : finishRoom === null || finishRoom === void 0 ? void 0 : finishRoom.lobby_generation) !== null && _d !== void 0 ? _d : 0;
        const settlementKey = (_e = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.battleInstanceId) !== null && _e !== void 0 ? _e : `${activeQuestData.roomNumber || body.room_number || "missing"}:${settlementGeneration}:${body.play_id}`;
        const settlementParticipants = (_f = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.participants) !== null && _f !== void 0 ? _f : ((finishRoom === null || finishRoom === void 0 ? void 0 : finishRoom.mates) || [])
            .map(mate => ({
            viewerId: Number(mate.viewer_id),
            comId: Number(mate.com_id || 0),
        }))
            .filter(mate => Number.isFinite(mate.viewerId) && mate.viewerId > 0);
        const expectedRealViewerIds = (_g = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.expectedRealViewerIds) !== null && _g !== void 0 ? _g : ((finishRoom === null || finishRoom === void 0 ? void 0 : finishRoom.expected_real_viewer_ids) || [])
            .map(Number)
            .filter(expectedViewerId => Number.isFinite(expectedViewerId) && expectedViewerId > 0);
        const finishedAsRescueGuest = (_h = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.isRescueGuest) !== null && _h !== void 0 ? _h : (activeQuestData.roomNumber
            ? SessionManager_1.sessionManager.isRescueGuest(activeQuestData.roomNumber, viewerId)
            : false);
        const finishedAsRescueFragmentEligible = (_j = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.isRescueFragmentEligible) !== null && _j !== void 0 ? _j : (activeQuestData.roomNumber
            ? SessionManager_1.sessionManager.isRescueFragmentEligibleGuest(activeQuestData.roomNumber, viewerId)
            : false);
        const finishedAsNewbieRescueGuest = (_k = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.isNewbieRescueGuest) !== null && _k !== void 0 ? _k : (activeQuestData.roomNumber
            ? SessionManager_1.sessionManager.isNewbieRescueGuest(activeQuestData.roomNumber, viewerId)
            : false);
        const questCategory = activeQuestData.category;
        const questId = activeQuestData.questId;
        const questData = (0, assets_1.getQuestFromCategorySync)(questCategory, questId);
        if (questData === null || !('rankPointReward' in questData)) {
            yield clearMatchingMultiActiveQuest(playerId, body.play_id, "stale_finish_unknown_quest");
            const terminal = buildTerminalMultiFinishAcknowledgement(player, body);
            (0, finish_response_cache_1.cacheFinishResponse)(finishCacheKey, terminal);
            console.warn(`[MULTI] stale finish acknowledged: viewer=${viewerId}`
                + ` play=${body.play_id} reason=quest_missing category=${questCategory} quest=${questId}`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send(terminal);
        }
        (0, settlement_performance_1.recordSettlementPhase)("multi", "preflight", Number(process.hrtime.bigint() - finishHandlerStartedAt) / 1000000);
        const coreStartedAt = process.hrtime.bigint();
        const settlementWasAlreadyInLobby = (settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.lifecycle) === "LOBBY";
        const settlingSnapshot = (0, settlement_snapshot_1.transitionMultiSettlementSnapshot)(playerId, body.play_id, "SETTLING");
        const finishedAsHost = (_l = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.isHost) !== null && _l !== void 0 ? _l : (activeQuestData.roomNumber
            ? ((_m = (0, manager_1.getRoom)(activeQuestData.roomNumber)) === null || _m === void 0 ? void 0 : _m.host_player_id) === playerId
            : false);
        if (activeQuestData.roomNumber) {
            yield embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(activeQuestData.roomNumber, () => {
                var _a;
                const room = (0, manager_1.getRoom)(activeQuestData.roomNumber);
                const matchesBattleGeneration = (room === null || room === void 0 ? void 0 : room.lobby_generation) === settlementGeneration;
                const lifecycleAllowsRoomMutation = settlementSnapshot === undefined
                    || (!settlementWasAlreadyInLobby && (settlingSnapshot === null || settlingSnapshot === void 0 ? void 0 : settlingSnapshot.lifecycle) !== "LOBBY");
                if (room && matchesBattleGeneration && lifecycleAllowsRoomMutation) {
                    const wasPending = room.settlement_return_pending;
                    const transition = embedded_1.embeddedMultiCoordinator.beginSettlementReturn(room, settlementGeneration);
                    if (!transition.ok) {
                        console.warn(`[MULTI-SETTLEMENT] lifecycle rejected finish room=${room.room_number}`
                            + ` viewer=${viewerId} reason=${transition.reason}`);
                        return;
                    }
                    SessionManager_1.sessionManager.clearBattleExpectedCount(activeQuestData.roomNumber);
                    if (!wasPending)
                        SessionManager_1.sessionManager.beginSettlementReturnGrace(room.room_number);
                    (0, settlement_snapshot_1.transitionMultiSettlementSnapshot)(playerId, body.play_id, "RETURN_PENDING");
                    (0, game_logging_1.gameVerboseLog)(() => `[MULTI] finish: room ${activeQuestData.roomNumber}`
                        + ` entered RETURNING by viewer=${viewerId}`);
                }
                else if (room) {
                    console.warn(`[MULTI-SETTLEMENT] skipped stale finish room mutation: room=${room.room_number}`
                        + ` viewer=${viewerId} finishGeneration=${settlementGeneration}`
                        + ` currentGeneration=${room.lobby_generation} lifecycle=${(_a = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.lifecycle) !== null && _a !== void 0 ? _a : "missing"}`);
                }
            });
        }
        // calculate clear rank
        const clearTime = body.elapsed_time_ms || 0;
        const hasRankThresholds = questData.bRankTime > 0;
        const clearRank = hasRankThresholds ? (questData.sPlusRankTime >= clearTime ? 5
            : questData.sRankTime >= clearTime ? 4
                : questData.aRankTime >= clearTime ? 3
                    : questData.bRankTime >= clearTime ? 2
                        : 1) : null;
        const beforeRankPoint = player.rankPoint;
        const displayMode15ManaAsFieldDrop = (0, mode15_optional_1.isMode15Quest)(questCategory, questId);
        const newRankPoint = beforeRankPoint + questData.rankPointReward;
        const manaObtained = questData.manaReward + (body.add_mana || 0);
        const newMana = (0, mana_1.calculateFreeManaGrant)(player, manaObtained).freeMana;
        let newBoostPoint = player.boostPoint - (activeQuestData.useBoostPoint ? 1 : 0);
        let newBossBoostPoint = player.bossBoostPoint - (activeQuestData.useBossBoostPoint ? 1 : 0);
        const useBoostPoint = (activeQuestData.useBoostPoint && (newBoostPoint >= 0)) || (activeQuestData.useBossBoostPoint && (newBossBoostPoint >= 0));
        // quest progress
        // Abyss progress refresh can update legacy best-time rows. It must
        // share the persistence owner with the rest of the finish path;
        // otherwise this apparently read-only lookup races another writer and
        // becomes the SQLITE_BUSY stack seen in cloud logs.
        const questProgress = yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "progress_refresh", () => ((0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "multi-settlement", playerId, operation: "progress_refresh",
        }, () => (0, quest_1.getPlayerSingleQuestProgressSync)(playerId, questCategory, questId))));
        const questPreviouslyCompleted = questProgress !== null;
        const questAccomplished = body.is_accomplished;
        const leaderId = (_s = (_r = (_q = (((_o = body.statistics) === null || _o === void 0 ? void 0 : _o.party) || ((_p = body.quest_statistics) === null || _p === void 0 ? void 0 : _p.party))) === null || _q === void 0 ? void 0 : _q.characters) === null || _r === void 0 ? void 0 : _r[0]) === null || _s === void 0 ? void 0 : _s.id;
        const eligibleRescueFragmentReward = (0, rescue_fragment_reward_1.getEligibleRescueFragmentReward)(questCategory, questId, questAccomplished, finishedAsRescueFragmentEligible);
        const bodyPartyStatistics = ((_t = body.statistics) === null || _t === void 0 ? void 0 : _t.party)
            || ((_u = body.quest_statistics) === null || _u === void 0 ? void 0 : _u.party)
            || { characters: [], unison_characters: [] };
        let clearReward = null;
        let sPlusClearReward = null;
        let rescueFragmentReward = null;
        let scoreRewardsResult;
        const oldRkDegree = (0, stamina_1.getRankDegree)(beforeRankPoint);
        const newDegreeId = (0, stamina_1.getRankDegree)(newRankPoint);
        const didLevelUp = newDegreeId > oldRkDegree;
        const playerData = player;
        const mode15RewardsResult = yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "reward_transaction", () => (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "multi-settlement", playerId, operation: "reward_transaction",
        }, () => {
            var _a, _b, _c, _d;
            if (questAccomplished) {
                if (questPreviouslyCompleted) {
                    const updateData = {
                        questId: questId,
                        finished: true,
                        hostFinished: questProgress.hostFinished || finishedAsHost,
                        bestElapsedTimeMs: questProgress.bestElapsedTimeMs === undefined || questProgress.bestElapsedTimeMs === null ? clearTime : Math.min(clearTime, questProgress.bestElapsedTimeMs),
                        highScore: questProgress.highScore === undefined ? (body.score || 0) : Math.max(body.score || 0, questProgress.highScore),
                        leaderCharacterId: leaderId !== null && leaderId !== void 0 ? leaderId : null
                    };
                    if (clearRank !== null) {
                        updateData.clearRank = questProgress.clearRank === undefined ? clearRank : Math.max(clearRank, questProgress.clearRank);
                    }
                    (0, quest_1.updatePlayerQuestProgressSync)(playerId, questCategory, updateData);
                }
                else {
                    (0, quest_1.insertPlayerQuestProgressSync)(playerId, questCategory, {
                        questId: questId,
                        finished: true,
                        hostFinished: finishedAsHost,
                        bestElapsedTimeMs: clearTime,
                        highScore: body.score || 0,
                        clearRank: clearRank !== null && clearRank !== void 0 ? clearRank : 5,
                        leaderCharacterId: leaderId !== null && leaderId !== void 0 ? leaderId : null
                    });
                }
            }
            (0, player_1.updatePlayerSync)(Object.assign({ id: playerId, freeMana: newMana, rankPoint: newRankPoint, boostPoint: newBoostPoint, bossBoostPoint: newBossBoostPoint, totalManaObtained: ((_a = player.totalManaObtained) !== null && _a !== void 0 ? _a : 0) + manaObtained, maxComboAchieved: Math.max((_b = player.maxComboAchieved) !== null && _b !== void 0 ? _b : 0, (_d = (_c = body.statistics) === null || _c === void 0 ? void 0 : _c.max_combo_count) !== null && _d !== void 0 ? _d : 0) }, (didLevelUp ? { stamina: player.stamina + (0, stamina_1.getMaxStamina)(newDegreeId), staminaHealTime: new Date() } : {})));
            if ((0, player_1.adjustPlayerExpPoolSync)(playerId, questData.poolExpReward, 'multi_battle_base_reward') === null) {
                throw new Error(`Failed to grant multi battle EXP to player ${playerId}`);
            }
            clearReward = !questPreviouslyCompleted && questData.clearReward != null ? (0, quest_2.givePlayerRewardSync)(playerId, questData.clearReward) : null;
            const isExpertSingleEvent = questCategory === types_1.QuestCategory.EXPERT_SINGLE_EVENT;
            const shouldGrantSPlusReward = isExpertSingleEvent
                ? (questProgress === null || questProgress === void 0 ? void 0 : questProgress.sPlusRewardReceived) !== true
                : (questProgress === null || questProgress === void 0 ? void 0 : questProgress.clearRank) !== 5;
            sPlusClearReward = (clearRank === 5) && shouldGrantSPlusReward && (questData.sPlusReward !== undefined)
                ? (0, quest_2.givePlayerRewardSync)(playerId, questData.sPlusReward)
                : null;
            if (isExpertSingleEvent && sPlusClearReward !== null) {
                (0, quest_1.updatePlayerQuestProgressSync)(playerId, questCategory, {
                    questId,
                    sPlusRewardReceived: true,
                });
                console.log(`[EXPERT_SINGLE_EVENT] SS reward granted: player=${playerId} quest=${questId} item=14040 count=3`);
            }
            if (didLevelUp) {
                playerData.stamina = playerData.stamina + (0, stamina_1.getMaxStamina)(newDegreeId);
                playerData.staminaHealTime = new Date();
            }
            scoreRewardsResult = (0, quest_2.givePlayerScoreRewardsSync)(playerId, questData.scoreRewardGroupId || 0, questData.scoreRewardGroup, useBoostPoint, questData.element, { questId, mode: "multi" });
            if (eligibleRescueFragmentReward !== null) {
                rescueFragmentReward = (0, quest_2.givePlayerRewardSync)(playerId, eligibleRescueFragmentReward);
                (0, game_logging_1.gameVerboseLog)(() => `[MULTI] rescue fragment granted: player=${playerId} quest=${questId} `
                    + `item=${eligibleRescueFragmentReward.id} count=${eligibleRescueFragmentReward.count}`);
            }
            // Mode15 settlement writes the cross-event progress marker and extra
            // rewards. Keep it inside the same transaction as the ordinary multi
            // rewards so this path cannot reopen the main database without the
            // persistence owner.
            return (0, mode15_optional_1.settleMode15BattleSync)(playerId, questCategory, questId, questAccomplished, {
                rescue: !finishedAsHost,
                playedParty: {
                    characterIds: (bodyPartyStatistics.characters || []).map((value) => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; }),
                    unisonCharacterIds: (bodyPartyStatistics.unison_characters || []).map((value) => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; }),
                    equipmentIds: (bodyPartyStatistics.equipments || []).map((value) => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; }),
                    abilitySoulIds: [...(bodyPartyStatistics.ability_soul_ids || [])],
                    evolutionImgLevels: (0, character_1.getCharactersEvolutionImgLevels)(playerId, (bodyPartyStatistics.characters || []).map((value) => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; })),
                    unisonEvolutionImgLevels: (0, character_1.getCharactersEvolutionImgLevels)(playerId, (bodyPartyStatistics.unison_characters || []).map((value) => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; })),
                },
            });
        }));
        const settledClearReward = clearReward;
        const settledSPlusClearReward = sPlusClearReward;
        const settledRescueFragmentReward = rescueFragmentReward;
        const rescueFragmentAdditionalReward = (0, rescue_fragment_reward_1.getRescueFragmentAdditionalReward)(eligibleRescueFragmentReward);
        const partyCharacterIdsArray = [];
        for (const value of [...(bodyPartyStatistics.characters || []), ...(bodyPartyStatistics.unison_characters || [])]) {
            if (value !== null && value.id !== null && value.id !== undefined)
                partyCharacterIdsArray.push(value.id);
        }
        // Track mission progress (decoupled from core quest mechanics)
        const finishCtx = {
            playerId, questCategory, questId,
            questAccomplished,
            clearTime, clearRank,
            party: bodyPartyStatistics,
            statistics: body.statistics || body.quest_statistics || {},
            player,
            questPreviouslyCompleted,
            questProgress,
            partySlot: (_v = activeQuestData.partySlot) !== null && _v !== void 0 ? _v : player.partySlot,
            isMulti: true,
            isMultiHost: finishedAsHost,
        };
        const multiBattleParty = (0, mission_1.collectPartyCharacterIds)(finishCtx.party);
        const missionEvaluationTime = new Date((0, utils_1.getServerTime)() * 1000);
        let missionBattleFacts;
        let steamRobotMissionId = null;
        let rewardCharacterExpResult;
        yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "facts_transaction", () => __awaiter(this, void 0, void 0, function* () {
            const factsResult = yield (0, persistence_coordinator_1.runWriterCommand)(command_names_1.MULTI_RECORD_BATTLE_FACTS, {
                finishCtx,
                partyCharacterIdsArray,
                characterExpReward: questData.characterExpReward || 0,
                fixedParty: questData.fixedParty !== undefined,
                evaluationTimeMs: missionEvaluationTime.getTime(),
            }, { domain: "multi-settlement", playerId, operation: "facts_transaction" });
            missionBattleFacts = factsResult.missionBattleFacts;
            steamRobotMissionId = factsResult.steamRobotMissionId;
            rewardCharacterExpResult = factsResult.rewardCharacterExpResult;
        }));
        const dataHeaders = (0, utils_1.generateDataHeaders)({ viewer_id: viewerId });
        const rawMatePlayerResult = (body.mate_player_result || []);
        (0, settlement_performance_1.recordSettlementPhase)("multi", "core", Number(process.hrtime.bigint() - coreStartedAt) / 1000000);
        const settlementResult = yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "barrier", () => (0, settlement_1.mergeMultiSettlementResults)({
            key: settlementKey,
            viewerId,
            participants: settlementParticipants,
            expectedRealViewerIds,
            ownScore: body.score || 0,
            ownContributionScore: body.contribution_score || 0,
            mateResults: rawMatePlayerResult,
            // Preserve the original repaired 1.2-second compatibility
            // barrier.  mergeMultiSettlementResults still returns early as
            // soon as every real participant has submitted.
            waitMs: parseInt(process.env.MULTI_SETTLEMENT_BARRIER_MS || "1200", 10),
        }));
        const postBarrierStartedAt = process.hrtime.bigint();
        const matePlayerResult = settlementResult.mateResults;
        const ownContributionScore = Number(body.contribution_score) || 0;
        const highestContributionScore = Math.max(ownContributionScore, ...matePlayerResult.map(result => Number(result.contribution_score) || 0));
        const finishedAsMvp = Boolean((_w = finishCtx.statistics) === null || _w === void 0 ? void 0 : _w.is_mvp)
            || ownContributionScore >= highestContributionScore;
        (0, mission_1.recordBattleMissionDimensionsSafe)(Object.assign(Object.assign({ type: "battle_finish", playerId,
            questCategory,
            questId, accomplished: questAccomplished, mode: "multi", role: finishedAsHost ? "host" : "guest", isRescue: finishedAsRescueGuest, isNewbieRescue: finishedAsNewbieRescueGuest, isMvp: questAccomplished && finishedAsMvp, clearRank, clearTimeMs: clearTime, score: Number(body.score) || 0 }, multiBattleParty), { statistics: (0, mission_1.summarizeBattleStatistics)(finishCtx.statistics) }));
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] settlement roster: room=${activeQuestData.roomNumber || body.room_number || "missing"} `
            + `generation=${settlementGeneration} viewer=${viewerId} `
            + `submitted=${settlementResult.submittedCount}/${settlementResult.expectedCount} `
            + `returned=${matePlayerResult.length} synthesized=${settlementResult.synthesizedViewerIds.join(",") || "none"}`);
        const followInfo = yield buildFinishFollowInfo(playerId, viewerId, matePlayerResult, activeQuestData.matePlayerIds || []);
        const finalPlayerData = (0, player_1.getPlayerSync)(playerId);
        const characterList = [
            ...rewardCharacterExpResult.character_list,
            ...((settledClearReward === null || settledClearReward === void 0 ? void 0 : settledClearReward.character_list) || []),
            ...((settledSPlusClearReward === null || settledSPlusClearReward === void 0 ? void 0 : settledSPlusClearReward.character_list) || []),
            ...scoreRewardsResult.character_list,
            ...((mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.character_list) || []),
        ];
        const missionSettlement = yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "mission", () => {
            var _a, _b, _c;
            return ((0, mission_2.settleMissionCategoriesAsync)(playerId, (0, battle_facts_1.buildBattleMissionSettlementScopes)(missionBattleFacts, Object.keys(Object.assign(Object.assign(Object.assign(Object.assign({}, ((_a = settledClearReward === null || settledClearReward === void 0 ? void 0 : settledClearReward.items) !== null && _a !== void 0 ? _a : {})), ((_b = settledSPlusClearReward === null || settledSPlusClearReward === void 0 ? void 0 : settledSPlusClearReward.items) !== null && _b !== void 0 ? _b : {})), scoreRewardsResult.items), ((_c = settledRescueFragmentReward === null || settledRescueFragmentReward === void 0 ? void 0 : settledRescueFragmentReward.items) !== null && _c !== void 0 ? _c : {}))).map(Number), steamRobotMissionId === null ? [] : [steamRobotMissionId], partyCharacterIdsArray), missionEvaluationTime));
        });
        const awakeMissionSettlement = (0, settlement_performance_1.measureSettlementPhase)("multi", "awake_mission", () => ((0, mission_2.settleAwakeMissionCandidates)(playerId, questAccomplished
            ? (0, mission_2.getAwakeBattleMissionIds)(partyCharacterIdsArray, missionBattleFacts.awakeMissionIds)
            : [], missionEvaluationTime)));
        const activeMissionSettlement = (0, settlement_performance_1.measureSettlementPhase)("multi", "active_mission", () => ((0, active_reconciliation_1.reconcileActiveMissionFacts)({
            playerId,
            repository: (0, content_snapshot_1.getContentSnapshot)().repository,
            now: missionEvaluationTime,
            patterns: (0, battle_facts_1.getBattleActiveMissionPatterns)(questCategory),
        })));
        reply.header("content-type", "application/x-msgpack");
        const responseData = {
            "user_info": {
                "free_mana": (_x = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.freeMana) !== null && _x !== void 0 ? _x : newMana,
                "exp_pool": (_y = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.expPool) !== null && _y !== void 0 ? _y : rewardCharacterExpResult.exp_pool,
                "exp_pooled_time": (0, utils_1.getServerTime)(playerData.expPooledTime),
                "free_vmoney": (_z = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.freeVmoney) !== null && _z !== void 0 ? _z : playerData.freeVmoney,
                "rank_point": newRankPoint,
                "degree_id": (_0 = playerData.degreeId) !== null && _0 !== void 0 ? _0 : 1,
                "stamina": playerData.stamina,
                "stamina_heal_time": (0, utils_1.realToVirtual)(playerData.staminaHealTime),
                "boost_point": newBoostPoint,
                "boss_boost_point": newBossBoostPoint
            },
            "add_exp_list": rewardCharacterExpResult.add_exp_list,
            "character_list": characterList,
            "bond_token_status_list": rewardCharacterExpResult.bond_token_status_list,
            "rewards": {
                "overflow_pool_exp": 0,
                "converted_pool_exp": 0,
                "reward_pool_exp": questData.poolExpReward,
                // Keep the credited total unchanged, but expose Mode15's
                // fixed Mana through the native visible field-drop slot.
                "reward_mana": displayMode15ManaAsFieldDrop ? 0 : questData.manaReward,
                "field_mana": (body.add_mana || 0)
                    + (displayMode15ManaAsFieldDrop ? questData.manaReward : 0)
            },
            "old_high_score": questProgress === null ? 0 : questProgress.highScore || 0,
            "joined_character_id_list": [
                ...((settledClearReward === null || settledClearReward === void 0 ? void 0 : settledClearReward.joined_character_id_list) || []),
                ...((settledSPlusClearReward === null || settledSPlusClearReward === void 0 ? void 0 : settledSPlusClearReward.joined_character_id_list) || []),
                ...scoreRewardsResult.joined_character_id_list,
                ...((settledRescueFragmentReward === null || settledRescueFragmentReward === void 0 ? void 0 : settledRescueFragmentReward.joined_character_id_list) || []),
                ...((mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.joined_character_id_list) || []),
            ],
            "before_rank_point": beforeRankPoint,
            "clear_rank": clearRank !== null && clearRank !== void 0 ? clearRank : 5,
            "drop_score_reward_ids": scoreRewardsResult.drop_score_reward_ids,
            "drop_rare_reward_ids": scoreRewardsResult.drop_rare_reward_ids,
            "drop_additional_reward_ids": [
                ...(rescueFragmentAdditionalReward === null
                    ? []
                    : [rescueFragmentAdditionalReward]),
                ...((_1 = mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.mode15_additional_reward_ids) !== null && _1 !== void 0 ? _1 : []),
            ],
            "drop_periodic_reward_ids": [],
            "equipment_list": [
                ...scoreRewardsResult.equipment_list,
                ...((settledClearReward === null || settledClearReward === void 0 ? void 0 : settledClearReward.equipment_list) || []),
                ...((settledSPlusClearReward === null || settledSPlusClearReward === void 0 ? void 0 : settledSPlusClearReward.equipment_list) || []),
                ...((settledRescueFragmentReward === null || settledRescueFragmentReward === void 0 ? void 0 : settledRescueFragmentReward.equipment_list) || []),
                ...((mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.equipment_list) || [])
            ],
            "category_id": questCategory,
            // Do not attach the single-player Rush settlement payload to a
            // multiplayer finish response.  The client routes any
            // non-null rush_event through SingleBattleQuestFinishRushEventProcess;
            // the multiplayer payload is not that type and causes F1034
            // (TypeError #1034), most visibly on stage 15 full clear.
            "start_time": dataHeaders['servertime'],
            "is_multi": "multi",
            "quest_name": "",
            "item_list": Object.assign(Object.assign(Object.assign(Object.assign(Object.assign({}, ((_2 = settledClearReward === null || settledClearReward === void 0 ? void 0 : settledClearReward.items) !== null && _2 !== void 0 ? _2 : {})), ((_3 = settledSPlusClearReward === null || settledSPlusClearReward === void 0 ? void 0 : settledSPlusClearReward.items) !== null && _3 !== void 0 ? _3 : {})), scoreRewardsResult.items), ((_4 = settledRescueFragmentReward === null || settledRescueFragmentReward === void 0 ? void 0 : settledRescueFragmentReward.items) !== null && _4 !== void 0 ? _4 : {})), ((_5 = mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.items) !== null && _5 !== void 0 ? _5 : {})),
            "presigned_quest_category": [],
            "mate_player_result": matePlayerResult,
            "follow_info": followInfo,
            "contribution_score": (_6 = body.contribution_score) !== null && _6 !== void 0 ? _6 : 0,
            "host_finished": finishedAsHost,
            "aborted_play_id": null,
        };
        (0, mission_2.mergeMissionSettlementResponse)(responseData, missionSettlement, viewerId);
        // Awake settlement re-publishes completed special unlocks itself,
        // including already-persisted rows whose earlier response was lost.
        (0, mission_2.mergeMissionSettlementResponse)(responseData, awakeMissionSettlement, viewerId);
        if (activeMissionSettlement.length > 0) {
            responseData.active_mission_list = activeMissionSettlement;
        }
        responseData.mail_arrived = (0, mail_1.getPlayerMailCountSync)(playerId, true) > 0;
        const finishResponse = {
            "data_headers": dataHeaders,
            "data": responseData,
        };
        if (questAccomplished) {
            (0, player_party_pool_1.recordSuccessfulQuestNpcParty)(settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.npcPartySnapshot);
        }
        (0, finish_response_cache_1.cacheFinishResponse)(finishCacheKey, finishResponse);
        (0, settlement_snapshot_1.transitionMultiSettlementSnapshot)(playerId, body.play_id, "RETURN_PENDING");
        // Clear only the quest that produced this response.  A late retry from
        // the previous battle must never delete a newer rematch's active quest.
        yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "active_quest_cleanup", () => (0, persistence_coordinator_1.runWriterCommand)(command_names_1.MULTI_CLEANUP_ACTIVE_QUEST, { playerId, expectedPlayId: activeQuestData.playId }, { domain: "multi-settlement", playerId, operation: "active_quest_cleanup" }));
        if (((_7 = singleBattleQuest_1.activeQuests[playerId]) === null || _7 === void 0 ? void 0 : _7.playId) === activeQuestData.playId) {
            delete singleBattleQuest_1.activeQuests[playerId];
        }
        (0, settlement_performance_1.recordSettlementPhase)("multi", "post_barrier", Number(process.hrtime.bigint() - postBarrierStartedAt) / 1000000);
        const responseStartedAt = process.hrtime.bigint();
        let responseFlushRecorded = false;
        const recordResponseFlush = () => {
            if (responseFlushRecorded)
                return;
            responseFlushRecorded = true;
            (0, settlement_performance_1.recordSettlementPhase)("multi", "response_flush", Number(process.hrtime.bigint() - responseStartedAt) / 1000000);
        };
        reply.raw.once("finish", recordResponseFlush);
        reply.raw.once("close", recordResponseFlush);
        return reply.status(200).send(finishResponse);
    }));
    // ---- abort ----
    fastify.post("/abort", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        var _8, _9, _10;
        const body = request.body;
        const viewerId = body.viewer_id;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] abort: viewer=${viewerId} quest=${body.quest_id} category=${body.category}`);
        if (isNaN(viewerId)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewerId);
        if (!ctx) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id or no player bound."
            });
        }
        const { playerId, player } = ctx;
        if ((0, five_boss_battle_1.shouldHandleFiveBossMemberRequest)(body, playerId)) {
            try {
                return yield (0, five_boss_battle_1.handleFiveBossAbort)(body, playerId, reply);
            }
            catch (error) {
                if (!(0, five_boss_battle_1.isFiveBossBattleRequestError)(error))
                    throw error;
                (0, five_boss_battle_1.logFiveBossRequestFailure)("abort", body, playerId, error);
                return reply.status(400).send({ error: "Bad Request", message: error.message });
            }
        }
        const memoryActiveQuest = singleBattleQuest_1.activeQuests[playerId];
        const persistedActiveQuest = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
        const activeQuestData = (memoryActiveQuest === null || memoryActiveQuest === void 0 ? void 0 : memoryActiveQuest.isMulti)
            && memoryActiveQuest.playId === body.play_id
            ? memoryActiveQuest
            : (persistedActiveQuest === null || persistedActiveQuest === void 0 ? void 0 : persistedActiveQuest.isMulti)
                && persistedActiveQuest.playId === body.play_id
                ? activeQuestFromPersistent(persistedActiveQuest)
                : undefined;
        if (activeQuestData) {
            const abortRoomNumber = activeQuestData.roomNumber;
            const abortRoom = abortRoomNumber ? (0, manager_1.getRoom)(abortRoomNumber) : undefined;
            const hostAborted = (abortRoom === null || abortRoom === void 0 ? void 0 : abortRoom.host_player_id) === playerId;
            const abortedPlayId = activeQuestData.playId;
            let abortedCurrentPlay = false;
            yield (0, persistence_coordinator_1.runPersistenceTransaction)({
                domain: "multi-settlement", playerId, operation: "abort",
            }, () => {
                abortedCurrentPlay = (0, quest_active_1.deletePlayerActiveQuestIfPlayIdSync)(playerId, abortedPlayId);
                // A multiplayer defeat is reported by the legacy client
                // through /abort rather than /finish(is_accomplished=false).
                // Mode15 boundary aborts clear only this battle; the settlement
                // runtime preserves the current 5/10/15 stage without rewards.
                if (abortedCurrentPlay && hostAborted) {
                    (0, mode15_optional_1.settleMode15BattleSync)(playerId, activeQuestData.category, activeQuestData.questId, false);
                }
            });
            if (abortedCurrentPlay && ((_8 = singleBattleQuest_1.activeQuests[playerId]) === null || _8 === void 0 ? void 0 : _8.playId) === abortedPlayId) {
                delete singleBattleQuest_1.activeQuests[playerId];
            }
            if (abortedCurrentPlay && hostAborted && abortRoomNumber) {
                // Retiring as the host no longer dissolves the room. The host
                // is treated as a leaving member: closing its battle socket
                // retires the seat (publishing Leave to the peers), the
                // remaining members keep fighting and settle normally, and the
                // hostless room is dissolved by its own settlement-return or
                // abandoned-battle watchdog.
                (0, game_logging_1.gameVerboseLog)(() => `[MULTI] abort: host ${viewerId} left room ${abortRoomNumber};`
                    + ` remaining members continue`);
            }
            if (abortedCurrentPlay && activeQuestData.roomNumber) {
                SessionManager_1.sessionManager.clearBattleExpectedCount(activeQuestData.roomNumber);
            }
            if (!abortedCurrentPlay) {
                console.warn(`[MULTI] stale abort acknowledged: viewer=${viewerId}`
                    + ` play=${body.play_id} reason=persistent_play_replaced`);
            }
        }
        else {
            console.warn(`[MULTI] stale abort acknowledged: viewer=${viewerId}`
                + ` play=${body.play_id} reason=active_quest_missing_or_replaced`);
        }
        const headers = (0, utils_1.generateDataHeaders)({ viewer_id: viewerId });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": headers,
            "data": {
                "user_info": {},
                "category_id": (_10 = (_9 = activeQuestData === null || activeQuestData === void 0 ? void 0 : activeQuestData.category) !== null && _9 !== void 0 ? _9 : body.category) !== null && _10 !== void 0 ? _10 : 0,
                "is_multi": "multi",
                "start_time": headers['servertime'],
                "quest_name": "",
                "aborted_play_id": null,
                "unfinished_play_id": null,
                "drawn_quest": null,
                "party_info": null,
                "presigned_url": null
            }
        });
    }));
    // ---- play_continue ----
    fastify.post("/play_continue", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        var _11, _12;
        const body = request.body;
        const viewerId = body.viewer_id;
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] play_continue: viewer=${viewerId} quest=${body.quest_id} category=${body.category}`);
        if (isNaN(viewerId)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        }
        const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(viewerId);
        if (!ctx || !ctx.player) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id or no player bound."
            });
        }
        const { playerId } = ctx;
        if ((0, continue_runtime_1.isFiveBossContinueRequest)(playerId, Number(body.category), Number(body.quest_id), body.play_id)) {
            try {
                const data = yield (0, continue_runtime_1.continueFiveBoss)({ playerId, category: Number(body.category), questId: Number(body.quest_id),
                    playId: body.play_id, isMulti: true, apiCount: body.api_count, statistics: body.statistics });
                const recovered = (0, active_quest_resolver_1.resolveActiveQuest)({ playerId, hint: body, memory: singleBattleQuest_1.activeQuests, allowRebuild: false });
                if ((recovered === null || recovered === void 0 ? void 0 : recovered.quest.playId) === body.play_id)
                    recovered.quest.continueCount = data.continue_count;
                reply.header("content-type", "application/x-msgpack");
                return reply.status(200).send({ data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }), data });
            }
            catch (error) {
                if (!(error instanceof continue_runtime_1.FiveBossContinueError))
                    throw error;
                if (error.stale) {
                    // The run ended before this client recovered it. The CN
                    // client treats a 400 here as a fatal H400 and logs out,
                    // so acknowledge without charging or reviving anything.
                    (0, game_logging_1.gameVerboseLog)(() => `[MULTI] play_continue: stale ack viewer=${viewerId}`
                        + ` quest=${body.quest_id} reason=${error.message}`);
                    reply.header("content-type", "application/x-msgpack");
                    return reply.status(200).send({
                        data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
                        data: (0, continue_runtime_1.fiveBossContinueAcknowledgement)(playerId),
                    });
                }
                (0, game_logging_1.gameVerboseLog)(() => `[MULTI] play_continue: rejected viewer=${viewerId}`
                    + ` quest=${body.quest_id} reason=${error.message}`);
                return reply.status(400).send({ error: "Bad Request", message: error.message });
            }
        }
        const persisted = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
        let activeData = (persisted === null || persisted === void 0 ? void 0 : persisted.isMulti)
            && persisted.playId === body.play_id
            ? ((_11 = singleBattleQuest_1.activeQuests[playerId]) === null || _11 === void 0 ? void 0 : _11.playId) === body.play_id
                ? singleBattleQuest_1.activeQuests[playerId]
                : activeQuestFromPersistent(persisted)
            : undefined;
        if (activeData)
            singleBattleQuest_1.activeQuests[playerId] = activeData;
        if (!activeData) {
            console.warn(`[MULTI] stale continue acknowledged: viewer=${viewerId}`
                + ` play=${body.play_id} reason=active_quest_missing_or_replaced`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
                data: { continue_count: 0 },
            });
        }
        const nextContinueCount = activeData.continueCount + 1;
        const updated = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "multi-settlement", playerId, operation: "continue",
        }, () => (0, quest_active_1.updatePlayerActiveQuestContinueCountIfPlayIdSync)(playerId, activeData.playId, nextContinueCount));
        if (!updated) {
            if (((_12 = singleBattleQuest_1.activeQuests[playerId]) === null || _12 === void 0 ? void 0 : _12.playId) === body.play_id) {
                delete singleBattleQuest_1.activeQuests[playerId];
            }
            console.warn(`[MULTI] stale continue acknowledged after race: viewer=${viewerId}`
                + ` play=${body.play_id}`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
                data: { continue_count: 0 },
            });
        }
        activeData.continueCount = nextContinueCount;
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                continue_count: nextContinueCount,
            }
        });
    }));
}
exports.registerBattleRoutes = registerBattleRoutes;
