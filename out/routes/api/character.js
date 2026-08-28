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
exports.characterMaxOverLimits = void 0;
const character_1 = require("../../data/domains/character");
const item_1 = require("../../data/domains/item");
const player_1 = require("../../data/domains/player");
const session_1 = require("../../data/domains/session");
const utils_1 = require("../../utils");
const assets_1 = require("../../lib/assets");
const character_2 = require("../../lib/character");
const utils_2 = require("../../data/utils");
const activeAccount_1 = require("../../data/activeAccount");
const mission_1 = require("../../lib/mission");
const game_logging_1 = require("../../lib/game-logging");
exports.characterMaxOverLimits = {
    [1]: 12, // 1* max over limit count
    [2]: 10, // 2* max over limit count
    [3]: 8, // 3* max over limit count
    [4]: 6, // 4* max over limit count
    [5]: 4, // 5* max over limit count
};
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/set_illustration_settings", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        const characterId = body.character_id;
        const illustration_settings = body.illustration_settings;
        if (isNaN(viewerId) || isNaN(characterId) || !illustration_settings)
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
        // get player id
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(viewerIdSession.accountId);
        if (playerId === undefined)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        // update character
        (0, character_1.updatePlayerCharacterSync)(playerId, characterId, {
            illustrationSettings: illustration_settings.slice(0, 6)
        });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": {}
        });
    }));
    fastify.post("/over_limit", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
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
        // get character data
        const characterId = body.character_id;
        const playerCharacterData = (0, character_1.getPlayerCharacterSync)(playerId, characterId);
        if (playerCharacterData === null)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Character not owned."
            });
        // get character asset data
        const characterAssetData = (0, assets_1.getCharacterDataSync)(characterId);
        if (characterAssetData === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No character asset data found."
            });
        // calculate new over limit
        const overLimitCount = body.over_limit_count;
        const newOverLimit = playerCharacterData.overLimitStep + overLimitCount;
        const characterRarity = characterAssetData.rarity;
        if (newOverLimit > exports.characterMaxOverLimits[characterRarity])
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Character cannot be uncapped further."
            });
        let stack = playerCharacterData.stack;
        const item_list = {};
        if (body.use_stack) {
            // stack uncapping
            // ensure that the character has enough stack
            stack = stack - overLimitCount;
            if (0 > stack)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Character does not have enough duplicates to uncap."
                });
            // update the character
            (0, character_1.updatePlayerCharacterSync)(playerId, characterId, {
                overLimitStep: newOverLimit,
                stack: stack
            });
        }
        else {
            // item uncapping
            const itemId = body.item_id;
            // ensure that the item trying to be used is valid
            // 5* characters can only be uncapped by item 10003 (awaking_crystal_5)
            // 4* characters and below can only be uncapped by items 10002 (awaking_crystal_4) and 10001 (awaking_crystal_3)
            if ((characterRarity === 5 && itemId !== 10003)
                || (4 >= characterRarity && (itemId !== 10002 && itemId !== 10001)))
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Attempted to use invalid item."
                });
            const itemData = (0, item_1.getPlayerItemSync)(playerId, itemId);
            if (itemData === null)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Attempted to use unowned item."
                });
            // make sure that the player has enough of the item
            const newAmount = itemData - overLimitCount;
            if (0 > newAmount)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Not enough of item to uncap."
                });
            // update the item count
            (0, item_1.updatePlayerItemSync)(playerId, itemId, newAmount);
            item_list[itemId] = newAmount; // add to items table
            // update the character
            (0, character_1.updatePlayerCharacterSync)(playerId, characterId, {
                overLimitStep: newOverLimit
            });
        }
        const responseData = {
            "character_list": [
                {
                    "over_limit_step": newOverLimit,
                    "character_id": characterId,
                    "stack": stack,
                    "create_time": (0, utils_2.clientSerializeDate)(playerCharacterData.joinTime),
                    "update_time": (0, utils_2.clientSerializeDate)(new Date()),
                    "join_time": (0, utils_2.clientSerializeDate)(playerCharacterData.joinTime)
                }
            ],
            "item_list": item_list,
            "mail_arrived": false
        };
        (0, mission_1.settleDegreeMissionResponse)(playerId, viewerId, responseData, undefined, [9]);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": responseData
        });
    }));
    fastify.post("/bulk_over_limit", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                error: "Bad Request", message: "Invalid request body.",
            });
        const viewerIdSession = yield (0, session_1.getSession)(viewerId.toString());
        if (!viewerIdSession)
            return reply.status(400).send({
                error: "Bad Request", message: "Invalid viewer id.",
            });
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(viewerIdSession.accountId);
        const player = playerId !== null ? (0, player_1.getPlayerSync)(playerId) : null;
        if (player === null)
            return reply.status(500).send({
                error: "Internal Server Error", message: "No players bound to account.",
            });
        const characters = (0, character_1.getPlayerCharactersSync)(playerId);
        (0, game_logging_1.gameVerboseLog)(() => `[bulk_over_limit] player=${playerId} totalChars=${Object.keys(characters).length}`);
        const characterList = [];
        for (const [charId, charData] of Object.entries(characters)) {
            if (charData.stack <= 0)
                continue;
            const assetData = (0, assets_1.getCharacterDataSync)(Number(charId));
            if (!assetData)
                continue;
            const maxOver = exports.characterMaxOverLimits[assetData.rarity];
            if (maxOver === undefined)
                continue;
            const rest = maxOver - charData.overLimitStep;
            if (rest <= 0)
                continue;
            const count = Math.min(charData.stack, rest);
            const newOverLimit = charData.overLimitStep + count;
            const newStack = charData.stack - count;
            (0, character_1.updatePlayerCharacterSync)(playerId, Number(charId), {
                overLimitStep: newOverLimit,
                stack: newStack,
            });
            characterList.push({
                character_id: Number(charId),
                over_limit_step: newOverLimit,
                stack: newStack,
                create_time: (0, utils_2.clientSerializeDate)(charData.joinTime),
                update_time: (0, utils_2.clientSerializeDate)(new Date()),
                join_time: (0, utils_2.clientSerializeDate)(charData.joinTime),
            });
        }
        (0, game_logging_1.gameVerboseLog)(() => `[bulk_over_limit] done: ${characterList.length} characters modified`);
        const responseData = {
            character_list: characterList,
            mail_arrived: false,
        };
        (0, mission_1.settleDegreeMissionResponse)(playerId, viewerId, responseData, undefined, [9]);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            data: responseData,
        });
    }));
    fastify.post("/add_character_from_town", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        const characterId = body.character_id;
        if (!viewerId || isNaN(viewerId) || !characterId || isNaN(characterId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const viewerIdSession = yield (0, session_1.getSession)(viewerId.toString());
        if (!viewerIdSession)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id."
            });
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(viewerIdSession.accountId);
        if (playerId === null)
            return reply.status(500).send({
                "error": "Internal Server Error", "message": "No player bound to account."
            });
        const giveResult = (0, character_2.givePlayerCharacterSync)(playerId, characterId);
        const existingCharacterList = (giveResult === null || giveResult === void 0 ? void 0 : giveResult.character)
            ? [giveResult.character]
            : [];
        const itemList = (giveResult === null || giveResult === void 0 ? void 0 : giveResult.item)
            ? { [giveResult.item.id]: giveResult.item.inventoryCount }
            : {};
        const characterList = existingCharacterList.length > 0
            ? (0, mission_1.reconcileAwakeUnlockCharacterList)(playerId, existingCharacterList)
            : existingCharacterList;
        const responseData = {
            "character_list": characterList,
            "item_list": itemList,
            "mail_arrived": false
        };
        (0, mission_1.settleDegreeMissionResponse)(playerId, viewerId, responseData, undefined, [4]);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": responseData
        });
    }));
});
exports.default = routes;
