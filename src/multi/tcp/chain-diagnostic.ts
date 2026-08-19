import * as fs from "fs"
import * as path from "path"
import type { SessionClient } from "../state/SessionManager"

type RelayKind = "broadcast" | "direct" | "notify"

interface RoomDiagnosticState {
    generation: number
    packetSequence: number
    lastObservedAt: number
}

interface ConnectionReceiveState {
    packetSequence: number
    lastReceivedAt: number
}

interface TargetedRoomState {
    matchedViewers: number[]
}

function enabled(value: string | undefined): boolean {
    return /^(1|true|yes|on)$/i.test(value ?? "false")
}

function positiveInteger(value: string | undefined, fallback: number, minimum = 1): number {
    const parsed = parseInt(value || "", 10)
    return Number.isFinite(parsed) ? Math.max(minimum, parsed) : fallback
}

export function parseDiagnosticViewerIds(value: string | undefined): Set<number> {
    const viewers = new Set<number>()
    for (const token of (value ?? "").split(/[\s,;]+/)) {
        if (!/^\d+$/.test(token)) continue
        const viewerId = Number(token)
        if (Number.isSafeInteger(viewerId) && viewerId > 0) viewers.add(viewerId)
    }
    return viewers
}

const FULL_DIAGNOSTIC_ENABLED = enabled(process.env.MULTI_CHAIN_DIAGNOSTIC)
// TEMPORARY CARD-C diagnostic. Remove the viewer-targeted recorder and its
// environment settings after the mixed real-player/COM root cause is fixed.
const TARGET_VIEWER_IDS = parseDiagnosticViewerIds(process.env.MULTI_CHAIN_DIAGNOSTIC_VIEWERS)
const TARGET_DIAGNOSTIC_ENABLED = TARGET_VIEWER_IDS.size > 0
const SEND_DIAGNOSTIC_ENABLED = enabled(
    process.env.MULTI_CHAIN_SEND_DIAGNOSTIC ?? process.env.MULTI_CHAIN_DIAGNOSTIC,
)
const ANY_DIAGNOSTIC_ENABLED = FULL_DIAGNOSTIC_ENABLED
    || TARGET_DIAGNOSTIC_ENABLED
    || SEND_DIAGNOSTIC_ENABLED
const MAX_FILE_BYTES = Math.max(1024 * 1024,
    parseInt(process.env.MULTI_CHAIN_DIAGNOSTIC_MAX_BYTES || "33554432", 10) || 33554432)
const MAX_PAYLOAD_CHARS = Math.max(512,
    parseInt(process.env.MULTI_CHAIN_DIAGNOSTIC_MAX_PAYLOAD_CHARS || "16384", 10) || 16384)
const RECEIVE_GAP_MS = positiveInteger(process.env.MULTI_CHAIN_DIAGNOSTIC_GAP_MS, 3_000, 100)
const EVENT_LOOP_SAMPLE_MS = positiveInteger(
    process.env.MULTI_CHAIN_DIAGNOSTIC_EVENT_LOOP_SAMPLE_MS,
    250,
    50,
)
const EVENT_LOOP_LAG_MS = positiveInteger(
    process.env.MULTI_CHAIN_DIAGNOSTIC_EVENT_LOOP_LAG_MS,
    250,
    10,
)

const roomStates = new Map<string, RoomDiagnosticState>()
const receiveStates = new Map<string, ConnectionReceiveState>()
const targetedRooms = new Map<string, TargetedRoomState>()
let stream: fs.WriteStream | undefined
let writtenBytes = 0
let stoppedByLimit = false
let eventLoopTimer: NodeJS.Timeout | undefined

function roomKey(client: SessionClient): string {
    return `${client.roomNumber}:${client.roomGeneration}`
}

function contextRoomKey(context: BattleSendDiagnosticContext): string | undefined {
    if (context.roomNumber === undefined || context.roomGeneration === undefined) return undefined
    return `${context.roomNumber}:${context.roomGeneration}`
}

function monotonicTime(): string {
    return process.hrtime.bigint().toString()
}

function ensureStream(): fs.WriteStream | undefined {
    if (!ANY_DIAGNOSTIC_ENABLED || stoppedByLimit) return undefined
    if (stream) return stream
    const logDirectory = path.join(process.cwd(), ".logs")
    fs.mkdirSync(logDirectory, { recursive: true })
    const stamp = new Date().toISOString().replace(/[:.]/g, "-")
    const logPath = path.join(logDirectory, `multi-chain-${stamp}-${process.pid}.jsonl`)
    stream = fs.createWriteStream(logPath, { flags: "a" })
    stream.on("error", (error) => {
        if (!stoppedByLimit) console.warn(`[MULTI-CHAIN] diagnostic log failed: ${error.message}`)
        stoppedByLimit = true
    })
    console.warn(`[MULTI-CHAIN] diagnostic enabled: path=${logPath}`
        + ` fullRelay=${FULL_DIAGNOSTIC_ENABLED} sendAnomaly=${SEND_DIAGNOSTIC_ENABLED}`
        + ` targetViewers=${[...TARGET_VIEWER_IDS].join(",") || "none"}`
        + " automaticFallback=disabled_pending_packet_identification")
    return stream
}

function safePayload(data: unknown): { json: string; truncated: boolean } {
    let json: string
    try {
        json = JSON.stringify(data)
    } catch {
        json = JSON.stringify({ unserializable: true })
    }
    if (json.length <= MAX_PAYLOAD_CHARS) return { json, truncated: false }
    return { json: json.slice(0, MAX_PAYLOAD_CHARS), truncated: true }
}

function writeRecord(record: Record<string, unknown>): void {
    const output = ensureStream()
    if (!output) return
    const line = JSON.stringify(record) + "\n"
    const bytes = Buffer.byteLength(line)
    if (writtenBytes + bytes > MAX_FILE_BYTES) {
        stoppedByLimit = true
        output.end()
        stream = undefined
        console.warn(`[MULTI-CHAIN] diagnostic stopped at byte limit: maxBytes=${MAX_FILE_BYTES}`)
        return
    }
    writtenBytes += bytes
    output.write(line)
}

function stopEventLoopMonitorIfIdle(): void {
    if (targetedRooms.size > 0 || !eventLoopTimer) return
    clearInterval(eventLoopTimer)
    eventLoopTimer = undefined
}

function ensureEventLoopMonitor(): void {
    if (!TARGET_DIAGNOSTIC_ENABLED || eventLoopTimer) return
    let expectedAt = Date.now() + EVENT_LOOP_SAMPLE_MS
    eventLoopTimer = setInterval(() => {
        const now = Date.now()
        const lagMs = Math.max(0, now - expectedAt)
        expectedAt = now + EVENT_LOOP_SAMPLE_MS
        if (targetedRooms.size === 0 || lagMs < EVENT_LOOP_LAG_MS) return
        writeRecord({
            event: "event_loop_lag",
            time: new Date(now).toISOString(),
            monotonicNs: monotonicTime(),
            lagMs,
            trackedRooms: [...targetedRooms].map(([key, state]) => ({
                roomKey: key,
                matchedViewers: state.matchedViewers,
            })),
        })
    }, EVENT_LOOP_SAMPLE_MS)
    eventLoopTimer.unref()
}

function activateTargetedRoom(
    roomNumber: string,
    generation: number,
    participants: readonly Pick<SessionClient, "connectionId" | "viewerId">[],
    reason: string,
): boolean {
    if (!TARGET_DIAGNOSTIC_ENABLED) return false
    const key = `${roomNumber}:${generation}`
    if (targetedRooms.has(key)) return true

    const matchedViewers = [...new Set(participants
        .map(participant => participant.viewerId)
        .filter(viewerId => TARGET_VIEWER_IDS.has(viewerId)))]
    if (matchedViewers.length === 0) return false

    targetedRooms.set(key, { matchedViewers })
    ensureEventLoopMonitor()
    writeRecord({
        event: "battle_room_targeted",
        time: new Date().toISOString(),
        monotonicNs: monotonicTime(),
        room: roomNumber,
        generation,
        reason,
        matchedViewers,
        participantConnections: participants.map(participant => participant.connectionId),
        participantViewers: participants.map(participant => participant.viewerId),
    })
    return true
}

function shouldRecordRoom(
    source: SessionClient,
    participants: readonly SessionClient[] = [],
    reason = "packet",
): boolean {
    if (!TARGET_DIAGNOSTIC_ENABLED) return FULL_DIAGNOSTIC_ENABLED
    if (targetedRooms.has(roomKey(source))) return true
    if (!TARGET_VIEWER_IDS.has(source.viewerId)
        && !participants.some(participant => TARGET_VIEWER_IDS.has(participant.viewerId))) {
        return FULL_DIAGNOSTIC_ENABLED
    }
    const uniqueParticipants = [...new Map(
        [source, ...participants].map(participant => [participant.connectionId, participant]),
    ).values()]
    const targeted = activateTargetedRoom(
        source.roomNumber,
        source.roomGeneration,
        uniqueParticipants,
        reason,
    )
    return FULL_DIAGNOSTIC_ENABLED || targeted
}

function nextState(client: SessionClient): RoomDiagnosticState {
    const key = roomKey(client)
    let state = roomStates.get(key)
    if (!state) {
        state = { generation: client.roomGeneration, packetSequence: 0, lastObservedAt: Date.now() }
        roomStates.set(key, state)
    }
    state.packetSequence += 1
    state.lastObservedAt = Date.now()
    return state
}

export function recordBattleRelay(
    source: SessionClient,
    recipients: readonly SessionClient[],
    kind: RelayKind,
    transportTag: number,
    data: unknown,
): void {
    if (!shouldRecordRoom(source, recipients, "relay")) return
    const state = nextState(source)
    const payload = safePayload(data)
    writeRecord({
        event: "battle_relay",
        time: new Date().toISOString(),
        monotonicNs: monotonicTime(),
        room: source.roomNumber,
        generation: source.roomGeneration,
        sequence: state.packetSequence,
        sourceConnection: source.connectionId,
        sourceViewer: source.viewerId,
        recipientConnections: recipients.map((client) => client.connectionId),
        recipientViewers: recipients.map((client) => client.viewerId),
        recipientSocketWritableLengths: recipients.map(client => client.socket.writableLength),
        kind,
        transportTag,
        payload: payload.json,
        payloadTruncated: payload.truncated,
    })
}

export function recordBattleNotify(client: SessionClient, notifyTag: number, data: unknown): void {
    if (!shouldRecordRoom(client, [], "notify")) return
    const state = nextState(client)
    const payload = safePayload(data)
    writeRecord({
        event: "battle_notify",
        time: new Date().toISOString(),
        monotonicNs: monotonicTime(),
        room: client.roomNumber,
        generation: client.roomGeneration,
        sequence: state.packetSequence,
        sourceConnection: client.connectionId,
        sourceViewer: client.viewerId,
        notifyTag,
        payload: payload.json,
        payloadTruncated: payload.truncated,
    })
}

export function recordBattleReceive(client: SessionClient, data: unknown): void {
    if (!shouldRecordRoom(client, [], "receive")) return
    const now = Date.now()
    const key = `${roomKey(client)}:${client.connectionId}`
    const previous = receiveStates.get(key)
    const receiveSequence = (previous?.packetSequence ?? 0) + 1
    const gapMs = previous ? Math.max(0, now - previous.lastReceivedAt) : null
    receiveStates.set(key, { packetSequence: receiveSequence, lastReceivedAt: now })

    const transportTag = Array.isArray(data) && typeof data[0] === "number" ? data[0] : null
    const notifyData = transportTag === 0 && Array.isArray(data) && Array.isArray(data[1])
        ? data[1]
        : null
    const notifyTag = notifyData && typeof notifyData[0] === "number" ? notifyData[0] : null
    const broadcastData = transportTag === 1 && Array.isArray(data) && Array.isArray(data[1])
        ? data[1]
        : null

    writeRecord({
        event: "battle_receive",
        time: new Date(now).toISOString(),
        monotonicNs: monotonicTime(),
        room: client.roomNumber,
        generation: client.roomGeneration,
        sourceConnection: client.connectionId,
        sourceViewer: client.viewerId,
        receiveSequence,
        gapMs,
        gapExceeded: gapMs !== null && gapMs >= RECEIVE_GAP_MS,
        transportTag,
        notifyTag,
        broadcastMessageCount: broadcastData?.length,
        socketBytesRead: client.socket.bytesRead,
        socketBytesWritten: client.socket.bytesWritten,
        socketReadableLength: client.socket.readableLength,
        socketWritableLength: client.socket.writableLength,
    })
}

export function recordBattleConnection(
    client: SessionClient,
    action: "connected" | "disconnected" | "replaced",
    participants: readonly SessionClient[] = [],
    phase?: string,
): void {
    if (!shouldRecordRoom(client, participants, `connection_${action}`)) return
    const state = nextState(client)
    writeRecord({
        event: "battle_connection",
        time: new Date().toISOString(),
        monotonicNs: monotonicTime(),
        room: client.roomNumber,
        generation: client.roomGeneration,
        sequence: state.packetSequence,
        action,
        phase,
        connection: client.connectionId,
        viewer: client.viewerId,
        participantConnections: participants.map(participant => participant.connectionId),
        participantViewers: participants.map(participant => participant.viewerId),
        roster: (client.mates ?? []).map(mate => ({
            viewerId: Number(mate?.viewerId) || null,
            comId: Number(mate?.comId) || 0,
            connectionId: mate?.connectionId ?? null,
        })),
        socketDestroyed: client.socket.destroyed,
        socketReadable: client.socket.readable,
        socketWritable: client.socket.writable,
        socketBytesRead: client.socket.bytesRead,
        socketBytesWritten: client.socket.bytesWritten,
        socketReadableLength: client.socket.readableLength,
        socketWritableLength: client.socket.writableLength,
    })
}

export function recordBattleServerSend(
    client: SessionClient,
    channel: string,
    result: "sent" | "queued" | "closed",
    data: unknown,
): void {
    if (!shouldRecordRoom(client, [], "server_send")) return
    const state = nextState(client)
    const payload = safePayload(data)
    writeRecord({
        event: "battle_server_send",
        time: new Date().toISOString(),
        monotonicNs: monotonicTime(),
        room: client.roomNumber,
        generation: client.roomGeneration,
        sequence: state.packetSequence,
        recipientConnection: client.connectionId,
        recipientViewer: client.viewerId,
        channel,
        result,
        socketWritableLength: client.socket.writableLength,
        payload: payload.json,
        payloadTruncated: payload.truncated,
    })
}

export function clearChainDiagnosticRoom(roomNumber: string): void {
    if (!ANY_DIAGNOSTIC_ENABLED) return
    for (const key of roomStates.keys()) {
        if (key.startsWith(`${roomNumber}:`)) roomStates.delete(key)
    }
    for (const key of receiveStates.keys()) {
        if (key.startsWith(`${roomNumber}:`)) receiveStates.delete(key)
    }
    for (const key of targetedRooms.keys()) {
        if (!key.startsWith(`${roomNumber}:`)) continue
        writeRecord({
            event: "battle_room_tracking_stopped",
            time: new Date().toISOString(),
            monotonicNs: monotonicTime(),
            room: roomNumber,
            roomKey: key,
        })
        targetedRooms.delete(key)
    }
    stopEventLoopMonitorIfIdle()
}

export interface BattleSendDiagnosticContext {
    roomNumber?: string
    connectionId?: string
    viewerId?: number
    roomGeneration?: number
    channel?: string
}

export function recordBattleSendAnomaly(
    anomaly: string,
    context?: BattleSendDiagnosticContext,
    details: Record<string, unknown> = {},
): void {
    const key = context ? contextRoomKey(context) : undefined
    let targeted = key ? targetedRooms.has(key) : false
    if (!targeted && context?.viewerId !== undefined && TARGET_VIEWER_IDS.has(context.viewerId)
        && context.roomNumber !== undefined && context.roomGeneration !== undefined) {
        targeted = activateTargetedRoom(
            context.roomNumber,
            context.roomGeneration,
            [{ connectionId: context.connectionId ?? "unknown", viewerId: context.viewerId }],
            "send_anomaly",
        )
    }
    if (!SEND_DIAGNOSTIC_ENABLED && !targeted) return
    writeRecord({
        event: "battle_send_anomaly",
        anomaly,
        time: new Date().toISOString(),
        monotonicNs: monotonicTime(),
        room: context?.roomNumber,
        generation: context?.roomGeneration,
        connection: context?.connectionId,
        viewer: context?.viewerId,
        channel: context?.channel,
        ...details,
    })
}

export function isBattleSendDiagnosticEnabled(): boolean {
    return SEND_DIAGNOSTIC_ENABLED || TARGET_DIAGNOSTIC_ENABLED
}

// Layer two intentionally remains observation-only until a real multi-human
// sample identifies the official Chain trigger packet. Guessing a packet here
// could produce duplicate damage or diverging battle simulations.
export function isAutomaticChainFallbackEnabled(): boolean {
    return false
}
