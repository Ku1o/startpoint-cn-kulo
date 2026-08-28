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
const utils_1 = require("../../utils");
const player_1 = require("../../data/domains/player");
const quest_active_1 = require("../../data/domains/quest_active");
const session_1 = require("../../data/domains/session");
const utils_2 = require("../../data/utils");
const content_snapshot_1 = require("../../content/runtime/content-snapshot");
const active_reconciliation_1 = require("../../lib/mission/active-reconciliation");
const activeAccount_1 = require("../../data/activeAccount");
const serializer_1 = require("../../multi/room/serializer");
const manager_1 = require("../../multi/room/manager");
const validate_1 = require("../../lib/validate");
const singleBattleQuest_1 = require("../api/singleBattleQuest");
const profileFavorite_1 = require("../../lib/profileFavorite");
const game_logging_1 = require("../../lib/game-logging");
const mode15_active_quest_recovery_1 = require("../../lib/mode15-active-quest-recovery");
const mode15_optional_1 = require("../../lib/mode15-optional");
const rushEvent_1 = require("../../data/domains/rushEvent");
const gauntlet_completion_classification_1 = require("../../lib/gauntlet-completion-classification");
const equipment_1 = require("../../data/domains/equipment");
const character_1 = require("../../data/domains/character");
const party_1 = require("../../data/domains/party");
const quest_1 = require("../../data/domains/quest");
function wrapOptionFields(d, playerId, resVer) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q;
    var _r, _s, _t, _u, _v, _w, _x, _y, _z, _0, _1, _2, _3, _4;
    // Report effective server version (CDN + patches) to trigger client update
    const { getEffectiveVersion } = require("../../lib/version");
    d.available_asset_version = getEffectiveVersion();
    if (d.user_info) {
        if (typeof d.user_info.last_login_time === 'number') {
            const dt = new Date(d.user_info.last_login_time * 1000);
            const p = (n) => n.toString().padStart(2, '0');
            d.user_info.last_login_time = `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())} ${p(dt.getHours())}:${p(dt.getMinutes())}:${p(dt.getSeconds())}`;
        }
        (_a = (_r = d.user_info).is_bought_fund_ex_quest) !== null && _a !== void 0 ? _a : (_r.is_bought_fund_ex_quest = false);
        (_b = (_s = d.user_info).is_bought_fund_main_quest) !== null && _b !== void 0 ? _b : (_s.is_bought_fund_main_quest = false);
        (_c = (_t = d.user_info).is_bought_fund_laite) !== null && _c !== void 0 ? _c : (_t.is_bought_fund_laite = false);
        (_d = (_u = d.user_info).is_bought_fund_laite2) !== null && _d !== void 0 ? _d : (_u.is_bought_fund_laite2 = false);
        (_e = (_v = d.user_info).is_bought_fund_laite3) !== null && _e !== void 0 ? _e : (_v.is_bought_fund_laite3 = false);
        (_f = (_w = d.user_info).is_newbie) !== null && _f !== void 0 ? _f : (_w.is_newbie = true);
        (_g = (_x = d.user_info).is_comeback) !== null && _g !== void 0 ? _g : (_x.is_comeback = false);
        (_h = (_y = d.user_info).month_card_remain_days) !== null && _h !== void 0 ? _h : (_y.month_card_remain_days = 0);
        (_j = (_z = d.user_info).weekly_bonus_remain_days) !== null && _j !== void 0 ? _j : (_z.weekly_bonus_remain_days = 0);
        (_k = (_0 = d.user_info).monthly_payment_total) !== null && _k !== void 0 ? _k : (_0.monthly_payment_total = 0);
        (_l = (_1 = d.user_info).renewal_gift_remain_days) !== null && _l !== void 0 ? _l : (_1.renewal_gift_remain_days = 0);
    }
    if (d.user_option) {
        (_m = (_2 = d.user_option).episode_encyclopedia_suggest_show) !== null && _m !== void 0 ? _m : (_2.episode_encyclopedia_suggest_show = false);
        (_o = (_3 = d.user_option).server_push) !== null && _o !== void 0 ? _o : (_3.server_push = false);
        (_p = (_4 = d.user_option).stamina) !== null && _p !== void 0 ? _p : (_4.stamina = false);
    }
    d.cn_crash_url = `http://${(0, serializer_1.getDisplayHost)()}:${process.env.CN_LISTEN_PORT || "8001"}/crash`;
    d.survey_url = "";
    d.qq_group_url = "";
    d.bug_report_url = "";
    d.enable_gift = false;
    d.enable_customer_service = false;
    d.enable_rename = true;
    d.enable_delete_file = false;
    d.enable_newbie = false;
    d.enable_little_assistant = false;
    d.mission_tips = false;
    d.monthly_tip = false;
    d.simple_payment_item_list = [];
    d.ex_boost_draw_result = null;
    d.pass_force_reward = false;
    d.crazy_gacha_result_list = [];
    d.last_crazy_gacha_draw_result = [];
    d.fund_receive_list = [];
    d.login_info = {};
    d.tower_dungeon_list = [];
    d.special_exchange_campaign_list = [];
    d.win_lottery_active_mission_list = [];
    d.stars_gacha_campaign_list = [];
    // Profile favorites are stored separately as party category 99.  Do not
    // rebuild them from the normal SET1 party, or the chosen favorite is lost
    // on every load.
    d.favorite_party_group_list = (0, profileFavorite_1.getFavoritePartyGroupListSync)(playerId, ((_q = d.user_info) === null || _q === void 0 ? void 0 : _q.leader_character_id) || 1);
    d.ranking_event_reward = [];
    d.party_list = [];
    d.payment_rebate_info = { expired_time: 0, status: 0, start_time: 0 };
    d.monthly_charge_bonus_info = { bonus_days: 0, expired_time: 0, init_time: 0, status: 0, start_time: 0 };
    d.comeback_campaign_boss_boost = { period_start_time: 0, period_end_time: 0 };
    return d;
}
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/load", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        try {
            const body = request.body;
            const viewerId = body.viewer_id || body.keychain || 1;
            const session = yield (0, session_1.getSession)(String(viewerId));
            const accountId = session ? session.accountId : (body.viewer_id || body.keychain || 1);
            const playerId = (0, activeAccount_1.resolvePlayerIdSync)(accountId);
            if (!playerId) {
                return reply.status(400).send({ error: "Bad Request", message: "No player found" });
            }
            const player = (0, player_1.getPlayerSync)(playerId);
            if (player === null) {
                return reply.status(500).send({ error: "Internal Server Error", message: "No player data." });
            }
            const now = (0, utils_1.getServerDate)();
            (0, player_1.dailyResetPlayerDataSync)(player, now);
            (0, player_1.collectPlayerDataPooledExpSync)(player, now);
            // Equipment is needed by both validation and serialization. Validators
            // mutate this request-local object when they repair a row.
            const equipmentList = (0, equipment_1.getPlayerEquipmentListSync)(playerId);
            (0, validate_1.runPermanentValidators)(playerId, { player, equipmentList });
            // 若自定义时间与 lastLogin 不同步，强制对齐（防止客户端弹"日期变了"）
            if (now.toDateString() !== player.lastLoginTime.toDateString()) {
                (0, player_1.updatePlayerSync)({ id: player.id, lastLoginTime: now });
            }
            // Daily reset and pooled EXP collection may update the base row. Read
            // it once after those mutations, then reuse the fresh snapshot through
            // the remaining synchronous /load pipeline.
            const currentPlayer = (0, player_1.getPlayerSync)(playerId);
            if (currentPlayer === null) {
                return reply.status(500).send({ error: "Internal Server Error", message: "No player data." });
            }
            const characterList = (0, character_1.getPlayerCharactersSync)(playerId);
            const characterManaNodeList = (0, character_1.getPlayerCharactersManaNodesSync)(playerId);
            const partyGroupList = (0, party_1.getPlayerPartyGroupListSync)(playerId);
            const questProgress = (0, quest_1.getPlayerQuestProgressSync)(playerId);
            (0, active_reconciliation_1.reconcileActiveMissionFacts)({
                playerId,
                player: currentPlayer,
                characterList,
                characterManaNodeList,
                equipmentList,
                partyGroupList,
                questProgress,
                repository: (0, content_snapshot_1.getContentSnapshot)().repository,
                now: (0, utils_1.getServerTime)() * 1000,
            });
            const removedMode15RescueRows = (0, mode15_optional_1.cleanupLegacyMode15RescueProgressSync)(playerId);
            if (removedMode15RescueRows > 0) {
                console.log(`[MODE15] removed legacy rescue progress: player=${playerId} rows=${removedMode15RescueRows}`);
            }
            // AdventEvent quest visibility points at Mode15's Rush quests.  The
            // legacy client cannot resolve that cross-event condition until the
            // corresponding Rush event exists in its player model.  A completed
            // or failed run removes the server row, so recreate the empty shell
            // before serializing /load instead of requiring a visit to Rush first.
            if ((0, mode15_optional_1.isMode15RuntimeLoaded)()
                && (0, rushEvent_1.getPlayerRushEventSync)(playerId, mode15_optional_1.MODE15_RUSH_EVENT_ID) === null) {
                (0, rushEvent_1.insertPlayerRushEventSync)(playerId, (0, rushEvent_1.getDefaultPlayerRushEventSync)(mode15_optional_1.MODE15_RUSH_EVENT_ID));
                console.log(`[MODE15] initialized Rush state during load: player=${playerId}`);
            }
            const repairedGauntletCompletions = (0, gauntlet_completion_classification_1.repairAllGauntletCompletionClassificationsSync)(playerId);
            if (repairedGauntletCompletions.length > 0) {
                console.log(`[RUSH] repaired completed classification during load: `
                    + `player=${playerId} events=${repairedGauntletCompletions.join(",")}`);
            }
            const serializedQuestProgress = removedMode15RescueRows > 0
                || repairedGauntletCompletions.length > 0
                ? (0, quest_1.getPlayerQuestProgressSync)(playerId)
                : questProgress;
            // Include Rush state in the initial payload so the legacy client can
            // evaluate cross-event clear conditions on a cold visit. Optional
            // saved party slots are normalized to null before packing (rather than
            // MessagePack's unsupported undefined extension, 0xD4).
            const clientData = (0, utils_2.getClientSerializedData)(playerId, {
                viewerId: accountId,
                serializeRushEventData: true,
                preloadedPlayer: currentPlayer,
                preloadedCharacterList: characterList,
                preloadedCharacterManaNodeList: characterManaNodeList,
                preloadedEquipmentList: equipmentList,
                preloadedPartyGroupList: partyGroupList,
                preloadedQuestProgress: serializedQuestProgress,
            });
            if (clientData === null) {
                return reply.status(500).send({ error: "Internal Server Error", message: "No player data." });
            }
            const resVer = request.headers['res_ver'];
            (0, game_logging_1.gameVerboseLog)(() => { var _a; return `[CN-LOAD] res_ver=${resVer || '(not sent)'} account=${accountId} player=${playerId} party_slot=${(_a = clientData === null || clientData === void 0 ? void 0 : clientData.user_info) === null || _a === void 0 ? void 0 : _a.party_slot}`; });
            wrapOptionFields(clientData, playerId, resVer);
            // Inject unfinished quest lists for battle recovery
            const activeQuest = (0, quest_active_1.getPlayerActiveQuestSync)(playerId);
            if (activeQuest) {
                // A multiplayer client can disconnect during settlement before its
                // own finish request removes the active quest.  Once the room has
                // already returned to the lobby, that battle can no longer be
                // resumed and exposing it as unfinished traps the client in a loop.
                const activeRoom = activeQuest.roomNumber ? (0, manager_1.getRoom)(activeQuest.roomNumber) : undefined;
                const roomExists = activeQuest.roomNumber ? !!activeRoom : true;
                const completedMultiRoom = activeQuest.isMulti && !!activeRoom && activeRoom.raising_state !== 4;
                const noLongerInCurrentBattle = activeQuest.isMulti
                    && !!activeRoom
                    && activeRoom.raising_state === 4
                    && activeRoom.expected_real_viewer_ids.length > 0
                    && !activeRoom.expected_real_viewer_ids.includes(accountId);
                if (!roomExists || completedMultiRoom || noLongerInCurrentBattle) {
                    const mode15Quest = (0, mode15_optional_1.isMode15Quest)(activeQuest.category, activeQuest.questId);
                    // Multiplayer rescue guests never own the Mode15 run represented
                    // by this room. Loading-stage disconnects may remove them from the
                    // room before /cn/load recovers their stale active quest, so only
                    // a persisted host marker is authoritative once the room is gone.
                    const shouldResetMode15Run = (0, mode15_active_quest_recovery_1.shouldResetMode15RunForStaleActiveQuest)(mode15Quest, activeQuest);
                    (0, game_logging_1.gameVerboseLog)(() => { var _a; return `[CN-LOAD] stale active quest cleared: room=${activeQuest.roomNumber} exists=${roomExists} state=${(_a = activeRoom === null || activeRoom === void 0 ? void 0 : activeRoom.raising_state) !== null && _a !== void 0 ? _a : "missing"} mode15=${mode15Quest} multiHost=${activeQuest.isMultiHost} reset=${shouldResetMode15Run}`; });
                    if (shouldResetMode15Run) {
                        (0, mode15_optional_1.resetMode15RunSync)(playerId);
                    }
                    (0, quest_active_1.deletePlayerActiveQuestSync)(playerId);
                    delete singleBattleQuest_1.activeQuests[playerId];
                    clientData.unfinished_quest_list = [];
                    clientData.unfinished_multi_quest_list = [];
                }
                else {
                    const entry = { play_id: activeQuest.playId, continue_count: activeQuest.continueCount };
                    if (activeQuest.isMulti) {
                        clientData.unfinished_quest_list = [];
                        clientData.unfinished_multi_quest_list = [entry];
                    }
                    else {
                        clientData.unfinished_quest_list = [entry];
                        clientData.unfinished_multi_quest_list = [];
                    }
                }
            }
            else {
                clientData.unfinished_quest_list = [];
                clientData.unfinished_multi_quest_list = [];
            }
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                data_headers: (0, utils_1.generateDataHeaders)({
                    asset_update: true,
                    viewer_id: accountId,
                    servertime: (0, utils_1.getServerTime)(),
                }),
                data: clientData
            });
        }
        catch (e) {
            console.error(`[CN-LOAD] ERROR:`, e.message, e.stack);
            return reply.status(500).send({ error: "Internal Server Error", message: e.message });
        }
    }));
});
exports.default = routes;
