interface PendingRoomAdmission {
    generation: number
    expiresAt: number
}

const DEFAULT_ADMISSION_TTL_MS = 15_000

function resolveAdmissionTtlMs(): number {
    const configured = Number.parseInt(
        process.env.MULTI_ROOM_ADMISSION_TTL_MS ?? String(DEFAULT_ADMISSION_TTL_MS),
        10,
    )
    return Number.isFinite(configured) && configured >= 1_000
        ? configured
        : DEFAULT_ADMISSION_TTL_MS
}

/**
 * Reserves the two guest seats between HTTP room selection and the TCP lobby
 * handshake. Without this bridge, several bell recipients can all pass the
 * HTTP capacity check before any of their sockets have connected.
 */
export class RoomAdmissionRegistry {
    private readonly admissions = new Map<string, Map<number, PendingRoomAdmission>>()

    constructor(private readonly ttlMs: number = resolveAdmissionTtlMs()) {}

    private prune(roomNumber: string, generation: number, now: number): Map<number, PendingRoomAdmission> | null {
        const roomAdmissions = this.admissions.get(roomNumber)
        if (!roomAdmissions) return null

        for (const [viewerId, admission] of roomAdmissions) {
            if (admission.generation !== generation || admission.expiresAt <= now) {
                roomAdmissions.delete(viewerId)
            }
        }
        if (roomAdmissions.size === 0) {
            this.admissions.delete(roomNumber)
            return null
        }
        return roomAdmissions
    }

    has(
        roomNumber: string,
        generation: number,
        viewerId: number,
        now: number = Date.now(),
    ): boolean {
        return this.prune(roomNumber, generation, now)?.has(viewerId) ?? false
    }

    getOccupancy(
        roomNumber: string,
        generation: number,
        occupiedViewerIds: Iterable<number>,
        now: number = Date.now(),
    ): number {
        const viewers = new Set(occupiedViewerIds)
        for (const viewerId of this.prune(roomNumber, generation, now)?.keys() ?? []) {
            viewers.add(viewerId)
        }
        return viewers.size
    }

    reserve(
        roomNumber: string,
        generation: number,
        viewerId: number,
        occupiedViewerIds: Iterable<number>,
        capacity: number,
        now: number = Date.now(),
    ): boolean {
        const occupied = new Set(occupiedViewerIds)
        if (occupied.has(viewerId)) return true

        let roomAdmissions = this.prune(roomNumber, generation, now)
        const existing = roomAdmissions?.get(viewerId)
        if (existing) {
            existing.expiresAt = now + this.ttlMs
            return true
        }

        const occupancy = this.getOccupancy(roomNumber, generation, occupied, now)
        if (occupancy >= capacity) return false

        if (!roomAdmissions) {
            roomAdmissions = new Map()
            this.admissions.set(roomNumber, roomAdmissions)
        }
        roomAdmissions.set(viewerId, {
            generation,
            expiresAt: now + this.ttlMs,
        })
        return true
    }

    consume(roomNumber: string, generation: number, viewerId: number, now: number = Date.now()): boolean {
        const roomAdmissions = this.prune(roomNumber, generation, now)
        if (!roomAdmissions?.delete(viewerId)) return false
        if (roomAdmissions.size === 0) this.admissions.delete(roomNumber)
        return true
    }

    release(roomNumber: string, viewerId: number): void {
        const roomAdmissions = this.admissions.get(roomNumber)
        roomAdmissions?.delete(viewerId)
        if (roomAdmissions?.size === 0) this.admissions.delete(roomNumber)
    }

    clearRoom(roomNumber: string): void {
        this.admissions.delete(roomNumber)
    }
}

export const roomAdmissionRegistry = new RoomAdmissionRegistry()
