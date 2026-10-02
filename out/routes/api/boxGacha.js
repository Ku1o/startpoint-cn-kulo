"use strict";
// Handles the insertion of mana into characters.
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
const boxGacha_1 = require("../../data/domains/boxGacha");
const item_1 = require("../../data/domains/item");
const player_1 = require("../../data/domains/player");
const session_1 = require("../../data/domains/session");
const activeAccount_1 = require("../../data/activeAccount");
const utils_1 = require("../../utils");
const assets_1 = require("../../lib/assets");
const gacha_1 = require("../../lib/gacha");
const mission_1 = require("../../lib/mission");
const persistence_coordinator_1 = require("../../lib/persistence-coordinator");
/**
 * Calculates the remaining stock from the current reward master and the
 * player's per-reward draw history. This remains correct when a patch expands
 * an existing box after the player has already emptied the previous version.
 */
function getCurrentRemainingNumber(rewards, drawnRewards) {
    const drawnMap = new Map(drawnRewards.map(reward => [reward.id, reward.number]));
    return Object.entries(rewards).reduce((remaining, [rewardId, reward]) => {
        var _a;
        return remaining + Math.max(0, reward.available - ((_a = drawnMap.get(Number(rewardId))) !== null && _a !== void 0 ? _a : 0));
    }, 0);
}
/**
 * Legacy players can have remaining_number=0/is_closed=true for a box that was
 * empty before its master-data stock was increased. Reopen only the newly
 * added difference; boxes closed early retain a positive stored remainder and
 * are deliberately left closed.
 */
function reconcileExpandedEmptyBox(playerId, boxGachaId, boxId, rewards, drawnRewards, playerBoxData) {
    if (playerBoxData === null || playerBoxData.remainingNumber !== 0)
        return playerBoxData;
    const currentRemainingNumber = getCurrentRemainingNumber(rewards, drawnRewards);
    if (currentRemainingNumber <= 0)
        return playerBoxData;
    (0, boxGacha_1.updatePlayerBoxGachaSync)(playerId, boxGachaId, {
        boxId,
        remainingNumber: currentRemainingNumber,
        isClosed: false
    });
    console.log(`[BOX] reopened expanded empty box: player=${playerId} gacha=${boxGachaId} box=${boxId} added=${currentRemainingNumber}`);
    return Object.assign(Object.assign({}, playerBoxData), { remainingNumber: currentRemainingNumber, isClosed: false });
}
/**
 * Returns all of a box gacha's box statuses serialized for the client.
 *
 * @param playerId The ID of the player.
 * @param boxGachaId The ID of the box gacha.
 * @param boxes A record of boxes to get the data of.
 * @param skipBoxId The ID of the box id to skip.
 */
function getAllBoxList(playerId, boxGachaId, boxes, skipBoxId) {
    var _a, _b;
    const boxInfo = [];
    for (const [boxId, rewards] of Object.entries(boxes)) {
        // get drawn rewards
        const parsedBoxId = Number(boxId);
        if (parsedBoxId !== skipBoxId) {
            const playerDrawnRewards = (0, boxGacha_1.getPlayerBoxGachaDrawnRewardsSync)(playerId, boxGachaId, parsedBoxId);
            const playerBoxData = reconcileExpandedEmptyBox(playerId, boxGachaId, parsedBoxId, rewards, playerDrawnRewards, (0, boxGacha_1.getPlayerBoxGachaSync)(playerId, boxGachaId, parsedBoxId));
            boxInfo.push({
                "box_id": parsedBoxId,
                "reset_times": (_a = playerBoxData === null || playerBoxData === void 0 ? void 0 : playerBoxData.resetTimes) !== null && _a !== void 0 ? _a : 0,
                "all_drawn_reward_list": playerDrawnRewards.map(reward => {
                    return {
                        "reward_id": reward.id,
                        "number": reward.number
                    };
                }),
                "coming_next_reward_list": [],
                "is_closed": (_b = playerBoxData === null || playerBoxData === void 0 ? void 0 : playerBoxData.isClosed) !== null && _b !== void 0 ? _b : false
            });
        }
    }
    return boxInfo;
}
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/reset", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = Number(body.viewer_id);
        const boxGachaId = Number(body.box_gacha_id);
        const boxId = Number(body.box_id);
        console.log(`[BOX] reset: boxGachaId=${boxGachaId} boxId=${boxId}`);
        if (!Number.isFinite(viewerId) || !Number.isFinite(boxGachaId) || !Number.isFinite(boxId))
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
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(viewerIdSession.accountId);
        if (playerId === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        const boxGachaData = (0, assets_1.getBoxGachaSync)(boxGachaId);
        const boxRewards = boxGachaData === null || boxGachaData === void 0 ? void 0 : boxGachaData.boxes[boxId];
        const availableCount = boxGachaData === null || boxGachaData === void 0 ? void 0 : boxGachaData.availableCounts[boxId];
        if (boxGachaData === null || boxRewards === undefined || availableCount === undefined)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid box gacha or box id."
            });
        const resetResult = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "gacha", playerId, operation: "box_reset",
        }, () => {
            const playerDrawnRewards = (0, boxGacha_1.getPlayerBoxGachaDrawnRewardsSync)(playerId, boxGachaId, boxId);
            const playerBoxData = reconcileExpandedEmptyBox(playerId, boxGachaId, boxId, boxRewards, playerDrawnRewards, (0, boxGacha_1.getPlayerBoxGachaSync)(playerId, boxGachaId, boxId));
            if (playerBoxData === null)
                return { allBoxInfo: null, errorMessage: "Box doesn't exist." };
            if (!playerBoxData.isClosed && playerBoxData.remainingNumber > 0) {
                return { allBoxInfo: null, errorMessage: "Box still has remaining rewards." };
            }
            if (!(0, boxGacha_1.resetPlayerBoxGachaSync)(playerId, boxGachaId, boxId, availableCount)) {
                return { allBoxInfo: null, errorMessage: "Failed to reset box." };
            }
            return { allBoxInfo: getAllBoxList(playerId, boxGachaId, boxGachaData.boxes) };
        });
        if (resetResult.allBoxInfo === null)
            return reply.status(resetResult.errorMessage === "Failed to reset box." ? 500 : 400).send({
                "error": resetResult.errorMessage === "Failed to reset box." ? "Internal Server Error" : "Bad Request",
                "message": resetResult.errorMessage,
            });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": {
                "all_box_info": resetResult.allBoxInfo
            }
        });
    }));
    fastify.post("/close", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        const boxGachaId = body.box_gacha_id;
        const boxId = body.box_id;
        if (isNaN(viewerId) || isNaN(boxGachaId) || isNaN(boxId))
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
        // get box asset data.
        const boxGachaData = (0, assets_1.getBoxGachaSync)(boxGachaId);
        if (boxGachaData === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid box gacha id."
            });
        const closeResult = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "gacha", playerId, operation: "box_close",
        }, () => {
            const playerBoxData = (0, boxGacha_1.getPlayerBoxGachaSync)(playerId, boxGachaId, boxId);
            if (playerBoxData === null)
                return { allBoxInfo: null, errorMessage: "Box doesn't exist" };
            if (playerBoxData.isClosed)
                return { allBoxInfo: null, errorMessage: "Box is already closed." };
            (0, boxGacha_1.updatePlayerBoxGachaSync)(playerId, boxGachaId, { boxId, isClosed: true });
            return { allBoxInfo: getAllBoxList(playerId, boxGachaId, boxGachaData.boxes) };
        });
        if (closeResult.allBoxInfo === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": closeResult.errorMessage,
            });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": {
                "all_box_info": closeResult.allBoxInfo
            }
        });
    }));
    fastify.post("/exec", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k;
        const body = request.body;
        const viewerId = body.viewer_id;
        const boxGachaId = body.box_gacha_id;
        const boxId = body.box_id;
        const pullCount = body.number;
        const stopOnFeaturedRewards = body.stop_on_featured_rewards;
        console.log(`[BOX] exec: boxGachaId=${boxGachaId} boxId=${boxId} pullCount=${pullCount}`);
        if (isNaN(viewerId) || isNaN(boxGachaId) || isNaN(boxId) || isNaN(pullCount) || stopOnFeaturedRewards === undefined)
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
        const player = playerId !== null ? (0, player_1.getPlayerSync)(playerId) : null;
        if (player === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        // get box gacha data
        const boxGachaData = (0, assets_1.getBoxGachaSync)(boxGachaId);
        if (boxGachaData === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid box gacha id."
            });
        // make sure the player has enough currency
        const pullCurrencyId = boxGachaData.redeemItemId;
        const playerPullCurrency = (0, item_1.getPlayerItemSync)(playerId, pullCurrencyId);
        if (playerPullCurrency === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "No pull currency."
            });
        const maximumPullCost = Math.abs(pullCount) * boxGachaData.redeemItemCount;
        if (playerPullCurrency < maximumPullCost)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Not enough pull currency."
            });
        // get the current box
        const boxRewards = boxGachaData.boxes[boxId];
        if (boxRewards === undefined)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid box ID."
            });
        const playerDrawnRewards = (0, boxGacha_1.getPlayerBoxGachaDrawnRewardsSync)(playerId, boxGachaId, boxId);
        const playerBoxData = reconcileExpandedEmptyBox(playerId, boxGachaId, boxId, boxRewards, playerDrawnRewards, (0, boxGacha_1.getPlayerBoxGachaSync)(playerId, boxGachaId, boxId));
        if (playerBoxData !== null && playerBoxData.isClosed)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Box is closed."
            });
        const settlement = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "gacha", playerId, operation: "box_exec",
        }, () => {
            var _a;
            const currentDrawnRewards = (0, boxGacha_1.getPlayerBoxGachaDrawnRewardsSync)(playerId, boxGachaId, boxId);
            const currentBoxData = reconcileExpandedEmptyBox(playerId, boxGachaId, boxId, boxRewards, currentDrawnRewards, (0, boxGacha_1.getPlayerBoxGachaSync)(playerId, boxGachaId, boxId));
            if (currentBoxData === null || currentBoxData === void 0 ? void 0 : currentBoxData.isClosed)
                throw new Error("Box is closed.");
            const currentCurrency = (0, item_1.getPlayerItemSync)(playerId, pullCurrencyId);
            if (currentCurrency === null)
                throw new Error("No pull currency.");
            const drawResult = (0, gacha_1.drawBoxGachaSync)(boxRewards, currentDrawnRewards, pullCount, stopOnFeaturedRewards);
            const actualPullCost = drawResult.drawCount * boxGachaData.redeemItemCount;
            const newPullCurrency = currentCurrency - actualPullCost;
            if (newPullCurrency < 0)
                throw new Error("Not enough pull currency.");
            console.log(`[BOX] exec result: boxGachaId=${boxGachaId} boxId=${boxId} requested=${pullCount} actual=${drawResult.drawCount} cost=${actualPullCost} stopOnFeatured=${stopOnFeaturedRewards}`);
            const rewardResult = (0, gacha_1.rewardPlayerBoxGachaResultSync)(playerId, drawResult);
            const playerDrawnRewardMap = new Map(currentDrawnRewards.map(reward => [reward.id, reward.number]));
            const totalDrawCount = currentDrawnRewards.reduce((total, reward) => total + reward.number, 0)
                + drawResult.rewards.reduce((total, reward) => total + reward.number, 0);
            const remainingDrawsNumber = ((_a = boxGachaData.availableCounts[boxId]) !== null && _a !== void 0 ? _a : totalDrawCount) - totalDrawCount;
            const shouldClose = remainingDrawsNumber === 0;
            if (currentBoxData === null) {
                (0, boxGacha_1.insertPlayerBoxGachaSync)(playerId, boxGachaId, {
                    boxId, isClosed: shouldClose, remainingNumber: remainingDrawsNumber, resetTimes: 0,
                });
            }
            else {
                (0, boxGacha_1.updatePlayerBoxGachaSync)(playerId, boxGachaId, {
                    boxId, isClosed: shouldClose, remainingNumber: remainingDrawsNumber,
                });
            }
            for (const drawnReward of drawResult.rewards) {
                const existing = playerDrawnRewardMap.get(drawnReward.id);
                if (existing === undefined) {
                    (0, boxGacha_1.insertPlayerBoxGachaDrawnRewardSync)(playerId, boxGachaId, boxId, {
                        id: drawnReward.id, number: drawnReward.number,
                    });
                }
                else {
                    (0, boxGacha_1.updatePlayerBoxGachaDrawnRewardSync)(playerId, boxGachaId, boxId, drawnReward.id, existing + drawnReward.number);
                }
            }
            (0, item_1.updatePlayerItemSync)(playerId, pullCurrencyId, newPullCurrency);
            return {
                drawResult, rewardResult, newPullCurrency,
                playerBoxData: currentBoxData !== null && currentBoxData !== void 0 ? currentBoxData : {
                    boxId, resetTimes: 0, remainingNumber: remainingDrawsNumber, isClosed: shouldClose,
                },
                currentDrawnRewards,
            };
        });
        const { drawResult, rewardResult, newPullCurrency, currentDrawnRewards } = settlement;
        const drawnRewards = drawResult.rewards;
        const allDrawResultMap = new Map();
        let totalDrawCount = 0;
        for (const drawnReward of drawnRewards) {
            totalDrawCount += drawnReward.number;
            allDrawResultMap.set(drawnReward.id, drawnReward.number);
        }
        for (const playerDrawnReward of currentDrawnRewards) {
            totalDrawCount += playerDrawnReward.number;
            allDrawResultMap.set(playerDrawnReward.id, ((_a = allDrawResultMap.get(playerDrawnReward.id)) !== null && _a !== void 0 ? _a : 0) + playerDrawnReward.number);
        }
        const remainingDrawsNumber = ((_b = boxGachaData.availableCounts[boxId]) !== null && _b !== void 0 ? _b : totalDrawCount) - totalDrawCount;
        const shouldClose = remainingDrawsNumber === 0;
        const responsePlayerBoxData = settlement.playerBoxData;
        // generate totalDrawnRewards array
        const allBoxInfo = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "gacha", playerId, operation: "box_response_reconcile",
        }, () => getAllBoxList(playerId, boxGachaId, boxGachaData.boxes, boxId));
        // add current box to allBoxInfo
        {
            // build all drawn reward list
            const allDrawnRewardList = [];
            for (const [rewardId, number] of allDrawResultMap) {
                allDrawnRewardList.push({
                    "reward_id": rewardId,
                    "number": number
                });
            }
            allBoxInfo.push({
                "box_id": boxId,
                "reset_times": (_c = responsePlayerBoxData === null || responsePlayerBoxData === void 0 ? void 0 : responsePlayerBoxData.resetTimes) !== null && _c !== void 0 ? _c : 0,
                "all_drawn_reward_list": allDrawnRewardList,
                "coming_next_reward_list": [],
                "is_closed": shouldClose ? true : (_d = responsePlayerBoxData === null || responsePlayerBoxData === void 0 ? void 0 : responsePlayerBoxData.isClosed) !== null && _d !== void 0 ? _d : false
            });
        }
        const existingCharacterList = ((_e = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.character_list) !== null && _e !== void 0 ? _e : []);
        const characterList = drawnRewards.length > 0
            ? (0, mission_1.reconcileAwakeUnlockCharacterList)(playerId, existingCharacterList)
            : existingCharacterList;
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": {
                "user_info": {
                    "free_mana": player.freeMana + ((_f = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.user_info.free_mana) !== null && _f !== void 0 ? _f : 0),
                    "exp_pool": player.expPool + ((_g = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.user_info.exp_pool) !== null && _g !== void 0 ? _g : 0),
                    "exp_pooled_time": (0, utils_1.getServerTime)(player.expPooledTime),
                },
                "drawn_reward_list": drawnRewards.map(reward => {
                    return {
                        "reward_id": reward.id,
                        "number": reward.number
                    };
                }),
                "all_box_info": allBoxInfo,
                "joined_character_id_list": (_h = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.joined_character_id_list) !== null && _h !== void 0 ? _h : [],
                "character_list": characterList,
                "equipment_list": (_j = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.equipment_list) !== null && _j !== void 0 ? _j : [],
                "item_list": Object.assign({ [pullCurrencyId]: newPullCurrency }, ((_k = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.items) !== null && _k !== void 0 ? _k : {})),
                "mail_arrived": false
            }
        });
    }));
    fastify.post("/get_box_list", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        const boxGachaId = body.box_gacha_id;
        console.log(`[BOX] get_box_list: boxGachaId=${boxGachaId}`);
        if (isNaN(viewerId) || isNaN(boxGachaId))
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
        const player = playerId !== null ? (0, player_1.getPlayerSync)(playerId) : null;
        if (player === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        // get box gacha data
        const boxGachaData = (0, assets_1.getBoxGachaSync)(boxGachaId);
        if (boxGachaData === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid box gacha id."
            });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": {
                "all_box_info": getAllBoxList(playerId, boxGachaId, boxGachaData.boxes)
            }
        });
    }));
});
exports.default = routes;
