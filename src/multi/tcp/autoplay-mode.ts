export interface AutoplayModeLobbyClient {
    viewerId: number
    roomNumber: string
    yourself?: Record<string, any>
    mates: Array<Record<string, any>>
}

export interface AutoplayModeChange {
    autoplayMode: boolean
    manualMode: boolean
}

export type AutoplayModeBroadcast = (roomNumber: string, message: unknown[]) => void

export function parseAutoplayModeChange(data: unknown[]): AutoplayModeChange | null {
    const autoplayMode = data[1]
    const manualMode = data[2]
    if (typeof autoplayMode !== "boolean" || typeof manualMode !== "boolean") return null
    return { autoplayMode, manualMode }
}

export function handleAutoplayModeChange(
    client: AutoplayModeLobbyClient,
    data: unknown[],
    broadcast: AutoplayModeBroadcast
): AutoplayModeChange | null {
    const change = parseAutoplayModeChange(data)
    if (!change || !client.yourself) return null

    client.yourself.autoplayMode = change.autoplayMode
    const rosterMate = client.mates.find(mate => Number(mate.viewerId) === client.viewerId)
    if (rosterMate) rosterMate.autoplayMode = change.autoplayMode

    broadcast(client.roomNumber, [
        1,
        [3, client.viewerId, change.autoplayMode, change.manualMode],
    ])
    return change
}
