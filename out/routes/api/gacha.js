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
const mail_1 = require("../../data/domains/mail");
const gacha_1 = require("../../data/domains/gacha");
const item_1 = require("../../data/domains/item");
const player_1 = require("../../data/domains/player");
const session_1 = require("../../data/domains/session");
const utils_1 = require("../../utils");
const gacha_2 = require("../../lib/gacha");
const assets_1 = require("../../lib/assets");
const types_1 = require("../../lib/types");
const utils_2 = require("../../data/utils");
const activeAccount_1 = require("../../data/activeAccount");
const character_1 = require("../../lib/character");
const equipment_1 = require("../../lib/equipment");
const gacha_exec_plan_1 = require("../../lib/gacha-exec-plan");
const gacha_rules_1 = require("../../lib/gacha-rules");
const db_1 = require("../../data/db");
const mission_1 = require("../../lib/mission");
const active_mission_counters_1 = require("../../data/domains/active_mission_counters");
const game_logging_1 = require("../../lib/game-logging");
const option_1 = require("../../data/domains/option");
var GachaPaymentType;
(function (GachaPaymentType) {
    GachaPaymentType[GachaPaymentType["EMPTY"] = 0] = "EMPTY";
    GachaPaymentType[GachaPaymentType["FREE_VMONEY"] = 1] = "FREE_VMONEY";
    GachaPaymentType[GachaPaymentType["VMONEY"] = 2] = "VMONEY";
    GachaPaymentType[GachaPaymentType["TICKET"] = 3] = "TICKET";
    GachaPaymentType[GachaPaymentType["CAMPAIGN"] = 4] = "CAMPAIGN";
})(GachaPaymentType || (GachaPaymentType = {}));
var GachaExecType;
(function (GachaExecType) {
    GachaExecType[GachaExecType["EMPTY"] = 0] = "EMPTY";
    GachaExecType[GachaExecType["VMONEY_SINGLE"] = 1] = "VMONEY_SINGLE";
    GachaExecType[GachaExecType["VMONEY_MULTI"] = 2] = "VMONEY_MULTI";
    GachaExecType[GachaExecType["UNKNOWN_1"] = 3] = "UNKNOWN_1";
    GachaExecType[GachaExecType["UNKNOWN_2"] = 4] = "UNKNOWN_2";
    GachaExecType[GachaExecType["DAILY_SINGLE"] = 5] = "DAILY_SINGLE";
    GachaExecType[GachaExecType["UNKNOWN_3"] = 6] = "UNKNOWN_3";
    GachaExecType[GachaExecType["CAMPAIGN_SINGLE"] = 7] = "CAMPAIGN_SINGLE";
    GachaExecType[GachaExecType["CAMPAIGN_MULTI"] = 8] = "CAMPAIGN_MULTI";
    GachaExecType[GachaExecType["MULTI_TICKET"] = 9] = "MULTI_TICKET";
    GachaExecType[GachaExecType["SINGLE_TICKET"] = 10] = "SINGLE_TICKET";
    GachaExecType[GachaExecType["UNKNOWN_4"] = 11] = "UNKNOWN_4";
    GachaExecType[GachaExecType["SINGLE_WEAPON_TICKET"] = 12] = "SINGLE_WEAPON_TICKET";
    GachaExecType[GachaExecType["MULTI_WEAPON_TICKET"] = 13] = "MULTI_WEAPON_TICKET";
})(GachaExecType || (GachaExecType = {}));
const exchangeRequiredPoints = 250;
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/exchange_equipment", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a;
        const body = request.body;
        const equipmentId = body.equipment_id;
        const gachaId = body.gacha_id;
        const viewerId = body.viewer_id;
        if (isNaN(viewerId) || isNaN(equipmentId) || isNaN(gachaId))
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            });
        const viewerIdSession = yield (0, session_1.getSession)(viewerId.toString());
        if (!viewerIdSession)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid viewer id."
            });
        // get player
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(viewerIdSession.accountId);
        if (playerId === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        // get gacha info
        const gachaInfo = (0, gacha_1.getPlayerGachaInfoSync)(playerId, gachaId);
        if (gachaInfo === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "No data for gacha with provided id."
            });
        const gachaData = (0, assets_1.getGachaSync)(gachaId);
        if (gachaData === null || gachaData.type !== types_1.GachaType.WEAPON)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "No equipment exchange data for gacha with provided id."
            });
        if ((0, gacha_rules_1.getExchangeableGachaItem)(gachaData, equipmentId) === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Equipment is not exchangeable from this gacha."
            });
        const newExchangePoints = ((_a = gachaInfo.gachaExchangePoint) !== null && _a !== void 0 ? _a : 0) - exchangeRequiredPoints;
        if (0 > newExchangePoints)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Not enough exchange points."
            });
        // reward equipment
        const giveResult = (0, equipment_1.givePlayerEquipmentSync)(playerId, equipmentId, 1);
        (0, mail_1.insertReceiveHistorySync)(playerId, { type: mail_1.MailType.EQUIPMENT, type_id: equipmentId, number: 1 });
        // update gacha info
        (0, gacha_1.updatePlayerGachaInfoSync)(playerId, {
            gachaId: gachaId,
            gachaExchangePoint: newExchangePoints
        });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": {
                "equipment_list": [
                    giveResult
                ],
                "gacha_info_list": [
                    {
                        "gacha_id": gachaId,
                        "is_account_first": gachaInfo.isAccountFirst,
                        "is_daily_first": gachaInfo.isDailyFirst,
                        "gacha_exchange_point": newExchangePoints
                    }
                ],
                "encyclopedia_info": [],
                "mail_arrived": false
            }
        });
    }));
    fastify.post("/exchange_character", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _b;
        const body = request.body;
        const characterId = body.character_id;
        const gachaId = body.gacha_id;
        const viewerId = body.viewer_id;
        if (isNaN(viewerId) || isNaN(characterId) || isNaN(gachaId))
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            });
        const viewerIdSession = yield (0, session_1.getSession)(viewerId.toString());
        if (!viewerIdSession)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid viewer id."
            });
        // get player
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(viewerIdSession.accountId);
        if (playerId === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        // get gacha info
        const gachaInfo = (0, gacha_1.getPlayerGachaInfoSync)(playerId, gachaId);
        if (gachaInfo === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "No data for gacha with provided id."
            });
        const gachaData = (0, assets_1.getGachaSync)(gachaId);
        if (gachaData === null || gachaData.type !== types_1.GachaType.CHARACTER)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "No character exchange data for gacha with provided id."
            });
        if ((0, gacha_rules_1.getExchangeableGachaItem)(gachaData, characterId) === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Character is not exchangeable from this gacha."
            });
        const newExchangePoints = ((_b = gachaInfo.gachaExchangePoint) !== null && _b !== void 0 ? _b : 0) - exchangeRequiredPoints;
        if (0 > newExchangePoints)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Not enough exchange points."
            });
        // reward character
        const giveResult = (0, character_1.givePlayerCharacterSync)(playerId, characterId);
        if (giveResult === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Could not give player character."
            });
        (0, mail_1.insertReceiveHistorySync)(playerId, { type: mail_1.MailType.CHARACTER, type_id: characterId, number: 1 });
        // update gacha info
        (0, gacha_1.updatePlayerGachaInfoSync)(playerId, {
            gachaId: gachaId,
            gachaExchangePoint: newExchangePoints
        });
        const existingCharacterList = giveResult.character
            ? [giveResult.character]
            : [];
        const characterList = existingCharacterList.length > 0
            ? (0, mission_1.reconcileAwakeUnlockCharacterList)(playerId, existingCharacterList)
            : existingCharacterList;
        const responseData = {
            "character_list": characterList,
            "item_list": giveResult.item !== undefined ? {
                [giveResult.item.id]: giveResult.item.inventoryCount
            } : [],
            "gacha_info_list": [
                {
                    "gacha_id": gachaId,
                    "is_account_first": gachaInfo.isAccountFirst,
                    "is_daily_first": gachaInfo.isDailyFirst,
                    "gacha_exchange_point": newExchangePoints
                }
            ],
            "encyclopedia_info": [],
            "mail_arrived": false
        };
        (0, mission_1.settleDegreeMissionResponse)(playerId, viewerId, responseData, undefined, [4]);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": responseData
        });
    }));
    fastify.post("/exec", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _c, _d;
        const body = request.body;
        const viewerId = body.viewer_id;
        const gachaId = body.gacha_id;
        const paymentType = body.payment_type;
        const numberOfExec = body.number_of_exec;
        const type = body.type;
        if (isNaN(viewerId) || isNaN(gachaId) || isNaN(paymentType) || isNaN(numberOfExec) || isNaN(type)) {
            console.log(`[GACHA] Invalid body: v=${viewerId} g=${gachaId} pt=${paymentType} n=${numberOfExec} t=${type}`);
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            });
        }
        const viewerIdSession = yield (0, session_1.getSession)(viewerId.toString());
        if (!viewerIdSession)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid viewer id."
            });
        // get player
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(viewerIdSession.accountId);
        if (playerId === null)
            return reply.status(500).send({ "error": "Internal Server Error", "message": "No players bound to account." });
        const player = (0, player_1.getPlayerSync)(playerId);
        if (player === null)
            return;
        // get the gacha
        const gachaData = (0, assets_1.getGachaSync)(gachaId);
        if (gachaData === null) {
            console.log(`[GACHA] Gacha not found: gachaId=${gachaId}`);
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Gacha doesn't exist."
            });
        }
        const isCharacterGacha = gachaData.type == types_1.GachaType.CHARACTER;
        // get player gacha data
        let playerGachaData = (0, gacha_1.getPlayerGachaInfoSync)(playerId, gachaId);
        const insertPlayerGachaData = playerGachaData === null;
        playerGachaData = playerGachaData !== null && playerGachaData !== void 0 ? playerGachaData : {
            gachaId: gachaId,
            isAccountFirst: true,
            isDailyFirst: true,
            gachaExchangePoint: 0
        };
        let gachaCampaigns = [];
        let items = {};
        let plannedCampaign = null;
        const planResult = (0, gacha_exec_plan_1.buildGachaExecPlan)({
            gacha: gachaData,
            paymentType,
            execType: type,
            numberOfExec,
            playerFunds: {
                freeVmoney: player.freeVmoney,
                paidVmoney: player.vmoney,
            },
            playerGachaData,
            getTicketCount: (itemId) => (0, item_1.getPlayerItemSync)(playerId, itemId),
            getCampaignState: () => {
                const campaignId = (0, assets_1.getGachaCampaignIdSync)(gachaId);
                if (campaignId === null)
                    return null;
                const existingCampaign = (0, gacha_1.getPlayerGachaCampaignSync)(playerId, gachaId, campaignId);
                const campaignForPlan = existingCampaign !== null && existingCampaign !== void 0 ? existingCampaign : {
                    gachaId,
                    campaignId,
                    count: 1,
                };
                plannedCampaign = campaignForPlan;
                return {
                    campaignId,
                    count: campaignForPlan.count,
                    insert: existingCampaign === null,
                };
            },
        });
        if (!planResult.ok) {
            console.log(`[GACHA] Exec plan rejected: gachaId=${gachaId} paymentType=${paymentType} type=${type} message=${planResult.message}`);
            return reply.status(planResult.status).send({
                "error": "Bad Request",
                "message": planResult.message
            });
        }
        const execPlan = planResult.plan;
        const pullCount = execPlan.pullCount;
        const playerPaidVmoney = execPlan.paidVmoney;
        const playerFreeVmoney = execPlan.freeVmoney;
        const drawMetadata = (0, gacha_2.drawGachaWithMetadataSync)(gachaData, pullCount);
        const drawResult = drawMetadata.map((draw) => draw.id);
        const skipNoRarityUpMovie = isCharacterGacha
            ? (0, option_1.getPlayerOptionSync)(playerId, "gacha_play_no_rarity_up_movie", false)
            : false;
        const plannedCharacterMovies = isCharacterGacha
            ? (0, gacha_2.planCharacterGachaMovies)(gachaData, drawResult, { skipNoRarityUpMovie })
            : undefined;
        const transactionResult = (0, db_1.getDb)().transaction(() => {
            var _a;
            if (execPlan.ticket) {
                items[execPlan.ticket.itemId] = execPlan.ticket.afterCount;
                (0, item_1.updatePlayerItemSync)(playerId, execPlan.ticket.itemId, execPlan.ticket.afterCount);
            }
            if (execPlan.campaign) {
                const campaignData = plannedCampaign !== null && plannedCampaign !== void 0 ? plannedCampaign : {
                    gachaId,
                    campaignId: execPlan.campaign.campaignId,
                    count: execPlan.campaign.count,
                };
                campaignData.count = execPlan.campaign.count;
                if (execPlan.campaign.insert) {
                    (0, gacha_1.insertPlayerGachaCampaignSync)(playerId, campaignData);
                }
                else {
                    (0, gacha_1.updatePlayerGachaCampaignSync)(playerId, gachaId, execPlan.campaign.campaignId, execPlan.campaign.count);
                }
                gachaCampaigns.push((0, utils_2.serializeGachaCampaign)(campaignData));
            }
            const rewardResult = (0, gacha_2.rewardPlayerGachaDrawResultSync)(playerId, gachaData, drawResult, drawMetadata, plannedCharacterMovies);
            // Log each drawn item in history
            const historyType = isCharacterGacha ? mail_1.MailType.CHARACTER : mail_1.MailType.EQUIPMENT;
            for (const itemId of drawResult) {
                (0, mail_1.insertReceiveHistorySync)(playerId, { type: historyType, type_id: itemId, number: 1 });
            }
            const newGachaExchangePoint = ((_a = playerGachaData.gachaExchangePoint) !== null && _a !== void 0 ? _a : 0) + pullCount;
            if (insertPlayerGachaData) {
                playerGachaData.isAccountFirst = false;
                playerGachaData.isDailyFirst = false;
                playerGachaData.gachaExchangePoint = newGachaExchangePoint;
                (0, gacha_1.insertPlayerGachaInfoSync)(playerId, playerGachaData);
            }
            else {
                (0, gacha_1.updatePlayerGachaInfoSync)(playerId, {
                    gachaId: gachaId,
                    isDailyFirst: false,
                    isAccountFirst: false,
                    gachaExchangePoint: newGachaExchangePoint
                });
            }
            (0, player_1.updatePlayerSync)({
                id: playerId,
                vmoney: playerPaidVmoney,
                freeVmoney: playerFreeVmoney
            });
            if (isCharacterGacha) {
                (0, active_mission_counters_1.incrementActiveMissionGachaCharacterCountSync)(playerId, drawResult.length);
            }
            if (execPlan.campaign) {
                (0, active_mission_counters_1.incrementActiveMissionGachaCampaignCountSync)(playerId);
            }
            return { rewardResult, newGachaExchangePoint };
        })();
        const { rewardResult, newGachaExchangePoint } = transactionResult;
        const rarityCounts = new Map();
        for (const draw of drawMetadata) {
            rarityCounts.set(draw.rank, ((_c = rarityCounts.get(draw.rank)) !== null && _c !== void 0 ? _c : 0) + 1);
        }
        const raritySummary = Array.from(rarityCounts.entries())
            .sort(([left], [right]) => left - right)
            .map(([rank, count]) => `${rank}:${count}`)
            .join(",");
        (0, game_logging_1.gameVerboseLog)(() => `[GACHA] gacha=${gachaId} type=${isCharacterGacha ? "character" : "equipment"} `
            + `pulls=${pullCount} rarity=${raritySummary}`);
        reply.header("content-type", "application/x-msgpack");
        if (isCharacterGacha) {
            const existingCharacterList = rewardResult.characters.filter((character) => character !== undefined
                && character !== null
                && typeof character === "object"
                && !Array.isArray(character));
            const characterList = existingCharacterList.length > 0
                ? (0, mission_1.reconcileAwakeUnlockCharacterList)(playerId, existingCharacterList)
                : existingCharacterList;
            const responseData = {
                "user_info": {
                    "free_vmoney": playerFreeVmoney,
                    "vmoney": playerPaidVmoney
                },
                "draw": rewardResult.draw,
                "character_list": characterList,
                "item_list": Object.assign(Object.assign({}, items), rewardResult.items),
                "gacha_campaign_list": gachaCampaigns,
                "gacha_info_list": [
                    {
                        "gacha_id": gachaId,
                        "is_account_first": false,
                        "is_daily_first": false,
                        "gacha_exchange_point": newGachaExchangePoint
                    }
                ],
                "encyclopedia_info": [],
                "mail_arrived": false
            };
            (0, mission_1.settleDegreeMissionResponse)(playerId, viewerId, responseData, undefined, [4]);
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({
                    viewer_id: viewerId
                }),
                "data": responseData
            });
        }
        else {
            const responseData = {
                "user_info": {
                    "free_vmoney": playerFreeVmoney,
                    "vmoney": playerPaidVmoney
                },
                "is_erupt": (_d = rewardResult.isErupt) !== null && _d !== void 0 ? _d : false,
                "draw_equipment": rewardResult.draw,
                "item_list": Object.assign(Object.assign({}, items), rewardResult.items),
                "equipment_list": rewardResult.equipment,
                "gacha_info_list": [
                    {
                        "gacha_id": gachaId,
                        "is_account_first": false,
                        "is_daily_first": false,
                        "gacha_exchange_point": newGachaExchangePoint
                    }
                ],
                "encyclopedia_info": [],
                "mail_arrived": false
            };
            // Equipment draws do not alter equipment awakening/Lv5 counts.
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({
                    viewer_id: viewerId
                }),
                "data": responseData
            });
        }
    }));
});
exports.default = routes;
