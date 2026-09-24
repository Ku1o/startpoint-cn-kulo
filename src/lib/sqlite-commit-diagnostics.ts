import type { Database } from "better-sqlite3"
import { closeSync, openSync, readSync } from "node:fs"
import { endianness } from "node:os"
import { performance } from "node:perf_hooks"
import { sqliteDiagnosticsEnabled } from "./memory-diagnostics"

type Kind = "single" | "immediate"
interface WalState { frames: number, backfilled: number, generation: string, pageSize: number }
interface Settings { journalMode: string | null, synchronous: number | null, autoCheckpoint: number | null, busyTimeout: number | null }
export interface CommitProbe {
    kind: Kind, startedAt: number, cpu: NodeJS.CpuUsage, before: WalState | null, settings: Settings,
}
const settingsCache = new WeakMap<Database, Settings>()
const littleEndian = endianness() === "LE"
const uint32 = (b: Buffer, offset: number) => littleEndian ? b.readUInt32LE(offset) : b.readUInt32BE(offset)
const uint16 = (b: Buffer, offset: number) => littleEndian ? b.readUInt16LE(offset) : b.readUInt16BE(offset)

/** Read WAL-index metadata only; never run a checkpoint or read player rows. */
export function readWalCommitState(db: Database): WalState | null {
    if (!db.open || db.memory || !db.name) return null
    let fd: number | undefined
    try {
        fd = openSync(`${db.name}-shm`, "r")
        const header = Buffer.allocUnsafe(100), verify = Buffer.allocUnsafe(100)
        // Matching copies and repeated reads reject concurrent/torn observations.
        if (readSync(fd, header, 0, 100, 0) !== 100 || readSync(fd, verify, 0, 100, 0) !== 100
            || !header.equals(verify) || !header.subarray(0, 48).equals(header.subarray(48, 96))
            || uint32(header, 0) !== 3007000 || header[12] !== 1) return null
        const frames = uint32(header, 16), backfilled = uint32(header, 96)
        if (backfilled > frames) return null
        const size = uint16(header, 14)
        return { frames, backfilled, generation: header.subarray(32, 40).toString("hex"), pageSize: size === 1 ? 65536 : size }
    } catch { return null }
    finally { if (fd !== undefined) { try { closeSync(fd) } catch { /* diagnostic only */ } } }
}

function settingsFor(db: Database): Settings {
    let settings = settingsCache.get(db)
    if (settings) return settings
    const read = (key: string) => { try { return db.pragma(key, { simple: true }) } catch { return null } }
    const number = (key: string) => { const v = read(key); return typeof v === "number" ? v : null }
    const mode = read("journal_mode")
    settings = { journalMode: typeof mode === "string" ? mode : null, synchronous: number("synchronous"),
        autoCheckpoint: number("wal_autocheckpoint"), busyTimeout: number("busy_timeout") }
    settingsCache.set(db, settings)
    return settings
}

export function beginCommitProbe(db: Database, kind: Kind): CommitProbe | undefined {
    if (!sqliteDiagnosticsEnabled() || /^(0|false|no|off)$/i.test(process.env.SQLITE_COMMIT_DIAGNOSTICS ?? "true")
        || /^(0|false|no|off)$/i.test(process.env.ROUTE_PERF_SUMMARY ?? "true")) return
    const settings = settingsFor(db)
    const before = settings.journalMode === "wal" ? readWalCommitState(db) : null
    return { kind, settings, before, cpu: process.cpuUsage(), startedAt: performance.now() }
}

interface Sample {
    timestamp: string, kind: Kind, wallMs: number, processCpuMs: number, success: boolean, errorCode: string | null,
    settings: Settings, before: WalState | null, after: WalState | null,
    checkpointProgress: boolean | null, walReset: boolean | null,
}
const stats = () => ({ n: 0, totalMs: 0, maxMs: 0, errors: 0, slow: 0, checkpointProgress: 0, unavailableWal: 0 })
let totals = stats(), samples: Sample[] = [], omitted = 0
const rounded = (n: number) => Math.round(n * 1000) / 1000

export function endCommitProbe(db: Database, probe: CommitProbe | undefined, success: boolean, error?: unknown): void {
    if (!probe) return
    // Exclude the following metadata read from the measured COMMIT interval.
    const wallMs = performance.now() - probe.startedAt
    const cpu = process.cpuUsage(probe.cpu)
    totals.n++; totals.totalMs += wallMs; totals.maxMs = Math.max(totals.maxMs, wallMs)
    if (!success) totals.errors++
    const configured = Number(process.env.SQLITE_SLOW_COMMIT_MS ?? 100)
    const threshold = Number.isFinite(configured) ? Math.max(0, configured) : 100
    if (success && wallMs < threshold) return
    totals.slow++
    const after = probe.settings.journalMode === "wal" ? readWalCommitState(db) : null
    const before = probe.before
    const walReset = before && after ? before.generation !== after.generation : null
    // Observed progress does not identify the connection that performed it.
    const checkpointProgress = before && after
        ? (walReset ? after.backfilled > 0 : after.backfilled > before.backfilled) : null
    if (checkpointProgress) totals.checkpointProgress++
    if (!before || !after) totals.unavailableWal++
    const code = String((error as { code?: string } | undefined)?.code ?? "")
    samples.push({ timestamp: new Date().toISOString(), kind: probe.kind, wallMs: rounded(wallMs),
        processCpuMs: rounded((cpu.user + cpu.system) / 1000), success,
        errorCode: /^SQLITE_[A-Z_]+$/.test(code) ? code : success ? null : "unknown",
        settings: probe.settings, before, after, checkpointProgress, walReset })
    samples.sort((a, b) => b.wallMs - a.wallMs)
    if (samples.length > 8) { samples.pop(); omitted++ }
}

export function drainSqliteCommitDiagnostics() {
    const summary = { ...totals, totalMs: rounded(totals.totalMs), maxMs: rounded(totals.maxMs),
        avgMs: totals.n ? rounded(totals.totalMs / totals.n) : 0, samples, omitted }
    totals = stats(); samples = []; omitted = 0
    return summary
}
