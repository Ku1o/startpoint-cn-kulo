"use strict";
// Multi battle TCP session handshake
// Protocol: JSON messages delimited by null byte (\0)
// Post-handshake messages use typepacker format with useEnumIndex=true:
//   [index, param1, param2, ...]
//
// HandshakeResult: Accept=0, Denied=1, Reconnect=2, Exception=3, Complete=4
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
exports.handleHandshake = exports.buildRealParty = void 0;
const party_1 = require("../../data/domains/party");
const character_1 = require("../../data/domains/character");
const equipment_1 = require("../../data/domains/equipment");
const types_1 = require("../../data/types");
const stamina_1 = require("../../lib/stamina");
const manager_1 = require("../room/manager");
const SessionManager_1 = require("../state/SessionManager");
const game_logging_1 = require("../../lib/game-logging");
const types_2 = require("../types");
const embedded_1 = require("../coordinator/embedded");
const admission_1 = require("../room/admission");
const player_context_1 = require("../player-context");
function buildRealParty(playerId, targetParty) {
    var _a, _b, _c, _d;
    const emptyChar = [1];
    const filledChars = [];
    const filledUnison = [];
    const filledEquips = [];
    const filledSouls = [];
    // Search for an NPC-named party across NORMAL and EVENT categories
    let selectedParty = targetParty !== null && targetParty !== void 0 ? targetParty : null;
    if (!selectedParty) {
        for (const category of [types_1.PartyCategory.NORMAL, types_1.PartyCategory.EVENT]) {
            const groups = (0, party_1.getPlayerPartyGroupListSync)(playerId, category);
            for (const g of Object.values(groups)) {
                for (const party of Object.values(g.list)) {
                    if (party.name && party.name.includes("NPC")) {
                        selectedParty = party;
                        break;
                    }
                }
                if (selectedParty)
                    break;
            }
            if (selectedParty)
                break;
        }
    }
    for (let i = 0; i < 3; i++) {
        const charId = (_a = selectedParty === null || selectedParty === void 0 ? void 0 : selectedParty.characterIds[i]) !== null && _a !== void 0 ? _a : null;
        if (!charId) {
            filledChars.push([1]);
            filledUnison.push([1]);
        }
        else {
            const dbChar = (0, character_1.getPlayerCharacterSync)(playerId, charId);
            if (!dbChar) {
                filledChars.push([1]);
                filledUnison.push([1]);
            }
            else {
                const rawManaNodes = (0, character_1.getPlayerCharacterManaNodesSync)(playerId, charId);
                const manaNodeMap = {};
                for (const id of rawManaNodes)
                    manaNodeMap[String(id)] = 0;
                let exBoost = [1];
                if (dbChar.exBoost && dbChar.exBoost.abilityIdList && dbChar.exBoost.abilityIdList.length > 0) {
                    exBoost = [0, { ability_id_list: dbChar.exBoost.abilityIdList, status_id: dbChar.exBoost.statusId }];
                }
                const charObj = {
                    id: charId,
                    evolution_level: dbChar.evolutionLevel,
                    exp: dbChar.exp,
                    over_limit_step: dbChar.overLimitStep,
                    mana_node_ids: manaNodeMap,
                    ex_boost: exBoost,
                    illustration_settings: [1],
                };
                filledChars.push([0, charObj]);
            }
            const unisonId = (_b = selectedParty === null || selectedParty === void 0 ? void 0 : selectedParty.unisonCharacterIds[i]) !== null && _b !== void 0 ? _b : null;
            if (!unisonId) {
                filledUnison.push([1]);
            }
            else {
                const dbUnison = (0, character_1.getPlayerCharacterSync)(playerId, unisonId);
                if (!dbUnison) {
                    filledUnison.push([1]);
                }
                else {
                    const rawNodes = (0, character_1.getPlayerCharacterManaNodesSync)(playerId, unisonId);
                    const nodeMap = {};
                    for (const id of rawNodes)
                        nodeMap[String(id)] = 0;
                    let ubEx = [1];
                    if (dbUnison.exBoost && dbUnison.exBoost.abilityIdList && dbUnison.exBoost.abilityIdList.length > 0) {
                        ubEx = [0, { ability_id_list: dbUnison.exBoost.abilityIdList, status_id: dbUnison.exBoost.statusId }];
                    }
                    filledUnison.push([0, {
                            id: unisonId,
                            evolution_level: dbUnison.evolutionLevel,
                            exp: dbUnison.exp,
                            over_limit_step: dbUnison.overLimitStep,
                            mana_node_ids: nodeMap,
                            ex_boost: ubEx,
                            illustration_settings: [1],
                        }]);
                }
            }
        }
        const equipId = (_c = selectedParty === null || selectedParty === void 0 ? void 0 : selectedParty.equipmentIds[i]) !== null && _c !== void 0 ? _c : null;
        if (!equipId) {
            filledEquips.push([1]);
        }
        else {
            const dbEquip = (0, equipment_1.getPlayerEquipmentSync)(playerId, equipId);
            if (!dbEquip) {
                filledEquips.push([1]);
            }
            else {
                filledEquips.push([0, { equipmentId: equipId, level: dbEquip.level, enhancementLevel: dbEquip.enhancementLevel }]);
            }
        }
        const soulId = (_d = selectedParty === null || selectedParty === void 0 ? void 0 : selectedParty.abilitySoulIds[i]) !== null && _d !== void 0 ? _d : null;
        filledSouls.push(soulId ? [0, soulId] : [1]);
    }
    return {
        characters: filledChars,
        unison_characters: filledUnison,
        equipments: filledEquips,
        abilitySoulIds: filledSouls,
    };
}
exports.buildRealParty = buildRealParty;
function handleHandshake(socket, data) {
    return __awaiter(this, void 0, void 0, function* () {
        var _a, _b, _c, _d, _e, _f, _g;
        (0, game_logging_1.gameVerboseLog)(() => `[TCP] handshake: ${JSON.stringify(data).substring(0, 200)}`);
        const socklet = data.socklet;
        const roomNumber = data.room_number || data.roomNumber;
        if (socklet === "cooperation_battle") {
            const connectionId = data.connection_id || data.connectionId || `${socket.remoteAddress}:${socket.remotePort}`;
            if (!roomNumber) {
                SessionManager_1.sessionManager.sendJson(socket, [3, "HANDSHAKE_DENIED"]);
                socket.end();
                return;
            }
            const roomId = String(roomNumber);
            // The battle handshake does not carry viewerId.  Resolve it from the
            // lobby connection that issued the same connection_id.  Leaving every
            // battle client as viewer 0 makes unrelated host/guest sockets look
            // like duplicate connections and causes one side to be replaced.
            const roomClient = SessionManager_1.sessionManager.getRoomClientByConnectionId(roomId, String(connectionId));
            const battleClient = SessionManager_1.sessionManager.createClient(socket, (_a = roomClient === null || roomClient === void 0 ? void 0 : roomClient.viewerId) !== null && _a !== void 0 ? _a : 0, roomId, String(connectionId), (_b = roomClient === null || roomClient === void 0 ? void 0 : roomClient.playerId) !== null && _b !== void 0 ? _b : null);
            battleClient.roomGeneration = (_e = (_c = roomClient === null || roomClient === void 0 ? void 0 : roomClient.roomGeneration) !== null && _c !== void 0 ? _c : (_d = (0, manager_1.getRoom)(roomId)) === null || _d === void 0 ? void 0 : _d.lobby_generation) !== null && _e !== void 0 ? _e : 0;
            battleClient.isBattle = true;
            SessionManager_1.sessionManager.addBattleClient(String(connectionId), battleClient);
            SessionManager_1.sessionManager.sendJson(socket, [0, roomNumber, ""]);
            return;
        }
        if (socklet === "cooperation_room") {
            const viewerId = data.viewerId;
            if (!viewerId || !roomNumber) {
                SessionManager_1.sessionManager.sendJson(socket, [3, "HANDSHAKE_DENIED"]);
                socket.end();
                return;
            }
            const roomId = String(roomNumber);
            if (!(0, manager_1.getRoom)(roomId)) {
                // CN does not ship the room_not_found UiString used by this denied
                // packet. A stale notice must never turn into client error C8601.
                SessionManager_1.sessionManager.sendJson(socket, [3, "HANDSHAKE_DENIED"]);
                socket.end();
                return;
            }
            const ctx = yield (0, player_context_1.resolveMultiPlayerContext)(Number(viewerId));
            if (!ctx) {
                SessionManager_1.sessionManager.sendJson(socket, [3, "HANDSHAKE_DENIED"]);
                socket.end();
                return;
            }
            // HTTP room selection and TCP connection are separate operations. Two
            // guests can pass the HTTP capacity check concurrently, so re-check the
            // live room atomically immediately before accepting this socket.
            const currentRoom = (0, manager_1.getRoom)(roomId);
            if (!currentRoom) {
                SessionManager_1.sessionManager.sendJson(socket, [3, "HANDSHAKE_DENIED"]);
                socket.end();
                return;
            }
            // A socket can emit close/error immediately before this handshake while
            // its indexed room client is still waiting for the event-loop cleanup.
            // Do not let that short race make a rescue room look full.
            const indexedClients = SessionManager_1.sessionManager.getClientsInRoom(roomId, currentRoom.lobby_generation)
                .filter(client => !client.isBattle);
            for (const indexedClient of indexedClients) {
                if (indexedClient.socket.destroyed
                    || !indexedClient.socket.readable
                    || !indexedClient.socket.writable) {
                    SessionManager_1.sessionManager.removeClient(indexedClient);
                }
            }
            const liveClients = SessionManager_1.sessionManager.getClientsInRoom(roomId, currentRoom.lobby_generation)
                .filter(client => !client.isBattle
                && !client.socket.destroyed
                && client.socket.readable
                && client.socket.writable);
            const liveViewerIds = new Set(liveClients.map(client => client.viewerId));
            const viewerAlreadyConnected = liveViewerIds.has(Number(viewerId));
            const requestedCategory = (_f = data.questCategory) !== null && _f !== void 0 ? _f : data.quest_category;
            const requestedQuestId = (_g = data.questId) !== null && _g !== void 0 ? _g : data.quest_id;
            const categoryMismatch = requestedCategory !== undefined
                && Number(requestedCategory) !== currentRoom.category;
            const questMismatch = requestedQuestId !== undefined
                && Number(requestedQuestId) !== currentRoom.quest_id;
            const isReturningMember = currentRoom.host_viewer_id === Number(viewerId)
                || currentRoom.expected_real_viewer_ids.includes(Number(viewerId))
                || currentRoom.mates.some(mate => mate.viewer_id === Number(viewerId));
            const waitingForExpectedMember = currentRoom.lobby_generation > 0
                && currentRoom.expected_real_viewer_ids.some(expectedViewerId => !liveViewerIds.has(expectedViewerId));
            const roomPhase = embedded_1.embeddedMultiCoordinator.ensureLifecycle(currentRoom).phase;
            const restoreBlocked = SessionManager_1.sessionManager.isRoomRestoreBlocked(roomId, Number(viewerId));
            const recordedPlayerId = (0, manager_1.getRoomMemberPlayerId)(currentRoom, Number(viewerId));
            const structuralReasons = [
                categoryMismatch ? "category_mismatch" : "",
                questMismatch ? "quest_mismatch" : "",
                recordedPlayerId !== null && recordedPlayerId !== ctx.playerId ? "player_mismatch" : "",
                !viewerAlreadyConnected && liveClients.length >= 3 ? "full" : "",
                !isReturningMember && (roomPhase === "STARTING" || roomPhase === "BATTLE") ? "battle_started" : "",
                !isReturningMember && waitingForExpectedMember ? "waiting_for_returning_member" : "",
                restoreBlocked ? "restore_blocked" : "",
            ].filter(Boolean);
            if (structuralReasons.length > 0) {
                for (const reason of structuralReasons)
                    (0, admission_1.recordRoomAdmissionDenial)(reason);
                console.warn(`[TCP] room handshake unavailable: viewer=${viewerId} room=${roomId}`
                    + ` live=${liveClients.length} state=${currentRoom.raising_state}`
                    + ` reason=${structuralReasons.join(",")}`);
                admission_1.roomAdmissionRegistry.release(roomId, Number(viewerId));
                // Normal stale/full cases are filtered before the TCP handshake.
                // Keep a protocol-level race fallback without looking up a missing
                // CN UiString key (room_full/room_not_found both cause C8601).
                SessionManager_1.sessionManager.sendJson(socket, [3, "HANDSHAKE_DENIED"]);
                socket.end();
                return;
            }
            const { playerId, player } = ctx;
            const connectionId = String(data.connection_id || data.connectionId || `${socket.remoteAddress}:${socket.remotePort}`);
            const party = buildRealParty(playerId);
            if (isReturningMember)
                (0, admission_1.recordRoomAdmissionBypass)("returning_member");
            const admissionClaim = isReturningMember
                ? null
                : admission_1.roomAdmissionRegistry.claim(roomId, currentRoom.lobby_generation, Number(viewerId), connectionId);
            if ((admissionClaim === null || admissionClaim === void 0 ? void 0 : admissionClaim.ok) === false) {
                console.warn(`[TCP] room handshake unavailable: viewer=${viewerId} room=${roomId}`
                    + ` live=${liveClients.length} state=${currentRoom.raising_state}`
                    + ` reason=not_reserved_${admissionClaim.reason}`);
                SessionManager_1.sessionManager.sendJson(socket, [3, "HANDSHAKE_DENIED"]);
                socket.end();
                return;
            }
            const client = SessionManager_1.sessionManager.createClient(socket, Number(viewerId), roomId, connectionId, playerId);
            client.roomGeneration = currentRoom.lobby_generation;
            client.admissionClaimed = (admissionClaim === null || admissionClaim === void 0 ? void 0 : admissionClaim.ok) === true;
            client.admissionGeneration = (admissionClaim === null || admissionClaim === void 0 ? void 0 : admissionClaim.ok) === true
                ? currentRoom.lobby_generation
                : undefined;
            client.clientState.tryTransition(types_2.ClientState.Handshaking);
            const yourSelf = {
                viewerId: Number(viewerId),
                playerId: playerId,
                name: player.name,
                rank: (0, stamina_1.getRankDegree)(player.rankPoint || 0),
                degreeId: player.degreeId || 1,
                mainCharacterId: player.leaderCharacterId,
                party,
                connectionId,
                playerRoleKind: player.role || 1,
                isNewbie: !!player.tutorialStep,
                isHost: Number(viewerId) === currentRoom.host_viewer_id,
                entryTime: Date.now(),
                currentPartyId: player.partySlot || 1,
                autoplayMode: false,
                autoskillMode: 1,
                autoSpeedLevel: 1,
                autoStart: false,
                skillAbilityBehaviorMode: 1,
                dashBehaviorMode: 1,
                allowHealFromOtherPlayers: true,
                state: [0],
            };
            client.yourself = yourSelf;
            SessionManager_1.sessionManager.addClientToRoom(client);
            SessionManager_1.sessionManager.sendJson(socket, [0, connectionId, roomNumber]);
            return;
        }
        // Unknown socklet
        SessionManager_1.sessionManager.sendJson(socket, [1, "DENIED"]);
        socket.end();
    });
}
exports.handleHandshake = handleHandshake;
