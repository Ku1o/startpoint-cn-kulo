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
exports.handleFiveBossAbort = exports.handleFiveBossFinish = exports.handleFiveBossStart = exports.shouldHandleFiveBossMemberRequest = exports.shouldHandleFiveBossStart = exports.isFiveBossBattleRequestError = exports.logFiveBossRequestFailure = void 0;
const quest_active_1 = require("../../data/domains/quest_active");
const fiveBossGauntletRun_1 = require("../../data/domains/fiveBossGauntletRun");
const item_1 = require("../../data/domains/item");
const equipment_1 = require("../../data/domains/equipment");
const player_1 = require("../../data/domains/player");
const party_1 = require("../../data/domains/party");
const equipment_2 = require("../../lib/equipment");
const utils_1 = require("../../utils");
const singleBattleQuest_1 = require("../../routes/api/singleBattleQuest");
const manager_1 = require("../room/manager");
const SessionManager_1 = require("../state/SessionManager");
const battle_runtime_1 = require("../five-boss/battle-runtime");
const contract_1 = require("../five-boss/contract");
const rewards_1 = require("../five-boss/rewards");
const solo_runtime_1 = require("../five-boss/solo-runtime");
const db_1 = require("../../data/db");
const settlement_performance_1 = require("../../lib/settlement-performance");
const coalesced_diagnostics_1 = require("../../lib/coalesced-diagnostics");
const connection_diagnostic_1 = require("../five-boss/connection-diagnostic");
const persistence_coordinator_1 = require("../../lib/persistence-coordinator");
/** Small structured evidence, without logging tokens, party data or the full request. */
function logFiveBossRequestFailure(operation, body, playerId, error) {
    const code = error === null || error === void 0 ? void 0 : error.code;
    const message = error === null || error === void 0 ? void 0 : error.message;
    const key = JSON.stringify(["request", operation, playerId, String(body.play_id).slice(0, 255),
        body.category, body.quest_id, code, message === null || message === void 0 ? void 0 : message.slice(0, 160)]);
    coalesced_diagnostics_1.fiveBossDiagnostics.report(key, () => {
        const run = (0, fiveBossGauntletRun_1.getFiveBossRunByClientSync)({ playerId, clientPlayId: body.play_id });
        const member = run ? (0, db_1.getDb)().prepare(`SELECT started_at, aborted_at, level_next_at, finalized_at
            FROM five_boss_gauntlet_members WHERE run_id = ? AND player_id = ?`).get(run.runId, playerId) : null;
        const active = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
        if (run && operation === "finish")
            connection_diagnostic_1.fiveBossConnectionDiagnostics.memberEvent(run.runId, playerId, "finish_rejected", code);
        return `[FIVE-BOSS-REJECT] ${JSON.stringify({ operation, player: playerId, play: body.play_id,
            category: body.category, quest: body.quest_id, run: run === null || run === void 0 ? void 0 : run.runId, room: run === null || run === void 0 ? void 0 : run.roomNumber,
            status: run === null || run === void 0 ? void 0 : run.status, code, message,
            proof: member, active: active ? { play: active.playId, multi: active.isMulti, room: active.roomNumber } : null,
            transport: run ? connection_diagnostic_1.fiveBossConnectionDiagnostics.snapshot(run.runId, playerId) : { available: false, reason: "run_not_found" } })}`;
    });
}
exports.logFiveBossRequestFailure = logFiveBossRequestFailure;
function isFiveBossBattleRequestError(error) {
    return error instanceof battle_runtime_1.FiveBossBattleRuntimeError
        || error instanceof fiveBossGauntletRun_1.FiveBossGauntletRunError;
}
exports.isFiveBossBattleRequestError = isFiveBossBattleRequestError;
function shouldHandleFiveBossStart(body) {
    const room = body.room_number ? (0, manager_1.getRoom)(body.room_number) : undefined;
    return (0, contract_1.isFiveBossGauntletQuest)(body.category, body.quest_id)
        || !!room && (0, contract_1.isFiveBossGauntletQuest)(room.category, room.quest_id);
}
exports.shouldHandleFiveBossStart = shouldHandleFiveBossStart;
function shouldHandleFiveBossMemberRequest(body, playerId) {
    if ((0, contract_1.isFiveBossGauntletQuest)(body.category, body.quest_id))
        return true;
    if ((0, fiveBossGauntletRun_1.getFiveBossRunByClientSync)({ playerId, clientPlayId: body.play_id }))
        return true;
    const memory = singleBattleQuest_1.activeQuests[playerId];
    if (memory && (0, contract_1.isFiveBossGauntletQuest)(memory.category, memory.questId))
        return true;
    const persistent = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
    return persistent !== null
        && (0, contract_1.isFiveBossGauntletQuest)(persistent.category, persistent.questId);
}
exports.shouldHandleFiveBossMemberRequest = shouldHandleFiveBossMemberRequest;
function clearMatchingMemoryActive(playerId, playId) {
    const active = singleBattleQuest_1.activeQuests[playerId];
    if ((active === null || active === void 0 ? void 0 : active.playId) === playId
        && (0, contract_1.isFiveBossGauntletQuest)(active.category, active.questId)) {
        delete singleBattleQuest_1.activeQuests[playerId];
    }
}
function terminalRoomTransition(roomNumber, runId, runStatus) {
    var _a;
    if (runStatus === "active")
        return;
    const room = (0, manager_1.getRoom)(roomNumber);
    if (!room
        || !(0, contract_1.isFiveBossGauntletQuest)(room.category, room.quest_id)
        || ((_a = room.five_boss_runtime) === null || _a === void 0 ? void 0 : _a.runId) !== runId) {
        return;
    }
    SessionManager_1.sessionManager.clearBattleExpectedCount(roomNumber);
    if (runStatus === "settled") {
        delete room.five_boss_runtime;
        // 结算后不再把房间退回 raising_state=1 复用,而是直接解散:
        // V7 客户端补丁 five-boss-random-map 的选图种子 = 房间号,同一房间再战
        // 会抽到同一套变体;解散逼房主重建房间 = 新房号 = 新一轮随机。
        // 代价是结算页点「再战」会提示房间已解散,回到关卡页重建(作者接受随机性优先)。
        console.log(`[MULTI] five-boss settled: disbanding room ${roomNumber} so the next run rerolls its map seed`);
        (0, manager_1.disbandRoom)(roomNumber);
        return;
    }
    (0, manager_1.disbandRoom)(roomNumber);
}
/**
 * CN 客户端的 multi finish / abort 请求体**不带 room_number**(官方
 * BattleQuestFinishRealRemote / QuestAbortRealRemote 都没有这个字段),原生多人路径
 * 一直是靠服务端 activeQuests 记住房号。五重 runtime 的冻结契约要求 requestRoomNumber
 * 非空,真机首战(2026-09-04)就因此在结算时连吃 6 个 H400。这里按
 * 请求体 → 此玩家/对局的不可变账本 → 内存 activeQuests → 持久化活动记录补房号;
 * 全都没有才让 runtime 用原来的 invalid_argument 拒绝。
 */
function resolveFiveBossRoomNumber(bodyRoomNumber, playerId, playId, boundRun) {
    if (typeof bodyRoomNumber === "string" && bodyRoomNumber.length > 0)
        return bodyRoomNumber;
    const run = boundRun === undefined ? (0, fiveBossGauntletRun_1.getFiveBossRunByClientSync)({ playerId, clientPlayId: playId }) : boundRun;
    if (run)
        return run.roomNumber;
    const memory = singleBattleQuest_1.activeQuests[playerId];
    if (memory && (0, contract_1.isFiveBossGauntletQuest)(memory.category, memory.questId) && memory.roomNumber) {
        return memory.roomNumber;
    }
    const persistent = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
    if (persistent
        && (0, contract_1.isFiveBossGauntletQuest)(persistent.category, persistent.questId)
        && persistent.roomNumber) {
        return persistent.roomNumber;
    }
    return "";
}
/**
 * 上一局没结算干净(客户端半路报错退出、房间早已解散)时,玩家身上还挂着旧的
 * 五重持久化 active quest,新一局 start 会被 runtime 以 active_quest_mismatch 拒绝,
 * 玩家从此进不了五重。开新局前把这条"房间已不存在"的旧局按 abort 收掉。
 * 按整轮身份区别同房号的新旧局；活动房间仍属于旧局时不清理。
 * 此函数与新局 start 同处一个事务，开新局失败时旧局保持原状。
 */
function abandonStaleFiveBossRun(body, playerId) {
    var _a, _b;
    const stale = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
    if (!stale
        || !(0, contract_1.isFiveBossGauntletQuest)(stale.category, stale.questId)
        || stale.playId === body.play_id) {
        return;
    }
    try {
        if (!stale.isMulti) {
            if ((0, solo_runtime_1.abandonFiveBossSoloForMultiSync)(playerId, stale.playId)) {
                clearMatchingMemoryActive(playerId, stale.playId);
                console.log(`[MULTI] five-boss start: abandoned previous solo player=${playerId} play=${stale.playId}`);
            }
            return;
        }
        const oldRun = (0, fiveBossGauntletRun_1.getFiveBossRunByClientSync)({ playerId, clientPlayId: stale.playId });
        const oldRoomNumber = (_a = oldRun === null || oldRun === void 0 ? void 0 : oldRun.roomNumber) !== null && _a !== void 0 ? _a : stale.roomNumber;
        const oldRoom = oldRoomNumber ? (0, manager_1.getRoom)(oldRoomNumber) : undefined;
        if (oldRoom && (!oldRun || ((_b = oldRoom.five_boss_runtime) === null || _b === void 0 ? void 0 : _b.runId) === oldRun.runId))
            return;
        if (!oldRun || !oldRoomNumber) {
            console.warn(`[FIVE-BOSS-STALE] missing immutable run player=${playerId} play=${stale.playId}`);
            return;
        }
        // Recover only a missing room field from this exact persisted player/play binding.
        if (!stale.roomNumber) {
            (0, db_1.getDb)().prepare(`UPDATE players_active_quests SET room_number = ?
                WHERE player_id = ? AND play_id = ? AND is_multi = 1 AND (room_number IS NULL OR room_number = '')`)
                .run(oldRoomNumber, playerId, stale.playId);
        }
        const aborted = (0, battle_runtime_1.abortFiveBossBattle)({
            playerId,
            clientPlayId: stale.playId,
            requestRoomNumber: oldRoomNumber,
            requestCategory: stale.category,
            requestQuestId: stale.questId,
        });
        clearMatchingMemoryActive(playerId, stale.playId);
        console.log(`[MULTI] five-boss start: abandoned stale run for player ${playerId}`
            + ` room=${stale.roomNumber} play=${stale.playId}`
            + ` status=${aborted.abortStatus}/${aborted.runStatus}`);
    }
    catch (error) {
        console.warn(`[MULTI] five-boss start: could not abandon stale run for player ${playerId}`
            + ` room=${stale.roomNumber}: ${error.message}`);
    }
}
function requirePlayer(playerId) {
    const player = (0, player_1.getPlayerSync)(playerId);
    if (!player)
        throw new Error(`five-boss player ${playerId} disappeared`);
    return player;
}
function finishItemList(result, playerId) {
    if (result.kind !== "success")
        return {};
    return Object.fromEntries(result.reward.grantedItems.map(item => {
        var _a;
        return [
            String(item.itemId),
            (_a = (0, item_1.getPlayerItemSync)(playerId, item.itemId)) !== null && _a !== void 0 ? _a : 0,
        ];
    }));
}
/** 旧 receipt 在武器掉落字段加入前已经落盘；缺失时按当年无武器处理。 */
function receiptGrantedEquipment(result) {
    if (result.kind !== "success")
        return [];
    const granted = result.reward.grantedEquipment;
    return Array.isArray(granted) ? granted : [];
}
/** 按 receipt 的命中顺序去重，回读当前持有状态，保证重放不重复发放。 */
function finishEquipmentList(result, playerId) {
    if (result.kind !== "success")
        return [];
    const seen = new Set();
    const list = [];
    for (const equipmentId of receiptGrantedEquipment(result)) {
        if (seen.has(equipmentId))
            continue;
        seen.add(equipmentId);
        const owned = (0, equipment_1.getPlayerEquipmentSync)(playerId, equipmentId);
        if (owned)
            list.push((0, equipment_2.clientSerializeEquipment)(equipmentId, owned));
    }
    return list;
}
function buildFinishData(player, body, result, dataHeaders, matePlayerResult, followInfo, exp) {
    var _a, _b, _c, _d;
    return {
        user_info: {
            free_mana: player.freeMana,
            exp_pool: player.expPool,
            exp_pooled_time: (0, utils_1.getServerTime)(player.expPooledTime),
            free_vmoney: player.freeVmoney,
            rank_point: player.rankPoint,
            // getRankDegree 算出来的是玩家 **rank**(高 rank 号如 250),不是称号表 degree 的键;
            // 结算页 MVP 卡会拿 user_info.degree_id 去查 master/degree/degree,查不到就 C8601
            // 「指定的Key不存在 key=250」(真机 2026-09-04)。普通多人/关注列表都用玩家持久化的 degreeId。
            degree_id: player.degreeId || 1,
            stamina: player.stamina,
            stamina_heal_time: (0, utils_1.realToVirtual)(player.staminaHealTime),
            boost_point: player.boostPoint,
            boss_boost_point: player.bossBoostPoint,
        },
        add_exp_list: (_a = exp === null || exp === void 0 ? void 0 : exp.add_exp_list) !== null && _a !== void 0 ? _a : [],
        character_list: (_b = exp === null || exp === void 0 ? void 0 : exp.character_list) !== null && _b !== void 0 ? _b : [],
        bond_token_status_list: (_c = exp === null || exp === void 0 ? void 0 : exp.bond_token_status_list) !== null && _c !== void 0 ? _c : [],
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
        clear_rank: result.kind === "success" ? 5 : 0,
        drop_score_reward_ids: [],
        drop_rare_reward_ids: [],
        drop_additional_reward_ids: result.kind === "success"
            ? [
                ...(0, rewards_1.buildFiveBossAdditionalRewardDrops)(result.reward.grantedItems),
                ...(0, rewards_1.buildFiveBossWeaponAdditionalRewardDrops)(receiptGrantedEquipment(result)),
            ]
            : [],
        drop_periodic_reward_ids: [],
        equipment_list: finishEquipmentList(result, player.id),
        category_id: body.category,
        start_time: dataHeaders.servertime,
        is_multi: "multi",
        quest_name: "",
        item_list: finishItemList(result, player.id),
        presigned_quest_category: [],
        mate_player_result: matePlayerResult,
        follow_info: followInfo,
        contribution_score: (_d = body.contribution_score) !== null && _d !== void 0 ? _d : 0,
        host_finished: true,
        aborted_play_id: null,
    };
}
function handleFiveBossStart(body, playerId, reply) {
    return __awaiter(this, void 0, void 0, function* () {
        var _a;
        const room = (0, manager_1.getRoom)(body.room_number);
        if (!room) {
            return reply.status(400).send({
                error: "Bad Request",
                message: "Room doesn't exist.",
            });
        }
        // 五重决战不消耗、不结算任何强化点:客户端在"降临讨伐"页签建房时会按官方 boss 战
        // 习惯默认勾上领主强化点(use_boss_boost_point=true),真机实测直接被 runtime 的
        // boost_not_allowed 拒成 H400 进不了战斗(2026-09-04)。这里把两个开关一律当 false
        // 交给 runtime(冻结契约不变:runtime 仍只接受 false),只留一行日志说明被忽略。
        if (body.use_boost_point === true || body.use_boss_boost_point === true) {
            console.log(`[MULTI] five-boss start: ignoring client boost flags`
                + ` viewer=${body.viewer_id} room=${body.room_number}`
                + ` boost=${body.use_boost_point}/${body.use_boss_boost_point}`);
        }
        const previousMemory = singleBattleQuest_1.activeQuests[playerId];
        let result;
        try {
            result = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
                domain: "multi-settlement", playerId, operation: "five_boss_start",
            }, () => {
                abandonStaleFiveBossRun(body, playerId);
                const result = (0, battle_runtime_1.startFiveBossBattle)({
                    playerId,
                    clientPlayId: body.play_id,
                    room,
                    requestRoomNumber: body.room_number,
                    requestCategory: body.category,
                    requestQuestId: body.quest_id,
                    useBoostPoint: false,
                    useBossBoostPoint: false,
                    httpIsAutoStartMode: body.is_auto_start_mode,
                    matePlayerIds: body.mate_player_ids,
                    mateComIds: room.mates.map(mate => mate.com_id),
                });
                // Keep the selected party update inside the same persistence owner as
                // the run ledger and active quest writes.
                if ((0, party_1.isValidNormalPartySlotSync)(playerId, body.party_id)) {
                    (0, player_1.updatePlayerSync)({ id: playerId, partySlot: body.party_id });
                }
                return result;
            });
        }
        catch (error) {
            if (previousMemory)
                singleBattleQuest_1.activeQuests[playerId] = previousMemory;
            else
                delete singleBattleQuest_1.activeQuests[playerId];
            throw error;
        }
        singleBattleQuest_1.activeQuests[playerId] = result.activeQuest;
        connection_diagnostic_1.fiveBossConnectionDiagnostics.begin(room);
        connection_diagnostic_1.fiveBossConnectionDiagnostics.memberEvent(result.runId, playerId, "http_start", result.startStatus);
        const player = requirePlayer(playerId);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: body.viewer_id }),
            data: {
                is_multi: "multi",
                play_id: body.play_id,
                user_info: { stamina: player.stamina, stamina_heal_time: (0, utils_1.realToVirtual)(player.staminaHealTime) },
                item_list: { [contract_1.FIVE_BOSS_GAUNTLET.ticketItemId]: (_a = (0, item_1.getPlayerItemSync)(playerId, contract_1.FIVE_BOSS_GAUNTLET.ticketItemId)) !== null && _a !== void 0 ? _a : 0 },
            },
        });
    });
}
exports.handleFiveBossStart = handleFiveBossStart;
function handleFiveBossFinish(body, playerId, reply, buildFollowInfo) {
    return __awaiter(this, void 0, void 0, function* () {
        var _a, _b, _c, _d;
        const memoryBeforeFinish = singleBattleQuest_1.activeQuests[playerId];
        const boundRun = (0, fiveBossGauntletRun_1.getFiveBossRunByClientSync)({ playerId, clientPlayId: body.play_id });
        if (boundRun)
            connection_diagnostic_1.fiveBossConnectionDiagnostics.memberEvent(boundRun.runId, playerId, "http_finish", body.is_accomplished === true ? "success_requested" : "failure_requested");
        const roomNumber = resolveFiveBossRoomNumber(body.room_number, playerId, body.play_id, boundRun);
        const party = (_b = (_a = body.statistics) === null || _a === void 0 ? void 0 : _a.party) !== null && _b !== void 0 ? _b : (_c = body.quest_statistics) === null || _c === void 0 ? void 0 : _c.party;
        const result = yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "five_boss_settlement", () => (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "multi-settlement", playerId, operation: "five_boss_finish",
        }, () => {
            var _a, _b, _c, _d, _e, _f;
            if (body.is_accomplished === true && (0, contract_1.isFiveBossGauntletQuest)(body.category, body.quest_id)
                && (boundRun === null || boundRun === void 0 ? void 0 : boundRun.roomNumber) === roomNumber) {
                const backfill = (0, fiveBossGauntletRun_1.backfillMissingFinalizeSync)({ playerId, clientPlayId: body.play_id });
                if (backfill.backfilled) {
                    connection_diagnostic_1.fiveBossConnectionDiagnostics.memberEvent(boundRun.runId, playerId, "finalize_recorded", "http_backfill");
                    console.warn(`[MULTI] five-boss finish: finalize signal never reached the battle channel;`
                        + ` backfilled from HTTP finish player=${playerId} run=${backfill.runId} room=${backfill.roomNumber}`);
                }
            }
            return (0, battle_runtime_1.finishFiveBossBattle)({
                playerId,
                clientPlayId: body.play_id,
                requestRoomNumber: roomNumber,
                requestCategory: body.category,
                requestQuestId: body.quest_id,
                accomplished: body.is_accomplished,
                elapsedTimeMs: (_b = (_a = body.elapsed_time_ms) !== null && _a !== void 0 ? _a : body.battle_time) !== null && _b !== void 0 ? _b : 0,
                highScore: (_c = body.score) !== null && _c !== void 0 ? _c : 0,
                leaderCharacterId: (_f = (_e = (_d = party === null || party === void 0 ? void 0 : party.characters) === null || _d === void 0 ? void 0 : _d[0]) === null || _e === void 0 ? void 0 : _e.id) !== null && _f !== void 0 ? _f : null,
            });
        }));
        clearMatchingMemoryActive(playerId, body.play_id);
        terminalRoomTransition(roomNumber, result.runId, result.runStatus);
        const matePlayerResult = (_d = body.mate_player_result) !== null && _d !== void 0 ? _d : [];
        const followInfo = yield (0, settlement_performance_1.measureSettlementPhaseAsync)("multi", "five_boss_follow", () => {
            var _a, _b;
            return buildFollowInfo(body.viewer_id, matePlayerResult, (_b = (_a = memoryBeforeFinish === null || memoryBeforeFinish === void 0 ? void 0 : memoryBeforeFinish.matePlayerIds) !== null && _a !== void 0 ? _a : body.mate_player_ids) !== null && _b !== void 0 ? _b : []);
        });
        const dataHeaders = (0, utils_1.generateDataHeaders)({ viewer_id: body.viewer_id });
        const exp = result.kind === "success" ? result.reward.characterExp : null;
        const player = requirePlayer(playerId);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: dataHeaders,
            data: buildFinishData(player, body, result, dataHeaders, matePlayerResult, followInfo, exp),
        });
    });
}
exports.handleFiveBossFinish = handleFiveBossFinish;
function handleFiveBossAbort(body, playerId, reply) {
    return __awaiter(this, void 0, void 0, function* () {
        const roomNumber = resolveFiveBossRoomNumber(body.room_number, playerId, body.play_id);
        const result = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "multi-settlement", playerId, operation: "five_boss_abort",
        }, () => (0, battle_runtime_1.abortFiveBossBattle)({
            playerId,
            clientPlayId: body.play_id,
            requestRoomNumber: roomNumber,
            requestCategory: body.category,
            requestQuestId: body.quest_id,
        }));
        clearMatchingMemoryActive(playerId, body.play_id);
        terminalRoomTransition(roomNumber, result.runId, result.runStatus);
        const headers = (0, utils_1.generateDataHeaders)({ viewer_id: body.viewer_id });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: headers,
            data: {
                user_info: {},
                category_id: body.category,
                is_multi: "multi",
                start_time: headers.servertime,
                quest_name: "",
                aborted_play_id: null,
                unfinished_play_id: null,
                drawn_quest: null,
                party_info: null,
                presigned_url: null,
            },
        });
    });
}
exports.handleFiveBossAbort = handleFiveBossAbort;
