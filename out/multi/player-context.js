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
exports.resolveMultiPlayerContext = void 0;
const activeAccount_1 = require("../data/activeAccount");
const player_1 = require("../data/domains/player");
const session_1 = require("../data/domains/session");
/** Resolve a multiplayer viewer token to that account's selected save. */
function resolveMultiPlayerContext(viewerId_1) {
    return __awaiter(this, arguments, void 0, function* (viewerId, dependencies = {}) {
        var _a, _b, _c;
        if (!Number.isSafeInteger(viewerId) || viewerId <= 0)
            return null;
        const session = yield ((_a = dependencies.getSession) !== null && _a !== void 0 ? _a : session_1.getSession)(String(viewerId));
        if (!session)
            return null;
        const playerId = ((_b = dependencies.resolvePlayerIdSync) !== null && _b !== void 0 ? _b : activeAccount_1.resolvePlayerIdSync)(session.accountId);
        if (!playerId)
            return null;
        const player = ((_c = dependencies.getPlayerSync) !== null && _c !== void 0 ? _c : player_1.getPlayerSync)(playerId);
        if (!player)
            return null;
        return { playerId, player };
    });
}
exports.resolveMultiPlayerContext = resolveMultiPlayerContext;
