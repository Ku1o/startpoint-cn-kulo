import { randomBytes, randomInt } from "crypto";
import { MultiRoom } from "../types";
import { QuestCategory } from "../../lib/types";
import { getServerTime } from "../../utils";
import { sessionManager } from "../state/SessionManager";
import { gameVerboseLog } from "../../lib/game-logging";
import { roomAdmissionRegistry } from "./admission";
import { embeddedMultiCoordinator } from "../coordinator/embedded";
import { getQuestFromCategorySync } from "../../lib/assets";

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

export function generateRoomNumber(): string {
    for (let attempt = 0; attempt < 100; attempt += 1) {
        const roomNumber = String(randomInt(100000, 1000000));
        if (!rooms.has(roomNumber)) return roomNumber;
    }
    throw new Error("Unable to allocate a unique multiplayer room number");
}

export function generateRoomAccessToken(): string {
    for (let attempt = 0; attempt < 100; attempt += 1) {
        const token = randomBytes(24).toString("base64url");
        if (!getRoomByToken(token)) return token;
    }
    throw new Error("Unable to allocate a unique multiplayer room token");
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
        access_token: generateRoomAccessToken(),
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
        member_viewer_ids: [hostViewerId],
        member_player_ids: { [hostViewerId]: hostPlayerId },
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

function getRoomEventId(room: MultiRoom): number | undefined {
    const quest = getQuestFromCategorySync(room.category, room.quest_id);
    if (quest?.eventId !== undefined) return quest.eventId;
    if ((room.category === QuestCategory.ADVENT_EVENT_SINGLE
        || room.category === QuestCategory.ADVENT_EVENT_MULTI)
        && Number.isSafeInteger(room.quest_id)
        && room.quest_id >= 1_000) {
        return Math.trunc(room.quest_id / 1_000);
    }
    return undefined;
}

export function getRooms(categoryId: number, eventId?: number): MultiRoom[] {
    const result: MultiRoom[] = [];
    for (const room of rooms.values()) {
        if (room.category !== categoryId) continue;
        if (eventId !== undefined) {
            const roomEventId = getRoomEventId(room);
            // Legacy advent tables encode the event in the quest's thousands
            // group instead of storing eventId explicitly. Other old tables
            // without either form remain visible for backward compatibility.
            if (roomEventId !== undefined && roomEventId !== Number(eventId)) continue;
        }
        result.push(room);
    }
    return result;
}

export function isRoomMember(room: MultiRoom, viewerId: number): boolean {
    if (room.member_viewer_ids?.includes(viewerId)) return true
    if (room.host_viewer_id === viewerId) return true
    if (room.expected_real_viewer_ids.includes(viewerId)) return true
    if (room.mates.some(mate => mate.viewer_id === viewerId)) return true
    return sessionManager.getClientsInRoom(room.room_number, room.lobby_generation)
        .some(client => !client.isBattle && client.viewerId === viewerId)
}

export function addRoomMember(roomNumber: string, viewerId: number, playerId: number): boolean {
    const room = rooms.get(roomNumber)
    if (!room) return false
    if (!room.member_viewer_ids.includes(viewerId)) room.member_viewer_ids.push(viewerId)
    room.member_player_ids[viewerId] = playerId
    return true
}

export function removeRoomMember(roomNumber: string, viewerId: number): boolean {
    const room = rooms.get(roomNumber)
    if (!room || viewerId === room.host_viewer_id) return false
    const index = room.member_viewer_ids.indexOf(viewerId)
    if (index < 0) return false
    room.member_viewer_ids.splice(index, 1)
    delete room.member_player_ids[viewerId]
    return true
}

export function getRoomMemberPlayerId(room: MultiRoom, viewerId: number): number | null {
    const recordedMemberPlayerId = room.member_player_ids?.[viewerId]
    if (recordedMemberPlayerId) return recordedMemberPlayerId
    if (room.host_viewer_id === viewerId) return room.host_player_id
    const recordedMate = room.mates.find(mate => mate.viewer_id === viewerId)
    if (recordedMate?.player_id) return recordedMate.player_id
    const liveClient = sessionManager.getClientsInRoom(room.room_number, room.lobby_generation)
        .find(client => !client.isBattle && client.viewerId === viewerId)
    return liveClient?.playerId ?? null
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
