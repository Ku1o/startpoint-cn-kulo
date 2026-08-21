import * as net from "net"
import { getSession } from "../data/domains/session"
import {
    attachLoungeSocket,
    broadcastLoungeFrame,
    canAttachLoungeViewer,
    detachLoungeSocket,
    enterLounge,
    getLounge,
    getLoungeSocketContext,
    loungeCanStart,
    matchesLoungeAccess,
    sendLoungeFrame,
    serializeLoungeMates,
    setLoungeMemberReady,
} from "./state"

function positiveSafeInteger(value: unknown): number | null {
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

function deny(socket: net.Socket, message = "HANDSHAKE_DENIED"): void {
    sendLoungeFrame(socket, [1, message])
    socket.end()
}

export async function handleLoungeHandshake(socket: net.Socket, data: Record<string, unknown>): Promise<void> {
    const viewerId = positiveSafeInteger(data.viewerId)
    const loungeId = positiveSafeInteger(data.loungeId)
    const useCase = positiveSafeInteger(data.useCase)
    const establisherViewerId = positiveSafeInteger(data.establisherViewerId)
    const advice = typeof data.advice === "string" ? data.advice : ""
    if (viewerId === null || loungeId === null || useCase === null || establisherViewerId === null || advice.length === 0) {
        deny(socket)
        return
    }
    const session = await getSession(String(viewerId))
    const room = getLounge(loungeId)
    if (!session || !room || !matchesLoungeAccess(room, { useCase, advice, establisherViewerId })
        || !canAttachLoungeViewer(room, viewerId)) {
        deny(socket)
        return
    }
    attachLoungeSocket(room, viewerId, socket)
    sendLoungeFrame(socket, [0, `lounge-${viewerId}`, loungeId])
}

export function handleLoungeMessage(socket: net.Socket, value: unknown): void {
    if (!Array.isArray(value) || Number(value[0]) !== 0 || !Array.isArray(value[1])) return
    const notify = value[1]
    const kind = Number(notify[0])
    if (kind === 0) {
        const profile = notify[1]
        if (!profile || typeof profile !== "object" || Array.isArray(profile)) return
        const entered = enterLounge(socket, profile as Record<string, unknown>)
        if (!entered) return
        const mates = serializeLoungeMates(entered.room)
        sendLoungeFrame(socket, [1, [3, mates]])
        broadcastLoungeFrame(entered.room, [1, [4, mates]])
        return
    }

    const context = getLoungeSocketContext(socket)
    if (!context || !context.member) return
    switch (kind) {
        case 1:
            sendLoungeFrame(socket, [1, [7, context.viewerId]])
            break
        case 2:
            break
        case 3: {
            const readyState = Array.isArray(notify[1]) ? notify[1] : [0]
            if (setLoungeMemberReady(context.room, context.viewerId, readyState)) {
                broadcastLoungeFrame(context.room, [1, [0, context.viewerId, readyState]])
            }
            break
        }
        case 4:
            if (context.viewerId !== context.room.hostViewerId || !loungeCanStart(context.room)) {
                sendLoungeFrame(socket, [1, [6, [1]]])
                break
            }
            context.room.raisingState = 97
            broadcastLoungeFrame(context.room, [1, [5]])
            break
        case 5:
            break
        case 6:
            detachLoungeSocket(socket, true)
            break
    }
}

export { detachLoungeSocket }
