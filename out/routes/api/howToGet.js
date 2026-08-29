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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const session_1 = require("../../data/domains/session");
const activeAccount_1 = require("../../data/activeAccount");
const utils_1 = require("../../utils");
const shopPurchase_1 = require("../../data/domains/shopPurchase");
const assets_1 = require("../../lib/assets");
const types_1 = require("../../lib/types");
const box_reward_json_1 = __importDefault(require("../../../assets/box_reward.json"));
const content_master_1 = require("../../lib/content-master");
const boss_coin_shop_json_1 = __importDefault(require("../../../assets/boss_coin_shop.json"));
function itemRewardContainsItemId(item, targetItemId, rewardTypes) {
    for (const reward of item.rewards) {
        if (rewardTypes.includes(reward.type)) {
            const itemReward = reward;
            if (itemReward.id === targetItemId) {
                return true;
            }
        }
    }
    return false;
}
function findBoxGachaIdsForItem(targetItemId, rewardTypes) {
    const result = [];
    for (const [boxGachaId, stages] of Object.entries(box_reward_json_1.default)) {
        for (const stage of Object.values(stages)) {
            for (const reward of Object.values(stage)) {
                const rewardObj = reward;
                if (rewardTypes.includes(rewardObj.type) && rewardObj.id === targetItemId) {
                    result.push(Number(boxGachaId));
                    break;
                }
            }
        }
    }
    return [...new Set(result)];
}
function buildEnhancementSalesList(playerId, items, targetItemId, rewardTypes) {
    var _a, _b, _c, _d, _e, _f, _g;
    if (Object.keys(items).length === 0)
        return [];
    const groups = new Map();
    for (const [itemId, item] of Object.entries(items)) {
        if (!itemRewardContainsItemId(item, targetItemId, rewardTypes))
            continue;
        const gid = (_a = item.groupId) !== null && _a !== void 0 ? _a : 0;
        if (!groups.has(gid)) {
            groups.set(gid, {
                groupId: gid,
                items: [],
                equipmentId: (_b = item.equipmentId) !== null && _b !== void 0 ? _b : 0
            });
        }
        groups.get(gid).items.push({ id: itemId, item, stage: (_c = item.stage) !== null && _c !== void 0 ? _c : 0 });
    }
    const result = [];
    const purchasedMap = (0, shopPurchase_1.getPlayerShopPurchasesMapSync)(playerId);
    for (const [, group] of groups) {
        group.items.sort((a, b) => a.stage - b.stage);
        const enhancementLevel = 0;
        let targetItem = group.items[0];
        let stockQuantity = (_d = targetItem.item.enhancementMaxLevel) !== null && _d !== void 0 ? _d : 0;
        let totalPurchaseNum = 0;
        for (const entry of group.items) {
            const maxLv = (_e = entry.item.enhancementMaxLevel) !== null && _e !== void 0 ? _e : 0;
            if (maxLv > enhancementLevel) {
                targetItem = entry;
                stockQuantity = maxLv - enhancementLevel;
                break;
            }
        }
        totalPurchaseNum = enhancementLevel;
        const maxLevel = (_f = group.items[group.items.length - 1].item.enhancementMaxLevel) !== null && _f !== void 0 ? _f : 0;
        result.push({
            "shop_item_id": Number(targetItem.id),
            "stock_quantity": stockQuantity,
            "today_purchase_num": (_g = purchasedMap[Number(targetItem.id)]) !== null && _g !== void 0 ? _g : 0,
            "this_month_purchase_num": null,
            "total_purchase_num": totalPurchaseNum,
            "group_info": {
                "group_total_stock_quantity": maxLevel - totalPurchaseNum,
                "group_total_purchase_num": totalPurchaseNum,
                "multi_stage": group.items.length > 1
            },
            "shop_type": types_1.ShopType.TREASURE_EQUIPMENT
        });
    }
    return result;
}
function addShopSalesItem(shopSalesList, itemId, item, shopType, purchasedMap) {
    var _a;
    const purchased = (_a = purchasedMap[Number(itemId)]) !== null && _a !== void 0 ? _a : 0;
    const stockQuantity = item.stock !== undefined ? Math.max(0, item.stock - purchased) : -1;
    const entry = {
        "shop_item_id": Number(itemId),
        "stock_quantity": stockQuantity,
        "today_purchase_num": purchased,
        "this_month_purchase_num": purchased,
        "total_purchase_num": purchased,
        "shop_type": shopType
    };
    if (shopType === types_1.ShopType.STAR_GRAIN || shopType === types_1.ShopType.TREASURE ||
        shopType === types_1.ShopType.GENERAL || shopType === types_1.ShopType.EVENT_ITEM || shopType === types_1.ShopType.BOSS_COIN) {
        entry["group_info"] = {
            "group_total_stock_quantity": stockQuantity,
            "group_total_purchase_num": purchased,
            "multi_stage": false
        };
    }
    shopSalesList.push(entry);
}
function buildEmptyResponse(reply, viewerId) {
    reply.header("content-type", "application/x-msgpack");
    return reply.status(200).send({
        "data_headers": {
            "force_update": false,
            "asset_update": false,
            "short_udid": 0,
            "viewer_id": viewerId,
            "servertime": (0, utils_1.getServerTime)(),
            "result_code": 1
        },
        "data": {
            "box_gacha_id_list": [],
            "unselected_lineup_shop_sales_list": [],
            "shop_sales_list": []
        }
    });
}
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/get_list", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a;
        const body = request.body;
        const viewerId = body === null || body === void 0 ? void 0 : body.viewer_id;
        const isEquipment = !!(body === null || body === void 0 ? void 0 : body.equipment_id);
        const targetItemId = (_a = body === null || body === void 0 ? void 0 : body.equipment_id) !== null && _a !== void 0 ? _a : body === null || body === void 0 ? void 0 : body.item_id;
        const rewardTypes = isEquipment
            ? [types_1.ShopItemRewardType.EQUIPMENT]
            : [types_1.ShopItemRewardType.ITEM];
        const boxRewardTypes = isEquipment
            ? [4]
            : [1];
        if (!viewerId || isNaN(viewerId) || !targetItemId || isNaN(targetItemId)) {
            return buildEmptyResponse(reply, viewerId !== null && viewerId !== void 0 ? viewerId : 0);
        }
        const viewerIdSession = yield (0, session_1.getSession)(viewerId.toString());
        if (!viewerIdSession) {
            return buildEmptyResponse(reply, viewerId);
        }
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(viewerIdSession.accountId);
        if (playerId === null) {
            return buildEmptyResponse(reply, viewerId);
        }
        const purchasedMap = (0, shopPurchase_1.getPlayerShopPurchasesMapSync)(playerId);
        const shopSalesList = [];
        const enhancementItems = {};
        for (const shopType of [types_1.ShopType.GENERAL, types_1.ShopType.STAR_GRAIN, types_1.ShopType.TREASURE_EQUIPMENT, types_1.ShopType.TREASURE]) {
            const items = (0, assets_1.getGenericShopItemsSync)(shopType);
            if (!items)
                continue;
            for (const [itemId, item] of Object.entries(items)) {
                if (!itemRewardContainsItemId(item, targetItemId, rewardTypes))
                    continue;
                if (shopType === types_1.ShopType.TREASURE_EQUIPMENT) {
                    enhancementItems[itemId] = item;
                }
                else {
                    addShopSalesItem(shopSalesList, itemId, item, shopType, purchasedMap);
                }
            }
        }
        for (const events of Object.values(content_master_1.serverEventShops)) {
            for (const items of Object.values(events)) {
                for (const [itemId, item] of Object.entries(items)) {
                    if (itemRewardContainsItemId(item, targetItemId, rewardTypes)) {
                        addShopSalesItem(shopSalesList, itemId, item, types_1.ShopType.EVENT_ITEM, purchasedMap);
                    }
                }
            }
        }
        for (const items of Object.values(boss_coin_shop_json_1.default)) {
            for (const [itemId, item] of Object.entries(items)) {
                if (itemRewardContainsItemId(item, targetItemId, rewardTypes)) {
                    addShopSalesItem(shopSalesList, itemId, item, types_1.ShopType.BOSS_COIN, purchasedMap);
                }
            }
        }
        shopSalesList.push(...buildEnhancementSalesList(playerId, enhancementItems, targetItemId, rewardTypes));
        const boxGachaIds = findBoxGachaIdsForItem(targetItemId, boxRewardTypes);
        if (shopSalesList.length === 0 && boxGachaIds.length === 0) {
            return buildEmptyResponse(reply, viewerId);
        }
        reply.header("content-type", "application/x-msgpack");
        reply.status(200).send({
            "data_headers": {
                "force_update": false,
                "asset_update": false,
                "short_udid": 0,
                "viewer_id": viewerId,
                "servertime": (0, utils_1.getServerTime)(),
                "result_code": 1
            },
            "data": {
                "box_gacha_id_list": boxGachaIds,
                "unselected_lineup_shop_sales_list": [],
                "shop_sales_list": shopSalesList
            }
        });
    }));
});
exports.default = routes;
