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
const mode15_optional_1 = require("../../lib/mode15-optional");
const player_party_pool_1 = require("../npc/player-party-pool");
const sqlite_write_coordinator_1 = require("../../lib/sqlite-write-coordinator");
const settlement_snapshot_1 = require("../settlement-snapshot");
const embedded_1 = require("../coordinator/embedded");
const mana_1 = require("../../lib/mana");
const player_context_1 = require("../player-context");
const recruitment_1 = require("../recruitment");
const recommended_party_history_1 = require("../../lib/quest/recommended-party-history");
function buildFinishFollowInfo(viewerId_1, mateResults_1) {
    return __awaiter(this, arguments, void 0, function* (viewerId, mateResults, fallbackMateIds = []) {
        const requesterCtx = yield (0, player_context_1.resolveMultiPlayerContext)(viewerId);
        if (!requesterCtx)
            return [];
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
            const info = (0, follow_1.buildFollowUserInfoSync)(requesterCtx.playerId, mateCtx.playerId);
            if (info)
                followInfo.push(info);
        }
        return followInfo;
    });
}
function registerBattleRoutes(fastify) {
    // ---- start ----
    fastify.post("/start", (request, reply) => __awaiter(this, void 0, void 0, function* () {
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
        if (body.attention_key
            && !(0, recruitment_1.validateRandomRecruitmentAttention)(room_number, viewer_id, body.attention_key)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid attention key."
            });
        }
        const questData = (0, assets_1.getQuestFromCategorySync)(category, quest_id);
        if (questData === null || !('rankPointReward' in questData)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Quest doesn't exist."
            });
        }
        if (!(0, mode15_optional_1.isMode15Quest)(category, quest_id)) {
            const restricted = (0, mode15_optional_1.getMode15ExclusiveGlobalPartyItemsSync)(ctx.playerId, 1, party_id);
            if (restricted.length > 0) {
                console.log(`[MODE15] exclusive equipment denied in multi start: player=${ctx.playerId} items=${restricted.join(",")}`);
                reply.header("content-type", "application/x-msgpack");
                return reply.status(200).send({
                    data_headers: (0, utils_1.generateDataHeaders)({ viewer_id, result_code: 4050 }),
                    data: {},
                });
            }
        }
        const roomStart = yield embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(room_number, () => {
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
            if (!(0, manager_1.setRoomBattle)(room_number)) {
                return { status: "unavailable" };
            }
            return { status: "ready", room: currentRoom };
        });
        if (roomStart.status === "forbidden") {
            return reply.status(403).send({
                "error": "Forbidden", "message": "Room permission denied."
            });
        }
        if (roomStart.status === "missing"
            || roomStart.status === "unavailable"
            || roomStart.status === "quest_mismatch"
            || roomStart.status === "player_mismatch") {
            return reply.status(400).send({
                "error": "Bad Request", "message": roomStart.status === "missing"
                    ? "Room doesn't exist."
                    : roomStart.status === "quest_mismatch"
                        ? "Room quest mismatch."
                        : roomStart.status === "player_mismatch"
                            ? "Room player mismatch."
                            : "Room is not available for battle."
            });
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
        const mateComIds = room.mates.map(m => m.com_id);
        const activeQuest = {
            questId: quest_id,
            category,
            useBoostPoint: use_boost_point,
            useBossBoostPoint: use_boss_boost_point,
            isAutoStartMode: is_auto_start_mode,
            isMulti: true,
            isMultiHost: room.host_viewer_id === viewer_id,
            roomNumber: room_number,
            matePlayerIds: mate_player_ids,
            mateComIds,
            partySlot: party_id,
            playId: play_id,
            continueCount: 0,
        };
        (0, singleBattleQuest_1.insertActiveQuest)(ctx.playerId, activeQuest);
        const frozenParticipants = room.mates
            .map(mate => ({
            viewerId: Number(mate.viewer_id),
            comId: Number(mate.com_id || 0),
        }))
            .filter(mate => Number.isFinite(mate.viewerId) && mate.viewerId > 0);
        const frozenExpectedRealViewerIds = room.expected_real_viewer_ids
            .map(Number)
            .filter(expectedViewerId => Number.isFinite(expectedViewerId) && expectedViewerId > 0);
        (0, settlement_snapshot_1.registerMultiSettlementSnapshot)({
            battleInstanceId: (0, settlement_snapshot_1.buildBattleInstanceId)(room_number, room.lobby_generation, category, quest_id),
            playerId: ctx.playerId,
            viewerId: viewer_id,
            playId: play_id,
            roomNumber: room_number,
            roomGeneration: room.lobby_generation,
            activeQuest,
            participants: frozenParticipants,
            expectedRealViewerIds: frozenExpectedRealViewerIds,
            isHost: room.host_viewer_id === viewer_id,
            isRescueGuest: SessionManager_1.sessionManager.isRescueGuest(room_number, viewer_id),
            isRescueFragmentEligible: SessionManager_1.sessionManager.isRescueFragmentEligibleGuest(room_number, viewer_id),
            isNewbieRescueGuest: SessionManager_1.sessionManager.isNewbieRescueGuest(room_number, viewer_id),
        });
        if (questData.fixedParty === undefined) {
            (0, player_1.updatePlayerSync)({ id: ctx.playerId, partySlot: party_id });
        }
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
        var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q, _r, _s, _t, _u, _v, _w, _x, _y, _z, _0, _1, _2, _3, _4, _5, _6;
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
        const finishCacheKey = (0, finish_response_cache_1.buildFinishResponseCacheKey)("multi", viewerId, body);
        const cachedFinishResponse = (0, finish_response_cache_1.getCachedFinishResponse)(finishCacheKey);
        if (cachedFinishResponse !== undefined) {
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send(cachedFinishResponse);
        }
        const releaseFinishExecution = yield (0, finish_response_cache_1.acquireFinishExecution)(finishCacheKey);
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
        // A delayed finish from the previous generation must use its frozen
        // snapshot. Taking the current active quest first can settle or clear a
        // rematch that merely happens to belong to the same player.
        const activeQuestData = (currentActiveQuest === null || currentActiveQuest === void 0 ? void 0 : currentActiveQuest.playId) === body.play_id
            ? currentActiveQuest
            : settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.activeQuest;
        if (activeQuestData === undefined) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "No active quest to finish."
            });
        }
        const finishRoom = activeQuestData.roomNumber
            ? (0, manager_1.getRoom)(activeQuestData.roomNumber)
            : undefined;
        const settlementGeneration = (_b = (_a = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.roomGeneration) !== null && _a !== void 0 ? _a : finishRoom === null || finishRoom === void 0 ? void 0 : finishRoom.lobby_generation) !== null && _b !== void 0 ? _b : 0;
        const settlementKey = (_c = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.battleInstanceId) !== null && _c !== void 0 ? _c : `${activeQuestData.roomNumber || body.room_number || "missing"}:${settlementGeneration}:${body.play_id}`;
        const settlementParticipants = (_d = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.participants) !== null && _d !== void 0 ? _d : ((finishRoom === null || finishRoom === void 0 ? void 0 : finishRoom.mates) || [])
            .map(mate => ({
            viewerId: Number(mate.viewer_id),
            comId: Number(mate.com_id || 0),
        }))
            .filter(mate => Number.isFinite(mate.viewerId) && mate.viewerId > 0);
        const expectedRealViewerIds = (_e = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.expectedRealViewerIds) !== null && _e !== void 0 ? _e : ((finishRoom === null || finishRoom === void 0 ? void 0 : finishRoom.expected_real_viewer_ids) || [])
            .map(Number)
            .filter(expectedViewerId => Number.isFinite(expectedViewerId) && expectedViewerId > 0);
        const finishedAsRescueGuest = (_f = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.isRescueGuest) !== null && _f !== void 0 ? _f : (activeQuestData.roomNumber
            ? SessionManager_1.sessionManager.isRescueGuest(activeQuestData.roomNumber, viewerId)
            : false);
        const finishedAsRescueFragmentEligible = (_g = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.isRescueFragmentEligible) !== null && _g !== void 0 ? _g : (activeQuestData.roomNumber
            ? SessionManager_1.sessionManager.isRescueFragmentEligibleGuest(activeQuestData.roomNumber, viewerId)
            : false);
        const finishedAsNewbieRescueGuest = (_h = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.isNewbieRescueGuest) !== null && _h !== void 0 ? _h : (activeQuestData.roomNumber
            ? SessionManager_1.sessionManager.isNewbieRescueGuest(activeQuestData.roomNumber, viewerId)
            : false);
        const questCategory = activeQuestData.category;
        const questId = activeQuestData.questId;
        const questData = (0, assets_1.getQuestFromCategorySync)(questCategory, questId);
        if (questData === null || !('rankPointReward' in questData)) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "Quest doesn't exist."
            });
        }
        (0, settlement_performance_1.recordSettlementPhase)("multi", "preflight", Number(process.hrtime.bigint() - finishHandlerStartedAt) / 1000000);
        const coreStartedAt = process.hrtime.bigint();
        const settlementWasAlreadyInLobby = (settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.lifecycle) === "LOBBY";
        const settlingSnapshot = (0, settlement_snapshot_1.transitionMultiSettlementSnapshot)(playerId, body.play_id, "SETTLING");
        const finishedAsHost = (_j = settlementSnapshot === null || settlementSnapshot === void 0 ? void 0 : settlementSnapshot.isHost) !== null && _j !== void 0 ? _j : (activeQuestData.roomNumber
            ? ((_k = (0, manager_1.getRoom)(activeQuestData.roomNumber)) === null || _k === void 0 ? void 0 : _k.host_player_id) === playerId
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
        const questProgress = (0, quest_1.getPlayerSingleQuestProgressSync)(playerId, questCategory, questId);
        const questPreviouslyCompleted = questProgress !== null;
        const questAccomplished = body.is_accomplished;
        const leaderId = (_q = (_p = (_o = (((_l = body.statistics) === null || _l === void 0 ? void 0 : _l.party) || ((_m = body.quest_statistics) === null || _m === void 0 ? void 0 : _m.party))) === null || _o === void 0 ? void 0 : _o.characters) === null || _p === void 0 ? void 0 : _p[0]) === null || _q === void 0 ? void 0 : _q.id;
        const eligibleRescueFragmentReward = (0, rescue_fragment_reward_1.getEligibleRescueFragmentReward)(questCategory, questId, questAccomplished, finishedAsRescueFragmentEligible);
        let clearReward = null;
        let sPlusClearReward = null;
        let rescueFragmentReward = null;
        let scoreRewardsResult;
        const oldRkDegree = (0, stamina_1.getRankDegree)(beforeRankPoint);
        const newDegreeId = (0, stamina_1.getRankDegree)(newRankPoint);
        const didLevelUp = newDegreeId > oldRkDegree;
        const playerData = player;
        yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "reward_transaction", () => (0, sqlite_write_coordinator_1.withPlayerWriteQueue)(playerId, () => (0, sqlite_write_coordinator_1.runImmediateTransactionWithRetry)(() => {
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
            scoreRewardsResult = (0, quest_2.givePlayerScoreRewardsSync)(playerId, questData.scoreRewardGroupId || 0, questData.scoreRewardGroup, useBoostPoint, questData.element);
            if (eligibleRescueFragmentReward !== null) {
                rescueFragmentReward = (0, quest_2.givePlayerRewardSync)(playerId, eligibleRescueFragmentReward);
                (0, game_logging_1.gameVerboseLog)(() => `[MULTI] rescue fragment granted: player=${playerId} quest=${questId} `
                    + `item=${eligibleRescueFragmentReward.id} count=${eligibleRescueFragmentReward.count}`);
            }
        })));
        const settledClearReward = clearReward;
        const settledSPlusClearReward = sPlusClearReward;
        const settledRescueFragmentReward = rescueFragmentReward;
        const rescueFragmentAdditionalReward = (0, rescue_fragment_reward_1.getRescueFragmentAdditionalReward)(eligibleRescueFragmentReward);
        const bodyPartyStatistics = ((_r = body.statistics) === null || _r === void 0 ? void 0 : _r.party) || ((_s = body.quest_statistics) === null || _s === void 0 ? void 0 : _s.party) || { characters: [], unison_characters: [] };
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
            partySlot: (_t = activeQuestData.partySlot) !== null && _t !== void 0 ? _t : player.partySlot,
            isMulti: true,
            isMultiHost: finishedAsHost,
        };
        const multiBattleParty = (0, mission_1.collectPartyCharacterIds)(finishCtx.party);
        const missionEvaluationTime = new Date((0, utils_1.getServerTime)() * 1000);
        let missionBattleFacts;
        let steamRobotMissionId = null;
        let rewardCharacterExpResult;
        yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "facts_transaction", () => (0, sqlite_write_coordinator_1.withPlayerWriteQueue)(playerId, () => (0, sqlite_write_coordinator_1.runImmediateTransactionWithRetry)(() => {
            missionBattleFacts = (0, battle_facts_1.recordMissionBattleFacts)(finishCtx, missionEvaluationTime);
            if (questData.fixedParty === undefined) {
                (0, recommended_party_history_1.recordQuestRecommendedPartySafe)(finishCtx);
            }
            steamRobotMissionId = (0, steam_robot_challenge_1.trackSteamRobotChallengeMission)({
                playerId,
                questCategory,
                questId,
                questAccomplished,
                clearRank,
                statistics: finishCtx.statistics,
            });
            if (steamRobotMissionId !== null) {
                console.log(`[MISSION] steam robot challenge cleared: player=${playerId} quest=${questId} mission=${steamRobotMissionId}`);
            }
            rewardCharacterExpResult = (0, character_1.givePlayerCharactersExpSync)(playerId, partyCharacterIdsArray, questData.characterExpReward || 0, questData.fixedParty !== undefined);
        })));
        const mode15RewardsResult = (0, mode15_optional_1.settleMode15BattleSync)(playerId, questCategory, questId, questAccomplished, {
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
        const finishedAsMvp = Boolean((_u = finishCtx.statistics) === null || _u === void 0 ? void 0 : _u.is_mvp)
            || ownContributionScore >= highestContributionScore;
        (0, mission_1.recordBattleMissionDimensionsSafe)(Object.assign(Object.assign({ type: "battle_finish", playerId,
            questCategory,
            questId, accomplished: questAccomplished, mode: "multi", role: finishedAsHost ? "host" : "guest", isRescue: finishedAsRescueGuest, isNewbieRescue: finishedAsNewbieRescueGuest, isMvp: questAccomplished && finishedAsMvp, clearRank, clearTimeMs: clearTime, score: Number(body.score) || 0 }, multiBattleParty), { statistics: (0, mission_1.summarizeBattleStatistics)(finishCtx.statistics) }));
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] settlement roster: room=${activeQuestData.roomNumber || body.room_number || "missing"} `
            + `generation=${settlementGeneration} viewer=${viewerId} `
            + `submitted=${settlementResult.submittedCount}/${settlementResult.expectedCount} `
            + `returned=${matePlayerResult.length} synthesized=${settlementResult.synthesizedViewerIds.join(",") || "none"}`);
        const followInfo = yield buildFinishFollowInfo(viewerId, matePlayerResult, activeQuestData.matePlayerIds || []);
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
                "free_mana": (_v = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.freeMana) !== null && _v !== void 0 ? _v : newMana,
                "exp_pool": (_w = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.expPool) !== null && _w !== void 0 ? _w : rewardCharacterExpResult.exp_pool,
                "exp_pooled_time": (0, utils_1.getServerTime)(playerData.expPooledTime),
                "free_vmoney": (_x = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.freeVmoney) !== null && _x !== void 0 ? _x : playerData.freeVmoney,
                "rank_point": newRankPoint,
                "degree_id": (_y = playerData.degreeId) !== null && _y !== void 0 ? _y : 1,
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
                ...((_z = mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.mode15_additional_reward_ids) !== null && _z !== void 0 ? _z : []),
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
            "item_list": Object.assign(Object.assign(Object.assign(Object.assign(Object.assign({}, ((_0 = settledClearReward === null || settledClearReward === void 0 ? void 0 : settledClearReward.items) !== null && _0 !== void 0 ? _0 : {})), ((_1 = settledSPlusClearReward === null || settledSPlusClearReward === void 0 ? void 0 : settledSPlusClearReward.items) !== null && _1 !== void 0 ? _1 : {})), scoreRewardsResult.items), ((_2 = settledRescueFragmentReward === null || settledRescueFragmentReward === void 0 ? void 0 : settledRescueFragmentReward.items) !== null && _2 !== void 0 ? _2 : {})), ((_3 = mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.items) !== null && _3 !== void 0 ? _3 : {})),
            "presigned_quest_category": [],
            "mate_player_result": matePlayerResult,
            "follow_info": followInfo,
            "contribution_score": (_4 = body.contribution_score) !== null && _4 !== void 0 ? _4 : 0,
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
            (0, player_party_pool_1.recordSuccessfulQuestNpcParty)(playerId, questCategory, questId, (_5 = activeQuestData.partySlot) !== null && _5 !== void 0 ? _5 : player.partySlot);
        }
        (0, finish_response_cache_1.cacheFinishResponse)(finishCacheKey, finishResponse);
        (0, settlement_snapshot_1.transitionMultiSettlementSnapshot)(playerId, body.play_id, "RETURN_PENDING");
        // Clear only the quest that produced this response.  A late retry from
        // the previous battle must never delete a newer rematch's active quest.
        if (((_6 = singleBattleQuest_1.activeQuests[playerId]) === null || _6 === void 0 ? void 0 : _6.playId) === activeQuestData.playId) {
            delete singleBattleQuest_1.activeQuests[playerId];
            (0, quest_active_1.deletePlayerActiveQuestSync)(playerId);
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
        const activeQuestData = singleBattleQuest_1.activeQuests[playerId];
        if (activeQuestData) {
            if (activeQuestData.roomNumber) {
                const room = (0, manager_1.getRoom)(activeQuestData.roomNumber);
                if (room && room.host_player_id === playerId) {
                    // A multiplayer defeat is reported by the legacy client
                    // through /abort rather than /finish(is_accomplished=false).
                    // Reset only the room owner's Mode15 run; rescue guests may
                    // leave or fail without changing their own sequence.
                    (0, mode15_optional_1.settleMode15BattleSync)(playerId, activeQuestData.category, activeQuestData.questId, false);
                    yield embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(activeQuestData.roomNumber, () => SessionManager_1.sessionManager.commitRoomDisband(activeQuestData.roomNumber, "host_aborted_battle"));
                    (0, game_logging_1.gameVerboseLog)(() => `[MULTI] abort: room ${activeQuestData.roomNumber} disbanded (host abandoned)`);
                }
            }
            delete singleBattleQuest_1.activeQuests[playerId];
            (0, quest_active_1.deletePlayerActiveQuestSync)(playerId);
            if (activeQuestData.roomNumber) {
                SessionManager_1.sessionManager.clearBattleExpectedCount(activeQuestData.roomNumber);
            }
        }
        const headers = (0, utils_1.generateDataHeaders)({ viewer_id: viewerId });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": headers,
            "data": {
                "user_info": {},
                "category_id": body.category,
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
        if (singleBattleQuest_1.activeQuests[playerId] === undefined) {
            return reply.status(400).send({
                "error": "Bad Request", "message": "No active quest to continue."
            });
        }
        const activeData = singleBattleQuest_1.activeQuests[playerId];
        activeData.continueCount++;
        (0, quest_active_1.updatePlayerActiveQuestContinueCountSync)(playerId, activeData.continueCount);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                continue_count: activeData.continueCount,
            }
        });
    }));
}
exports.registerBattleRoutes = registerBattleRoutes;
