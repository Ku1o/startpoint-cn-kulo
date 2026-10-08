"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.isNpcPartyAllowedInRoom = void 0;
const mode15_optional_1 = require("../../lib/mode15-optional");
const PARTY_ITEM_FIELDS = [
    "equipments",
    "equipmentIds",
    "equipment_ids",
    "abilitySoulIds",
    "ability_soul_ids",
];
const FANTASY_ITEM_IDS = new Set(Array.from({ length: 11 }, (_, index) => 100013 + index));
function itemId(raw) {
    var _a, _b, _c, _d;
    const value = Array.isArray(raw)
        ? (raw[0] === 0 ? raw[1] : null)
        : raw;
    if (!value || typeof value !== "object")
        return value;
    return (_d = (_c = (_b = (_a = value.equipmentId) !== null && _a !== void 0 ? _a : value.equipment_id) !== null && _b !== void 0 ? _b : value.abilitySoulId) !== null && _c !== void 0 ? _c : value.ability_soul_id) !== null && _d !== void 0 ? _d : value.id;
}
function isFantasyItem(raw) {
    const id = Number(itemId(raw));
    return FANTASY_ITEM_IDS.has(id)
        || (0, mode15_optional_1.getMode15ExclusiveItemIds)([id]).length > 0;
}
/**
 * Reject a complete AI party if it carries Fantasy-only equipment outside a
 * Fantasy quest. The party must never enter a room in a silently altered form.
 */
function isNpcPartyAllowedInRoom(category, questId, party) {
    if (!party || typeof party !== "object")
        return false;
    if (category !== undefined && questId !== undefined
        && (0, mode15_optional_1.isMode15EquipmentAllowedQuest)(category, questId))
        return true;
    for (const field of PARTY_ITEM_FIELDS) {
        const values = party[field];
        if (!Array.isArray(values))
            continue;
        if (values.some(isFantasyItem))
            return false;
    }
    return true;
}
exports.isNpcPartyAllowedInRoom = isNpcPartyAllowedInRoom;
