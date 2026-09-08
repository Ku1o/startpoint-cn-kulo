import { randomUUID } from "crypto"
import type { MultiRoom } from "../../lib/types/multi"
import { getRoomMemberPlayerId } from "../room/manager"
import { sessionManager, type SessionClient } from "../state/SessionManager"
import { recordMemberBattleSignalSync } from "../../data/domains/fiveBossGauntletRun"
import { getPlayerCharacterSync } from "../../data/domains/character"
import { isFiveBossGauntletQuest } from "./contract"

/** Freeze the canonical live lobby before either HTTP or TCP starts the battle. */
export function freezeFiveBossLobby(room: MultiRoom, members?: any[]): boolean {
    if (!isFiveBossGauntletQuest(room.category, room.quest_id)) return true
    if (room.five_boss_runtime) return true
    const generation = room.lifecycle.phase === "BATTLE"
        ? Math.max(0, room.lobby_generation - 1) : room.lobby_generation
    const clients = sessionManager.getClientsInRoom(room.room_number, generation)
        .filter(client => !client.isBattle && !client.superseded)
    const host = clients.find(client => client.viewerId === room.host_viewer_id)
    const canonical = new Map<string, any>()
    for (const mate of [...(members ?? host?.mates ?? []), ...clients.map(c => c.yourself)]) {
        if (mate) canonical.set(mate.comId ? `com:${mate.comId}` : `viewer:${mate.viewerId}`, mate)
    }
    const roster = [...canonical.values()]
    if (!host || roster.length !== 3 || !roster.every(mate => mate.state?.[0] === 1)) return false
    const frozen: NonNullable<MultiRoom["five_boss_runtime"]> = {
        runId: randomUUID(), expectedRealPlayerIds: [], autoplayModeByPlayerId: {},
        partyCharacterIdsByPlayerId: {}, battleIdentityByViewerId: {},
    }
    for (const mate of roster.filter(m => !m.comId)) {
        const live = clients.find(client => client.viewerId === Number(mate.viewerId))
        const playerId = getRoomMemberPlayerId(room, Number(mate.viewerId))
        if (!live || !playerId || live.playerId !== playerId
            || typeof live.yourself?.autoplayMode !== "boolean" || !live.socket.remoteAddress) return false
        const party = live.yourself.party
        if (!Array.isArray(party?.characters) || !Array.isArray(party?.unison_characters)
            || party.characters.length > 3 || party.unison_characters.length > 3) return false
        const ids = [...(party?.characters ?? []), ...(party?.unison_characters ?? [])]
            .filter(entry => Array.isArray(entry) && entry[0] === 0)
            .map(entry => Number(entry[1]?.id))
            .filter(id => Number.isSafeInteger(id) && id > 0)
        if (!ids.length || ids.some(id => !getPlayerCharacterSync(playerId, id))
            || frozen.expectedRealPlayerIds.includes(playerId)) return false
        frozen.expectedRealPlayerIds.push(playerId)
        frozen.autoplayModeByPlayerId[String(playerId)] = live.yourself.autoplayMode
        frozen.partyCharacterIdsByPlayerId[String(playerId)] = [...new Set(ids)]
        frozen.battleIdentityByViewerId[String(live.viewerId)] = {
            playerId, remoteAddress: live.socket.remoteAddress, connectionId: live.connectionId,
        }
    }
    if (!frozen.expectedRealPlayerIds.includes(room.host_player_id)) return false
    room.five_boss_runtime = frozen
    return true
}

export function isFrozenFiveBossBattleClient(room: MultiRoom, client: SessionClient): boolean {
    const identity = room.five_boss_runtime?.battleIdentityByViewerId[String(client.viewerId)]
    return !!identity && identity.playerId === client.playerId
        && identity.remoteAddress === client.socket.remoteAddress
        && identity.connectionId === client.connectionId && !client.superseded
}

export function recordFiveBossSignal(room: MultiRoom, client: SessionClient, signal: "level_next" | "finalize"): void {
    if (!isFrozenFiveBossBattleClient(room, client)) return
    try {
        recordMemberBattleSignalSync({ runId: room.five_boss_runtime!.runId,
            playerId: client.playerId!, roomNumber: room.room_number, signal })
    } catch (error) {
        console.warn(`[MULTI] five-boss signal rejected: ${(error as Error).message}`)
    }
}
