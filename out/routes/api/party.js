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
const player_1 = require("../../data/domains/player");
const session_1 = require("../../data/domains/session");
const character_1 = require("../../data/domains/character");
const equipment_1 = require("../../data/domains/equipment");
const party_1 = require("../../data/domains/party");
const db_1 = require("../../data/db");
const active_mission_counters_1 = require("../../data/domains/active_mission_counters");
const utils_1 = require("../../utils");
const activeAccount_1 = require("../../data/activeAccount");
const special_event_parties_1 = require("../../lib/special-event-parties");
const publishedParty_1 = require("../../data/domains/publishedParty");
const game_logging_1 = require("../../lib/game-logging");
const profileFavorite_1 = require("../../lib/profileFavorite");
const counters_1 = require("../../lib/mission/counters");
const degree_response_1 = require("../../lib/mission/degree-response");
const ability_soul_facts_1 = require("../../lib/mission/ability-soul-facts");
function hasEditablePartyCategory(value) {
    if (value !== null
        && typeof value === "object"
        && "party_category" in value
        && value.party_category
            === profileFavorite_1.PROFILE_FAVORITE_PARTY_CATEGORY) {
        return true;
    }
    return (0, special_event_parties_1.hasValidPartyCategory)(value);
}
const isObject = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
const asInteger = (value) => typeof value === "number" && Number.isSafeInteger(value) ? value : null;
function sanitizeIntegerArray(value, maxLength) {
    if (!Array.isArray(value) || value.length > maxLength)
        return null;
    const result = [];
    for (const entry of value) {
        const integer = asInteger(entry);
        if (integer === null)
            return null;
        result.push(integer);
    }
    return result;
}
function sanitizeCharacter(value) {
    if (value === null)
        return null;
    if (!isObject(value))
        return undefined;
    const id = asInteger(value.id);
    const evolutionLevel = asInteger(value.evolution_level);
    const exp = asInteger(value.exp);
    const overLimitStep = asInteger(value.over_limit_step);
    if (id === null || evolutionLevel === null || exp === null || overLimitStep === null)
        return undefined;
    let manaNodeIds = null;
    if (value.mana_node_ids !== null && value.mana_node_ids !== undefined) {
        manaNodeIds = sanitizeIntegerArray(value.mana_node_ids, 256);
        if (manaNodeIds === null)
            return undefined;
    }
    let illustrationSettings = null;
    if (value.illustration_settings !== null && value.illustration_settings !== undefined) {
        illustrationSettings = sanitizeIntegerArray(value.illustration_settings, 32);
        if (illustrationSettings === null)
            return undefined;
    }
    let exBoost = null;
    if (value.ex_boost !== null && value.ex_boost !== undefined) {
        if (!isObject(value.ex_boost))
            return undefined;
        const statusId = asInteger(value.ex_boost.status_id);
        const abilityIdList = sanitizeIntegerArray(value.ex_boost.ability_id_list, 32);
        if (statusId === null || abilityIdList === null)
            return undefined;
        exBoost = { status_id: statusId, ability_id_list: abilityIdList };
    }
    return {
        id,
        mana_node_ids: manaNodeIds,
        evolution_level: evolutionLevel,
        exp,
        over_limit_step: overLimitStep,
        illustration_settings: illustrationSettings,
        ex_boost: exBoost,
    };
}
function sanitizeCharacterArray(value) {
    if (!Array.isArray(value) || value.length !== 3)
        return null;
    const result = [];
    for (const entry of value) {
        const character = sanitizeCharacter(entry);
        if (character === undefined)
            return null;
        result.push(character);
    }
    return result;
}
function sanitizeEquipmentArray(value) {
    if (!Array.isArray(value) || value.length !== 3)
        return null;
    const result = [];
    for (const entry of value) {
        if (entry === null) {
            result.push(null);
            continue;
        }
        if (!isObject(entry))
            return null;
        const equipmentId = asInteger(entry.equipment_id);
        const level = asInteger(entry.level);
        if (equipmentId === null || level === null)
            return null;
        result.push({ equipment_id: equipmentId, level });
    }
    return result;
}
function sanitizeAbilitySoulArray(value) {
    if (!Array.isArray(value) || value.length !== 3)
        return null;
    const result = [];
    for (const entry of value) {
        if (entry === null) {
            result.push(null);
            continue;
        }
        const id = asInteger(entry);
        if (id === null)
            return null;
        result.push(id);
    }
    return result;
}
function sanitizeBattleParty(value) {
    if (!isObject(value))
        return null;
    const characters = sanitizeCharacterArray(value.characters);
    const unisonCharacters = sanitizeCharacterArray(value.unison_characters);
    const equipments = sanitizeEquipmentArray(value.equipments);
    const abilitySoulIds = sanitizeAbilitySoulArray(value.ability_soul_ids);
    if (!characters || !unisonCharacters || !equipments || !abilitySoulIds)
        return null;
    return {
        characters,
        unison_characters: unisonCharacters,
        equipments,
        ability_soul_ids: abilitySoulIds,
    };
}
function resolvePartyPlayer(body) {
    return __awaiter(this, void 0, void 0, function* () {
        const viewerId = Number(body === null || body === void 0 ? void 0 : body.viewer_id);
        if (!Number.isFinite(viewerId))
            return null;
        const session = yield (0, session_1.getSession)(String(viewerId));
        if (!session)
            return null;
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(session.accountId);
        return playerId === null ? null : { viewerId, playerId };
    });
}
function sendPartyResponse(reply, viewerId, data, resultCode = 1) {
    reply.header("content-type", "application/x-msgpack");
    return reply.status(200).send({
        data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId, result_code: resultCode }),
        data,
    });
}
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/publish", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const context = yield resolvePartyPlayer(body);
        if (!context)
            return reply.status(400).send({ error: "Bad Request", message: "Invalid viewer id." });
        if (typeof body.party_name !== "string" || body.party_name.length > 100) {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid party name." });
        }
        const battleParty = sanitizeBattleParty(body.battle_party);
        if (!battleParty || JSON.stringify(battleParty).length > 65536) {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid battle party." });
        }
        const partyCode = (0, publishedParty_1.publishPartySync)(context.playerId, body.party_name, battleParty);
        console.log(`[PARTY CODE] publish player=${context.playerId} code=${partyCode}`);
        return sendPartyResponse(reply, context.viewerId, { party_code: partyCode });
    }));
    fastify.post("/refer", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const context = yield resolvePartyPlayer(body);
        if (!context)
            return reply.status(400).send({ error: "Bad Request", message: "Invalid viewer id." });
        const partyCode = typeof body.party_code === "string" ? body.party_code.trim().toUpperCase() : "";
        if (!/^[2-9A-HJ-NP-Z]{10}$/.test(partyCode)) {
            return sendPartyResponse(reply, context.viewerId, {}, 3404);
        }
        const publishedParty = (0, publishedParty_1.getPublishedPartySync)(partyCode);
        if (!publishedParty)
            return sendPartyResponse(reply, context.viewerId, {}, 3404);
        if (publishedParty.schemaVersion !== 1)
            return sendPartyResponse(reply, context.viewerId, {}, 3403);
        const battleParty = sanitizeBattleParty(publishedParty.battleParty);
        if (!battleParty)
            return sendPartyResponse(reply, context.viewerId, {}, 3403);
        console.log(`[PARTY CODE] refer player=${context.playerId} code=${partyCode}`);
        return sendPartyResponse(reply, context.viewerId, {
            party_name: publishedParty.partyName,
            battle_party: battleParty,
        });
    }));
    fastify.post("/edit", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            });
        if (!Array.isArray(body.party_info_list)
            || body.party_info_list.some(info => !hasEditablePartyCategory(info)
                || (0, special_event_parties_1.parseGlobalPartyId)(info.party_id) === null)) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid party category or party ID."
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
        const player = playerId !== null ? (0, player_1.getPlayerSync)(playerId) : null;
        if (player === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        // update each slot
        const characterOwnedMap = {};
        const equipmentOwnedMap = {};
        const editCategories = [];
        for (const updateInfo of body.party_info_list) {
            editCategories.push(updateInfo.party_category);
        }
        (0, game_logging_1.gameVerboseLog)(() => `[PARTY] edit: viewer=${viewerId} parties=${body.party_info_list.length} categories=${JSON.stringify(editCategories)} mainPartyId=${body.main_party_id}`);
        const mapOwnedCharacters = (characterId) => {
            let isOwned = characterId === null ? false : characterOwnedMap[characterId];
            if (isOwned === undefined) {
                isOwned = (0, character_1.playerOwnsCharacterSync)(playerId, characterId);
                characterOwnedMap[characterId] = isOwned;
            }
            return isOwned ? characterId : null;
        };
        const mapOwnedEquipment = (equipmentId) => {
            let isOwned = equipmentId === null ? false : equipmentOwnedMap[equipmentId];
            if (isOwned === undefined) {
                isOwned = (0, equipment_1.playerOwnsEquipmentSync)(playerId, equipmentId);
                equipmentOwnedMap[equipmentId] = isOwned;
            }
            return isOwned ? equipmentId : null;
        };
        const mappedParties = body.party_info_list.map(updateInfo => {
            var _a, _b;
            const parsed = (0, special_event_parties_1.parseGlobalPartyId)(updateInfo.party_id);
            (0, game_logging_1.gameVerboseLog)(() => { var _a; return `[PARTY] edit: player=${playerId} id=${updateInfo.party_id} -> group=${parsed.groupId} slot=${parsed.slot} name="${updateInfo.party_name}" chars=${((_a = updateInfo.character_ids) === null || _a === void 0 ? void 0 : _a.filter(Boolean).length) || 0}`; });
            return {
                parsed,
                party: {
                    name: updateInfo.party_name,
                    unisonCharacterIds: updateInfo.unison_character_ids.map(mapOwnedCharacters),
                    characterIds: updateInfo.character_ids.map(mapOwnedCharacters),
                    equipmentIds: updateInfo.equipment_ids.map(mapOwnedEquipment), // TODO: Implement stack checking, to see if more equipment is being equipped than is owned.
                    abilitySoulIds: updateInfo.ability_soul_ids,
                    options: { allowOtherPlayersToHealMe: updateInfo.options.allow_other_players_to_heal_me },
                    edited: updateInfo.party_edited,
                    category: updateInfo.party_category,
                    currentBattlePower: (_a = updateInfo.current_battle_power) !== null && _a !== void 0 ? _a : 0,
                    beforeBattlePower: (_b = updateInfo.before_battle_power) !== null && _b !== void 0 ? _b : 0,
                },
            };
        });
        (0, db_1.getDb)().transaction(() => {
            const battleParties = mappedParties.filter(({ party }) => party.category !== profileFavorite_1.PROFILE_FAVORITE_PARTY_CATEGORY);
            let abilitySoulEquipCount = 0;
            const getPreviousSouls = (0, db_1.getDb)().prepare(`
                SELECT ability_soul_1, ability_soul_2, ability_soul_3
                FROM players_parties
                WHERE player_id = ? AND group_id = ? AND slot = ? AND category = ?
            `);
            // store full global PartyId so /load returns the correct group+slot combo
            // Editing profile favorites is independent from the battle SET selected
            // by the player. Empty edits are still used by the client to switch SETs.
            if ((mappedParties.length === 0 || battleParties.length > 0)
                && player.partySlot !== body.main_party_id) {
                (0, player_1.updatePlayerSync)({
                    id: playerId,
                    partySlot: body.main_party_id,
                });
            }
            for (const { parsed, party } of mappedParties) {
                if (party.category !== profileFavorite_1.PROFILE_FAVORITE_PARTY_CATEGORY) {
                    const previous = getPreviousSouls.get(playerId, parsed.groupId, parsed.slot, party.category);
                    const previousIds = previous
                        ? [previous.ability_soul_1, previous.ability_soul_2, previous.ability_soul_3]
                        : [];
                    abilitySoulEquipCount += (0, ability_soul_facts_1.countNewAbilitySoulEquipments)(previousIds, party.abilitySoulIds);
                }
                (0, party_1.updatePlayerPartySync)(playerId, parsed.slot, party, parsed.groupId);
            }
            if (abilitySoulEquipCount > 0) {
                (0, counters_1.addMissionCounterSync)(playerId, {
                    dimension: "party.ability_soul_equip",
                    scopeType: "lifetime",
                    scopeKey: "all",
                    qualifier: {},
                }, abilitySoulEquipCount);
            }
            if (battleParties.length > 0) {
                (0, active_mission_counters_1.incrementActiveMissionPartyActionCountsSync)(playerId, {
                    equipmentEquipCount: battleParties.some(({ party }) => party.equipmentIds.some(id => id !== null)) ? 1 : 0,
                    unisonSetCount: battleParties.some(({ party }) => party.unisonCharacterIds.some(id => id !== null)) ? 1 : 0,
                    partyCharacterSetCount: battleParties.some(({ party }) => party.characterIds.some(id => id !== null)) ? 1 : 0,
                });
            }
        })();
        const responseData = { mail_arrived: false };
        (0, degree_response_1.settleDegreeMissionResponse)(playerId, viewerId, responseData, undefined, [35]);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            }),
            "data": responseData
        });
    }));
    fastify.post("/check_word", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": { "check_passed": true }
        });
    }));
});
exports.default = routes;
