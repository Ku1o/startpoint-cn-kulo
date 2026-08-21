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
exports.detachLoungeSocket = exports.handleLoungeMessage = exports.handleLoungeHandshake = void 0;
const session_1 = require("../data/domains/session");
const state_1 = require("./state");
Object.defineProperty(exports, "detachLoungeSocket", { enumerable: true, get: function () { return state_1.detachLoungeSocket; } });
const protocol_1 = require("./protocol");
function positiveSafeInteger(value) {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}
function deny(socket, message = protocol_1.LOUNGE_DISMISSED_MESSAGE) {
    (0, state_1.sendLoungeFrame)(socket, [1, message]);
    socket.end();
}
function handleLoungeHandshake(socket, data) {
    return __awaiter(this, void 0, void 0, function* () {
        const viewerId = positiveSafeInteger(data.viewerId);
        const loungeId = positiveSafeInteger(data.loungeId);
        const useCase = positiveSafeInteger(data.useCase);
        const establisherViewerId = positiveSafeInteger(data.establisherViewerId);
        const advice = typeof data.advice === "string" ? data.advice : "";
        if (viewerId === null || loungeId === null || useCase === null || establisherViewerId === null || advice.length === 0) {
            deny(socket);
            return;
        }
        const session = yield (0, session_1.getSession)(String(viewerId));
        const room = (0, state_1.getLounge)(loungeId);
        if (!session || !room || !(0, state_1.matchesLoungeAccess)(room, { useCase, advice, establisherViewerId })
            || !(0, state_1.canAttachLoungeViewer)(room, viewerId)) {
            deny(socket);
            return;
        }
        (0, state_1.attachLoungeSocket)(room, viewerId, socket);
        (0, state_1.sendLoungeFrame)(socket, [0, `lounge-${viewerId}`, loungeId]);
    });
}
exports.handleLoungeHandshake = handleLoungeHandshake;
function handleLoungeMessage(socket, value) {
    if (!Array.isArray(value) || Number(value[0]) !== 0 || !Array.isArray(value[1]))
        return;
    const notify = value[1];
    const kind = Number(notify[0]);
    if (kind === 0) {
        const profile = notify[1];
        if (!profile || typeof profile !== "object" || Array.isArray(profile))
            return;
        const entered = (0, state_1.enterLounge)(socket, profile);
        if (!entered)
            return;
        const mates = (0, state_1.serializeLoungeMates)(entered.room);
        (0, state_1.sendLoungeFrame)(socket, [1, [3, mates]]);
        (0, state_1.broadcastLoungeFrame)(entered.room, [1, [4, mates]]);
        return;
    }
    const context = (0, state_1.getLoungeSocketContext)(socket);
    if (!context || !context.member)
        return;
    switch (kind) {
        case 1:
            (0, state_1.touchLoungeActivity)(context.room);
            (0, state_1.sendLoungeFrame)(socket, [1, [7, context.viewerId]]);
            break;
        case 2:
            break;
        case 3: {
            const readyState = Array.isArray(notify[1]) ? notify[1] : [0];
            if ((0, state_1.setLoungeMemberReady)(context.room, context.viewerId, readyState)) {
                (0, state_1.broadcastLoungeFrame)(context.room, [1, [0, context.viewerId, readyState]]);
            }
            break;
        }
        case 4:
            if (context.viewerId !== context.room.hostViewerId || !(0, state_1.loungeCanStart)(context.room)) {
                (0, state_1.sendLoungeFrame)(socket, [1, [6, [1]]]);
                break;
            }
            context.room.raisingState = 97;
            (0, state_1.broadcastLoungeFrame)(context.room, [1, [5]]);
            break;
        case 5:
            break;
        case 6:
            (0, state_1.detachLoungeSocket)(socket, true);
            break;
    }
}
exports.handleLoungeMessage = handleLoungeMessage;
