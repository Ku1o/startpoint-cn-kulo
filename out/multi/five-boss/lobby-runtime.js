"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.recordFiveBossSignal = exports.isFrozenFiveBossBattleClient = exports.freezeFiveBossLobby = void 0;
const crypto_1 = require("crypto");
const manager_1 = require("../room/manager");
const SessionManager_1 = require("../state/SessionManager");
const fiveBossGauntletRun_1 = require("../../data/domains/fiveBossGauntletRun");
const character_1 = require("../../data/domains/character");
const contract_1 = require("./contract");
const coalesced_diagnostics_1 = require("../../lib/coalesced-diagnostics");
const connection_diagnostic_1 = require("./connection-diagnostic");
const persistence_coordinator_1 = require("../../lib/persistence-coordinator");
/** Freeze the canonical live lobby before either HTTP or TCP starts the battle. */
function freezeFiveBossLobby(room, members) {
    var _a, _b, _c, _d;
    if (!(0, contract_1.isFiveBossGauntletQuest)(room.category, room.quest_id))
        return true;
    if (room.five_boss_runtime)
        return true;
    const generation = room.lifecycle.phase === "BATTLE"
        ? Math.max(0, room.lobby_generation - 1) : room.lobby_generation;
    const clients = SessionManager_1.sessionManager.getClientsInRoom(room.room_number, generation)
        .filter(client => !client.isBattle && !client.superseded);
    const host = clients.find(client => client.viewerId === room.host_viewer_id);
    const canonical = new Map();
    for (const mate of [...((_a = members !== null && members !== void 0 ? members : host === null || host === void 0 ? void 0 : host.mates) !== null && _a !== void 0 ? _a : []), ...clients.map(c => c.yourself)]) {
        if (mate)
            canonical.set(mate.comId ? `com:${mate.comId}` : `viewer:${mate.viewerId}`, mate);
    }
    const roster = [...canonical.values()];
    if (!host || roster.length !== 3 || !roster.every(mate => { var _a; return ((_a = mate.state) === null || _a === void 0 ? void 0 : _a[0]) === 1; }))
        return false;
    const frozen = {
        runId: (0, crypto_1.randomUUID)(), expectedRealPlayerIds: [], autoplayModeByPlayerId: {},
        partyCharacterIdsByPlayerId: {}, battleIdentityByViewerId: {},
    };
    for (const mate of roster.filter(m => !m.comId)) {
        const live = clients.find(client => client.viewerId === Number(mate.viewerId));
        const playerId = (0, manager_1.getRoomMemberPlayerId)(room, Number(mate.viewerId));
        if (!live || !playerId || live.playerId !== playerId
            || typeof ((_b = live.yourself) === null || _b === void 0 ? void 0 : _b.autoplayMode) !== "boolean" || !live.socket.remoteAddress)
            return false;
        const party = live.yourself.party;
        if (!Array.isArray(party === null || party === void 0 ? void 0 : party.characters) || !Array.isArray(party === null || party === void 0 ? void 0 : party.unison_characters)
            || party.characters.length > 3 || party.unison_characters.length > 3)
            return false;
        const ids = [...((_c = party === null || party === void 0 ? void 0 : party.characters) !== null && _c !== void 0 ? _c : []), ...((_d = party === null || party === void 0 ? void 0 : party.unison_characters) !== null && _d !== void 0 ? _d : [])]
            .filter(entry => Array.isArray(entry) && entry[0] === 0)
            .map(entry => { var _a; return Number((_a = entry[1]) === null || _a === void 0 ? void 0 : _a.id); })
            .filter(id => Number.isSafeInteger(id) && id > 0);
        if (!ids.length || ids.some(id => !(0, character_1.getPlayerCharacterSync)(playerId, id))
            || frozen.expectedRealPlayerIds.includes(playerId))
            return false;
        frozen.expectedRealPlayerIds.push(playerId);
        frozen.autoplayModeByPlayerId[String(playerId)] = live.yourself.autoplayMode;
        frozen.partyCharacterIdsByPlayerId[String(playerId)] = [...new Set(ids)];
        frozen.battleIdentityByViewerId[String(live.viewerId)] = {
            playerId, remoteAddress: live.socket.remoteAddress, connectionId: live.connectionId,
        };
    }
    if (!frozen.expectedRealPlayerIds.includes(room.host_player_id))
        return false;
    room.five_boss_runtime = frozen;
    connection_diagnostic_1.fiveBossConnectionDiagnostics.begin(room);
    return true;
}
exports.freezeFiveBossLobby = freezeFiveBossLobby;
function isFrozenFiveBossBattleClient(room, client) {
    var _a;
    const identity = (_a = room.five_boss_runtime) === null || _a === void 0 ? void 0 : _a.battleIdentityByViewerId[String(client.viewerId)];
    return !!identity && identity.playerId === client.playerId
        && identity.remoteAddress === client.socket.remoteAddress
        && identity.connectionId === client.connectionId && !client.superseded;
}
exports.isFrozenFiveBossBattleClient = isFrozenFiveBossBattleClient;
function recordFiveBossSignal(room, client, signal) {
    var _a;
    if (!isFrozenFiveBossBattleClient(room, client)) {
        connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(client.socket, "signal_rejected", `${signal}:identity`);
        coalesced_diagnostics_1.fiveBossDiagnostics.report(JSON.stringify(["signal", (_a = room.five_boss_runtime) === null || _a === void 0 ? void 0 : _a.runId, room.room_number,
            client.playerId, signal, "identity"]), () => {
            var _a;
            return `[FIVE-BOSS-SIGNAL] rejected=identity room=${room.room_number}`
                + ` run=${(_a = room.five_boss_runtime) === null || _a === void 0 ? void 0 : _a.runId} player=${client.playerId} connection=${client.connectionId} signal=${signal}`;
        });
        return;
    }
    const runId = room.five_boss_runtime.runId;
    const playerId = client.playerId;
    const roomNumber = room.room_number;
    // The TCP handler must only update the in-memory barrier and return. The
    // proof row is durable evidence, but it is not part of the realtime ACK.
    connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(client.socket, signal === "level_next" ? "level_next_queued" : "finalize_queued", "tcp");
    void (0, persistence_coordinator_1.runPersistenceTransaction)({
        domain: "multi-settlement", playerId, operation: `five_boss_${signal}`,
    }, () => (0, fiveBossGauntletRun_1.recordMemberBattleSignalSync)({ runId, playerId, roomNumber, signal }))
        .then(() => {
        connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(client.socket, signal === "level_next" ? "level_next_recorded" : "finalize_recorded", "tcp");
    })
        .catch(error => {
        var _a;
        const code = (_a = error.code) !== null && _a !== void 0 ? _a : "unknown";
        connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(client.socket, "signal_rejected", `${signal}:${code}`);
        coalesced_diagnostics_1.fiveBossDiagnostics.report(JSON.stringify(["signal", runId, roomNumber,
            playerId, signal, code]), () => `[FIVE-BOSS-SIGNAL] rejected=${code}`
            + ` room=${roomNumber} run=${runId}`
            + ` player=${playerId} connection=${client.connectionId} signal=${signal}: ${error.message}`);
    });
}
exports.recordFiveBossSignal = recordFiveBossSignal;
