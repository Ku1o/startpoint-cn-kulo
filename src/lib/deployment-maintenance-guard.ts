import DatabaseConstructor, { Database } from "better-sqlite3"
import { createHash } from "node:crypto"
import { closeSync, existsSync, openSync, readSync, realpathSync, statSync } from "node:fs"
import { isAbsolute, resolve } from "node:path"

/** The CLI must stop and drain all service processes before opening the target.
 * A SQLite write lock excludes concurrent writers during this transaction; it
 * cannot prove that a waiting service will not resume after the commit.
 */
export interface DeploymentMaintenanceGuard {
    kind: "approved-stopped-database"
    databasePath: string
    backupPath: string
    expectedDatabaseFingerprint: string
    expectedBackupSha256: string
}
export interface DeploymentMaintenanceContext { readonly kind: "deployment-maintenance-transaction" }
const active = new WeakMap<object, Database>()
const canonical = (value: unknown): string => JSON.stringify(value,
    (_key, item) => typeof item === "bigint" ? { maintenanceInteger: item.toString() }
        : typeof item === "number" && !Number.isFinite(item) ? { maintenanceReal: String(item) } : item)
const quote = (value: string): string => `"${value.replace(/"/g, '""')}"`
const samePath = (left: string, right: string): boolean => process.platform === "win32"
    ? left.toLowerCase() === right.toLowerCase() : left === right
const digest = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value)

/** Includes every table/receipt and persistent schema. No default DB or initializer. */
export function getDeploymentDatabaseFingerprintSync(db: Database): string {
    if (!db.open) throw new Error("Maintenance fingerprint requires an open explicit database")
    const schema = db.prepare("SELECT type,name,tbl_name,sql FROM main.sqlite_master ORDER BY type,name").all() as Array<{ type: string; name: string }>
    const hash = createHash("sha256").update(canonical(schema)).update("\n")
    for (const pragma of ["user_version", "application_id", "encoding"]) hash.update(canonical(db.pragma(pragma))).update("\n")
    for (const row of schema) if (row.type === "table") {
        hash.update(canonical(row.name)).update("\n")
        const statement = db.prepare(`SELECT * FROM main.${quote(row.name)}`).raw().safeIntegers()
        for (const values of statement.iterate()) hash.update(canonical(values)).update("\n")
    }
    return hash.digest("hex")
}

function fileIdentity(filename: string): string {
    if (typeof filename !== "string" || !isAbsolute(filename)) throw new Error("Maintenance requires absolute physical file paths")
    const physical = realpathSync(filename), stat = statSync(physical)
    if (!stat.isFile() || stat.nlink !== 1 || !samePath(resolve(filename), physical)) {
        throw new Error("Maintenance rejects aliased, hard-linked or non-file database paths")
    }
    if (/(^|[\\/])(\.cdn|config)([\\/]|$)/i.test(physical)) throw new Error("Maintenance database cannot be CDN/config state")
    return physical
}
function hashFile(filename: string): string {
    const hash = createHash("sha256"), buffer = Buffer.allocUnsafe(1024 * 1024), fd = openSync(filename, "r")
    try {
        let bytes: number
        while ((bytes = readSync(fd, buffer, 0, buffer.length, null)) > 0) hash.update(buffer.subarray(0, bytes))
    } finally { closeSync(fd) }
    return hash.digest("hex")
}
function assertExplicitConnection(db: Database): string {
    if (!db.open || db.readonly || !isAbsolute(db.name)) throw new Error("Maintenance requires an open writable explicit file database")
    const databases = db.prepare("PRAGMA database_list").all() as Array<{ name: string; file: string }>
    if (databases.some(row => !["main", "temp"].includes(row.name))) throw new Error("Maintenance rejects attached databases")
    if (db.prepare("SELECT 1 FROM sqlite_temp_master WHERE type IN ('table','view') AND name IN (SELECT name FROM main.sqlite_master)").get()) {
        throw new Error("Maintenance rejects temporary state shadows")
    }
    const physical = fileIdentity(db.name), main = databases.find(row => row.name === "main")?.file
    if (!main || !samePath(fileIdentity(main), physical)) throw new Error("Maintenance connection identity mismatch")
    return physical
}
function assertIntegrity(db: Database): void {
    const result = db.pragma("quick_check") as Array<{ quick_check: string }>
    if (result.length !== 1 || result[0].quick_check !== "ok") throw new Error("Maintenance database integrity check failed")
}
/** The opaque context expires at callback return. Passing a lookalike, another
 * connection, or reusing it later cannot bypass the old rehearsal path guard.
 */
export function assertDeploymentMaintenanceContextSync(db: Database, context: DeploymentMaintenanceContext): void {
    if (!context || active.get(context) !== db || !db.inTransaction) throw new Error("Active maintenance transaction context required")
    assertExplicitConnection(db)
}

/** One exclusive transaction for content and clock. Backup must be a standalone
 * SQLite backup of this exact pre-maintenance state, never a live raw file copy.
 * Failure rolls back all stages; never installs a process clock or opens a service.
 */
export function withDeploymentMaintenanceTransactionSync<T>(db: Database, guard: DeploymentMaintenanceGuard,
    execute: (context: DeploymentMaintenanceContext) => T): T {
    if (db.inTransaction) throw new Error("Maintenance must own the outer transaction")
    if (!guard || guard.kind !== "approved-stopped-database" || !digest(guard.expectedDatabaseFingerprint)
        || !digest(guard.expectedBackupSha256)) throw new Error("Invalid explicit maintenance guard")
    const target = assertExplicitConnection(db), approved = fileIdentity(guard.databasePath), backup = fileIdentity(guard.backupPath)
    if (!samePath(target, approved) || samePath(target, backup)) throw new Error("Maintenance target/backup path mismatch")
    // SQLite may create empty WAL/SHM lock sidecars even for a readonly open of
    // a backup whose header retains WAL mode. Only nonempty journals contain
    // state not covered by the standalone file SHA and must be refused.
    if (["-wal", "-journal"].some(suffix => existsSync(backup + suffix) && statSync(backup + suffix).size > 0)) {
        throw new Error("Maintenance backup must be standalone without a nonempty journal/WAL")
    }
    if (hashFile(backup) !== guard.expectedBackupSha256) throw new Error("Maintenance backup SHA256 mismatch")
    const copy = new DatabaseConstructor(backup, { readonly: true, fileMustExist: true })
    try {
        assertIntegrity(copy)
        if (getDeploymentDatabaseFingerprintSync(copy) !== guard.expectedDatabaseFingerprint) throw new Error("Maintenance backup state mismatch")
    } finally { copy.close() }
    if (hashFile(backup) !== guard.expectedBackupSha256) throw new Error("Maintenance backup changed during validation")
    assertIntegrity(db)
    return db.transaction(() => {
        if (!samePath(assertExplicitConnection(db), target)
            || getDeploymentDatabaseFingerprintSync(db) !== guard.expectedDatabaseFingerprint) throw new Error("Maintenance target changed before exclusive lock")
        const context = Object.freeze({ kind: "deployment-maintenance-transaction" as const })
        active.set(context, db)
        try {
            const result = execute(context)
            if (result && typeof (result as { then?: unknown }).then === "function") throw new Error("Maintenance callback must be synchronous")
            assertDeploymentMaintenanceContextSync(db, context)
            assertIntegrity(db)
            return result
        } finally { active.delete(context) }
    }).exclusive()
}
