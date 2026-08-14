import { sessionManager } from "../state/SessionManager"
import type { SessionClient } from "../state/SessionManager"
import { recordBattleRelay } from "./chain-diagnostic"

export function relayToBattleRoom(
    source: SessionClient,
    data: unknown,
    relayKind: "broadcast" | "direct",
    transportTag: number,
): void {
    // Freeze this logical broadcast's receiver list before writing. A client
    // reconnecting during the loop belongs to another connection generation
    // and must not cause one member of this packet fan-out to be skipped.
    const recipients = sessionManager.snapshotBattleRelayRecipients(source)
    recordBattleRelay(source, recipients, relayKind, transportTag, data)
    for (const client of recipients) {
        sessionManager.sendJson(client.socket, data, {
            roomNumber: source.roomNumber,
            connectionId: client.connectionId,
            viewerId: client.viewerId,
            roomGeneration: source.roomGeneration,
            channel: `battle_${relayKind}`,
        })
    }
}
