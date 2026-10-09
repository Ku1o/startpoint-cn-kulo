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
exports.notifyEquipmentPartySaved = exports.freezeEquipmentSelections = exports.recordEquipmentPartyChange = exports.enforceRoomEquipmentReady = exports.enforceEquipmentReady = exports.setPreparation = exports.clearEquipmentBlock = exports.hasRestrictedEquipment = exports.selectedPartyId = exports.legalNpcParty = exports.exclusiveWirePartyItems = exports.EQUIPMENT_IDLE_MS = void 0;
const player_1 = require("../../data/domains/player");
const mode15_optional_1 = require("../../lib/mode15-optional");
const equipment_policy_1 = require("../npc/equipment-policy");
const SessionManager_1 = require("../state/SessionManager");
const embedded_1 = require("../coordinator/embedded");
const quest_party_snapshot_1 = require("../npc/quest-party-snapshot");
function getRoom(roomNumber) {
    return require("./manager").getRoom(roomNumber);
}
exports.EQUIPMENT_IDLE_MS = 30000;
/** Accept both the TCP Option encoding and the HTTP/plain party encoding. */
function exclusiveWirePartyItems(party) {
    return (0, equipment_policy_1.exclusivePartyItems)(party);
}
exports.exclusiveWirePartyItems = exclusiveWirePartyItems;
/** AI parties belong to the server, so normalize them before publishing a roster. */
function legalNpcParty(room, party) {
    if ((0, mode15_optional_1.isMode15EquipmentAllowedQuest)(room.category, room.quest_id)
        || exclusiveWirePartyItems(party).length === 0)
        return party;
    const result = Object.assign({}, party);
    for (const field of ["equipments", "equipmentIds", "equipment_ids",
        "abilitySoulIds", "ability_soul_ids"]) {
        if (!Array.isArray(party[field]))
            continue;
        result[field] = party[field].map((raw) => {
            if (!exclusiveWirePartyItems({ [field]: [raw] }).length)
                return raw;
            return Array.isArray(raw) ? [1] : null;
        });
    }
    return result;
}
exports.legalNpcParty = legalNpcParty;
function selectedPartyId(client) {
    var _a, _b, _c;
    // HTTP /party/edit can finish before TCP ChangeParty, while TCP can arrive
    // before the deferred player.partySlot write. Explicit changes win.
    return (_a = client.equipmentSelectedPartyId) !== null && _a !== void 0 ? _a : Number(((_b = (0, player_1.getPlayerSync)(Number(client.playerId))) === null || _b === void 0 ? void 0 : _b.partySlot)
        || ((_c = client.yourself) === null || _c === void 0 ? void 0 : _c.currentPartyId) || 1);
}
exports.selectedPartyId = selectedPartyId;
function hasRestrictedEquipment(room, client) {
    var _a;
    if ((0, mode15_optional_1.isMode15EquipmentAllowedQuest)(room.category, room.quest_id))
        return false;
    if (exclusiveWirePartyItems((_a = client.yourself) === null || _a === void 0 ? void 0 : _a.party).length)
        return true;
    return (0, mode15_optional_1.getMode15ExclusiveGlobalPartyItemsSync)(Number(client.playerId), 1, selectedPartyId(client)).length > 0;
}
exports.hasRestrictedEquipment = hasRestrictedEquipment;
function clearEquipmentBlock(client) {
    if (client.equipmentReadyBlock)
        clearTimeout(client.equipmentReadyBlock.timer);
    client.equipmentReadyBlock = undefined;
}
exports.clearEquipmentBlock = clearEquipmentBlock;
function setPreparation(client, forceReply = false) {
    var _a, _b;
    const room = getRoom(client.roomNumber);
    if (room)
        room.readyCountdownPending = false;
    const changed = client.isReady || ((_b = (_a = client.yourself) === null || _a === void 0 ? void 0 : _a.state) === null || _b === void 0 ? void 0 : _b[0]) === 1;
    client.isReady = false;
    if (client.yourself)
        client.yourself.state = [0];
    for (const mate of client.mates) {
        if (Number(mate.viewerId) === client.viewerId)
            mate.state = [0];
    }
    if (changed || forceReply) {
        SessionManager_1.sessionManager.broadcastToRoom(client.roomNumber, [1, [2, client.connectionId, [0]]], undefined, client.roomGeneration);
    }
}
exports.setPreparation = setPreparation;
function scheduleEquipmentExpiry(room, client) {
    if (client.equipmentReadyBlock)
        return;
    const state = {
        instanceId: room.lifecycle.instanceId,
        generation: room.lobby_generation,
        deadline: Date.now() + exports.EQUIPMENT_IDLE_MS,
        timer: undefined,
    };
    state.timer = setTimeout(() => {
        void embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(room.room_number, () => {
            if (client.equipmentReadyBlock !== state)
                return;
            const current = getRoom(room.room_number);
            clearEquipmentBlock(client);
            if (!current || current.lifecycle.instanceId !== state.instanceId
                || current.lobby_generation !== state.generation
                || current.lifecycle.phase !== "LOBBY"
                || SessionManager_1.sessionManager.getClient(client.viewerId, room.room_number) !== client
                || client.superseded || client.isBattle)
                return;
            if (!hasRestrictedEquipment(current, client))
                return;
            if (current.host_viewer_id === client.viewerId) {
                SessionManager_1.sessionManager.commitRoomDisband(current.room_number, "equipment_host_idle");
            }
            else {
                SessionManager_1.sessionManager.ejectEquipmentGuest(current.room_number, client.viewerId);
            }
        }).catch(error => console.error("[MULTI] equipment idle expiry failed", error));
    }, exports.EQUIPMENT_IDLE_MS);
    state.timer.unref();
    client.equipmentReadyBlock = state;
}
/** Only readiness attempts create a deadline. Heartbeats/retries never refresh it. */
function enforceEquipmentReady(room, client, forceReply = false) {
    if (!hasRestrictedEquipment(room, client)) {
        clearEquipmentBlock(client);
        return true;
    }
    setPreparation(client, forceReply);
    SessionManager_1.sessionManager.clearRescueGuestLobbyWait(client.roomNumber, client.viewerId);
    scheduleEquipmentExpiry(room, client);
    return false;
}
exports.enforceEquipmentReady = enforceEquipmentReady;
/** Run inside the room queue; no generation can start with a known invalid peer. */
function enforceRoomEquipmentReady(room, generation = room.lobby_generation) {
    let allowed = true;
    for (const client of SessionManager_1.sessionManager.getClientsInRoom(room.room_number, generation)) {
        if (client.isBattle || client.superseded || !client.yourself || client.enterData === null)
            continue;
        if (!enforceEquipmentReady(room, client))
            allowed = false;
    }
    if (!allowed) {
        const host = SessionManager_1.sessionManager.getClient(room.host_viewer_id, room.room_number);
        if (host)
            setPreparation(host);
    }
    return allowed;
}
exports.enforceRoomEquipmentReady = enforceRoomEquipmentReady;
function recordEquipmentPartyChange(client, partyId, userAction = true) {
    var _a, _b;
    if (Number.isSafeInteger(partyId) && partyId >= 1 && partyId <= 120) {
        client.equipmentSelectedPartyId = partyId;
    }
    // A meaningful edit grants another 30s; rechecking itself must not do so.
    const wasBlocked = !!client.equipmentReadyBlock;
    if (userAction)
        clearEquipmentBlock(client);
    const room = getRoom(client.roomNumber);
    if (!room || room.lifecycle.phase !== "LOBBY"
        || client.roomGeneration !== room.lobby_generation)
        return;
    if (wasBlocked || client.isReady || ((_b = (_a = client.yourself) === null || _a === void 0 ? void 0 : _a.state) === null || _b === void 0 ? void 0 : _b[0]) === 1) {
        enforceEquipmentReady(room, client);
    }
}
exports.recordEquipmentPartyChange = recordEquipmentPartyChange;
/** Freeze the checked selection so late lobby edits cannot change this battle. */
function freezeEquipmentSelections(room, generation = room.lobby_generation) {
    var _a;
    room.equipmentPartyIds = {};
    room.npcPartySnapshots = {};
    for (const client of SessionManager_1.sessionManager.getClientsInRoom(room.room_number, generation)) {
        if (client.isBattle || !client.playerId || client.enterData === null)
            continue;
        const partyId = selectedPartyId(client);
        room.equipmentPartyIds[client.viewerId] = partyId;
        try {
            const snapshot = (0, quest_party_snapshot_1.captureQuestNpcPartySnapshot)(Number(client.playerId), room.category, room.quest_id, partyId, (_a = client.yourself) === null || _a === void 0 ? void 0 : _a.party);
            if (snapshot)
                room.npcPartySnapshots[client.viewerId] = snapshot;
        }
        catch (error) {
            // History is optional; a capture failure must not reject the battle.
            console.error("[MULTI] NPC clear-party capture failed", error);
        }
        clearEquipmentBlock(client);
    }
}
exports.freezeEquipmentSelections = freezeEquipmentSelections;
function notifyEquipmentPartySaved(playerId, changedPartyIds, selectionChanged) {
    return __awaiter(this, void 0, void 0, function* () {
        if (!selectionChanged && !changedPartyIds.length)
            return;
        for (const client of SessionManager_1.sessionManager.getLobbyClientsForPlayer(playerId)) {
            yield embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(client.roomNumber, () => {
                var _a;
                const room = getRoom(client.roomNumber);
                if (!room || room.lifecycle.phase !== "LOBBY"
                    || client.roomGeneration !== room.lobby_generation
                    || SessionManager_1.sessionManager.getClient(client.viewerId, client.roomNumber) !== client)
                    return;
                const selected = (_a = (0, player_1.getPlayerSync)(playerId)) === null || _a === void 0 ? void 0 : _a.partySlot;
                if (selected === undefined || (!selectionChanged && !changedPartyIds.includes(selected)))
                    return;
                recordEquipmentPartyChange(client, selected);
                // Do not replace the client's wire party with a DB edit. Wait for
                // ChangeParty to agree before allowing the next Ready.
                setPreparation(client, true);
                const lobby = require("../tcp/lobby");
                lobby.refreshEquipmentReadiness(client.roomNumber);
            });
        }
    });
}
exports.notifyEquipmentPartySaved = notifyEquipmentPartySaved;
