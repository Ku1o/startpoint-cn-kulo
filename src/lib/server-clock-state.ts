import type { Database } from "better-sqlite3"
import { createHash } from "node:crypto"
import { getServerClockSnapshot, installServerClockSnapshot, ServerClockSnapshot, validateServerClockSnapshot } from "../utils"
import { assertTimeCutoverOfflineDatabaseSync, getTimeCutoverDatabaseDigestSync, getTimeCutoverProtectedDatabaseDigestSync,
    OfflineDatabaseGuard, buildTimeCutoverPlanInTransactionSync, TimeCutoverRehearsalOptions, TimeCutoverRehearsalPlan } from "./time-cutover-rehearsal"
import { getExistingPlayerTimeStateSync, PlayerTimeState } from "./player-time-compat"
import { assertDeploymentMaintenanceContextSync, DeploymentMaintenanceContext } from "./deployment-maintenance-guard"

export const SERVER_CLOCK_STATE_TABLE = "server_clock_state"
export const SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE = "server_clock_rollback_receipt"
const quoteIdentifier = (value: string): string => `"${value.replace(/"/g, '""')}"`
const serializeReceipt = (value: unknown): string => JSON.stringify(value,
    (_key, item) => typeof item === "bigint" ? { clockReceiptInteger: item.toString() }
        : typeof item === "number" && !Number.isFinite(item) ? { clockReceiptReal: String(item) } : item)
const fingerprint = (value: unknown): string => createHash("sha256").update(serializeReceipt(value)).digest("hex")
const validDigest = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value)
interface ClockRollbackPayload {
    version: 1
    plan: TimeCutoverRehearsalPlan
    snapshot: ServerClockSnapshot
    beforeFingerprint: string
    afterFingerprint: string
    beforeTimeFields: Array<[number, unknown, unknown]>
}
interface ClockRollbackReceipt { payload: ClockRollbackPayload; status: "applied" | "rolled-back" }
const receiptFields = ["id", "version", "plan_digest", "receipt_json", "receipt_digest", "status"]

/** All persistent schema/rows, including old plays, claims, balances, stock and every other ledger.
 * Only this module's self-referential receipt is excluded; it has a separate integrity check.
 * Streaming safeIntegers avoids both large copies and loss of adjacent 64-bit INTEGER values.
 */
function clockPersistentFingerprint(db: Database, protection?: TimeCutoverRehearsalPlan): string {
    if (!db.open) throw new Error("Clock fingerprint requires an open explicit database")
    let schema = db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").all() as Row[]
    schema = schema.filter(row => row.name !== SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE && row.tbl_name !== SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE)
    const tables = schema.filter(row => row.type === "table").map(row => String(row.name))
    const mutablePlayers = new Set(protection?.players.filter(player => player.createMarker).map(player => player.playerId) ?? [])
    const ignoreTable = (name: string): boolean => !!protection && (name === SERVER_CLOCK_STATE_TABLE
        || (name === "player_time_state" && !protection.markerTableExisted))
    const hash = createHash("sha256").update(serializeReceipt(schema.filter(row => !ignoreTable(String(row.tbl_name))))).update("\n")
    for (const pragma of ["user_version", "application_id", "encoding"]) {
        hash.update(serializeReceipt(db.pragma(pragma))).update("\n")
    }
    for (const name of tables) {
        if (ignoreTable(name)) continue
        hash.update(serializeReceipt(name)).update("\n")
        const statement = db.prepare(`SELECT * FROM main.${quoteIdentifier(name)}`).raw().safeIntegers()
        const columns = statement.columns().map(column => column.name)
        for (const row of statement.iterate() as Iterable<unknown[]>) {
            if (name === "player_time_state" && mutablePlayers.has(Number(row[columns.indexOf("player_id")]))) continue
            const values = name === "players" && mutablePlayers.has(Number(row[columns.indexOf("id")]))
                ? row.map((value, index) => ["exp_pooled_time", "time_offset"].includes(columns[index]) ? { clockField: columns[index] } : value)
                : row
            hash.update(serializeReceipt(values)).update("\n")
        }
    }
    return hash.digest("hex")
}

export function getServerClockPersistentFingerprintSync(db: Database): string {
    return clockPersistentFingerprint(db)
}

function assertNoTemporaryStateShadow(db: Database): void {
    if (db.prepare("SELECT 1 FROM sqlite_temp_master WHERE type IN ('table','view') AND name IN (SELECT name FROM sqlite_master)").get()) {
        throw new Error("Temporary shadow of persistent clock/database state is forbidden")
    }
}

function readClockRollbackReceipt(db: Database): ClockRollbackReceipt | null {
    const objects = db.prepare("SELECT type FROM sqlite_master WHERE name=?").all(SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE) as Row[]
    if (objects.length === 0) return null
    if (objects.length !== 1 || objects[0].type !== "table") throw new Error("Invalid clock rollback receipt table")
    const columns = db.prepare(`PRAGMA table_info(${SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE})`).all() as Array<{ name: string; type: string; pk: number }>
    if (columns.length !== receiptFields.length || columns.some((column, index) => column.name !== receiptFields[index]
        || column.type.toUpperCase() !== (index < 2 ? "INTEGER" : "TEXT") || Number(column.pk) !== (index === 0 ? 1 : 0))) {
        throw new Error("Unsupported clock rollback receipt schema")
    }
    if (db.prepare("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?").get(SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE)) {
        throw new Error("Clock rollback receipt triggers are forbidden")
    }
    const rows = db.prepare(`SELECT * FROM ${SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE}`).safeIntegers().all() as Row[]
    if (rows.length !== 1 || rows[0].id !== BigInt(1) || rows[0].version !== BigInt(1) || !validDigest(rows[0].plan_digest)
        || typeof rows[0].receipt_json !== "string" || !validDigest(rows[0].receipt_digest)
        || !["applied", "rolled-back"].includes(String(rows[0].status))) throw new Error("Invalid clock rollback receipt singleton/version")
    const row = rows[0]
    if (fingerprint({ version: 1, planDigest: row.plan_digest, receiptJson: row.receipt_json, status: row.status }) !== row.receipt_digest) {
        throw new Error("Corrupt clock rollback receipt integrity")
    }
    const payload = JSON.parse(String(row.receipt_json), (_key, item) => {
        if (item && typeof item === "object" && Object.keys(item).length === 1 && typeof item.clockReceiptInteger === "string") {
            if (!/^-?\d+$/.test(item.clockReceiptInteger)) throw new Error("Invalid clock rollback receipt integer")
            return BigInt(item.clockReceiptInteger)
        }
        if (item && typeof item === "object" && Object.keys(item).length === 2 && item.type === "Buffer" && Array.isArray(item.data)
            && item.data.every((value: unknown) => typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 255)) {
            return Buffer.from(item.data)
        }
        return item
    }) as ClockRollbackPayload
    if (!payload || payload.version !== 1 || !payload.plan || payload.plan.digest !== row.plan_digest
        || !validDigest(payload.beforeFingerprint) || !validDigest(payload.afterFingerprint)
        || !validDigest(payload.plan.beforeDigest) || !validDigest(payload.plan.preservedDigest)
        || typeof payload.plan.markerTableExisted !== "boolean" || !Array.isArray(payload.plan.players)
        || !Array.isArray(payload.beforeTimeFields)) throw new Error("Unsupported clock rollback receipt payload")
    // The phase3 digest uses its own canonical bigint spelling. Preserve its exact contract.
    const { digest, ...unsigned } = payload.plan
    const planHash = createHash("sha256").update(JSON.stringify(unsigned,
        (_key, item) => typeof item === "bigint" ? { bigint: item.toString() } : item)).digest("hex")
    if (planHash !== digest || payload.plan.version !== 1) throw new Error("Corrupt clock rollback plan integrity")
    validateServerClockSnapshot(payload.snapshot)
    assertLegacyCutoverCoordinate(payload.snapshot)
    if (payload.snapshot.mode !== "real" || payload.snapshot.cutoverRealMs !== payload.plan.cutoverRealMs
        || payload.snapshot.legacyBattleOffsetMs !== payload.plan.legacyOffsetMs) throw new Error("Clock rollback snapshot/plan conflict")
    const migrated = payload.plan.players.filter(player => player.createMarker)
    const sqliteValue = (value: unknown): boolean => value === null || typeof value === "string" || Buffer.isBuffer(value)
        || (typeof value === "number" && Number.isFinite(value))
        || (typeof value === "bigint" && value >= BigInt("-9223372036854775808") && value <= BigInt("9223372036854775807"))
    if (payload.beforeTimeFields.length !== migrated.length || payload.beforeTimeFields.some((row, index) => !Array.isArray(row)
        || row.length !== 3 || !Number.isSafeInteger(row[0]) || row[0] < 1 || row[0] !== migrated[index].playerId
        || !sqliteValue(row[1]) || !sqliteValue(row[2]))) throw new Error("Clock rollback before image conflict")
    return { payload, status: row.status as ClockRollbackReceipt["status"] }
}

function writeClockRollbackReceipt(db: Database, payload: ClockRollbackPayload, status: ClockRollbackReceipt["status"]): void {
    const receiptJson = serializeReceipt(payload)
    const digest = fingerprint({ version: 1, planDigest: payload.plan.digest, receiptJson, status })
    db.prepare(`INSERT INTO ${SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE} VALUES (1,1,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET plan_digest=excluded.plan_digest,receipt_json=excluded.receipt_json,
        receipt_digest=excluded.receipt_digest,status=excluded.status`).run(payload.plan.digest, receiptJson, digest, status)
}
/** Maintenance approval is issued only through the explicit backed-up transaction. */
export interface PersistedServerClockState {
    readonly snapshot: Readonly<ServerClockSnapshot>
    readonly readiness: "scenario-only" | "maintenance-approved"
    readonly planDigest: string
}
type Row = Record<string, unknown>
const fields = ["id", "version", "mode", "business_offset_ms", "legacy_battle_offset_ms", "cutover_real_ms",
    "day_anchor_ms", "week_anchor_ms", "revision", "readiness", "plan_digest"]
const defaultDegreesTriggerSql = `CREATE TRIGGER trg_players_default_degrees
    AFTER INSERT ON players
    BEGIN
        INSERT OR IGNORE INTO players_degrees (player_id, degree_id, acquired_at)
        VALUES (NEW.id, 1, 0);
        INSERT OR IGNORE INTO players_degrees (player_id, degree_id, acquired_at)
        SELECT NEW.id, NEW.degree_id, 0 WHERE NEW.degree_id > 0;
    END`
const normalizeSql = (sql: string): string => sql.trim().replace(/\s+/g, " ").toLowerCase()

function assertLazyMigrationTriggers(db: Database): void {
    const triggers = db.prepare("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name IN ('players','player_time_state')")
        .all() as Array<{ name: string; tbl_name: string; sql: string }>
    // Exact initialized SQL, including the INSERT-only event and both original
    // degree statements. A same-name trigger with any changed body is unsafe.
    if (triggers.some(trigger => trigger.name !== "trg_players_default_degrees" || trigger.tbl_name !== "players"
        || typeof trigger.sql !== "string" || normalizeSql(trigger.sql) !== normalizeSql(defaultDegreesTriggerSql))) {
        throw new Error("Player clock migration triggers are forbidden")
    }
}

function assertLegacyCutoverCoordinate(snapshot: ServerClockSnapshot): void {
    const legacyEpoch = snapshot.cutoverRealMs! + (snapshot.legacyBattleOffsetMs ?? 0)
    if (!Number.isSafeInteger(legacyEpoch) || !Number.isFinite(new Date(legacyEpoch).getTime())) {
        throw new Error("Invalid legacy battle clock cutover coordinate")
    }
}

function integer(value: unknown): number | null {
    if (value === null) return null
    if (typeof value === "bigint") {
        if (value > BigInt(Number.MAX_SAFE_INTEGER) || value < BigInt(Number.MIN_SAFE_INTEGER)) throw new Error("Unsafe persisted clock integer")
        return Number(value)
    }
    if (typeof value !== "number" || !Number.isSafeInteger(value)) throw new Error("Invalid persisted clock integer")
    return value
}

/** No schema creation, migration, writes, default connection or fallback occurs here. */
export function readServerClockStateSync(db: Database): PersistedServerClockState | null {
    if (!db.open) throw new Error("Clock restore requires an open explicit database")
    const objects = db.prepare("SELECT type FROM sqlite_master WHERE name=?").all(SERVER_CLOCK_STATE_TABLE) as Array<{ type: string }>
    if (objects.length === 0) return null
    if (objects.length !== 1 || objects[0].type !== "table") throw new Error("Invalid persisted clock table")
    const columns = db.prepare(`PRAGMA table_info(${SERVER_CLOCK_STATE_TABLE})`).all() as Array<{ name: string; type: string; pk: number }>
    if (columns.length !== fields.length || columns.some((column, index) => column.name !== fields[index]
        || column.type.toUpperCase() !== (["mode", "readiness", "plan_digest"].includes(column.name) ? "TEXT" : "INTEGER")
        || Number(column.pk) !== (index === 0 ? 1 : 0))) throw new Error("Unsupported persisted clock schema")
    if (db.prepare("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?").get(SERVER_CLOCK_STATE_TABLE)) throw new Error("Clock state triggers are forbidden")
    const rows = db.prepare(`SELECT * FROM ${SERVER_CLOCK_STATE_TABLE}`).safeIntegers().all() as Row[]
    if (rows.length !== 1 || integer(rows[0].id) !== 1) throw new Error("Invalid persisted clock singleton")
    const row = rows[0]
    const snapshot = {
        version: integer(row.version), mode: row.mode, businessOffsetMs: integer(row.business_offset_ms),
        legacyBattleOffsetMs: integer(row.legacy_battle_offset_ms), cutoverRealMs: integer(row.cutover_real_ms),
        dayAnchorMs: integer(row.day_anchor_ms), weekAnchorMs: integer(row.week_anchor_ms), revision: integer(row.revision),
    }
    validateServerClockSnapshot(snapshot)
    assertLegacyCutoverCoordinate(snapshot)
    if (snapshot.mode !== "real" || !["scenario-only", "maintenance-approved"].includes(String(row.readiness)) || typeof row.plan_digest !== "string"
        || !/^[a-f0-9]{64}$/.test(row.plan_digest)) throw new Error("Unsupported persisted clock state")
    return Object.freeze({ snapshot: Object.freeze(snapshot), readiness: row.readiness as PersistedServerClockState["readiness"], planDigest: row.plan_digest })
}

/** Restore only an already committed state; absence leaves the legacy caller in control. */
export function restoreServerClockStateSync(db: Database): PersistedServerClockState | null {
    const state = readServerClockStateSync(db)
    if (state) installServerClockSnapshot(state.snapshot)
    return state
}

export interface ActivateRealServerClockOptions {
    cutoverRealMs: number
    legacyOffsetMs: number | null
    expectedPlanDigest: string
    offlineGuard?: OfflineDatabaseGuard
    readiness: "scenario-only"
    faultAt?: "after-player-migration" | "after-clock-state" | "after-activation-receipt"
}

/** Offline only. Commit every player migration and the global coordinate in one transaction; never install the process clock. */
export function activateRealServerClockOfflineSync(db: Database, options: ActivateRealServerClockOptions): PersistedServerClockState {
    assertTimeCutoverOfflineDatabaseSync(db, options.offlineGuard)
    if (options.readiness !== "scenario-only") throw new Error("Production real-time cutover is no_go")
    return db.transaction(() => activateRealServerClockInTransactionSync(db, options, "scenario-only")).immediate()
}

export type MaintenanceRealServerClockOptions = Omit<ActivateRealServerClockOptions, "readiness" | "offlineGuard">
/** Call after content initialization in the same outer maintenance transaction. */
export function planRealServerClockMaintenanceSync(db: Database, options: Omit<TimeCutoverRehearsalOptions, "offlineGuard">,
    context: DeploymentMaintenanceContext): TimeCutoverRehearsalPlan {
    assertDeploymentMaintenanceContextSync(db, context)
    return buildTimeCutoverPlanInTransactionSync(db, options)
}
export function activateRealServerClockMaintenanceSync(db: Database, options: MaintenanceRealServerClockOptions,
    context: DeploymentMaintenanceContext): PersistedServerClockState {
    assertDeploymentMaintenanceContextSync(db, context)
    return activateRealServerClockInTransactionSync(db, options, "maintenance-approved")
}
function activateRealServerClockInTransactionSync(db: Database, options: MaintenanceRealServerClockOptions,
    readiness: PersistedServerClockState["readiness"]): PersistedServerClockState {
    assertNoTemporaryStateShadow(db)
    if (!/^[a-f0-9]{64}$/.test(options.expectedPlanDigest)) throw new Error("Invalid clock migration plan digest")
    const revision = getServerClockSnapshot().revision + 1
    const snapshot: ServerClockSnapshot = { version: 1, mode: "real", businessOffsetMs: 0,
        legacyBattleOffsetMs: options.legacyOffsetMs, cutoverRealMs: options.cutoverRealMs,
        dayAnchorMs: options.cutoverRealMs, weekAnchorMs: options.cutoverRealMs, revision }
    validateServerClockSnapshot(snapshot)
    assertLegacyCutoverCoordinate(snapshot)
    const existing = readServerClockStateSync(db)
    const oldReceipt = readClockRollbackReceipt(db)
    if (existing) {
        if (!oldReceipt || oldReceipt.status !== "applied") throw new Error("Committed clock has no valid rollback receipt; activation refused")
        if (existing.readiness !== readiness || existing.planDigest !== options.expectedPlanDigest || existing.snapshot.cutoverRealMs !== options.cutoverRealMs
            || existing.snapshot.legacyBattleOffsetMs !== options.legacyOffsetMs
            || oldReceipt.payload.plan.digest !== existing.planDigest
            || JSON.stringify(oldReceipt.payload.snapshot) !== JSON.stringify(existing.snapshot)) throw new Error("Persisted clock activation conflict")
        return existing
    }
    if (oldReceipt?.status === "applied") throw new Error("Applied clock rollback receipt has no committed global state")
    const plan = buildTimeCutoverPlanInTransactionSync(db, options)
    if (plan.digest !== options.expectedPlanDigest) throw new Error("Clock plan digest mismatch")
    return db.transaction(() => {
        if (getTimeCutoverDatabaseDigestSync(db) !== plan.beforeDigest) throw new Error("Clock plan changed before activation")
        const beforeFingerprint = getServerClockPersistentFingerprintSync(db)
        const preservedFingerprint = clockPersistentFingerprint(db, plan)
        const beforeTimeFields: ClockRollbackPayload["beforeTimeFields"] = plan.players.filter(player => player.createMarker).map(player => {
            const row = db.prepare("SELECT exp_pooled_time,time_offset FROM players WHERE id=?").safeIntegers().get(player.playerId) as Row
            return [player.playerId, row.exp_pooled_time, row.time_offset]
        })
        db.exec(`CREATE TABLE IF NOT EXISTS player_time_state (
            player_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE, version INTEGER NOT NULL,
            cutover_real_ms INTEGER NOT NULL, day_anchor_ms INTEGER NOT NULL, week_anchor_ms INTEGER NOT NULL)`)
        const update = db.prepare("UPDATE players SET exp_pooled_time=?,time_offset=? WHERE id=?")
        const marker = db.prepare("INSERT INTO player_time_state(player_id,version,cutover_real_ms,day_anchor_ms,week_anchor_ms) VALUES (?,1,?,?,?)")
        for (const player of plan.players) if (player.createMarker) {
            update.run(player.after.exp_pooled_time, player.after.time_offset, player.playerId)
            marker.run(player.playerId, options.cutoverRealMs, options.cutoverRealMs, options.cutoverRealMs)
        }
        // Verify after every write: a later player's trigger must not alter an
        // earlier target field which the unrelated-state digest omits.
        for (const player of plan.players) if (player.createMarker) {
            const actual = db.prepare("SELECT exp_pooled_time,time_offset FROM players WHERE id=?").get(player.playerId)
            const state = getExistingPlayerTimeStateSync(player.playerId, db)
            if (JSON.stringify(actual) !== JSON.stringify(player.after) || !state || state.cutoverRealMs !== options.cutoverRealMs
                || state.dayAnchorMs !== options.cutoverRealMs || state.weekAnchorMs !== options.cutoverRealMs) throw new Error("Clock migration fields did not match plan")
        }
        if (options.faultAt === "after-player-migration") throw new Error("Injected clock activation failure after-player-migration")
        db.exec(`CREATE TABLE ${SERVER_CLOCK_STATE_TABLE} (
            id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL CHECK(version=1), mode TEXT NOT NULL CHECK(mode='real'),
            business_offset_ms INTEGER NOT NULL CHECK(business_offset_ms=0), legacy_battle_offset_ms INTEGER,
            cutover_real_ms INTEGER NOT NULL, day_anchor_ms INTEGER NOT NULL, week_anchor_ms INTEGER NOT NULL,
            revision INTEGER NOT NULL, readiness TEXT NOT NULL CHECK(readiness IN ('scenario-only','maintenance-approved')), plan_digest TEXT NOT NULL)`)
        db.prepare(`INSERT INTO ${SERVER_CLOCK_STATE_TABLE} VALUES (1,1,'real',0,?,?,?,?,?,?,?)`)
            .run(snapshot.legacyBattleOffsetMs, snapshot.cutoverRealMs, snapshot.dayAnchorMs, snapshot.weekAnchorMs, snapshot.revision, readiness, plan.digest)
        const committed = readServerClockStateSync(db)
        if (!committed || JSON.stringify(committed.snapshot) !== JSON.stringify(snapshot)) throw new Error("Clock singleton did not match planned snapshot")
        if (getTimeCutoverProtectedDatabaseDigestSync(db, plan, true) !== plan.preservedDigest) throw new Error("Clock activation changed unrelated persistent state")
        if (clockPersistentFingerprint(db, plan) !== preservedFingerprint) throw new Error("Clock activation changed unrelated full persistent state")
        if (options.faultAt === "after-clock-state") throw new Error("Injected clock activation failure after-clock-state")
        const afterFingerprint = getServerClockPersistentFingerprintSync(db)
        db.exec(`CREATE TABLE IF NOT EXISTS ${SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE} (
            id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL CHECK(version=1), plan_digest TEXT NOT NULL,
            receipt_json TEXT NOT NULL, receipt_digest TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('applied','rolled-back')))`)
        writeClockRollbackReceipt(db, { version: 1, plan, snapshot, beforeFingerprint, afterFingerprint, beforeTimeFields }, "applied")
        const receipt = readClockRollbackReceipt(db)
        if (!receipt || receipt.payload.afterFingerprint !== getServerClockPersistentFingerprintSync(db)) throw new Error("Clock activation receipt mismatch")
        if (options.faultAt === "after-activation-receipt") throw new Error("Injected clock activation failure after-activation-receipt")
        return committed
    }).immediate()
}

export interface RollbackRealServerClockOptions {
    expectedPlanDigest: string
    offlineGuard?: OfflineDatabaseGuard
    faultAt?: "after-player-restore" | "after-clock-restore" | "after-rollback-receipt"
}
export interface RollbackRealServerClockResult {
    status: "rolled-back" | "already-rolled-back"
    planDigest: string
    beforeFingerprint: string
    afterFingerprint: string
}
/** Explicit offline reversal only. Never force-reset a real process clock, erase new facts or run at startup/import.
 * Stop/drain every writer before opening this path; a process with the old real snapshot must not resume business.
 */
export function rollbackRealServerClockOfflineSync(db: Database, options: RollbackRealServerClockOptions): RollbackRealServerClockResult {
    assertTimeCutoverOfflineDatabaseSync(db, options.offlineGuard)
    return rollbackRealServerClockInTransactionSync(db, options)
}
export function rollbackRealServerClockMaintenanceSync(db: Database, options: Omit<RollbackRealServerClockOptions, "offlineGuard">,
    context: DeploymentMaintenanceContext): RollbackRealServerClockResult {
    assertDeploymentMaintenanceContextSync(db, context)
    return rollbackRealServerClockInTransactionSync(db, options)
}
function rollbackRealServerClockInTransactionSync(db: Database, options: Omit<RollbackRealServerClockOptions, "offlineGuard">): RollbackRealServerClockResult {
    assertNoTemporaryStateShadow(db)
    if (!validDigest(options.expectedPlanDigest)) throw new Error("Invalid clock rollback plan digest")
    return db.transaction(() => {
        const receipt = readClockRollbackReceipt(db)
        if (!receipt) throw new Error("No clock rollback receipt; cannot infer the legacy before image")
        const { payload } = receipt
        if (payload.plan.digest !== options.expectedPlanDigest) throw new Error("Clock rollback plan digest mismatch")
        const result = { planDigest: payload.plan.digest, beforeFingerprint: payload.beforeFingerprint, afterFingerprint: payload.afterFingerprint }
        const current = readServerClockStateSync(db)
        if (receipt.status === "rolled-back") {
            if (current || getServerClockPersistentFingerprintSync(db) !== payload.beforeFingerprint) {
                throw new Error("Rollback refused: persistent state changed after rollback")
            }
            return { status: "already-rolled-back" as const, ...result }
        }
        if (!current || current.planDigest !== payload.plan.digest || JSON.stringify(current.snapshot) !== JSON.stringify(payload.snapshot)) {
            throw new Error("Clock rollback committed snapshot conflict")
        }
        if (getServerClockPersistentFingerprintSync(db) !== payload.afterFingerprint) {
            throw new Error("Rollback refused: progress or persistent state changed after activation")
        }
        const update = db.prepare("UPDATE players SET exp_pooled_time=?,time_offset=? WHERE id=?")
        const removeMarker = db.prepare("DELETE FROM player_time_state WHERE player_id=?")
        for (const [playerId, checkpoint, offset] of payload.beforeTimeFields) {
            if (update.run(checkpoint, offset, playerId).changes !== 1 || removeMarker.run(playerId).changes !== 1) {
                throw new Error("Clock rollback player/marker before image mismatch")
            }
        }
        if (options.faultAt === "after-player-restore") throw new Error("Injected clock rollback failure after-player-restore")
        if (!payload.plan.markerTableExisted) db.exec("DROP TABLE player_time_state")
        db.exec(`DROP TABLE ${SERVER_CLOCK_STATE_TABLE}`)
        if (options.faultAt === "after-clock-restore") throw new Error("Injected clock rollback failure after-clock-restore")
        if (getServerClockPersistentFingerprintSync(db) !== payload.beforeFingerprint) {
            throw new Error("Clock rollback did not restore exact full persistent before image")
        }
        writeClockRollbackReceipt(db, payload, "rolled-back")
        if (options.faultAt === "after-rollback-receipt") throw new Error("Injected clock rollback failure after-rollback-receipt")
        return { status: "rolled-back" as const, ...result }
    }).immediate()
}

function epoch(value: unknown): number | null {
    if (typeof value === "string") {
        if (!/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value)) return null
        value = new Date(value).getTime()
    }
    return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && Number.isFinite(new Date(value).getTime()) ? value : null
}

/** Read-only consistency gate for every business transaction, including operations without a player id. */
export function assertServerClockMatchesDatabaseSync(db: Database): PersistedServerClockState | null {
    const global = readServerClockStateSync(db)
    const configured = getServerClockSnapshot()
    if (!global) {
        if (configured.mode === "real") throw new Error("Configured real clock has no committed global state")
        return null
    }
    if ((Object.keys(global.snapshot) as Array<keyof ServerClockSnapshot>).some(key => global.snapshot[key] !== configured[key])) {
        throw new Error("Configured server clock differs from committed global state")
    }
    return global
}

/** Must run in the same load transaction before mail/day/week/EXP maintenance. */
export function ensurePlayerClockStateForLoadSync(playerId: number, db: Database): PlayerTimeState | null {
    if (!Number.isSafeInteger(playerId) || playerId < 1) throw new Error("Invalid clock migration player id")
    const global = assertServerClockMatchesDatabaseSync(db)
    if (!global) return getExistingPlayerTimeStateSync(playerId, db)
    if (!db.inTransaction) throw new Error("Player clock migration requires the existing load transaction")
    const existing = getExistingPlayerTimeStateSync(playerId, db)
    if (existing) return existing
    // Unsupported triggers can mutate balances/progress behind these two writes.
    assertLazyMigrationTriggers(db)
    const row = db.prepare("SELECT exp_pooled_time,time_offset FROM players WHERE id=?").get(playerId) as Row | undefined
    if (!row) throw new Error("Clock migration player is missing")
    const saved = epoch(row.exp_pooled_time)
    const offset = row.time_offset
    const reliable = saved !== null && typeof offset === "number" && Number.isSafeInteger(offset) && epoch(saved - offset) !== null
    const real = reliable ? saved! - Number(offset) : global.snapshot.cutoverRealMs!
    const checkpoint = typeof row.exp_pooled_time === "number" ? real : new Date(real).toISOString()
    db.prepare("UPDATE players SET exp_pooled_time=?,time_offset=0 WHERE id=?").run(checkpoint, playerId)
    db.prepare("INSERT INTO player_time_state(player_id,version,cutover_real_ms,day_anchor_ms,week_anchor_ms) VALUES (?,1,?,?,?)")
        .run(playerId, global.snapshot.cutoverRealMs, global.snapshot.dayAnchorMs, global.snapshot.weekAnchorMs)
    const migrated = getExistingPlayerTimeStateSync(playerId, db)
    const actual = db.prepare("SELECT exp_pooled_time,time_offset FROM players WHERE id=?").get(playerId) as Row
    if (!migrated || actual.exp_pooled_time !== checkpoint || actual.time_offset !== 0) throw new Error("Player clock migration fields mismatch")
    return migrated
}
