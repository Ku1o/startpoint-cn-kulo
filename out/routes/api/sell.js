"use strict";
// Equipment dismantle/sell endpoints: sell_equipment, sell_stack, bulk_sell_stack.
// Registered under /api/index.php/equipment prefix (shared with equipment.ts).
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
const equipment_1 = require("../../data/domains/equipment");
const item_1 = require("../../data/domains/item");
const session_1 = require("../../data/domains/session");
const utils_1 = require("../../utils");
const equipment_2 = require("../../lib/equipment");
const equipment_dissolve_1 = require("../../lib/equipment-dissolve");
const activeAccount_1 = require("../../data/activeAccount");
const assets_1 = require("../../lib/assets");
const game_logging_1 = require("../../lib/game-logging");
const persistence_coordinator_1 = require("../../lib/persistence-coordinator");
const wrightpieceItemId = () => (0, assets_1.getConfigSync)().craft_point_item_id || 100000;
const starGrainItemId = () => (0, assets_1.getConfigSync)().star_grain_item_id || 990008;
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    // ── sell_equipment (single equipment, all stacks) ──────────────────
    fastify.post("/sell_equipment", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a;
        const body = request.body;
        const viewerId = body.viewer_id;
        const toSellEquipmentList = body.equipment_list;
        if (isNaN(viewerId) || !toSellEquipmentList) {
            return reply.status(400).send({ "error": "Bad Request", "message": "Invalid request body." });
        }
        const session = yield (0, session_1.getSession)(viewerId.toString());
        if (!session)
            return reply.status(400).send({ "error": "Bad Request", "message": "Invalid viewer id." });
        const accountId = session.accountId;
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(accountId);
        if (playerId === null)
            return reply.status(500).send({ "error": "Internal Server Error", "message": "No players bound to account." });
        let totalCraftPoints = 0;
        let totalStarGrains = 0;
        const totalAbilitySouls = {};
        const soldIds = [];
        for (const toSell of toSellEquipmentList) {
            const equipmentId = toSell.equipment_id;
            const equipment = (0, equipment_1.getPlayerEquipmentSync)(playerId, equipmentId);
            if (!equipment) {
                return reply.status(400).send({ "error": "Bad Request", "message": "Player does not own equipment." });
            }
            const stack = equipment.stack;
            if (stack <= 0)
                continue;
            // 1 unit, not × stack (client Expected sell_equipment gives 1 ability soul per unit)
            const rewards = (0, equipment_dissolve_1.calculateDissolveRewards)(equipmentId, 1);
            totalCraftPoints += rewards.craftPoints;
            totalStarGrains += rewards.starGrains;
            for (const [soulId, count] of Object.entries(rewards.abilitySouls)) {
                totalAbilitySouls[parseInt(soulId)] = ((_a = totalAbilitySouls[parseInt(soulId)]) !== null && _a !== void 0 ? _a : 0) + count;
            }
            soldIds.push(equipmentId);
        }
        const returnItemList = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "player", playerId, operation: "sell_equipment",
        }, () => {
            for (const equipmentId of soldIds) {
                (0, equipment_1.updatePlayerEquipmentSync)(playerId, equipmentId, { stack: 0 });
            }
            const result = {};
            if (totalCraftPoints > 0) {
                result[wrightpieceItemId()] = (0, item_1.givePlayerItemSync)(playerId, wrightpieceItemId(), totalCraftPoints);
            }
            if (totalStarGrains > 0) {
                result[starGrainItemId()] = (0, item_1.givePlayerItemSync)(playerId, starGrainItemId(), totalStarGrains);
            }
            for (const [soulId, count] of Object.entries(totalAbilitySouls)) {
                result[parseInt(soulId)] = (0, item_1.givePlayerItemSync)(playerId, parseInt(soulId), count);
            }
            return result;
        });
        const returnEquipmentList = (0, equipment_2.buildFullEquipmentList)(playerId);
        const craftLog = totalCraftPoints > 0 ? `craft +${totalCraftPoints} ` : "";
        const starLog = totalStarGrains > 0 ? `star +${totalStarGrains} ` : "";
        const soulTypes = Object.keys(totalAbilitySouls).length;
        const soulDetail = Object.entries(totalAbilitySouls).map(([id, c]) => `${id}×${c}`).join(' ');
        console.log(`[SELL_EQUIP] account=${accountId} player=${playerId}: ${soldIds.length} equipment sold (${soldIds.join(',')}), ${craftLog}${starLog}ability souls: ${soulTypes} types [${soulDetail}]`);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                "equipment_list": returnEquipmentList,
                "item_list": returnItemList,
                "mail_arrived": false
            }
        });
    }));
    // ── sell_stack (partial stack sale) ─────────────────────────────────
    fastify.post("/sell_stack", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _b, _c;
        const body = request.body;
        const viewerId = body.viewer_id;
        const toSellEquipmentList = body.equipment_list;
        if (isNaN(viewerId) || !toSellEquipmentList) {
            return reply.status(400).send({ "error": "Bad Request", "message": "Invalid request body." });
        }
        const session = yield (0, session_1.getSession)(viewerId.toString());
        if (!session)
            return reply.status(400).send({ "error": "Bad Request", "message": "Invalid viewer id." });
        const accountId = session.accountId;
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(accountId);
        if (playerId === null)
            return reply.status(500).send({ "error": "Internal Server Error", "message": "No players bound to account." });
        let totalCraftPoints = 0;
        let totalStarGrains = 0;
        const totalAbilitySouls = {};
        const plannedStacks = [];
        const projectedStacks = new Map();
        for (const toSell of toSellEquipmentList) {
            const equipmentId = toSell.equipment_id;
            const sellCount = Math.max(1, toSell.number);
            const equipment = (0, equipment_1.getPlayerEquipmentSync)(playerId, equipmentId);
            if (!equipment) {
                return reply.status(400).send({ "error": "Bad Request", "message": "Player does not own equipment." });
            }
            const currentStack = (_b = projectedStacks.get(equipmentId)) !== null && _b !== void 0 ? _b : equipment.stack;
            const newStack = currentStack - sellCount;
            if (newStack < 0) {
                return reply.status(400).send({ "error": "Bad Request", "message": "Attempt to sell more stacks than owned." });
            }
            const rewards = (0, equipment_dissolve_1.calculateDissolveRewards)(equipmentId, sellCount);
            totalCraftPoints += rewards.craftPoints;
            totalStarGrains += rewards.starGrains;
            for (const [soulId, count] of Object.entries(rewards.abilitySouls)) {
                totalAbilitySouls[parseInt(soulId)] = ((_c = totalAbilitySouls[parseInt(soulId)]) !== null && _c !== void 0 ? _c : 0) + count;
            }
            projectedStacks.set(equipmentId, newStack);
            plannedStacks.push({ equipmentId, newStack });
        }
        const returnItemList = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "player", playerId, operation: "sell_equipment_stack",
        }, () => {
            for (const { equipmentId, newStack } of plannedStacks) {
                (0, equipment_1.updatePlayerEquipmentSync)(playerId, equipmentId, { stack: newStack });
            }
            const result = {};
            if (totalCraftPoints > 0) {
                result[wrightpieceItemId()] = (0, item_1.givePlayerItemSync)(playerId, wrightpieceItemId(), totalCraftPoints);
            }
            if (totalStarGrains > 0) {
                result[starGrainItemId()] = (0, item_1.givePlayerItemSync)(playerId, starGrainItemId(), totalStarGrains);
            }
            for (const [soulId, count] of Object.entries(totalAbilitySouls)) {
                result[parseInt(soulId)] = (0, item_1.givePlayerItemSync)(playerId, parseInt(soulId), count);
            }
            return result;
        });
        const returnEquipmentList = (0, equipment_2.buildFullEquipmentList)(playerId);
        const soulTypes = Object.keys(totalAbilitySouls).length;
        const soulDetail = Object.entries(totalAbilitySouls).map(([id, c]) => `${id}×${c}`).join(' ');
        console.log(`[SELL_STACK] account=${accountId} player=${playerId}: ${toSellEquipmentList.length} equipment stack sold, craft +${totalCraftPoints} star +${totalStarGrains} ability souls: ${soulTypes} types [${soulDetail}]`);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                "equipment_list": returnEquipmentList,
                "item_list": returnItemList,
                "mail_arrived": false
            }
        });
    }));
    // ── bulk_sell_stack (one-click dismantle) ──────────────────────────
    fastify.post("/bulk_sell_stack", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _d;
        const body = request.body;
        const viewerId = body.viewer_id;
        const equipmentIds = body.equipment_ids;
        if (isNaN(viewerId) || !equipmentIds || !Array.isArray(equipmentIds) || equipmentIds.length === 0) {
            return reply.status(400).send({ "error": "Bad Request", "message": "Invalid request body." });
        }
        const session = yield (0, session_1.getSession)(viewerId.toString());
        if (!session)
            return reply.status(400).send({ "error": "Bad Request", "message": "Invalid viewer id." });
        const accountId = session.accountId;
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(accountId);
        if (playerId === null)
            return reply.status(500).send({ "error": "Internal Server Error", "message": "No players bound to account." });
        // Phase 1: calculate rewards per equipment
        let totalCraftPoints = 0;
        let totalStarGrains = 0;
        const totalAbilitySouls = {};
        const toSell = [];
        const seen = new Set();
        for (const equipmentId of equipmentIds) {
            if (seen.has(equipmentId))
                continue;
            seen.add(equipmentId);
            const equipment = (0, equipment_1.getPlayerEquipmentSync)(playerId, equipmentId);
            if (!equipment)
                continue;
            const stack = equipment.stack;
            if (stack <= 0)
                continue;
            const rewards = (0, equipment_dissolve_1.calculateDissolveRewards)(equipmentId, stack);
            totalCraftPoints += rewards.craftPoints;
            totalStarGrains += rewards.starGrains;
            for (const [soulId, count] of Object.entries(rewards.abilitySouls)) {
                totalAbilitySouls[parseInt(soulId)] = ((_d = totalAbilitySouls[parseInt(soulId)]) !== null && _d !== void 0 ? _d : 0) + count;
            }
            (0, game_logging_1.gameVerboseLog)(() => `[BULK_SELL] account=${accountId} player=${playerId}  -> eid=${equipmentId} stack=${stack} rarity=${Math.floor(equipmentId / 1000000)} craft=${rewards.craftPoints} star=${rewards.starGrains} souls=${JSON.stringify(rewards.abilitySouls)}`);
            toSell.push(equipmentId);
        }
        if (toSell.length === 0) {
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
                "data": { "equipment_list": [], "item_list": {}, "mail_arrived": false }
            });
        }
        // Phase 2: set stack to 0 and grant all dissolve rewards atomically.
        const returnItemList = yield (0, persistence_coordinator_1.runPersistenceTransaction)({
            domain: "player", playerId, operation: "bulk_sell_equipment_stack",
        }, () => {
            for (const equipmentId of toSell) {
                (0, equipment_1.updatePlayerEquipmentSync)(playerId, equipmentId, { stack: 0 });
            }
            const result = {};
            if (totalCraftPoints > 0) {
                result[wrightpieceItemId()] = (0, item_1.givePlayerItemSync)(playerId, wrightpieceItemId(), totalCraftPoints);
            }
            if (totalStarGrains > 0) {
                result[starGrainItemId()] = (0, item_1.givePlayerItemSync)(playerId, starGrainItemId(), totalStarGrains);
            }
            for (const [soulId, count] of Object.entries(totalAbilitySouls)) {
                result[parseInt(soulId)] = (0, item_1.givePlayerItemSync)(playerId, parseInt(soulId), count);
            }
            return result;
        });
        const returnEquipmentList = (0, equipment_2.buildFullEquipmentList)(playerId);
        const craftLog = totalCraftPoints > 0 ? `craft +${totalCraftPoints} ` : "";
        const starLog = totalStarGrains > 0 ? `star +${totalStarGrains} ` : "";
        const soulTypes = Object.keys(totalAbilitySouls).length;
        const soulDetail = Object.entries(totalAbilitySouls).map(([id, c]) => `${id}×${c}`).join(' ');
        (0, game_logging_1.gameVerboseLog)(() => `[BULK_SELL] account=${accountId} player=${playerId}: ${toSell.length} equipment dissolved (${toSell.join(',')}), ${craftLog}${starLog}ability souls: ${soulTypes} types [${soulDetail}]`);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                "equipment_list": returnEquipmentList,
                "item_list": returnItemList,
                "mail_arrived": false
            }
        });
    }));
});
exports.default = routes;
