import { randomInt } from "crypto"
import { FastifyRequest } from "fastify"
import { AsyncLocalStorage } from "node:async_hooks"

// The server's current time offset (real time + offset = simulated time)
let timeOffset: number | null = null;  // business clock; milliseconds, null = use system time
export interface ServerClockSnapshot {
    readonly version: 1
    readonly mode: "legacy" | "real"
    readonly businessOffsetMs: number | null
    readonly legacyBattleOffsetMs: number | null
    readonly cutoverRealMs: number | null
    readonly dayAnchorMs: number | null
    readonly weekAnchorMs: number | null
    readonly revision: number
}
let clockSnapshot: Readonly<ServerClockSnapshot> = Object.freeze({ version: 1, mode: "legacy",
    businessOffsetMs: null, legacyBattleOffsetMs: null, cutoverRealMs: null, dayAnchorMs: null, weekAnchorMs: null, revision: 0 })
const clockSnapshotListeners = new Set<(snapshot: Readonly<ServerClockSnapshot>) => void>()

/** Strictly validate the complete coordinate before changing any process state. */
export function validateServerClockSnapshot(value: unknown): asserts value is ServerClockSnapshot {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid server clock snapshot")
    const clock = value as ServerClockSnapshot
    const keys = ["version", "mode", "businessOffsetMs", "legacyBattleOffsetMs", "cutoverRealMs", "dayAnchorMs", "weekAnchorMs", "revision"]
    if (Object.keys(value).length !== keys.length || keys.some(key => !Object.prototype.hasOwnProperty.call(value, key))) throw new Error("Invalid server clock snapshot schema")
    if (clock.version !== 1 || !["legacy", "real"].includes(clock.mode) || !Number.isSafeInteger(clock.revision) || clock.revision < 0) throw new Error("Unsupported server clock snapshot")
    for (const offset of [clock.businessOffsetMs, clock.legacyBattleOffsetMs]) {
        if (offset !== null && !Number.isSafeInteger(offset)) throw new Error("Invalid server clock offset")
    }
    const anchors = [clock.cutoverRealMs, clock.dayAnchorMs, clock.weekAnchorMs]
    if (clock.mode === "legacy") {
        if (clock.businessOffsetMs !== clock.legacyBattleOffsetMs || anchors.some(anchor => anchor !== null)) throw new Error("Invalid legacy server clock")
    } else {
        if (clock.businessOffsetMs !== 0 || clock.revision < 1 || anchors.some(anchor => typeof anchor !== "number"
            || !Number.isSafeInteger(anchor) || anchor < 0 || !Number.isFinite(new Date(anchor).getTime()))) throw new Error("Invalid real server clock")
        if (clock.dayAnchorMs! < clock.cutoverRealMs! || clock.weekAnchorMs! < clock.cutoverRealMs!) throw new Error("Invalid server clock anchors")
    }
}
export function getServerClockSnapshot(): Readonly<ServerClockSnapshot> { return clockSnapshot }
export function getConfiguredBusinessTimeOffset(): number | null { return timeOffset }
export function onServerClockSnapshotChanged(listener: (snapshot: Readonly<ServerClockSnapshot>) => void): () => void {
    clockSnapshotListeners.add(listener)
    return () => { clockSnapshotListeners.delete(listener) }
}
/** Startup/worker synchronization only; database activation commits before calling this. */
export function installServerClockSnapshot(snapshot: ServerClockSnapshot): void {
    validateServerClockSnapshot(snapshot)
    const equal = (Object.keys(clockSnapshot) as Array<keyof ServerClockSnapshot>).every(key => clockSnapshot[key] === snapshot[key])
    if (clockSnapshot.mode === "real" && !equal) throw new Error("Persisted real clock is immutable")
    // Persisted real and transient legacy revisions are different epochs.
    if (snapshot.mode === clockSnapshot.mode && snapshot.revision < clockSnapshot.revision) throw new Error("Stale server clock revision")
    if (snapshot.mode === clockSnapshot.mode && snapshot.revision === clockSnapshot.revision && !equal) throw new Error("Server clock revision conflict")
    clockSnapshot = Object.freeze({ ...snapshot })
    timeOffset = snapshot.businessOffsetMs
    publishTimeOffset()
}
console.log(`[TIME] startup offset=${timeOffset ?? 'null(system)'}`);

/**
 * In-process consumers that must share the main thread's virtual clock.
 *
 * The SQLite writer thread is a separate thread with its own copy of this
 * module, so it receives the offset over the worker protocol; this hook is how
 * it hears about later changes (management-panel time changes) without the
 * utility module depending on the writer client.
 */
const timeOffsetListeners = new Set<(offset: number | null) => void>()

interface ServerClockContext { nowMs: number; effectiveOffset: number }
const serverClock = new AsyncLocalStorage<ServerClockContext>()

/** Freeze business time and its coordinate offset together across awaits. */
export function withServerClock<T>(now: number | Date, callback: () => T, effectiveOffset = getTimeOffset() ?? 0): T {
    const nowMs = now instanceof Date ? now.getTime() : now
    if (!Number.isFinite(nowMs) || !Number.isSafeInteger(effectiveOffset)) throw new Error("Invalid server clock context")
    return serverClock.run({ nowMs, effectiveOffset }, callback)
}

export function withCurrentServerClock<T>(callback: () => T): T {
    const captured = serverClock.getStore()
    return captured ? callback() : withServerClock(Date.now() + (timeOffset ?? 0), callback, timeOffset ?? 0)
}

/** The configured legacy offset, unaffected by an individual player's context. */
export function getLegacyTimeOffset(): number | null { return clockSnapshot.legacyBattleOffsetMs }

/** Real time captured at the same execution boundary as the business clock. */
export function getRealServerDate(): Date {
    const captured = serverClock.getStore()
    return new Date(captured ? captured.nowMs - captured.effectiveOffset : Date.now())
}


export function onServerTimeOffsetChanged(listener: (offset: number | null) => void): () => void {
    timeOffsetListeners.add(listener)
    return () => { timeOffsetListeners.delete(listener) }
}

function publishTimeOffset(): void {
    for (const listener of timeOffsetListeners) {
        try {
            listener(timeOffset)
        } catch (error) {
            console.error("[TIME] offset listener failed", error instanceof Error ? error.message : String(error))
        }
    }
    for (const listener of clockSnapshotListeners) {
        try { listener(clockSnapshot) } catch (error) {
            console.error("[TIME] snapshot listener failed", error instanceof Error ? error.message : String(error))
        }
    }
}

/**
 * Returns the current server time as a unix epoch.
 * Without argument: returns simulated current time.
 * With argument: converts the given Date to epoch (ignoring offset for serialization).
 * 
 * @param date An optional date to convert to epoch.
 * @returns The unix epoch.
 */
export function getServerTime(
    date?: Date
): number {
    if (date !== undefined) {
        return Math.floor(date.getTime() / 1000);
    }
    return Math.floor((serverClock.getStore()?.nowMs ?? Date.now() + (timeOffset ?? 0)) / 1000);
}

/**
 * Gets the current server time as a Date.
 * 
 * @returns The current server time as a date.
 */
export function getServerDate(): Date {
    return new Date(serverClock.getStore()?.nowMs ?? Date.now() + (timeOffset ?? 0));
}

/** Convert a real Date (as stored in DB) to virtual epoch seconds for client. */
export function realToVirtual(date: Date): number {
    return Math.floor((date.getTime() + (getTimeOffset() ?? 0)) / 1000);
}

/**
 * Sets a custom server time from an absolute date.
 * The offset (target - real time) is computed and stored.
 * Set to null to reset to system time.
 */
export function setServerTime(date: Date | null) {
    setServerTimeOffset(date ? date.getTime() - Date.now() : null);
    console.log(`[TIME] setServerTime → ${date?.toISOString() || 'null(system)'} offset=${timeOffset}`);
}

/**
 * Sets the time offset directly (used on startup restore).
 */
export function setServerTimeOffset(offset: number | null) {
    if (clockSnapshot.mode === "real") throw new Error("Persisted real clock rejects virtual-time reset")
    installServerClockSnapshot({ version: 1, mode: "legacy", businessOffsetMs: offset, legacyBattleOffsetMs: offset,
        cutoverRealMs: null, dayAnchorMs: null, weekAnchorMs: null, revision: clockSnapshot.revision + 1 })
    console.log(`[TIME] startup restore offset=${offset ?? 'null(system)'}`);
}

/**
 * Returns the raw time offset (used for persistence).
 */
export function getTimeOffset(): number | null {
    return serverClock.getStore()?.effectiveOffset ?? timeOffset;
}

/**
 * Returns server time for a specific player.
 * Content and client time use the global legacy clock; saved EXP offsets are storage coordinates.
 */
export function getServerTimeForPlayer(playerId?: number): number {
    void playerId
    return getServerTime()
}

/**
 * Converts a server time value (unix epoch in seconds) into a Date.
 * 
 * @param serverTime The unix epoch value.
 * @returns The date.
 */
export function getDateFromServerTime(serverTime: number): Date {
    return new Date(serverTime * 1000)
}

/**
 * Generates an IdpAlias to identify a particular device.
 * 
 * @param appId 
 * @param idpId 
 * @param serialNo 
 * @returns The generated IdpAlias
 */
export function generateIdpAlias(
    appId: string,
    deviceId: string,
    serialNo: string
): string {
    return `${appId}:${deviceId}:${serialNo}`
}

/**
 * Generates a random viewer ID using the crypto library.
 * 
 * @returns A number between 100,000,000 and 899,999,999.
 *
 * Values from 900,000,000 onward are reserved by the multiplayer protocol
 * for COM/AI participants. Assigning a real account one of those values makes
 * older clients treat that player as an AI and omit them from co-op results.
 */
export function generateViewerId(): number {
    return randomInt(100000000, 900000000)
}

export interface DataHeaders {
    force_update?: boolean
    asset_update?: boolean
    force_news?: number | null
    short_udid?: number
    viewer_id?: number
    servertime?: number
    result_code?: number
    udid?: string
}

/**
 * Generates a default data headers object, which is used in communication with the client.
 * 
 * @param customValues A partial DataHeaders object with custom fields to replace the default ones.
 * @returns A DataHeaders object.
 */
export function generateDataHeaders(
    customValues: Partial<DataHeaders> = {},
    fields: (keyof DataHeaders)[] = ['force_update', 'asset_update', 'force_news', 'short_udid', 'viewer_id', 'servertime', 'result_code'],
): Record<string, any> {
    const defaultHeaders: DataHeaders = {
        force_update: false,
        asset_update: false,
        force_news: null,
        short_udid: 0,
        viewer_id: 0,
        servertime: 0,
        result_code: 1
    }
    const headers: Record<string, any> = {}

    for (const field of fields) {
        const customValue = customValues[field]
        let defaultValue = defaultHeaders[field]
        // servertime evaluated fresh each request (uses simulated time if set)
        if (field === 'servertime') {
            defaultValue = getServerTime();
        }
        headers[field] = customValue === undefined ? defaultValue : customValue
    }

    return headers
}

export enum Platform {
    ANDROID,
    IOS
}

export function getRequestPlatformSync(
    request: FastifyRequest
): Platform {
    // check user agent
    if ((request.headers["user-agent"] || '').includes('iOS;'))
        return Platform.IOS;

    // check requestedby header
    if ((request.headers["requestedby"] || '') === 'ios')
        return Platform.IOS;

    return Platform.ANDROID
}
