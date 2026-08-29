"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.PartySlotValidator = void 0;
const player_1 = require("../../data/domains/player");
const PARTY_SLOT_MAX = 120;
exports.PartySlotValidator = {
    name: "party-slot",
    version: 1,
    validate(playerId, context) {
        var _a;
        const player = (_a = context === null || context === void 0 ? void 0 : context.player) !== null && _a !== void 0 ? _a : (0, player_1.getPlayerSync)(playerId);
        if (!(player === null || player === void 0 ? void 0 : player.id))
            return 0;
        if (player.partySlot >= 1 && player.partySlot <= PARTY_SLOT_MAX)
            return 0;
        (0, player_1.updatePlayerSync)({ id: playerId, partySlot: 1 });
        player.partySlot = 1;
        return 1;
    }
};
