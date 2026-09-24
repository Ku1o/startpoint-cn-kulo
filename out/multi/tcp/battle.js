"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.handleBattleMessage = void 0;
const SessionManager_1 = require("../state/SessionManager");
const relay_1 = require("./relay");
const chain_diagnostic_1 = require("./chain-diagnostic");
const manager_1 = require("../room/manager");
const lobby_runtime_1 = require("../five-boss/lobby-runtime");
const connection_diagnostic_1 = require("../five-boss/connection-diagnostic");
const online_presence_1 = require("../../lib/online-presence");
function findBattleClientBySocket(socket) {
    const client = SessionManager_1.sessionManager.findClientBySocket(socket);
    return (client === null || client === void 0 ? void 0 : client.isBattle) ? client : undefined;
}
function sendToBattleClient(client, data, channel) {
    SessionManager_1.sessionManager.sendJson(client.socket, data, {
        roomNumber: client.roomNumber,
        connectionId: client.connectionId,
        viewerId: client.viewerId,
        roomGeneration: client.roomGeneration,
        channel,
    });
}
function handleBattleNotify(socket, data) {
    var _a, _b;
    if (!Array.isArray(data))
        return;
    const tag = data[0];
    const client = findBattleClientBySocket(socket);
    if (client)
        (0, chain_diagnostic_1.recordBattleNotify)(client, tag, data);
    if (tag === 0 || tag === 1 || tag === 2) {
        connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(socket, tag === 0 ? "scene_ready" : tag === 1 ? "level_next" : "finalize", client ? "indexed" : "client_unindexed");
    }
    switch (tag) {
        case 0: { // SceneReady
            if (!client)
                break;
            SessionManager_1.sessionManager.markSceneReady(client.connectionId, client.roomNumber);
            break;
        }
        case 1: { // LevelNext (CN dual-boss battle)
            if (client) {
                const room = (0, manager_1.getRoom)(client.roomNumber);
                if (room === null || room === void 0 ? void 0 : room.five_boss_runtime)
                    (0, lobby_runtime_1.recordFiveBossSignal)(room, client, "level_next");
                SessionManager_1.sessionManager.beginBattleLevelNext(client.connectionId, client.roomNumber);
            }
            break;
        }
        case 2: { // Finalize
            const room = client && (0, manager_1.getRoom)(client.roomNumber);
            if (client && (room === null || room === void 0 ? void 0 : room.five_boss_runtime))
                (0, lobby_runtime_1.recordFiveBossSignal)(room, client, "finalize");
            if (client)
                sendToBattleClient(client, [1, [2]], "battle_finalize_ack");
            break;
        }
        case 3: { // Measurement
            if (client) {
                const params = data[1];
                const frame = (_a = params === null || params === void 0 ? void 0 : params[0]) !== null && _a !== void 0 ? _a : 0;
                const clientTime = (_b = params === null || params === void 0 ? void 0 : params[1]) !== null && _b !== void 0 ? _b : 0;
                sendToBattleClient(client, [1, [3, frame, clientTime, Date.now()]], "battle_measurement_ack");
            }
            break;
        }
        case 4: // LineSpeedWarning
            break;
        case 5: // Heartbeat
            if (client)
                sendToBattleClient(client, [1, [3, 0, 0, Date.now()]], "battle_heartbeat_ack");
            break;
        default:
            break;
    }
}
function handleBattleMessage(socket, data) {
    if (!Array.isArray(data))
        return;
    const tag = data[0];
    const activityClient = findBattleClientBySocket(socket);
    connection_diagnostic_1.fiveBossConnectionDiagnostics.packet(socket, !!activityClient);
    if (activityClient) {
        SessionManager_1.sessionManager.noteBattleActivity(activityClient.connectionId);
        if (!socket.destroyed && SessionManager_1.sessionManager.isCurrentBattleClient(activityClient)) {
            (0, online_presence_1.markPlayerOnlineFromTcp)(activityClient.viewerId);
        }
    }
    switch (tag) {
        case 0: // Notify
            handleBattleNotify(socket, data[1]);
            break;
        case 1: { // Broadcast → relay as BattleServer2Client.Messages(2, senderId, array)
            const client = findBattleClientBySocket(socket);
            if (client) {
                const bcData = data[1];
                (0, relay_1.relayToBattleRoom)(client, [2, client.connectionId, bcData], "broadcast", tag);
                sendToBattleClient(client, [1, [3, 0, 0, Date.now()]], "battle_broadcast_ack");
            }
            break;
        }
        case 2: { // Send → relay as BattleServer2Client.Send(3, senderId, message)
            const client = findBattleClientBySocket(socket);
            if (client) {
                const sendMsg = data[2];
                if (sendMsg !== undefined && sendMsg !== null) {
                    (0, relay_1.relayToBattleRoom)(client, [3, client.connectionId, sendMsg], "direct", tag);
                }
                sendToBattleClient(client, [1, [3, 0, 0, Date.now()]], "battle_direct_ack");
            }
            break;
        }
        default:
            break;
    }
}
exports.handleBattleMessage = handleBattleMessage;
