import * as fs from "fs"
import * as path from "path"
import type { SessionClient } from "../state/SessionManager"

type RelayKind = "broadcast" | "direct" | "notify"

interface RoomDiagnosticState {
    generation: number
    packetSequence: number
    lastObservedAt: number
}

function enabled(value: string | undefined): boolean {
    return /^(1|true|yes|on)$/i.test(value ?? "false")
}

const FULL_DIAGNOSTIC_ENABLED = enabled(process.env.MULTI_CHAIN_DIAGNOSTIC)
const SEND_DIAGNOSTIC_ENABLED = enabled(
    process.env.MULTI_CHAIN_SEND_DIAGNOSTIC ?? process.env.MULTI_CHAIN_DIAGNOSTIC,
)
const ANY_DIAGNOSTIC_ENABLED = FULL_DIAGNOSTIC_ENABLED || SEND_DIAGNOSTIC_ENABLED
const MAX_FILE_BYTES = Math.max(1024 * 1024,
    parseInt(process.env.MULTI_CHAIN_DIAGNOSTIC_MAX_BYTES || "33554432", 10) || 33554432)
const MAX_PAYLOAD_CHARS = Math.max(512,
    parseInt(process.env.MULTI_CHAIN_DIAGNOSTIC_MAX_PAYLOAD_CHARS || "16384", 10) || 16384)

const roomStates = new Map<string, RoomDiagnosticState>()
let stream: fs.WriteStream | undefined
let writtenBytes = 0
let stoppedByLimit = false

function roomKey(client: SessionClient): string {
    return `${client.roomNumber}:${client.roomGeneration}`
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
    if (!FULL_DIAGNOSTIC_ENABLED) return
    const state = nextState(source)
    const payload = safePayload(data)
    writeRecord({
        event: "battle_relay",
        time: new Date().toISOString(),
        room: source.roomNumber,
        generation: source.roomGeneration,
        sequence: state.packetSequence,
        sourceConnection: source.connectionId,
        sourceViewer: source.viewerId,
        recipientConnections: recipients.map((client) => client.connectionId),
        recipientViewers: recipients.map((client) => client.viewerId),
        kind,
        transportTag,
        payload: payload.json,
        payloadTruncated: payload.truncated,
    })
}

export function recordBattleNotify(client: SessionClient, notifyTag: number, data: unknown): void {
    if (!FULL_DIAGNOSTIC_ENABLED) return
    const state = nextState(client)
    const payload = safePayload(data)
    writeRecord({
        event: "battle_notify",
        time: new Date().toISOString(),
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

export function clearChainDiagnosticRoom(roomNumber: string): void {
    if (!FULL_DIAGNOSTIC_ENABLED) return
    for (const key of roomStates.keys()) {
        if (key.startsWith(`${roomNumber}:`)) roomStates.delete(key)
    }
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
    if (!SEND_DIAGNOSTIC_ENABLED) return
    writeRecord({
        event: "battle_send_anomaly",
        anomaly,
        time: new Date().toISOString(),
        room: context?.roomNumber,
        generation: context?.roomGeneration,
        connection: context?.connectionId,
        viewer: context?.viewerId,
        channel: context?.channel,
        ...details,
    })
}

export function isBattleSendDiagnosticEnabled(): boolean {
    return SEND_DIAGNOSTIC_ENABLED
}

// Layer two intentionally remains observation-only until a real multi-human
// sample identifies the official Chain trigger packet. Guessing a packet here
// could produce duplicate damage or diverging battle simulations.
export function isAutomaticChainFallbackEnabled(): boolean {
    return false
}
