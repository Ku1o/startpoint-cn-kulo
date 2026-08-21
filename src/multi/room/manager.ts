import { randomInt } from "crypto";
import { MultiRoom, QuestCategory } from "../types";
import { getServerTime } from "../../utils";
import { sessionManager } from "../state/SessionManager";
import { gameVerboseLog } from "../../lib/game-logging";
import { roomAdmissionRegistry } from "./admission";
import { embeddedMultiCoordinator } from "../coordinator/embedded";

const rooms = new Map<string, MultiRoom>();

let roomSequence = 1;

const INCOMPLETE_EXPIRY_MS = parseInt(process.env.MULTI_ROOM_INCOMPLETE_EXPIRY_MS || "900000"); // 15min, mates < 3
const FULL_ROOM_EXPIRY_MS = parseInt(process.env.MULTI_ROOM_FULL_EXPIRY_MS || "1800000"); // 30min, mates >= 3
const CLEAN_INTERVAL_MS = parseInt(process.env.MULTI_ROOM_CLEAN_INTERVAL_MS || "60000");
const REMAINING_NOTIFY_MS = 30000; // send RemainingTime float 30s before disband

// Track which rooms have already been notified (to avoid repeat floats)
const notifiedRooms = new Set<string>();

function cleanExpiredRooms() {
    for (const [roomNumber, room] of rooms) {
        const lifecycle = embeddedMultiCoordinator.ensureLifecycle(room);
        // Battle and settlement rooms are governed by their own watchdogs.
        // Skip them before allocating a Promise chain every cleanup tick.
        if (lifecycle.phase !== "LOBBY") continue;
        const instanceId = lifecycle.instanceId;
        const lifecycleVersion = lifecycle.version;
        void embeddedMultiCoordinator.enqueueRoomCommand(roomNumber, () => {
            const current = rooms.get(roomNumber);
            if (!embeddedMultiCoordinator.isCurrentInstance(current, instanceId)
                || current.lifecycle.version !== lifecycleVersion) return;
            // Only an ordinary lobby uses idle expiry. Battle and settlement
            // phases have their own watchdogs and grace periods.
            if (current.lifecycle.phase !== "LOBBY") return;

            const now = Date.now();
            const timeOffset = now - getServerTime() * 1000;
            const idleAge = now - (current.host_entry_time * 1000 + timeOffset);
            const timeout = current.mates.length < 3 ? INCOMPLETE_EXPIRY_MS : FULL_ROOM_EXPIRY_MS;
            const remaining = timeout - idleAge;

            if (remaining > 0 && remaining <= REMAINING_NOTIFY_MS && !notifiedRooms.has(roomNumber)) {
                sessionManager.broadcastToRoom(roomNumber, [1, [7, Math.ceil(remaining / 1000)]])
                notifiedRooms.add(roomNumber)
                gameVerboseLog(() => `[MULTI] RemainingTime sent: room=${roomNumber} seconds=${Math.ceil(remaining / 1000)}`)
            }

            if (idleAge > timeout && sessionManager.commitRoomDisband(roomNumber, "room_expired")) {
                notifiedRooms.delete(roomNumber);
            }
        }).catch(error => console.error(`[MULTI] room cleanup failed: room=${roomNumber}`, error));
    }
}
setInterval(cleanExpiredRooms, CLEAN_INTERVAL_MS);

export const STATIC_ACCESS_TOKEN = "multi_battle_quest_access_token";

export function generateRoomNumber(): string {
    return String(randomInt(100000, 999999));
}

export function isRoomWaitingForExpectedMember(room: MultiRoom): boolean {
    if (room.lobby_generation <= 0 || room.expected_real_viewer_ids.length === 0) {
        return false
    }

    const liveViewerIds = new Set(
        sessionManager.getClientsInRoom(room.room_number, room.lobby_generation)
            .filter(client => !client.isBattle
                && !client.socket.destroyed
                && client.socket.readable
                && client.socket.writable)
            .map(client => client.viewerId),
    )
    return room.expected_real_viewer_ids.some(viewerId => !liveViewerIds.has(viewerId))
}

export function createRoom(
    hostViewerId: number,
    hostPlayerId: number,
    hostPartyId: number,
    category: QuestCategory,
    questId: number,
    acceptedType: number,
    hostMainCharacterId: number,
    isNpcMode: boolean = false
): MultiRoom {
    const roomNumber = generateRoomNumber();
    const room: MultiRoom = {
        room_number: roomNumber,
        access_token: STATIC_ACCESS_TOKEN,
        category,
        quest_id: questId,
        host_viewer_id: hostViewerId,
        host_player_id: hostPlayerId,
        host_party_id: hostPartyId,
        host_main_character_id: hostMainCharacterId,
        accepted_type: acceptedType,
        created_at: Date.now(),
        raising_state: 2,
        room_sequence: roomSequence++,
        host_entry_time: getServerTime(),
        mates: [],
        share_room_options: 0,
        is_npc_mode: isNpcMode,
        npc_count: 0,
        expected_real_viewer_ids: [],
        lobby_generation: 0,
        rematch_wait_started_at: null,
        settlement_return_pending: false,
        lifecycle: embeddedMultiCoordinator.createLifecycle(),
    };
    rooms.set(roomNumber, room);
    gameVerboseLog(() => `[MULTI] room created: ${roomNumber} host=${hostViewerId} category=${category} quest=${questId}`);
    return room;
}

export function getRoom(roomNumber: string): MultiRoom | undefined {
    const room = rooms.get(roomNumber);
    if (!room) gameVerboseLog(() => `[MULTI] room not found: ${roomNumber}`);
    return room;
}

export function getRoomByToken(token: string): MultiRoom | undefined {
    for (const room of rooms.values()) {
        if (room.access_token === token) return room;
    }
    return undefined;
}

export function getRooms(categoryId: number, eventId?: number): MultiRoom[] {
    const result: MultiRoom[] = [];
    for (const room of rooms.values()) {
        if (room.category === categoryId) {
            result.push(room);
        }
    }
    return result;
}

export function setRoomBattle(roomNumber: string): boolean {
    const room = rooms.get(roomNumber);
    if (!room) return false;
    const lifecycle = embeddedMultiCoordinator.ensureLifecycle(room);
    if (lifecycle.phase === "BATTLE") return true;
    return embeddedMultiCoordinator.commitBattleStart(room).ok;
}

export function disbandRoom(roomNumber: string, reason = "room_manager_delete"): boolean {
    const room = rooms.get(roomNumber);
    if (room) embeddedMultiCoordinator.commitDisband(room, reason);
    const deleted = rooms.delete(roomNumber);
    if (deleted) {
        gameVerboseLog(() => `[MULTI] room deleted: ${roomNumber}`);
        roomAdmissionRegistry.clearRoom(roomNumber);
        try {
            const { stopRandomRecruitment } = require("../recruitment")
            stopRandomRecruitment(roomNumber)
        } catch (e) {}
        sessionManager.removeRoomState(roomNumber);
        notifiedRooms.delete(roomNumber);
    }
    return deleted;
}

export function updateHostEntryTime(roomNumber: string): boolean {
    const room = rooms.get(roomNumber);
    if (!room) return false;
    room.host_entry_time = getServerTime();
    return true;
}
