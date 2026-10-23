import { createHash } from "node:crypto"
import { execFileSync } from "node:child_process"
import { existsSync, realpathSync, statSync } from "node:fs"
import { isAbsolute, join, relative, resolve, sep } from "node:path"
import type { Database } from "better-sqlite3"

/** No default connection, clock setter, initializer or login hook is used here. */
export interface OfflineDatabaseGuard {
    kind: "approved-offline-file"
    databasePath: string
    allowedRoot: string
    protectedRoots?: string[]
}
export interface TimeCutoverRehearsalOptions {
    cutoverRealMs: number
    legacyOffsetMs: number | null
    offlineGuard?: OfflineDatabaseGuard
}
export interface CutoverDiagnostic {
    code: string
    playerId?: number
    playId?: string
    detail: string
}
export interface PlayerCutoverPatch {
    playerId: number
    basis: "saved-offset" | "unknown" | "existing-v1"
    before: { exp_pooled_time: unknown; time_offset: unknown }
    after: { exp_pooled_time: unknown; time_offset: unknown }
    createMarker: boolean
}
export interface TimeCutoverRehearsalPlan {
    version: 1
    digest: string
    beforeDigest: string
    preservedDigest: string
    cutoverRealMs: number
    legacyOffsetMs: number | null
    markerTableExisted: boolean
    players: PlayerCutoverPatch[]
    diagnostics: CutoverDiagnostic[]
}
export interface TimeCutoverApplyOptions extends TimeCutoverRehearsalOptions {
    expectedPlanDigest: string
    faultAt?: "after-schema" | "after-player-update" | "before-ledger" | "after-ledger"
}
export interface TimeCutoverRollbackOptions {
    expectedPlanDigest: string
    offlineGuard?: OfflineDatabaseGuard
    faultAt?: "after-player-restore" | "before-ledger"
}
export const TIME_CUTOVER_REHEARSAL_LEDGER = "time_cutover_rehearsal_ledger"
type Row = Record<string, unknown>
type Ledger = { plan_digest: string; plan_json: string; after_digest: string; status: string }
const quote = (s: string) => `"${s.replace(/"/g, '""')}"`
function canonical(value: unknown): string {
    return JSON.stringify(value, (_key, item) => typeof item === "bigint" ? { bigint: item.toString() } : item)
}
const hash = (value: unknown) => createHash("sha256").update(canonical(value)).digest("hex")
function hasTable(db: Database, name: string): boolean {
    return !!db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(name)
}
function validEpoch(value: unknown): value is number {
    return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
        && Number.isFinite(new Date(value).getTime())
}
function validateOptions(options: TimeCutoverRehearsalOptions): void {
    if (!validEpoch(options.cutoverRealMs)) throw new Error("Invalid cutoverRealMs")
    if (options.legacyOffsetMs !== null && !Number.isSafeInteger(options.legacyOffsetMs)) throw new Error("Invalid legacyOffsetMs")
}
function within(root: string, candidate: string): boolean {
    const suffix = relative(root, candidate)
    return suffix === "" || (!isAbsolute(suffix) && suffix !== ".." && !suffix.startsWith(`..${sep}`))
}
/** The caller has already opened the explicit synthetic/offline database. This only checks it. */
export function assertTimeCutoverOfflineDatabaseSync(db: Database, guard?: OfflineDatabaseGuard): void {
    if (!db.open || db.readonly || db.inTransaction) throw new Error("Cutover requires an open writable explicit database outside a transaction")
    if (db.prepare("SELECT 1 FROM sqlite_temp_master WHERE type IN ('table','view') AND name IN (SELECT name FROM sqlite_master)").get()) {
        throw new Error("Temporary shadow of persistent cutover state is forbidden")
    }
    const databases = db.prepare("PRAGMA database_list").all() as Array<{ name: string; file: string }>
    if (databases.some(row => row.name !== "main" && row.name !== "temp")) throw new Error("Attached databases are forbidden in rehearsal")
    if (db.name === ":memory:" && databases.find(row => row.name === "main")?.file === "") return
    if (!guard || guard.kind !== "approved-offline-file" || !isAbsolute(guard.databasePath) || !isAbsolute(guard.allowedRoot)) {
        throw new Error("File database requires an explicit approved offline path guard")
    }
    const file = realpathSync(db.name)
    if (statSync(file).nlink > 1) throw new Error("Hard-linked database files are forbidden in rehearsal")
    const mainFile = databases.find(row => row.name === "main")?.file
    if (!mainFile || realpathSync(mainFile).toLowerCase() !== file.toLowerCase()
        || realpathSync(guard.databasePath).toLowerCase() !== file.toLowerCase()) throw new Error("Offline database path mismatch")
    const root = realpathSync(guard.allowedRoot)
    if (!within(root, file) || /(^|[\\/])(\.database|\.cdn|config)([\\/]|$)/i.test(file)) throw new Error("Database outside approved offline scope")
    // Discover every currently registered checkout. Fixed historical lists miss
    // newly created worktrees; aliases below are resolved before any write.
    const inventory = execFileSync("git", ["-c", "core.quotePath=false", "worktree", "list", "--porcelain"],
        { cwd: resolve(__dirname, "../.."), encoding: "utf8", windowsHide: true })
    const registeredRoots = inventory.split(/\r?\n/).filter(line => line.startsWith("worktree ")).map(line => line.slice(9))
    if (registeredRoots.length === 0) throw new Error("Cannot establish protected Git worktree inventory")
    const protectedRoots = [...new Set([...registeredRoots, ...(guard.protectedRoots ?? [])])]

    for (const protectedRoot of protectedRoots) {
        // A missing required protected location cannot silently weaken the guard.
        if (within(realpathSync(protectedRoot), file)) throw new Error("Protected database location is forbidden")
        const databaseDirectory = join(protectedRoot, ".database")
        if (existsSync(databaseDirectory) && within(realpathSync(databaseDirectory), file)) throw new Error("Protected database directory alias is forbidden")
    }
}
/** Full database state, including shared/indirect progress and real-time receipts, protects rollback. */
function databaseDigests(db: Database, protection?: { markerTableExisted: boolean; players: PlayerCutoverPatch[] }, ignoreServerClockState = false): { digest: string; preservedDigest: string } {
    const schema = (db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").all() as Row[])
        .filter(row => row.name !== TIME_CUTOVER_REHEARSAL_LEDGER && row.tbl_name !== TIME_CUTOVER_REHEARSAL_LEDGER
            && (!ignoreServerClockState || (row.name !== "server_clock_state" && row.tbl_name !== "server_clock_state")))
    const tables = schema.filter(row => row.type === "table").map(row => String(row.name))
    const digest = createHash("sha256").update(canonical(schema)).update("\n")
    const preservedSchema = protection && !protection.markerTableExisted ? schema.filter(row => row.tbl_name !== "player_time_state") : schema
    const preserved = createHash("sha256").update(canonical(preservedSchema)).update("\n")
    const mutablePlayers = new Set(protection?.players.filter(player => player.createMarker).map(player => player.playerId) ?? [])
    // Stream large historical tables rather than materializing a second copy in memory.
    // Table traversal remains in SQLite storage order; harmless reordering is a conservative conflict.
    for (const name of tables) {
        digest.update(canonical(name)).update("\n")
        const skipTable = name === "player_time_state" && protection && !protection.markerTableExisted
        if (!skipTable) preserved.update(canonical(name)).update("\n")
        // Adjacent SQLite INTEGER values above 2^53 must never collapse to the same hash.
        const statement = db.prepare(`SELECT * FROM ${quote(name)}`).raw().safeIntegers()
        const columns = statement.columns().map(column => column.name)
        for (const row of statement.iterate() as Iterable<unknown[]>) {
            digest.update(canonical(row)).update("\n")
            if (skipTable || (name === "player_time_state" && mutablePlayers.has(Number(row[columns.indexOf("player_id")])))) continue
            const protectedRow = name === "players" && mutablePlayers.has(Number(row[columns.indexOf("id")]))
                ? row.map((value, index) => ["exp_pooled_time", "time_offset"].includes(columns[index]) ? { cutoverField: columns[index] } : value)
                : row
            preserved.update(canonical(protectedRow)).update("\n")
        }
    }
    return { digest: digest.digest("hex"), preservedDigest: preserved.digest("hex") }
}
export function getTimeCutoverDatabaseDigestSync(db: Database): string {
    return databaseDigests(db).digest
}
/** Read-only protection fingerprint for atomic global-clock integration. Default behavior is unchanged. */
export function getTimeCutoverProtectedDatabaseDigestSync(db: Database, plan: TimeCutoverRehearsalPlan, ignoreServerClockState = false): string {
    return databaseDigests(db, plan, ignoreServerClockState).preservedDigest
}
function checkpoint(value: unknown): number | null {
    if (validEpoch(value)) return value
    // Only timezone-bearing date text is reliable; do not infer the machine timezone.
    if (typeof value !== "string" || !/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value)) return null
    const epoch = new Date(value).getTime()
    return validEpoch(epoch) ? epoch : null
}
function storedCheckpoint(original: unknown, epoch: number): unknown {
    return typeof original === "number" ? epoch : new Date(epoch).toISOString()
}
function buildPlan(db: Database, options: TimeCutoverRehearsalOptions): TimeCutoverRehearsalPlan {
    validateOptions(options)
    const columns = db.prepare("PRAGMA table_info(players)").all() as Array<{ name: string }>
    for (const name of ["id", "exp_pooled_time", "exp_pool", "time_offset"]) {
        if (!columns.some(column => column.name === name)) throw new Error(`Required players column missing: ${name}`)
    }
    const markerTableExisted = hasTable(db, "player_time_state")
    const states = markerTableExisted ? db.prepare("SELECT * FROM player_time_state ORDER BY player_id").all() as Row[] : []
    const byPlayer = new Map(states.map(row => [row.player_id, row]))
    for (const state of states) {
        if (state.version !== 1 || !validEpoch(state.cutover_real_ms) || !validEpoch(state.day_anchor_ms) || !validEpoch(state.week_anchor_ms)) {
            throw new Error("Unsupported or invalid existing player time state")
        }
    }
    const diagnostics: CutoverDiagnostic[] = []
    const players = (db.prepare("SELECT id,exp_pooled_time,time_offset FROM players ORDER BY id").all() as Row[]).map(row => {
        const playerId = Number(row.id)
        if (!Number.isSafeInteger(playerId) || playerId < 1) throw new Error("Invalid player id")
        const before = { exp_pooled_time: row.exp_pooled_time, time_offset: row.time_offset }
        if (byPlayer.has(row.id)) {
            diagnostics.push({ code: "existing-v1-preserved", playerId, detail: "Existing checkpoint, offset and anchors remain untouched" })
            return { playerId, basis: "existing-v1" as const, before, after: before, createMarker: false }
        }
        const saved = checkpoint(row.exp_pooled_time)
        const reliable = typeof row.time_offset === "number" && Number.isSafeInteger(row.time_offset)
            && saved !== null && validEpoch(saved - row.time_offset)
        const real = reliable ? saved! - Number(row.time_offset) : options.cutoverRealMs
        if (!reliable) diagnostics.push({ code: "unknown-exp-basis", playerId,
            detail: "Balance retained; EXP checkpoint restarted at cutover without assuming the global legacy offset" })
        if (reliable && real > options.cutoverRealMs) diagnostics.push({ code: "future-exp-checkpoint-preserved", playerId,
            detail: "Reliable checkpoint converts exactly; future checkpoint is not used to grant EXP" })
        return { playerId, basis: reliable ? "saved-offset" as const : "unknown" as const, before,
            after: { exp_pooled_time: storedCheckpoint(row.exp_pooled_time, real), time_offset: 0 }, createMarker: true }
    })
    if (hasTable(db, "players_active_quests")) {
        for (const play of db.prepare("SELECT * FROM players_active_quests ORDER BY player_id").all() as Row[]) {
            const real = play.clock_version === 1
            diagnostics.push({ code: real ? "real-battle-preserved" : "legacy-battle-preserved", playerId: Number(play.player_id),
                playId: String(play.play_id), detail: real ? "Registered real battle timestamp is already real; elapsed duration remains unchanged"
                    : "No per-play offset provenance: preserve playId, started_at_ms and clock version for existing finish compatibility" })
        }
    }
    const fingerprints = databaseDigests(db, { markerTableExisted, players })
    const unsigned = { version: 1 as const, beforeDigest: fingerprints.digest, preservedDigest: fingerprints.preservedDigest, cutoverRealMs: options.cutoverRealMs,
        legacyOffsetMs: options.legacyOffsetMs, markerTableExisted, players, diagnostics }
    return { ...unsigned, digest: hash(unsigned) }
}
export function planTimeCutoverRehearsalSync(db: Database, options: TimeCutoverRehearsalOptions): TimeCutoverRehearsalPlan {
    assertTimeCutoverOfflineDatabaseSync(db, options.offlineGuard)
    return db.transaction(() => buildPlan(db, options))()
}
function ledger(db: Database, digest: string): Ledger | undefined {
    return hasTable(db, TIME_CUTOVER_REHEARSAL_LEDGER) ? db.prepare(`SELECT * FROM ${TIME_CUTOVER_REHEARSAL_LEDGER} WHERE plan_digest=?`).get(digest) as Ledger | undefined : undefined
}
function fault(actual: string | undefined, at: string): void {
    if (actual === at) throw new Error(`Injected cutover failure: ${at}`)
}
export function applyTimeCutoverRehearsalSync(db: Database, options: TimeCutoverApplyOptions): { status: "applied" | "already-applied"; digest: string } {
    assertTimeCutoverOfflineDatabaseSync(db, options.offlineGuard)
    validateOptions(options)
    return db.transaction(() => {
        if (db.prepare("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?").get(TIME_CUTOVER_REHEARSAL_LEDGER)) {
            throw new Error("Rehearsal ledger triggers are forbidden")
        }
        const existing = ledger(db, options.expectedPlanDigest)
        if (existing?.status === "applied") {
            const prior = JSON.parse(existing.plan_json) as TimeCutoverRehearsalPlan
            if (prior.cutoverRealMs !== options.cutoverRealMs || prior.legacyOffsetMs !== options.legacyOffsetMs) throw new Error("Applied cutover options mismatch")
            return { status: "already-applied" as const, digest: options.expectedPlanDigest }
        }
        if (hasTable(db, TIME_CUTOVER_REHEARSAL_LEDGER) && db.prepare(`SELECT 1 FROM ${TIME_CUTOVER_REHEARSAL_LEDGER} WHERE status='applied'`).get()) throw new Error("Another rehearsal plan is already applied")
        const plan = buildPlan(db, options)
        if (plan.digest !== options.expectedPlanDigest) throw new Error("Plan digest mismatch: state or options changed after preview")
        db.exec(`CREATE TABLE IF NOT EXISTS player_time_state (
            player_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE, version INTEGER NOT NULL,
            cutover_real_ms INTEGER NOT NULL, day_anchor_ms INTEGER NOT NULL, week_anchor_ms INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS ${TIME_CUTOVER_REHEARSAL_LEDGER} (
            plan_digest TEXT PRIMARY KEY, plan_json TEXT NOT NULL, after_digest TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('applied','rolled-back')));`)
        fault(options.faultAt, "after-schema")
        const update = db.prepare("UPDATE players SET exp_pooled_time=?,time_offset=? WHERE id=?")
        const marker = db.prepare("INSERT INTO player_time_state(player_id,version,cutover_real_ms,day_anchor_ms,week_anchor_ms) VALUES (?,1,?,?,?)")
        for (const player of plan.players) if (player.createMarker) {
            update.run(player.after.exp_pooled_time, player.after.time_offset, player.playerId)
            marker.run(player.playerId, options.cutoverRealMs, options.cutoverRealMs, options.cutoverRealMs)
            fault(options.faultAt, "after-player-update")
        }
        for (const player of plan.players) if (player.createMarker) {
            const actual = db.prepare("SELECT exp_pooled_time,time_offset FROM players WHERE id=?").get(player.playerId)
            const state = db.prepare("SELECT * FROM player_time_state WHERE player_id=?").get(player.playerId)
            if (canonical(actual) !== canonical(player.after) || canonical(state) !== canonical({ player_id: player.playerId,
                version: 1, cutover_real_ms: options.cutoverRealMs, day_anchor_ms: options.cutoverRealMs, week_anchor_ms: options.cutoverRealMs })) {
                throw new Error("Cutover write did not produce the exact planned fields and anchors")
            }
        }
        const after = databaseDigests(db, plan)
        if (after.preservedDigest !== plan.preservedDigest) throw new Error("Cutover refused: unrelated persistent state changed during apply")
        fault(options.faultAt, "before-ledger")
        db.prepare(`INSERT INTO ${TIME_CUTOVER_REHEARSAL_LEDGER}(plan_digest,plan_json,after_digest,status) VALUES (?,?,?,'applied')
            ON CONFLICT(plan_digest) DO UPDATE SET plan_json=excluded.plan_json,after_digest=excluded.after_digest,status='applied'`)
            .run(plan.digest, JSON.stringify(plan), after.digest)
        fault(options.faultAt, "after-ledger")
        return { status: "applied" as const, digest: plan.digest }
    }).immediate()
}
export function rollbackTimeCutoverRehearsalSync(db: Database, options: TimeCutoverRollbackOptions): { status: "rolled-back" | "already-rolled-back"; digest: string } {
    assertTimeCutoverOfflineDatabaseSync(db, options.offlineGuard)
    return db.transaction(() => {
        if (db.prepare("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?").get(TIME_CUTOVER_REHEARSAL_LEDGER)) {
            throw new Error("Rehearsal ledger triggers are forbidden")
        }
        const receipt = ledger(db, options.expectedPlanDigest)
        if (!receipt) throw new Error("No rehearsal receipt for rollback")
        if (receipt.status === "rolled-back") return { status: "already-rolled-back" as const, digest: options.expectedPlanDigest }
        const plan = JSON.parse(receipt.plan_json) as TimeCutoverRehearsalPlan
        const { digest, ...unsigned } = plan
        if (digest !== receipt.plan_digest || hash(unsigned) !== digest) throw new Error("Corrupt rehearsal receipt")
        if (getTimeCutoverDatabaseDigestSync(db) !== receipt.after_digest) throw new Error("Rollback refused: progress or real operations changed after apply")
        const update = db.prepare("UPDATE players SET exp_pooled_time=?,time_offset=? WHERE id=?")
        const removeMarker = db.prepare("DELETE FROM player_time_state WHERE player_id=?")
        for (const player of plan.players) if (player.createMarker) {
            update.run(player.before.exp_pooled_time, player.before.time_offset, player.playerId)
            removeMarker.run(player.playerId)
            fault(options.faultAt, "after-player-restore")
        }
        if (!plan.markerTableExisted) db.exec("DROP TABLE player_time_state")
        if (getTimeCutoverDatabaseDigestSync(db) !== plan.beforeDigest) throw new Error("Rollback did not restore the exact pre-apply database")
        fault(options.faultAt, "before-ledger")
        db.prepare(`UPDATE ${TIME_CUTOVER_REHEARSAL_LEDGER} SET status='rolled-back' WHERE plan_digest=?`).run(digest)
        return { status: "rolled-back" as const, digest }
    }).immediate()
}
