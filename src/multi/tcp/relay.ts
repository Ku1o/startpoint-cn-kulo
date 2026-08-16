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
    if (recipients.length === 0) return
    // Every recipient receives the same immutable protocol payload. Serialize
    // once per logical fan-out instead of once per teammate.
    const frame = JSON.stringify(data) + "\0"
    for (const client of recipients) {
        sessionManager.sendFrame(client.socket, frame, {
            roomNumber: source.roomNumber,
            connectionId: client.connectionId,
            viewerId: client.viewerId,
            roomGeneration: source.roomGeneration,
            channel: `battle_${relayKind}`,
        })
    }
}
