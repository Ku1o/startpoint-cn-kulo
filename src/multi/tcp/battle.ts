import * as net from "net"
import { sessionManager } from "../state/SessionManager"
import type { SessionClient } from "../state/SessionManager"
import { relayToBattleRoom } from "./relay"
import {
    recordBattleNotify,
    recordBattleReceive,
    recordBattleServerSend,
} from "./chain-diagnostic"

function findBattleClientBySocket(socket: net.Socket): SessionClient | undefined {
    const client = sessionManager.findClientBySocket(socket)
    return client?.isBattle ? client : undefined
}

function sendToBattleClient(client: SessionClient, data: unknown, channel: string): void {
    const result = sessionManager.sendJson(client.socket, data, {
        roomNumber: client.roomNumber,
        connectionId: client.connectionId,
        viewerId: client.viewerId,
        roomGeneration: client.roomGeneration,
        channel,
    })
    recordBattleServerSend(client, channel, result, data)
}

function handleBattleNotify(socket: net.Socket, data: unknown): void {
    if (!Array.isArray(data)) return
    const tag = data[0] as number
    const client = findBattleClientBySocket(socket)
    if (client) recordBattleNotify(client, tag, data)

    switch (tag) {
        case 0: { // SceneReady
            if (!client) break
            const allReady = sessionManager.markSceneReady(client.connectionId, client.roomNumber)
            if (allReady) {
                const recipients = sessionManager.snapshotBattleRelayRecipients(client, true)
                for (const recipient of recipients) {
                    sendToBattleClient(recipient, [1, [1]], "battle_scene_start")
                }
            }
            break
        }
        case 1: { // LevelNext (CN dual-boss battle)
            if (client) {
                sessionManager.beginBattleLevelNext(client.connectionId, client.roomNumber)
            }
            break
        }
        case 2: { // Finalize
            if (client) sendToBattleClient(client, [1, [2]], "battle_finalize_ack")
            break
        }
        case 3: { // Measurement
            if (client) {
                const params = data[1]
                const frame = params?.[0] ?? 0
                const clientTime = params?.[1] ?? 0
                sendToBattleClient(client, [1, [3, frame, clientTime, Date.now()]], "battle_measurement_ack")
            }
            break
        }
        case 4: // LineSpeedWarning
            break
        case 5: // Heartbeat
            if (client) sendToBattleClient(client, [1, [3, 0, 0, Date.now()]], "battle_heartbeat_ack")
            break
        default:
            break
    }
}

export function handleBattleMessage(socket: net.Socket, data: unknown): void {
    if (!Array.isArray(data)) return
    const tag = data[0] as number
    const activityClient = findBattleClientBySocket(socket)
    if (activityClient) {
        sessionManager.noteBattleActivity(activityClient.connectionId)
        recordBattleReceive(activityClient, data)
    }

    switch (tag) {
        case 0: // Notify
            handleBattleNotify(socket, data[1])
            break
        case 1: { // Broadcast → relay as BattleServer2Client.Messages(2, senderId, array)
            const client = findBattleClientBySocket(socket)
            if (client) {
                const bcData = data[1]
                relayToBattleRoom(client, [2, client.connectionId, bcData], "broadcast", tag)
                sendToBattleClient(client, [1, [3, 0, 0, Date.now()]], "battle_broadcast_ack")
            }
            break
        }
        case 2: { // Send → relay as BattleServer2Client.Send(3, senderId, message)
            const client = findBattleClientBySocket(socket)
            if (client) {
                const sendMsg = data[2]
                if (sendMsg !== undefined && sendMsg !== null) {
                    relayToBattleRoom(client, [3, client.connectionId, sendMsg], "direct", tag)
                }
                sendToBattleClient(client, [1, [3, 0, 0, Date.now()]], "battle_direct_ack")
            }
            break
        }
        default:
            break
    }
}
