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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const active_mission_counters_1 = require("../../data/domains/active_mission_counters");
const shopPurchase_1 = require("../../data/domains/shopPurchase");
const equipment_1 = require("../../data/domains/equipment");
const item_1 = require("../../data/domains/item");
const player_1 = require("../../data/domains/player");
const degree_1 = require("../../data/domains/degree");
const session_1 = require("../../data/domains/session");
const activeAccount_1 = require("../../data/activeAccount");
const db_1 = require("../../data/db");
const assets_1 = require("../../lib/assets");
const types_1 = require("../../lib/types");
const utils_1 = require("../../utils");
const quest_1 = require("../../lib/quest");
const stamina_1 = require("../../lib/stamina");
const equipment_2 = require("../../lib/equipment");
const equipment_enhancement_1 = require("../../lib/equipment-enhancement");
const cdn_general_shop_whitelist_json_1 = __importDefault(require("../../../assets/cdn_general_shop_whitelist.json"));
const game_logging_1 = require("../../lib/game-logging");
const mission_1 = require("../../lib/mission");
const mission_2 = require("../../lib/mission");
const counters_1 = require("../../lib/mission/counters");
const free_first_deduction_1 = require("../../lib/free-first-deduction");
const GENERAL_SHOP_CDN_KEYS = new Set(cdn_general_shop_whitelist_json_1.default);
function isShopItemAvailable(item, now) {
    var _a;
    const periods = [{
            availableFrom: item.availableFrom,
            availableUntil: item.availableUntil,
        }, ...((_a = item.compatibilityPeriods) !== null && _a !== void 0 ? _a : [])];
    return periods.some(period => {
        if (period.availableFrom) {
            const availableFrom = new Date(period.availableFrom.replace(' ', 'T') + 'Z');
            if (availableFrom > now)
                return false;
        }
        if (period.availableUntil) {
            const availableUntil = new Date(period.availableUntil.replace(' ', 'T') + 'Z');
            if (availableUntil < now)
                return false;
        }
        return true;
    });
}
function recordTreasureShopProgress(playerId, shopType, purchaseCount, manaSpent) {
    if (shopType !== types_1.ShopType.TREASURE)
        return;
    if (purchaseCount > 0) {
        (0, counters_1.addMissionCounterSync)(playerId, {
            dimension: "shop.treasure_purchase",
            scopeType: "lifetime",
            scopeKey: "all",
            qualifier: {},
        }, purchaseCount);
    }
    if (manaSpent > 0) {
        (0, counters_1.addMissionCounterSync)(playerId, {
            dimension: "shop.treasure_mana_spent",
            scopeType: "lifetime",
            scopeKey: "all",
            qualifier: {},
        }, manaSpent);
    }
}
function mergeShopDegreeSettlement(responseData, playerId, viewerId) {
    (0, mission_2.mergeMissionSettlementResponse)(responseData, (0, mission_2.settleMissionCategories)(playerId, [{
            category: 5,
            missionIds: (0, mission_2.getDegreeMissionIdsForConditionTypes)([3, 45]),
        }], new Date((0, utils_1.getServerTime)() * 1000)), viewerId);
}
// These one-time GENERAL products reuse shop_item_id values from STAR_GRAIN.
// The legacy table is keyed only by (player_id, shop_item_id), so store these
// purchases under private negative keys. Equipment ownership cannot be used as
// a substitute because the same equipment may have been granted elsewhere.
const GENERAL_EQUIPMENT_SCOPED_PURCHASE_KEYS = new Map([
    [100008, -8100008], // 酒神权杖
    [110005, -8110005], // 埃癸斯·日华
    [110006, -8110006], // 埃癸斯·幽冥
]);
// Fantasy Rush exposes the same twelve products through its Rush (solo) and
// Advent (multiplayer) screens.  The client requires different shop_item_id
// rows for those two event families, but the inventory is one-time and shared.
// Store each pair under one private key so either screen immediately reflects
// a purchase made in the other screen.
const MODE15_SHARED_EVENT_PURCHASE_KEYS = new Map(Array.from({ length: 12 }, (_, index) => {
    const sharedKey = -9702001 - index;
    return [
        [9700201 + index, sharedKey],
        [9700301 + index, sharedKey],
    ];
}).flat());
function getEffectiveShopPurchaseCountSync(playerId, shopType, shopItemId) {
    if (shopType === types_1.ShopType.EVENT_ITEM) {
        const sharedPurchaseKey = MODE15_SHARED_EVENT_PURCHASE_KEYS.get(shopItemId);
        if (sharedPurchaseKey !== undefined) {
            return (0, shopPurchase_1.getPlayerShopPurchaseCountSync)(playerId, sharedPurchaseKey);
        }
    }
    if (shopType === types_1.ShopType.GENERAL) {
        const scopedPurchaseKey = GENERAL_EQUIPMENT_SCOPED_PURCHASE_KEYS.get(shopItemId);
        if (scopedPurchaseKey !== undefined) {
            return (0, shopPurchase_1.getPlayerShopPurchaseCountSync)(playerId, scopedPurchaseKey);
        }
    }
    return (0, shopPurchase_1.getPlayerShopPurchaseCountSync)(playerId, shopItemId);
}
function addEffectiveShopPurchaseCountSync(playerId, shopType, shopItemId, count) {
    if (shopType === types_1.ShopType.EVENT_ITEM) {
        const sharedPurchaseKey = MODE15_SHARED_EVENT_PURCHASE_KEYS.get(shopItemId);
        if (sharedPurchaseKey !== undefined) {
            return (0, shopPurchase_1.addPlayerShopPurchaseCountSync)(playerId, sharedPurchaseKey, count);
        }
    }
    if (shopType === types_1.ShopType.GENERAL &&
        GENERAL_EQUIPMENT_SCOPED_PURCHASE_KEYS.has(shopItemId)) {
        return (0, shopPurchase_1.addPlayerShopPurchaseCountSync)(playerId, GENERAL_EQUIPMENT_SCOPED_PURCHASE_KEYS.get(shopItemId), count);
    }
    return (0, shopPurchase_1.addPlayerShopPurchaseCountSync)(playerId, shopItemId, count);
}
// Item 5000 originally shipped with max_frequency=2 in the 1.4.57 client
// master. The server-side stock was later expanded to 999. Keep cached legacy
// clients usable by offsetting only the client-facing lifetime counter; the
// authoritative purchased count and stock validation remain unchanged.
const LEGACY_CLIENT_MAX_FREQUENCY = new Map([
    [5000, 2],
]);
function getClientTotalPurchaseNum(shopType, itemId, purchased, stock) {
    if (shopType !== types_1.ShopType.EVENT_ITEM)
        return purchased;
    const legacyLimit = LEGACY_CLIENT_MAX_FREQUENCY.get(itemId);
    if (legacyLimit === undefined || stock === undefined || stock <= legacyLimit)
        return purchased;
    return purchased - (stock - legacyLimit);
}
function buildEnhancementSalesList(playerId, items) {
    var _a, _b, _c, _d, _e, _f, _g, _h;
    if (Object.keys(items).length === 0)
        return [];
    // Group items by groupId
    const groups = new Map();
    for (const [itemId, item] of Object.entries(items)) {
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
    for (const [, group] of groups) {
        // Sort by stage ascending
        group.items.sort((a, b) => a.stage - b.stage);
        const equipmentId = group.equipmentId;
        const enhancementLevel = (0, equipment_1.playerOwnsEquipmentSync)(playerId, equipmentId)
            ? ((_e = (_d = (0, equipment_1.getPlayerEquipmentSync)(playerId, equipmentId)) === null || _d === void 0 ? void 0 : _d.enhancementLevel) !== null && _e !== void 0 ? _e : 0)
            : -1;
        // Find target product: first item with enhancementMaxLevel > current enhancementLevel
        let targetItem = null;
        let stockQuantity = 0;
        let totalPurchaseNum = 0;
        if (enhancementLevel < 0) {
            // Player doesn't have the equipment
            targetItem = group.items[0];
            stockQuantity = (_f = targetItem.item.enhancementMaxLevel) !== null && _f !== void 0 ? _f : 0;
            totalPurchaseNum = 0;
        }
        else {
            for (const entry of group.items) {
                const maxLv = (_g = entry.item.enhancementMaxLevel) !== null && _g !== void 0 ? _g : 0;
                if (maxLv > enhancementLevel) {
                    targetItem = entry;
                    stockQuantity = maxLv - enhancementLevel;
                    break;
                }
            }
            // If no target found (fully maxed), use last item with stock_quantity=0
            if (!targetItem) {
                targetItem = group.items[group.items.length - 1];
                stockQuantity = 0;
            }
            totalPurchaseNum = enhancementLevel;
        }
        // Group info: max level from last item in group
        const maxLevel = (_h = group.items[group.items.length - 1].item.enhancementMaxLevel) !== null && _h !== void 0 ? _h : 0;
        const multiStage = group.items.length > 1;
        result.push({
            "shop_item_id": Number(targetItem.id),
            "stock_quantity": stockQuantity,
            "today_purchase_num": 0,
            "this_month_purchase_num": null, // null → MsgPack nil / Option.None
            "total_purchase_num": totalPurchaseNum,
            "discount_id": null,
            "discount_rate": null,
            "discounted_price": null,
            "group_info": {
                "group_total_stock_quantity": maxLevel - totalPurchaseNum,
                "group_total_purchase_num": totalPurchaseNum,
                "multi_stage": multiStage
            },
            "shop_type": types_1.ShopType.TREASURE_EQUIPMENT
        });
    }
    return result;
}
function getShopDegreeRewards(shopItem, purchaseAmount) {
    const degreeIds = [];
    for (const reward of shopItem.rewards) {
        if (reward.type !== types_1.ShopItemRewardType.DEGREE)
            continue;
        const degree = reward;
        if (purchaseAmount !== 1
            || degree.count !== 1
            || !Number.isSafeInteger(degree.id)
            || degree.id <= 0)
            throw new Error("Degree shop rewards must grant one title in one purchase.");
        degreeIds.push(degree.id);
    }
    return degreeIds;
}
function appendShopItemRewards(rewards, shopItem, purchaseAmount) {
    for (const reward of shopItem.rewards) {
        switch (reward.type) {
            case types_1.ShopItemRewardType.ITEM: {
                const shopReward = reward;
                rewards.push({
                    name: "",
                    type: types_1.RewardType.ITEM,
                    id: shopReward.id,
                    count: shopReward.count * purchaseAmount
                });
                break;
            }
            case types_1.ShopItemRewardType.EXP: {
                const shopReward = reward;
                rewards.push({
                    name: "",
                    type: types_1.RewardType.EXP,
                    count: shopReward.count * purchaseAmount
                });
                break;
            }
            case types_1.ShopItemRewardType.MANA: {
                const shopReward = reward;
                rewards.push({
                    name: "",
                    type: types_1.RewardType.MANA,
                    count: shopReward.count * purchaseAmount
                });
                break;
            }
            case types_1.ShopItemRewardType.CHARACTER: {
                const shopReward = reward;
                for (let i = 0; i < purchaseAmount; i++) {
                    rewards.push({
                        name: "",
                        type: types_1.RewardType.CHARACTER,
                        id: shopReward.id
                    });
                }
                break;
            }
            case types_1.ShopItemRewardType.EQUIPMENT: {
                const shopReward = reward;
                rewards.push({
                    name: "",
                    type: types_1.RewardType.EQUIPMENT,
                    id: shopReward.id,
                    count: shopReward.count * purchaseAmount
                });
                break;
            }
        }
    }
}
function mergeCountedRewards(rewards) {
    const counted = new Map();
    const uncounted = [];
    for (const reward of rewards) {
        switch (reward.type) {
            case types_1.RewardType.ITEM:
            case types_1.RewardType.EQUIPMENT: {
                const value = reward;
                const key = `${value.type}:${value.id}`;
                const existing = counted.get(key);
                if (existing) {
                    existing.count += value.count;
                }
                else {
                    counted.set(key, Object.assign({}, value));
                }
                break;
            }
            case types_1.RewardType.BEADS:
            case types_1.RewardType.MANA:
            case types_1.RewardType.EXP: {
                const value = reward;
                const key = String(value.type);
                const existing = counted.get(key);
                if (existing) {
                    existing.count += value.count;
                }
                else {
                    counted.set(key, Object.assign({}, value));
                }
                break;
            }
            default:
                uncounted.push(reward);
        }
    }
    return [...counted.values(), ...uncounted];
}
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/buy", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a, _b, _c, _d, _e, _f;
        const body = request.body;
        const viewerId = body.viewer_id;
        const shopType = body.shop_type;
        const rawPurchaseAmount = body.number;
        const shopItemId = body.shop_item_id;
        if (isNaN(viewerId) || isNaN(shopType) || isNaN(rawPurchaseAmount) || isNaN(shopItemId))
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            });
        const purchaseAmount = Math.max(1, rawPurchaseAmount);
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
        // get the shop item's data
        const shopItemData = (0, assets_1.getShopItemSync)(shopType, shopItemId);
        if (shopItemData === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Shop item with specified id does not exist."
            });
        // Event products may still be present in a stale client cache after
        // their exchange window closes. The listing filter is not a security
        // boundary, so enforce the same period again before any costs change.
        if (shopType === types_1.ShopType.EVENT_ITEM && !isShopItemAvailable(shopItemData, (0, utils_1.getServerDate)())) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Event shop item is not currently available."
            });
        }
        let degreeIds;
        try {
            degreeIds = getShopDegreeRewards(shopItemData, purchaseAmount);
        }
        catch (error) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": error instanceof Error ? error.message : "Invalid degree reward."
            });
        }
        if (degreeIds.some(degreeId => (0, degree_1.hasPlayerDegreeSync)(playerId, degreeId))) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Player already owns this degree."
            });
        }
        // validate stock limit
        if (shopItemData.stock !== undefined && shopItemData.stock > 0) {
            const purchased = getEffectiveShopPurchaseCountSync(playerId, shopType, shopItemId);
            if (purchased + purchaseAmount > shopItemData.stock) {
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Shop item purchase limit reached."
                });
            }
        }
        let enhancementPurchase = null;
        if (shopType === types_1.ShopType.TREASURE_EQUIPMENT) {
            const now = (0, utils_1.getServerDate)();
            if (!isShopItemAvailable(shopItemData, now))
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Enhancement item is not currently available."
                });
            const equipmentId = shopItemData.equipmentId;
            const stageMaxLevel = shopItemData.enhancementMaxLevel;
            const requiredAwakeningLevel = shopItemData.requireAwakeningLevel;
            const shopCategoryId = shopItemData.shopCategoryId;
            const groupId = shopItemData.groupId;
            if (equipmentId === undefined
                || stageMaxLevel === undefined
                || requiredAwakeningLevel === undefined
                || shopCategoryId === undefined
                || groupId === undefined)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Enhancement item is missing progression data."
                });
            const currentEquipment = (0, equipment_1.getPlayerEquipmentSync)(playerId, equipmentId);
            if (currentEquipment === null)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Player does not own the target equipment."
                });
            const stages = Object.entries((_a = (0, assets_1.getGenericShopItemsSync)(types_1.ShopType.TREASURE_EQUIPMENT)) !== null && _a !== void 0 ? _a : {})
                .filter(([, item]) => isShopItemAvailable(item, now))
                .flatMap(([id, item]) => {
                if (item.shopCategoryId === undefined
                    || item.groupId === undefined
                    || item.equipmentId === undefined
                    || item.stage === undefined
                    || item.enhancementMaxLevel === undefined)
                    return [];
                return [{
                        shopItemId: Number(id),
                        shopCategoryId: item.shopCategoryId,
                        groupId: item.groupId,
                        equipmentId: item.equipmentId,
                        stage: item.stage,
                        maxLevel: item.enhancementMaxLevel,
                    }];
            });
            const currentStage = (0, equipment_enhancement_1.findCurrentEquipmentEnhancementStage)(stages, {
                shopCategoryId,
                groupId,
                equipmentId,
                currentLevel: currentEquipment.enhancementLevel,
            });
            if (currentStage === null || currentStage.shopItemId !== shopItemId) {
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Enhancement item is not the current stage."
                });
            }
            const plan = (0, equipment_enhancement_1.planEquipmentEnhancementPurchase)(currentEquipment.enhancementLevel, rawPurchaseAmount, stageMaxLevel, currentEquipment.level, requiredAwakeningLevel, shopItemData.enhancementPurchaseMode);
            if (!plan.ok)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": plan.message
                });
            enhancementPurchase = {
                equipmentId,
                newLevel: plan.newLevel,
                chargedPurchaseAmount: plan.chargedPurchaseAmount,
                grantedLevelCount: plan.grantedLevelCount,
            };
        }
        const chargedPurchaseAmount = (_b = enhancementPurchase === null || enhancementPurchase === void 0 ? void 0 : enhancementPurchase.chargedPurchaseAmount) !== null && _b !== void 0 ? _b : purchaseAmount;
        (0, game_logging_1.gameVerboseLog)(() => `[shop:buy] player=${playerId} shopType=${shopType} item=${shopItemId} ` +
            `requested=${purchaseAmount} charged=${chargedPurchaseAmount} ` +
            `before freeMana=${player.freeMana} paidMana=${player.paidMana} ` +
            `freeVmoney=${player.freeVmoney} vmoney=${player.vmoney}`);
        // keep track of various stats
        const itemList = {};
        let freeVmoney = player.freeVmoney;
        let vmoney = player.vmoney;
        let freeMana = player.freeMana;
        let paidMana = player.paidMana;
        let bondTokens = player.bondToken;
        // verify user costs
        const userCost = shopItemData.userCost;
        if (userCost !== undefined) {
            const totalCost = userCost.amount * chargedPurchaseAmount;
            switch (userCost.type) {
                case types_1.ShopItemUserCostType.MANA: {
                    const deduction = (0, free_first_deduction_1.computeFreeFirstDeduction)(freeMana, paidMana, totalCost);
                    if (deduction === null)
                        return reply.status(400).send({
                            "error": "Bad Request",
                            "message": `Not enough mana to purchase shop item.`
                        });
                    freeMana = deduction.freeBalance;
                    paidMana = deduction.paidBalance;
                    break;
                }
                case types_1.ShopItemUserCostType.BEADS: {
                    const deduction = (0, free_first_deduction_1.computeFreeFirstDeduction)(freeVmoney, vmoney, totalCost);
                    if (deduction === null)
                        return reply.status(400).send({
                            "error": "Bad Request",
                            "message": `Not enough beads to purchase shop item.`
                        });
                    freeVmoney = deduction.freeBalance;
                    vmoney = deduction.paidBalance;
                    break;
                }
                case types_1.ShopItemUserCostType.AMITY_SCROLL:
                    bondTokens -= totalCost;
            }
            if (0 > bondTokens)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": `Not enough amity scrolls to purchase shop item.`
                });
        }
        // verify cost items
        {
            for (const cost of shopItemData.costs) {
                const itemId = cost.id;
                const itemAmount = (_c = (0, item_1.getPlayerItemSync)(playerId, itemId)) !== null && _c !== void 0 ? _c : 0;
                const newItemAmount = itemAmount - (cost.amount * chargedPurchaseAmount);
                if (0 > newItemAmount)
                    return reply.status(400).send({
                        "error": "Bad Request",
                        "message": `Not enough of item with id ${itemId} to purchase shop item.`
                    });
                itemList[itemId] = newItemAmount;
            }
        }
        const manaSpent = Math.max(0, (player.freeMana + player.paidMana) - (freeMana + paidMana));
        const applyPurchaseCosts = () => {
            for (const [itemId, newAmount] of Object.entries(itemList)) {
                (0, item_1.updatePlayerItemSync)(playerId, itemId, newAmount);
            }
            (0, player_1.updatePlayerSync)({
                id: playerId,
                freeMana: freeMana,
                paidMana: paidMana,
                freeVmoney: freeVmoney,
                vmoney: vmoney,
                bondToken: bondTokens
            });
            if (manaSpent > 0)
                (0, active_mission_counters_1.incrementActiveMissionUsedManaCountSync)(playerId, manaSpent);
        };
        // Equipment enhancement shop: update equipment enhancement level
        if (enhancementPurchase !== null) {
            const { equipmentId, newLevel, grantedLevelCount } = enhancementPurchase;
            (0, db_1.getDb)().transaction(() => {
                applyPurchaseCosts();
                (0, equipment_1.updatePlayerEquipmentSync)(playerId, equipmentId, { enhancementLevel: newLevel });
                addEffectiveShopPurchaseCountSync(playerId, shopType, shopItemId, chargedPurchaseAmount);
            })();
            const currentEquipment = (0, equipment_1.getPlayerEquipmentSync)(playerId, equipmentId);
            (0, game_logging_1.gameVerboseLog)(() => `[shop:enhancement-benefit] player=${playerId} equipment=${equipmentId} ` +
                `item=${shopItemId} grantedLevels=${grantedLevelCount} newLevel=${newLevel}`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({
                    viewer_id: viewerId
                }),
                "data": {
                    "user_info": {
                        "vmoney": vmoney,
                        "free_vmoney": freeVmoney,
                        "paid_mana": paidMana,
                        "free_mana": freeMana,
                        "bond_token": bondTokens
                    },
                    "character_list": [],
                    "equipment_list": [(0, equipment_2.clientSerializeEquipment)(equipmentId, currentEquipment)],
                    "item_list": itemList,
                    "mail_arrived": false
                }
            });
        }
        // build rewards array
        const rewards = [];
        for (const reward of shopItemData.rewards) {
            switch (reward.type) {
                case types_1.ShopItemRewardType.ITEM: {
                    const shopReward = reward;
                    rewards.push({
                        name: "",
                        type: types_1.RewardType.ITEM,
                        id: shopReward.id,
                        count: shopReward.count * purchaseAmount
                    });
                    break;
                }
                case types_1.ShopItemRewardType.EXP: {
                    const shopReward = reward;
                    rewards.push({
                        name: "",
                        type: types_1.RewardType.EXP,
                        count: shopReward.count * purchaseAmount
                    });
                    break;
                }
                case types_1.ShopItemRewardType.MANA: {
                    const shopReward = reward;
                    rewards.push({
                        name: "",
                        type: types_1.RewardType.MANA,
                        count: shopReward.count * purchaseAmount
                    });
                    break;
                }
                case types_1.ShopItemRewardType.CHARACTER: {
                    const shopReward = reward;
                    for (let i = 0; i < purchaseAmount; i++) {
                        rewards.push({
                            name: "",
                            type: types_1.RewardType.CHARACTER,
                            id: shopReward.id
                        });
                    }
                    break;
                }
                case types_1.ShopItemRewardType.EQUIPMENT: {
                    const shopReward = reward;
                    rewards.push({
                        name: "",
                        type: types_1.RewardType.EQUIPMENT,
                        id: shopReward.id,
                        count: shopReward.count * purchaseAmount
                    });
                    break;
                }
            }
        }
        // Costs, ordinary rewards, title ownership and stock history must commit
        // together. A title product must never charge the player and then fail
        // between the reward and ownership writes.
        const rewardResult = (0, db_1.getDb)().transaction(() => {
            applyPurchaseCosts();
            const result = (0, quest_1.givePlayerRewardsSync)(playerId, rewards);
            if (result === null)
                throw new Error("Failed to grant shop rewards.");
            for (const degreeId of degreeIds) {
                if (!(0, degree_1.grantPlayerDegreeSync)(playerId, degreeId)) {
                    throw new Error(`Degree ${degreeId} is already owned.`);
                }
            }
            addEffectiveShopPurchaseCountSync(playerId, shopType, shopItemId, purchaseAmount);
            return result;
        })();
        recordTreasureShopProgress(playerId, shopType, purchaseAmount, manaSpent);
        const characterList = (0, mission_1.reconcileAwakeUnlockCharacterList)(playerId, ((_d = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.character_list) !== null && _d !== void 0 ? _d : []));
        // verify DB write
        const afterPlayer = (0, player_1.getPlayerSync)(playerId);
        (0, game_logging_1.gameVerboseLog)(() => {
            var _a;
            return `[shop:buy] after DB freeMana=${afterPlayer.freeMana} paidMana=${afterPlayer.paidMana} ` +
                `freeVmoney=${afterPlayer.freeVmoney} vmoney=${afterPlayer.vmoney} ` +
                `rewardItems=${JSON.stringify((_a = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.items) !== null && _a !== void 0 ? _a : {})}`;
        });
        reply.header("content-type", "application/x-msgpack");
        const responseData = {
            "user_info": {
                "vmoney": afterPlayer.vmoney,
                "free_vmoney": afterPlayer.freeVmoney,
                "paid_mana": afterPlayer.paidMana,
                "free_mana": afterPlayer.freeMana,
                "bond_token": afterPlayer.bondToken,
                "exp_pool": afterPlayer.expPool,
            },
            "character_list": characterList,
            "equipment_list": (_e = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.equipment_list) !== null && _e !== void 0 ? _e : [],
            "item_list": Object.assign(Object.assign({}, itemList), ((_f = rewardResult === null || rewardResult === void 0 ? void 0 : rewardResult.items) !== null && _f !== void 0 ? _f : {})),
            "degree_list": degreeIds.map(degreeId => ({
                viewer_id: viewerId,
                degree_id: degreeId,
            })),
            "mail_arrived": false
        };
        mergeShopDegreeSettlement(responseData, playerId, viewerId);
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": responseData
        });
    }));
    fastify.post("/get_sales_list", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _g, _h, _j;
        const body = request.body;
        const viewerId = body.viewer_id;
        const shopTypes = body.shop_types;
        const bossCoinShopCategoryIds = body.boss_coin_shop_category_ids;
        const equipmentEnhancementCategoryIds = body.equipment_enhancement_shop_category_ids;
        const eventList = body.event_list;
        if (isNaN(viewerId) || shopTypes === undefined || bossCoinShopCategoryIds === undefined || eventList === undefined)
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
        (0, game_logging_1.gameVerboseLog)(() => `[shop:req] viewer=${viewerId} types=${JSON.stringify(shopTypes)} bossCats=${JSON.stringify(bossCoinShopCategoryIds)} equipCats=${JSON.stringify(equipmentEnhancementCategoryIds)} events=${eventList.length} eventList=${JSON.stringify(eventList)}`);
        let toParseShopItems = {};
        // shop types
        for (const type of shopTypes) {
            const items = (0, assets_1.getGenericShopItemsSync)(type);
            const existing = (_g = toParseShopItems[type]) !== null && _g !== void 0 ? _g : {};
            toParseShopItems[type] = items === null ? existing : Object.assign(Object.assign({}, existing), items);
        }
        // event list
        for (const event of eventList) {
            const type = event.event_type;
            for (const eventId of event.event_ids) {
                const items = (0, assets_1.getEventShopItemsSync)(type, eventId);
                const existing = (_h = toParseShopItems[types_1.ShopType.EVENT_ITEM]) !== null && _h !== void 0 ? _h : {};
                toParseShopItems[types_1.ShopType.EVENT_ITEM] = items === null ? existing : Object.assign(Object.assign({}, existing), items);
            }
        }
        // boss coin shop category ids
        for (const category of bossCoinShopCategoryIds) {
            const items = (0, assets_1.getBossCoinShopItemsSync)(category);
            const existing = (_j = toParseShopItems[types_1.ShopType.BOSS_COIN]) !== null && _j !== void 0 ? _j : {};
            toParseShopItems[types_1.ShopType.BOSS_COIN] = items === null ? existing : Object.assign(Object.assign({}, existing), items);
        }
        // parse shop items
        const salesList = [];
        // Load purchase history for stock tracking
        const purchasedMap = (0, shopPurchase_1.getPlayerShopPurchasesMapSync)(playerId);
        const ownedDegrees = new Set((0, degree_1.getPlayerDegreeIdsSync)(playerId));
        const totalPurchased = Object.values(purchasedMap).reduce((a, b) => a + b, 0);
        (0, game_logging_1.gameVerboseLog)(() => `[shop:get_sales] player=${playerId} purchasedKeys=${Object.keys(purchasedMap).length} totalPurchased=${totalPurchased}`);
        let filteredCdnCount = 0;
        // Collect enhancement shop items for group-level processing
        const enhancementItems = {};
        for (const [shopType, items] of Object.entries(toParseShopItems)) {
            const shopTypeNum = Number(shopType);
            for (const [itemId, item] of Object.entries(items)) {
                if (shopTypeNum === types_1.ShopType.GENERAL && !GENERAL_SHOP_CDN_KEYS.has(Number(itemId))) {
                    filteredCdnCount++;
                    continue;
                }
                // Filter equipment enhancement shop by category IDs
                if (shopTypeNum === types_1.ShopType.TREASURE_EQUIPMENT && (equipmentEnhancementCategoryIds === null || equipmentEnhancementCategoryIds === void 0 ? void 0 : equipmentEnhancementCategoryIds.length)) {
                    if (item.shopCategoryId === undefined || !equipmentEnhancementCategoryIds.includes(item.shopCategoryId)) {
                        continue;
                    }
                }
                // Date filtering: only show items active at current server time
                if (!isShopItemAvailable(item, (0, utils_1.getServerDate)()))
                    continue;
                if (shopTypeNum === types_1.ShopType.TREASURE_EQUIPMENT) {
                    // Collect for group-level processing later
                    enhancementItems[itemId] = item;
                    continue;
                }
                const purchased = getEffectiveShopPurchaseCountSync(playerId, shopTypeNum, Number(itemId));
                const stock = item.stock;
                const degreeOwned = item.rewards.some(reward => reward.type === types_1.ShopItemRewardType.DEGREE
                    && ownedDegrees.has(reward.id));
                const stockQuantity = degreeOwned
                    ? 0
                    : (stock !== undefined ? Math.max(0, stock - purchased) : -1);
                const clientTotalPurchaseNum = getClientTotalPurchaseNum(shopTypeNum, Number(itemId), purchased, stock);
                salesList.push({
                    "shop_item_id": Number(itemId),
                    "stock_quantity": stockQuantity,
                    "today_purchase_num": purchased,
                    "this_month_purchase_num": purchased,
                    "total_purchase_num": clientTotalPurchaseNum,
                    "group_info": {
                        "group_total_stock_quantity": stockQuantity,
                        "group_total_purchase_num": purchased,
                        "multi_stage": false
                    },
                    "shop_type": Number(shopType)
                });
            }
        }
        // Process equipment enhancement items by group
        const enhancementSales = buildEnhancementSalesList(playerId, enhancementItems);
        salesList.push(...enhancementSales);
        if (filteredCdnCount > 0) {
            (0, game_logging_1.gameVerboseLog)(() => `[shop] Filtered ${filteredCdnCount} general shop items not in CDN master data`);
        }
        const salesByType = {};
        for (const item of salesList) {
            const t = item.shop_type;
            salesByType[t] = (salesByType[t] || 0) + 1;
        }
        (0, game_logging_1.gameVerboseLog)(() => `[shop:res] totalSales=${salesList.length} byType=${JSON.stringify(salesByType)} toParseItems=${JSON.stringify(Object.fromEntries(Object.entries(toParseShopItems).map(([k, v]) => [k, Object.keys(v).length])))}`);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": {
                "sales_list": salesList
            }
        });
    }));
    fastify.post("/recover_stamina", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId)) {
            console.warn(`[RECOVER-STAMINA] invalid viewer_id: ${viewerId}`);
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer_id."
            });
        }
        const session = yield (0, session_1.getSession)(viewerId.toString());
        if (!session)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id."
            });
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(session.accountId);
        if (playerId === null)
            return reply.status(500).send({
                "error": "Internal Server Error", "message": "No player bound to account."
            });
        const player = (0, player_1.getPlayerSync)(playerId);
        if (!player)
            return reply.status(500).send({
                "error": "Internal Server Error", "message": "Player not found."
            });
        const config = (0, assets_1.getConfigSync)();
        const recoveryCost = config.stamina_recovery_virtual_money;
        const recoveryValue = config.stamina_recovery_value;
        const maxOverflow = config.max_stamina_overflow;
        const currentStamina = (0, stamina_1.computeRealTimeStamina)(player);
        // Already at max
        if (currentStamina >= maxOverflow) {
            (0, game_logging_1.gameVerboseLog)(() => `[RECOVER-STAMINA] player ${playerId} already at max (${currentStamina} >= ${maxOverflow})`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId, result_code: 2102 }),
                "data": {}
            });
        }
        const vmoneyDeduction = (0, free_first_deduction_1.computeFreeFirstDeduction)(player.freeVmoney, player.vmoney, recoveryCost);
        if (vmoneyDeduction === null) {
            console.warn(`[RECOVER-STAMINA] player ${playerId} insufficient vmoney: ` +
                `free=${player.freeVmoney} paid=${player.vmoney} cost=${recoveryCost}`);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId, result_code: 0 }),
                "data": {}
            });
        }
        // Calculate recovery amount (capped at overflow)
        const afterStamina = Math.min(currentStamina + recoveryValue, maxOverflow);
        const actualRecovery = afterStamina - currentStamina;
        (0, player_1.updatePlayerSync)({
            id: playerId,
            stamina: afterStamina,
            staminaHealTime: new Date(),
            freeVmoney: vmoneyDeduction.freeBalance,
            vmoney: vmoneyDeduction.paidBalance,
        });
        (0, game_logging_1.gameVerboseLog)(() => `[RECOVER-STAMINA] player ${playerId}: stamina ${currentStamina}->${afterStamina} (+${actualRecovery}), ` +
            `freeVmoney ${player.freeVmoney}->${vmoneyDeduction.freeBalance}, ` +
            `vmoney ${player.vmoney}->${vmoneyDeduction.paidBalance}`);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                "user_info": {
                    "stamina": afterStamina,
                    "stamina_heal_time": (0, utils_1.realToVirtual)(new Date()),
                    "vmoney": vmoneyDeduction.paidBalance,
                    "free_vmoney": vmoneyDeduction.freeBalance,
                }
            }
        });
    }));
    // Buy multiple shop products as one atomic operation. Different client builds
    // use either POST or GET, and GET query parsing may leave buy_item_list as JSON
    // or as flattened buy_item_list[ID] keys.
    fastify.route({
        method: ["GET", "POST"],
        url: "/bulk_buy",
        handler: (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
            var _k, _l, _m, _o, _p;
            const rawRequest = (request.method === "GET"
                ? Object.assign(Object.assign({}, request.query), request.body) : request.body);
            const viewerId = Number(rawRequest === null || rawRequest === void 0 ? void 0 : rawRequest.viewer_id);
            const shopType = Number(rawRequest === null || rawRequest === void 0 ? void 0 : rawRequest.shop_type);
            let buyItemList = null;
            const rawBuyItemList = rawRequest === null || rawRequest === void 0 ? void 0 : rawRequest.buy_item_list;
            if (rawBuyItemList !== null && typeof rawBuyItemList === "object" && !Array.isArray(rawBuyItemList)) {
                buyItemList = rawBuyItemList;
            }
            else if (typeof rawBuyItemList === "string") {
                try {
                    const parsed = JSON.parse(rawBuyItemList);
                    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
                        buyItemList = parsed;
                    }
                }
                catch (_q) {
                    // Some clients use flattened query keys; handled below.
                }
            }
            if (buyItemList === null && rawRequest !== undefined) {
                const flattened = {};
                for (const [key, value] of Object.entries(rawRequest)) {
                    const match = /^buy_item_list\[(\d+)\]$/.exec(key);
                    if (match !== null && (typeof value === "number" || typeof value === "string")) {
                        flattened[match[1]] = value;
                    }
                }
                if (Object.keys(flattened).length > 0)
                    buyItemList = flattened;
            }
            if (!Number.isSafeInteger(viewerId) || !Number.isSafeInteger(shopType))
                return reply.status(400).send({
                    "error": "Bad Request", "message": "Invalid request body."
                });
            const rawEntries = buyItemList === null ? [] : Object.entries(buyItemList).slice(0, 500);
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
            const player = (0, player_1.getPlayerSync)(playerId);
            if (player === null)
                return reply.status(500).send({
                    "error": "Internal Server Error",
                    "message": "Player not found."
                });
            const purchases = [];
            const rewards = [];
            const degreeIds = [];
            const ownedDegreeIds = new Set((0, degree_1.getPlayerDegreeIdsSync)(playerId));
            const plannedDegreeIds = new Set();
            const itemCostTotals = new Map();
            let manaCost = 0;
            let vmoneyCost = 0;
            let bondTokenCost = 0;
            let availableFreeMana = player.freeMana;
            let availablePaidMana = player.paidMana;
            let availableFreeVmoney = player.freeVmoney;
            let availablePaidVmoney = player.vmoney;
            let availableBondToken = player.bondToken;
            const availableItems = new Map();
            const purchaseNow = (0, utils_1.getServerDate)();
            let skippedEntries = Math.max(0, (buyItemList === null ? 0 : Object.keys(buyItemList).length) - rawEntries.length);
            for (const [rawShopItemId, rawPurchaseAmount] of rawEntries) {
                const shopItemId = Number(rawShopItemId);
                const requestedAmount = Number(rawPurchaseAmount);
                if (!Number.isSafeInteger(shopItemId) ||
                    !Number.isSafeInteger(requestedAmount) ||
                    requestedAmount <= 0) {
                    skippedEntries++;
                    continue;
                }
                const shopItem = (0, assets_1.getShopItemSync)(shopType, shopItemId);
                if (shopItem === null) {
                    skippedEntries++;
                    continue;
                }
                if (shopType === types_1.ShopType.EVENT_ITEM && !isShopItemAvailable(shopItem, purchaseNow)) {
                    skippedEntries++;
                    continue;
                }
                // Keep unlimited/free products bounded even if a malformed client sends
                // an extreme amount. Stock-limited products are capped again below.
                let purchaseAmount = Math.min(requestedAmount, 10000);
                if (shopItem.stock !== undefined && shopItem.stock > 0) {
                    const purchased = getEffectiveShopPurchaseCountSync(playerId, shopType, shopItemId);
                    purchaseAmount = Math.min(purchaseAmount, Math.max(0, shopItem.stock - purchased));
                    if (purchaseAmount <= 0) {
                        skippedEntries++;
                        continue;
                    }
                }
                let shopDegreeIds;
                try {
                    shopDegreeIds = getShopDegreeRewards(shopItem, purchaseAmount);
                }
                catch (_r) {
                    skippedEntries++;
                    continue;
                }
                if (shopDegreeIds.some(degreeId => ownedDegreeIds.has(degreeId) || plannedDegreeIds.has(degreeId))) {
                    skippedEntries++;
                    continue;
                }
                const userCost = shopItem.userCost;
                let userCostBudget = null;
                if (userCost !== undefined) {
                    if (!Number.isSafeInteger(userCost.amount) || userCost.amount < 0) {
                        skippedEntries++;
                        continue;
                    }
                    switch (userCost.type) {
                        case types_1.ShopItemUserCostType.MANA:
                            userCostBudget = availableFreeMana + availablePaidMana;
                            break;
                        case types_1.ShopItemUserCostType.BEADS:
                            userCostBudget = availableFreeVmoney + availablePaidVmoney;
                            break;
                        case types_1.ShopItemUserCostType.AMITY_SCROLL:
                            userCostBudget = availableBondToken;
                            break;
                        default:
                            skippedEntries++;
                            continue;
                    }
                    if (userCost.amount > 0) {
                        purchaseAmount = Math.min(purchaseAmount, Math.floor(userCostBudget / userCost.amount));
                    }
                }
                const perPurchaseItemCosts = new Map();
                let invalidCost = false;
                for (const cost of shopItem.costs) {
                    if (!Number.isSafeInteger(cost.id) || !Number.isSafeInteger(cost.amount) || cost.amount < 0) {
                        invalidCost = true;
                        break;
                    }
                    const perPurchase = ((_k = perPurchaseItemCosts.get(cost.id)) !== null && _k !== void 0 ? _k : 0) + cost.amount;
                    if (!Number.isSafeInteger(perPurchase)) {
                        invalidCost = true;
                        break;
                    }
                    perPurchaseItemCosts.set(cost.id, perPurchase);
                }
                if (invalidCost) {
                    skippedEntries++;
                    continue;
                }
                for (const [itemId, perPurchase] of perPurchaseItemCosts) {
                    let available = availableItems.get(itemId);
                    if (available === undefined) {
                        available = (_l = (0, item_1.getPlayerItemSync)(playerId, itemId)) !== null && _l !== void 0 ? _l : 0;
                        availableItems.set(itemId, available);
                    }
                    if (perPurchase > 0) {
                        purchaseAmount = Math.min(purchaseAmount, Math.floor(available / perPurchase));
                    }
                }
                if (purchaseAmount <= 0) {
                    skippedEntries++;
                    continue;
                }
                if (userCost !== undefined) {
                    const total = userCost.amount * purchaseAmount;
                    if (!Number.isSafeInteger(total)) {
                        skippedEntries++;
                        continue;
                    }
                    switch (userCost.type) {
                        case types_1.ShopItemUserCostType.MANA: {
                            const deduction = (0, free_first_deduction_1.computeFreeFirstDeduction)(availableFreeMana, availablePaidMana, total);
                            if (deduction === null) {
                                skippedEntries++;
                                continue;
                            }
                            manaCost += total;
                            availableFreeMana = deduction.freeBalance;
                            availablePaidMana = deduction.paidBalance;
                            break;
                        }
                        case types_1.ShopItemUserCostType.BEADS: {
                            const deduction = (0, free_first_deduction_1.computeFreeFirstDeduction)(availableFreeVmoney, availablePaidVmoney, total);
                            if (deduction === null) {
                                skippedEntries++;
                                continue;
                            }
                            vmoneyCost += total;
                            availableFreeVmoney = deduction.freeBalance;
                            availablePaidVmoney = deduction.paidBalance;
                            break;
                        }
                        case types_1.ShopItemUserCostType.AMITY_SCROLL:
                            bondTokenCost += total;
                            availableBondToken -= total;
                            break;
                    }
                }
                for (const [itemId, perPurchase] of perPurchaseItemCosts) {
                    const total = perPurchase * purchaseAmount;
                    const existing = (_m = itemCostTotals.get(itemId)) !== null && _m !== void 0 ? _m : 0;
                    const available = (_o = availableItems.get(itemId)) !== null && _o !== void 0 ? _o : 0;
                    if (!Number.isSafeInteger(total) || !Number.isSafeInteger(existing + total)) {
                        invalidCost = true;
                        break;
                    }
                    itemCostTotals.set(itemId, existing + total);
                    availableItems.set(itemId, available - total);
                }
                if (invalidCost) {
                    // This can only be reached for corrupt master data; previous checks
                    // make it unreachable for normal client input.
                    skippedEntries++;
                    continue;
                }
                for (const degreeId of shopDegreeIds) {
                    plannedDegreeIds.add(degreeId);
                    degreeIds.push(degreeId);
                }
                appendShopItemRewards(rewards, shopItem, purchaseAmount);
                purchases.push({ shopItemId, purchaseAmount, shopItem });
            }
            if (!Number.isSafeInteger(manaCost) ||
                !Number.isSafeInteger(vmoneyCost) ||
                !Number.isSafeInteger(bondTokenCost))
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Bulk purchase cost is too large."
                });
            const costItemList = {};
            for (const [itemId, amount] of itemCostTotals) {
                const currentAmount = (_p = (0, item_1.getPlayerItemSync)(playerId, itemId)) !== null && _p !== void 0 ? _p : 0;
                costItemList[itemId] = currentAmount - amount;
            }
            const mergedRewards = mergeCountedRewards(rewards);
            for (const reward of mergedRewards) {
                if (!("count" in reward))
                    continue;
                const countedReward = reward;
                if (!Number.isSafeInteger(countedReward.count) ||
                    countedReward.count < 0)
                    return reply.status(400).send({
                        "error": "Bad Request",
                        "message": "Bulk purchase reward amount is too large."
                    });
            }
            (0, game_logging_1.gameVerboseLog)(() => `[shop:bulk_buy] player=${playerId} shopType=${shopType} ` +
                `items=${JSON.stringify(Object.fromEntries(purchases.map(v => [v.shopItemId, v.purchaseAmount])))} ` +
                `skipped=${skippedEntries} ` +
                `manaCost=${manaCost} vmoneyCost=${vmoneyCost} bondTokenCost=${bondTokenCost} ` +
                `itemCosts=${JSON.stringify(Object.fromEntries(itemCostTotals))}`);
            let rewardResult;
            try {
                rewardResult = (0, db_1.getDb)().transaction(() => {
                    for (const [itemId, newAmount] of Object.entries(costItemList)) {
                        (0, item_1.updatePlayerItemSync)(playerId, itemId, newAmount);
                    }
                    (0, player_1.updatePlayerSync)({
                        id: playerId,
                        freeMana: availableFreeMana,
                        paidMana: availablePaidMana,
                        freeVmoney: availableFreeVmoney,
                        vmoney: availablePaidVmoney,
                        bondToken: player.bondToken - bondTokenCost
                    });
                    if (manaCost > 0)
                        (0, active_mission_counters_1.incrementActiveMissionUsedManaCountSync)(playerId, manaCost);
                    const result = (0, quest_1.givePlayerRewardsSync)(playerId, mergedRewards);
                    if (result === null) {
                        throw new Error(`Failed to grant bulk shop rewards for player ${playerId}`);
                    }
                    for (const degreeId of degreeIds) {
                        if (!(0, degree_1.grantPlayerDegreeSync)(playerId, degreeId)) {
                            throw new Error(`Degree ${degreeId} is already owned.`);
                        }
                    }
                    for (const purchase of purchases) {
                        addEffectiveShopPurchaseCountSync(playerId, shopType, purchase.shopItemId, purchase.purchaseAmount);
                    }
                    recordTreasureShopProgress(playerId, shopType, purchases.reduce((total, purchase) => total + purchase.purchaseAmount, 0), manaCost);
                    return result;
                })();
            }
            catch (error) {
                console.error(`[shop:bulk_buy] transaction failed player=${playerId}`, error);
                return reply.status(500).send({
                    "error": "Internal Server Error",
                    "message": "Bulk purchase transaction failed."
                });
            }
            const afterPlayer = (0, player_1.getPlayerSync)(playerId);
            if (afterPlayer === null || rewardResult === null)
                return reply.status(500).send({
                    "error": "Internal Server Error",
                    "message": "Failed to load player after bulk purchase."
                });
            const characterList = (0, mission_1.reconcileAwakeUnlockCharacterList)(playerId, rewardResult.character_list);
            (0, game_logging_1.gameVerboseLog)(() => `[shop:bulk_buy] completed player=${playerId} ` +
                `freeMana=${afterPlayer.freeMana} paidMana=${afterPlayer.paidMana} ` +
                `freeVmoney=${afterPlayer.freeVmoney} vmoney=${afterPlayer.vmoney} ` +
                `rewardItems=${JSON.stringify(rewardResult.items)}`);
            reply.header("content-type", "application/x-msgpack");
            const responseData = {
                "user_info": {
                    "vmoney": afterPlayer.vmoney,
                    "free_vmoney": afterPlayer.freeVmoney,
                    "paid_mana": afterPlayer.paidMana,
                    "free_mana": afterPlayer.freeMana,
                    "bond_token": afterPlayer.bondToken,
                    "exp_pool": afterPlayer.expPool
                },
                "character_list": characterList,
                "equipment_list": rewardResult.equipment_list,
                "item_list": Object.assign(Object.assign({}, costItemList), rewardResult.items),
                "degree_list": degreeIds.map(degreeId => ({
                    viewer_id: viewerId,
                    degree_id: degreeId,
                })),
                "mail_arrived": false
            };
            mergeShopDegreeSettlement(responseData, playerId, viewerId);
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
                "data": responseData
            });
        })
    });
    // get_campaign_lineup_id — stub
    fastify.post("/get_campaign_lineup_id", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": { "lineup_id": null }
        });
    }));
    // set_campaign_lineup_id — stub
    fastify.post("/set_campaign_lineup_id", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {}
        });
    }));
});
exports.default = routes;
