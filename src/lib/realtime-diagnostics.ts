import { registerMemoryCounters } from "./memory-diagnostics"

export type RealtimeDiagnosticMode = "basic" | "room-trace"

export interface RealtimeDiagnosticEvent {
    at: string
    roomNumber: string
    event: string
    details?: Record<string, number | string | boolean | null>
}

interface RealtimeDiagnosticState {
    mode: RealtimeDiagnosticMode
    roomNumber?: string
    expiresAt: number
    maxEvents: number
    events: RealtimeDiagnosticEvent[]
    droppedEvents: number
}

const state: RealtimeDiagnosticState = {
    mode: "basic",
    expiresAt: 0,
    maxEvents: 256,
    events: [],
    droppedEvents: 0,
}

function expireIfNeeded(now = Date.now()): void {
    if (state.mode !== "basic" && state.expiresAt > 0 && state.expiresAt <= now) {
        state.mode = "basic"
        state.roomNumber = undefined
        state.expiresAt = 0
        state.events = []
        state.droppedEvents = 0
    }
}

function positiveInteger(value: unknown, fallback: number, min: number, max: number): number {
    const parsed = typeof value === "number" ? value : Number(value)
    if (!Number.isSafeInteger(parsed)) return fallback
    return Math.min(max, Math.max(min, parsed))
}

export function configureRealtimeDiagnostics(input: {
    mode?: unknown
    roomNumber?: unknown
    ttlMs?: unknown
    maxEvents?: unknown
}): ReturnType<typeof getRealtimeDiagnostics> {
    const mode = input.mode === "room-trace" ? "room-trace" : "basic"
    if (mode === "room-trace") {
        const roomNumber = typeof input.roomNumber === "string" ? input.roomNumber.trim() : ""
        if (!roomNumber) throw new Error("room-trace 模式必须指定 roomNumber")
        state.mode = mode
        state.roomNumber = roomNumber.slice(0, 128)
        state.expiresAt = Date.now() + positiveInteger(input.ttlMs, 10 * 60_000, 30_000, 30 * 60_000)
        state.maxEvents = positiveInteger(input.maxEvents, 256, 16, 2_000)
        state.events = []
        state.droppedEvents = 0
    } else {
        state.mode = "basic"
        state.roomNumber = undefined
        state.expiresAt = 0
        state.events = []
        state.droppedEvents = 0
    }
    return getRealtimeDiagnostics()
}

export function getRealtimeDiagnostics(): {
    mode: RealtimeDiagnosticMode
    roomNumber: string | null
    expiresAt: string | null
    remainingMs: number
    maxEvents: number
    bufferedEvents: number
    droppedEvents: number
    events: RealtimeDiagnosticEvent[]
} {
    expireIfNeeded()
    const remainingMs = state.expiresAt > 0 ? Math.max(0, state.expiresAt - Date.now()) : 0
    return {
        mode: state.mode,
        roomNumber: state.roomNumber ?? null,
        expiresAt: state.expiresAt > 0 ? new Date(state.expiresAt).toISOString() : null,
        remainingMs,
        maxEvents: state.maxEvents,
        bufferedEvents: state.events.length,
        droppedEvents: state.droppedEvents,
        events: [...state.events],
    }
}

/** Record bounded metadata for one selected room without serializing payloads. */
export function recordRealtimeDiagnostic(
    roomNumber: string,
    event: string,
    details?: Record<string, number | string | boolean | null>,
): void {
    expireIfNeeded()
    if (state.mode !== "room-trace" || state.roomNumber !== roomNumber) return
    if (state.events.length >= state.maxEvents) {
        state.droppedEvents++
        return
    }
    state.events.push({
        at: new Date().toISOString(),
        roomNumber,
        event: event.slice(0, 80),
        ...(details ? { details } : {}),
    })
}

registerMemoryCounters("realtimeDiagnostics", () => {
    expireIfNeeded()
    return {
        modeRoomTrace: state.mode === "room-trace",
        traceRoomActive: state.roomNumber ? 1 : 0,
        traceRemainingMs: state.expiresAt > 0 ? Math.max(0, state.expiresAt - Date.now()) : 0,
        bufferedEvents: state.events.length,
        droppedEvents: state.droppedEvents,
    }
})
