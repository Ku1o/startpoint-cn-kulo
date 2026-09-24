"use strict";
// Character bond token and mana board opening endpoints
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
const character_1 = require("../../../data/domains/character");
const player_1 = require("../../../data/domains/player");
const session_1 = require("../../../data/domains/session");
const utils_1 = require("../../../utils");
const assets_1 = require("../../../lib/assets");
const utils_2 = require("../../../data/utils");
const activeAccount_1 = require("../../../data/activeAccount");
const character_helpers_1 = require("../../../lib/character-helpers");
const character_2 = require("../../../lib/character");
const mission_1 = require("../../../lib/mission");
const game_logging_1 = require("../../../lib/game-logging");
const openManaBoardRequiredUncaps = {
    [1]: 10, [2]: 8, [3]: 6, [4]: 4, [5]: 2
};
const openManaBoardRequiredExp = {
    [3]: character_2.characterExpCaps[3][0],
    [4]: character_2.characterExpCaps[4][0],
    [5]: character_2.characterExpCaps[5][0]
};
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/receive_bond_token", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        const characterId = body.character_id;
        const manaBoardIndex = body.mana_board_index;
        (0, game_logging_1.gameVerboseLog)(() => `[MANA] receive_bond_token: viewer=${viewerId} char=${characterId} boardIdx=${manaBoardIndex}`);
        if (isNaN(viewerId) || isNaN(characterId) || isNaN(manaBoardIndex))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const sess = yield (0, character_helpers_1.validateSessionAndPlayer)(viewerId, reply);
        if (!sess)
            return reply;
        const { playerId, player } = sess;
        const characterData = (0, character_helpers_1.validateCharacterOwnership)(playerId, characterId, reply);
        if (!characterData)
            return reply;
        const bondToken = characterData.bondTokenList
            .find(token => token.manaBoardIndex === manaBoardIndex);
        if (!bondToken || bondToken.status === 0)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Cannot receive bond token."
            });
        // Already claimed — return current state
        if (bondToken.status === 2) {
            return (0, character_helpers_1.sendCharacterResponse)(reply, viewerId, {
                user_info: { bond_token: player.bondToken },
                character_list: [(0, character_helpers_1.buildCharacterListEntry)(characterId, characterData, {
                        bond_token_list: characterData.bondTokenList.map(e => ({ mana_board_index: e.manaBoardIndex, status: e.status })),
                    })],
                user_character_mana_node_list: {},
                item_list: {},
                evolution: [],
                mail_arrived: false,
            }, playerId);
        }
        // Claim the bond token
        const newBondTokens = player.bondToken + 1;
        (0, player_1.updatePlayerSync)({ id: playerId, bondToken: newBondTokens });
        (0, character_1.updatePlayerCharacterBondTokenSync)(playerId, characterId, { manaBoardIndex, status: 2 });
        const bondTokenList = [];
        for (const entry of characterData.bondTokenList) {
            bondTokenList.push({ "mana_board_index": entry.manaBoardIndex, "status": entry.manaBoardIndex === manaBoardIndex ? 2 : entry.status });
        }
        const characterList = (0, mission_1.reconcileAwakeUnlockCharacterList)(playerId, [
            (0, character_helpers_1.buildCharacterListEntry)(characterId, characterData, { bond_token_list: bondTokenList })
        ]);
        return (0, character_helpers_1.sendCharacterResponse)(reply, viewerId, {
            user_info: { bond_token: newBondTokens },
            character_list: characterList,
            user_character_mana_node_list: {},
            item_list: {},
            evolution: [],
            mail_arrived: false,
        }, playerId);
    }));
    fastify.post("/open_mana_board", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a;
        const body = request.body;
        const viewerId = body.viewer_id;
        const characterId = body.character_id;
        const manaBoardIndex = body.mana_board_index;
        (0, game_logging_1.gameVerboseLog)(() => `[MANA] open_mana_board: viewer=${viewerId} char=${characterId} boardIdx=${manaBoardIndex}`);
        if (isNaN(viewerId) || isNaN(characterId) || isNaN(manaBoardIndex))
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
                "error": "Internal Server Error", "message": "No players bound to account."
            });
        // get character data
        const characterData = (0, character_1.getPlayerCharacterSync)(playerId, characterId);
        if (characterData === null)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Character not owned."
            });
        // get character asset data
        const characterAssetData = (0, assets_1.getCharacterDataSync)(characterId);
        if (characterAssetData === null)
            return reply.status(500).send({
                "error": "Internal Server Error", "message": "No character asset data found."
            });
        // make sure that the mana board index is valid, auto-create missing bond tokens
        if (!characterData.bondTokenList.some(token => token.manaBoardIndex === manaBoardIndex)) {
            const boardCount = (0, assets_1.getCharacterManaBoardCountSync)(characterId);
            (0, game_logging_1.gameVerboseLog)(() => `[MANA] open_mana_board: auto-creating bond tokens, bondListLen=${characterData.bondTokenList.length} boardCount=${boardCount}`);
            const existingBoards = new Set(characterData.bondTokenList.map(token => token.manaBoardIndex));
            for (let i = 1; i <= boardCount; i++) {
                if (existingBoards.has(i))
                    continue;
                (0, character_1.insertPlayerCharacterBondTokenSync)(playerId, characterId, { manaBoardIndex: i, status: 0 });
                characterData.bondTokenList.push({ manaBoardIndex: i, status: 0 });
            }
            characterData.bondTokenList.sort((left, right) => left.manaBoardIndex - right.manaBoardIndex);
        }
        // ensure that the mana board can be opened
        const requiredLevelExp = openManaBoardRequiredExp[characterAssetData.rarity];
        if (requiredLevelExp !== undefined && requiredLevelExp > characterData.exp) {
            console.warn(`[MANA] open_mana_board FAIL: exp too low, need=${requiredLevelExp} have=${characterData.exp}`);
            return reply.status(400).send({
                "error": "Bad Request", "message": `Character level is too low to unlock mana board.`
            });
        }
        if (openManaBoardRequiredUncaps[characterAssetData.rarity] > characterData.overLimitStep) {
            console.warn(`[MANA] open_mana_board FAIL: uncap too low, need=${openManaBoardRequiredUncaps[characterAssetData.rarity]} have=${characterData.overLimitStep}`);
            return reply.status(400).send({
                "error": "Bad Request", "message": `Character is not uncapped enough to unlock mana board.`
            });
        }
        const previousBoardToken = characterData.bondTokenList
            .find(token => token.manaBoardIndex === manaBoardIndex - 1);
        if (manaBoardIndex > 1 && 1 > ((_a = previousBoardToken === null || previousBoardToken === void 0 ? void 0 : previousBoardToken.status) !== null && _a !== void 0 ? _a : 0)) {
            console.warn(`[MANA] open_mana_board FAIL: prev board bond not claimed, prevBoard=${manaBoardIndex - 1} prevStatus=${previousBoardToken === null || previousBoardToken === void 0 ? void 0 : previousBoardToken.status}`);
            return reply.status(400).send({
                "error": "Bad Request", "message": `Must unlock all previous mana board nodes.`
            });
        }
        (0, character_1.updatePlayerCharacterSync)(playerId, characterId, { manaBoardIndex: manaBoardIndex });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": {
                "character_list": [{
                        "viewer_id": viewerId,
                        "character_id": characterId,
                        "mana_board_index": manaBoardIndex,
                        "create_time": (0, utils_2.clientSerializeDate)(characterData.joinTime),
                        "update_time": (0, utils_2.clientSerializeDate)(characterData.updateTime),
                        "join_time": (0, utils_2.clientSerializeDate)(characterData.joinTime)
                    }],
                "mail_arrived": false
            }
        });
    }));
});
exports.default = routes;
