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
const crypto_1 = require("crypto");
const activeAccount_1 = require("../../data/activeAccount");
const character_1 = require("../../data/domains/character");
const player_1 = require("../../data/domains/player");
const session_1 = require("../../data/domains/session");
const multi_special_exchange_1 = require("../../lib/multi-special-exchange");
const eligibility_1 = require("../../lounge/eligibility");
const state_1 = require("../../lounge/state");
const serializer_1 = require("../../multi/room/serializer");
const utils_1 = require("../../utils");
const protocol_1 = require("../../lounge/protocol");
function positiveSafeInteger(value) {
    if (typeof value !== "number" && (typeof value !== "string" || !/^\d+$/.test(value)))
        return null;
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}
function requestBody(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function resolveViewer(body) {
    return __awaiter(this, void 0, void 0, function* () {
        const viewerId = positiveSafeInteger(body.viewer_id);
        if (viewerId === null)
            return null;
        const session = yield (0, session_1.getSession)(String(viewerId));
        if (!session)
            return null;
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(session.accountId);
        if (playerId === null)
            return null;
        const player = (0, player_1.getPlayerSync)(playerId);
        return player ? { viewerId, playerId, player } : null;
    });
}
function hasAccess(room, body) {
    const useCase = positiveSafeInteger(body.use_case);
    const establisherViewerId = positiveSafeInteger(body.establisher_viewer_id);
    return !!room && useCase === 1 && !!(0, multi_special_exchange_1.getMultiSpecialExchangeCampaignDefinition)(room.campaignId) && establisherViewerId !== null
        && typeof body.advice === "string"
        && (0, state_1.matchesLoungeAccess)(room, {
            useCase,
            advice: body.advice,
            establisherViewerId,
        });
}
function connectionData(room) {
    return {
        application_update_url: "",
        ip_address: (0, serializer_1.getDisplayHost)(),
        lounge_number: room.number,
        port: Number.parseInt(process.env.SESSION_PORT || "8003", 10),
        raising_state: room.raisingState,
    };
}
function loungeListEntry(room) {
    return {
        advice: room.advice,
        establisher_character: room.hostProfile.characterId,
        establisher_character_evolution_img_level: room.hostProfile.characterEvolutionLevel,
        establisher_follow: 0,
        establisher_name: room.hostProfile.name,
        establisher_viewer_id: room.hostViewerId,
        lounge_id: room.id,
        mates: Math.max(1, (0, state_1.getLoungeOccupancy)(room)),
        raising_state: room.raisingState,
        use_case: room.useCase,
    };
}
function sendLoungeNotFound(reply, viewerId) {
    reply.header("content-type", "application/x-msgpack");
    return reply.status(200).send({
        data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId, result_code: 4511 }),
        data: {},
    });
}
function sendLoungeDisbanded(reply, viewerId, loungeId, operation) {
    // This is a recoverable client state, not an account/login failure. The
    // client recognizes raising_state=99 and removes lounge_restore_data.
    console.warn(`[LOUNGE] stale ${operation}: viewer=${viewerId} lounge=${loungeId}; returning disbanded state`);
    reply.header("content-type", "application/x-msgpack");
    return reply.status(200).send({
        data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
        data: (0, protocol_1.buildLoungeDisbandedConnectionData)(),
    });
}
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/get_list", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a;
        const body = requestBody(request.body);
        const context = yield resolveViewer(body);
        const useCase = positiveSafeInteger(body.use_case);
        if (!context || useCase !== 1)
            return sendLoungeNotFound(reply, (_a = context === null || context === void 0 ? void 0 : context.viewerId) !== null && _a !== void 0 ? _a : 0);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: context.viewerId }),
            data: { lounge_list: (0, state_1.listLounges)(useCase).filter(room => (0, eligibility_1.canParticipateInLounge)(context.playerId, room.campaignId)).map(loungeListEntry) },
        });
    }));
    fastify.post("/create", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _b, _c;
        const body = requestBody(request.body);
        const context = yield resolveViewer(body);
        const useCase = positiveSafeInteger(body.use_case);
        const campaignId = positiveSafeInteger(body.campaign_id);
        if (!context || useCase !== 1 || campaignId === null
            || !(0, multi_special_exchange_1.getMultiSpecialExchangeCampaignDefinition)(campaignId)
            || !(0, eligibility_1.canParticipateInLounge)(context.playerId, campaignId)) {
            return sendLoungeNotFound(reply, (_b = context === null || context === void 0 ? void 0 : context.viewerId) !== null && _b !== void 0 ? _b : 0);
        }
        const characterId = Number(context.player.leaderCharacterId) || 1;
        const character = (0, character_1.getPlayerCharacterSync)(context.playerId, characterId);
        const room = (0, state_1.createLounge)({
            advice: (0, crypto_1.randomUUID)(),
            useCase,
            campaignId,
            hostViewerId: context.viewerId,
            hostPlayerId: context.playerId,
            hostProfile: {
                name: context.player.name || `Player${context.viewerId}`,
                characterId,
                characterEvolutionLevel: (_c = character === null || character === void 0 ? void 0 : character.evolutionLevel) !== null && _c !== void 0 ? _c : 0,
            },
        });
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: context.viewerId }),
            data: { advice: room.advice, lounge_id: room.id },
        });
    }));
    fastify.post("/prepare", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _d;
        const body = requestBody(request.body);
        const context = yield resolveViewer(body);
        const loungeId = positiveSafeInteger(body.lounge_id);
        if (!context || loungeId === null)
            return sendLoungeNotFound(reply, (_d = context === null || context === void 0 ? void 0 : context.viewerId) !== null && _d !== void 0 ? _d : 0);
        const room = (0, state_1.getLounge)(loungeId);
        if (!hasAccess(room, body) || context.viewerId !== room.hostViewerId) {
            return sendLoungeDisbanded(reply, context.viewerId, loungeId, "prepare");
        }
        (0, state_1.prepareLounge)(room);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: context.viewerId }),
            data: {},
        });
    }));
    fastify.post("/select", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _e;
        const body = requestBody(request.body);
        const context = yield resolveViewer(body);
        const loungeId = positiveSafeInteger(body.lounge_id);
        if (!context || loungeId === null)
            return sendLoungeNotFound(reply, (_e = context === null || context === void 0 ? void 0 : context.viewerId) !== null && _e !== void 0 ? _e : 0);
        const room = (0, state_1.getLounge)(loungeId);
        if (!hasAccess(room, body))
            return sendLoungeDisbanded(reply, context.viewerId, loungeId, "select");
        if (!(0, eligibility_1.canParticipateInLounge)(context.playerId, room.campaignId) || !(0, state_1.canAttachLoungeViewer)(room, context.viewerId)) {
            return sendLoungeNotFound(reply, context.viewerId);
        }
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: context.viewerId }),
            data: connectionData(room),
        });
    }));
    fastify.post("/search", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _f;
        const body = requestBody(request.body);
        const context = yield resolveViewer(body);
        const useCase = positiveSafeInteger(body.use_case);
        if (!context || useCase !== 1 || typeof body.lounge_number !== "string") {
            return sendLoungeNotFound(reply, (_f = context === null || context === void 0 ? void 0 : context.viewerId) !== null && _f !== void 0 ? _f : 0);
        }
        const room = (0, state_1.getLoungeByNumber)(body.lounge_number);
        const data = room && room.useCase === useCase && room.raisingState === 2
            && !!(0, multi_special_exchange_1.getMultiSpecialExchangeCampaignDefinition)(room.campaignId)
            && (0, eligibility_1.canParticipateInLounge)(context.playerId, room.campaignId)
            && (0, state_1.canAttachLoungeViewer)(room, context.viewerId)
            ? {
                lounge_exists: true,
                advice: room.advice,
                establisher_follow: 0,
                establisher_viewer_id: room.hostViewerId,
                lounge_id: room.id,
            }
            : { lounge_exists: false };
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: context.viewerId }),
            data,
        });
    }));
    fastify.post("/restore", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _g;
        const body = requestBody(request.body);
        const context = yield resolveViewer(body);
        const loungeId = positiveSafeInteger(body.lounge_id);
        if (!context || loungeId === null)
            return sendLoungeNotFound(reply, (_g = context === null || context === void 0 ? void 0 : context.viewerId) !== null && _g !== void 0 ? _g : 0);
        const room = (0, state_1.getLounge)(loungeId);
        if (!hasAccess(room, body) || (room.raisingState === 2 && !(0, eligibility_1.canParticipateInLounge)(context.playerId, room.campaignId))) {
            return sendLoungeDisbanded(reply, context.viewerId, loungeId, "restore");
        }
        const data = connectionData(room);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: context.viewerId }),
            data: { ip_address: data.ip_address, port: data.port, raising_state: data.raising_state },
        });
    }));
    fastify.post("/share", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _h;
        const body = requestBody(request.body);
        const context = yield resolveViewer(body);
        const loungeId = positiveSafeInteger(body.lounge_id);
        if (!context || loungeId === null || !Array.isArray(body.share_type_list)) {
            return sendLoungeNotFound(reply, (_h = context === null || context === void 0 ? void 0 : context.viewerId) !== null && _h !== void 0 ? _h : 0);
        }
        const room = (0, state_1.getLounge)(loungeId);
        if (!hasAccess(room, body) || context.viewerId !== room.hostViewerId) {
            return sendLoungeNotFound(reply, context.viewerId);
        }
        (0, state_1.setLoungeShareTypes)(room, body.share_type_list.map(Number).filter(Number.isSafeInteger));
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: context.viewerId }),
            data: {},
        });
    }));
});
exports.default = routes;
