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
exports.NpcMateProvider = exports.selectStableNpcSlots = void 0;
const builder_1 = require("./builder");
const manager_1 = require("../room/manager");
function selectStableNpcSlots(recruitedMates, count) {
    const desiredCount = Math.max(0, Math.min(2, Math.floor(count)));
    if (desiredCount === 0)
        return [];
    // Real players replace COM seats from the front (COM1, then COM2). Keep
    // the remaining tail seats when the lobby is rebuilt so a 2R1B rematch
    // does not silently change the surviving bot from COM2 back to COM1.
    return [...recruitedMates]
        .sort((left, right) => left.com_id - right.com_id)
        .slice(-desiredCount);
}
exports.selectStableNpcSlots = selectStableNpcSlots;
class NpcMateProvider {
    getMates(roomNumber) {
        const room = (0, manager_1.getRoom)(roomNumber);
        const { mate1, mate2 } = (0, builder_1.buildNpcMates)(room === null || room === void 0 ? void 0 : room.quest_id, room === null || room === void 0 ? void 0 : room.category);
        return [mate1, mate2].filter((m) => m !== null);
    }
    onRecruit(roomNumber, hostViewerId) {
        return __awaiter(this, void 0, void 0, function* () {
            return {
                recruitedMates: [
                    { viewer_id: 900000001, com_id: 1 },
                    { viewer_id: 900000002, com_id: 2 },
                ],
            };
        });
    }
    isRoomFull(roomNumber) {
        return true;
    }
    getAvailableCompanions(hostViewerId) {
        return [];
    }
}
exports.NpcMateProvider = NpcMateProvider;
