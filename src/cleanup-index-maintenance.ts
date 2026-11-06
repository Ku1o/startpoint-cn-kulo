/** Narrow offline CLI: never opens the business database through data/db. */
import Database from "better-sqlite3"
import { randomUUID } from "crypto"
import { closeSync, existsSync, fsyncSync, openSync, readFileSync, realpathSync, statSync, unlinkSync, writeFileSync } from "fs"
import path from "path"
import { findMissingCascadeDeleteIndexes, ensureCascadeDeleteIndexes, MissingCascadeDeleteIndex } from "./lib/admin-account-cleanup"
import { writeJsonAtomicSync } from "./lib/atomic-json-file"
import { WDFP_DATA_VERSION } from "./lib/storage-layout"
import { maintenancePaths, MaintenancePaths } from "./storage-maintenance"

export const CLEANUP_INDEX_CONFIRMATION = "CREATE_CASCADE_DELETE_INDEXES"

interface IndexMaintenanceState {
    format: 1
    kind: "cleanup-indexes"
    id: string
    database: string
    phase: "preparing" | "indexing" | "completed" | "failed"
    startedAt: string
    finishedAt?: string
    missing: MissingCascadeDeleteIndex[]
    createdIndexes: number
    ddlCommitted: boolean
    error?: string
}

export interface CleanupIndexApplyOptions {
    offline: boolean
    confirm: string
    confirmDatabase: string
}

function samePath(left: string, right: string): boolean {
    const normalize = (value: string) => process.platform === "win32"
        ? path.resolve(value).toLowerCase() : path.resolve(value)
    return normalize(left) === normalize(right)
}

function statePath(paths: MaintenancePaths): string {
    return path.join(path.dirname(paths.database), "cleanup-index-maintenance-state.json")
}

function validateTarget(paths: MaintenancePaths): void {
    if (!path.isAbsolute(paths.database) || !samePath(realpathSync(paths.project), paths.project)
        || !samePath(realpathSync(paths.database), paths.database) || !statSync(paths.database).isFile()) {
        throw new Error("数据库目标必须是明确的实际绝对路径，不能使用数据库文件链接")
    }
    const directory = path.dirname(paths.database)
    if (path.basename(paths.database) !== "wdfp_data.db"
        || !samePath(paths.lock, path.join(directory, "storage-maintenance.lock"))
        || !samePath(paths.state, path.join(directory, "storage-maintenance-state.json"))) {
        throw new Error("维护路径与数据库目标不匹配")
    }
    const version = readFileSync(paths.database + ".version", "utf8").trim()
    if (version !== String(WDFP_DATA_VERSION)) {
        throw new Error(`基础数据库版本 ${version} 与维护工具要求 ${WDFP_DATA_VERSION} 不一致`)
    }
}

function assertPreviousMaintenanceFinished(paths: MaintenancePaths): void {
    const controllerDirectory = path.join(paths.project, ".storage-maintenance")
    if (existsSync(path.join(controllerDirectory, "active.lock"))) {
        throw new Error("已有未结束的 Windows 存储维护控制器，请先审核原维护")
    }
    const controllerPath = path.join(controllerDirectory, "controller.json")
    if (existsSync(controllerPath)) {
        const controller = JSON.parse(readFileSync(controllerPath, "utf8")) as { project?: string; database?: string; phase?: string }
        if (!controller.project || !samePath(controller.project, paths.project) || !controller.database
            || !samePath(controller.database, paths.database) || !["completed", "recovered"].includes(controller.phase ?? "")) {
            throw new Error("已有未完成或不匹配的 Windows 存储维护控制器记录，请先审核原维护")
        }
    }
    if (existsSync(paths.state)) {
        const previous = JSON.parse(readFileSync(paths.state, "utf8")) as { format?: number; database?: string; phase?: string }
        if (previous.format !== 1 || !previous.database || !samePath(previous.database, paths.database)
            || !["completed", "rolled-back"].includes(previous.phase ?? "")) {
            throw new Error("已有未完成或不匹配的存储维护记录，请先审核原维护；不会覆盖或自动恢复数据库")
        }
    }
    if (existsSync(statePath(paths))) {
        const previous = JSON.parse(readFileSync(statePath(paths), "utf8")) as IndexMaintenanceState
        if (previous.format !== 1 || previous.kind !== "cleanup-indexes" || !previous.database
            || !samePath(previous.database, paths.database)
            || !(previous.phase === "completed" || (previous.phase === "failed" && previous.ddlCommitted === false))) {
            throw new Error("上次索引维护未明确结束，请审核状态和保留的维护锁；禁止直接重试或覆盖真实库")
        }
    }
}

function missingIndexes(db: Database.Database): MissingCascadeDeleteIndex[] {
    for (const table of ["accounts", "players"]) {
        if (!db.prepare("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?").get(table)) {
            throw new Error(`目标数据库缺少必要表 ${table}`)
        }
    }
    return findMissingCascadeDeleteIndexes(db)
}

export function previewCleanupIndexes(paths: MaintenancePaths): {
    database: string; databaseVersion: number; missing: MissingCascadeDeleteIndex[]; locked: boolean; state: string
} {
    validateTarget(paths)
    const db = new Database(paths.database, { readonly: true, fileMustExist: true, timeout: 1000 })
    try {
        db.pragma("query_only=ON")
        return { database: paths.database, databaseVersion: WDFP_DATA_VERSION, missing: missingIndexes(db),
            locked: existsSync(paths.lock), state: statePath(paths) }
    } finally { db.close() }
}

function saveState(paths: MaintenancePaths, state: IndexMaintenanceState): void {
    writeJsonAtomicSync(statePath(paths), state, { backup: false })
}

function releaseOwnedLock(paths: MaintenancePaths, id: string): void {
    const lock = JSON.parse(readFileSync(paths.lock, "utf8")) as { id?: string; pid?: number; database?: string; kind?: string }
    if (lock.id !== id || lock.pid !== process.pid || lock.kind !== "cleanup-indexes"
        || !lock.database || !samePath(lock.database, paths.database)) {
        throw new Error("维护锁身份已变化，未删除该锁；请人工审核")
    }
    unlinkSync(paths.lock)
}

export async function applyCleanupIndexes(
    paths: MaintenancePaths,
    options: CleanupIndexApplyOptions,
    checkpoint: (stage: string) => void = () => {},
): Promise<IndexMaintenanceState> {
    if (!options.offline || options.confirm !== CLEANUP_INDEX_CONFIRMATION) {
        throw new Error("仅允许明确停服维护：需要 --offline 和正确的 --confirm")
    }
    validateTarget(paths)
    if (!path.isAbsolute(options.confirmDatabase) || !samePath(realpathSync(options.confirmDatabase), paths.database)) {
        throw new Error("--confirm-database 必须与预览确认的实际数据库绝对路径一致")
    }
    assertPreviousMaintenanceFinished(paths)
    const id = `cleanup-indexes-${new Date().toISOString().replace(/[-:.]/g, "")}-${randomUUID()}`
    const descriptor = openSync(paths.lock, "wx")
    try {
        writeFileSync(descriptor, JSON.stringify({ kind: "cleanup-indexes", id, pid: process.pid,
            database: paths.database, createdAt: new Date().toISOString() }))
        fsyncSync(descriptor)
    } finally { closeSync(descriptor) }

    let db: Database.Database | undefined
    let mayReleaseLock = false
    let stateStarted = false
    const state: IndexMaintenanceState = {
        format: 1, kind: "cleanup-indexes", id, database: paths.database, phase: "preparing",
        startedAt: new Date().toISOString(), missing: [], createdIndexes: 0, ddlCommitted: false,
    }
    try {
        // Recheck after acquiring the shared startup-blocking lock to close the
        // gap between preflight and a different maintenance controller.
        assertPreviousMaintenanceFinished(paths)
        stateStarted = true
        saveState(paths, state)
        db = new Database(paths.database, { fileMustExist: true, timeout: 1000 })
        db.pragma("temp_store=FILE")
        db.pragma("foreign_keys=ON")
        db.pragma("locking_mode=EXCLUSIVE")
        db.exec("BEGIN EXCLUSIVE; COMMIT")
        state.missing = missingIndexes(db)
        if (state.missing.length === 0) {
            state.phase = "completed"
            state.finishedAt = new Date().toISOString()
            saveState(paths, state)
            mayReleaseLock = true
            return state
        }

        state.phase = "indexing"
        saveState(paths, state)

        // All DDL, including the final preflight, belongs to one transaction.
        // A name collision or partial failure must not leave the first index.
        db.exec("BEGIN EXCLUSIVE")
        try {
            const created = ensureCascadeDeleteIndexes(db)
            checkpoint("indexes-created")
            const remaining = findMissingCascadeDeleteIndexes(db)
            if (remaining.length > 0) throw new Error(`补建后仍缺少 ${remaining.length} 个删除索引，事务已拒绝提交`)
            db.exec("COMMIT")
            state.ddlCommitted = true
            state.createdIndexes = created
        } catch (error) {
            if (db.inTransaction) db.exec("ROLLBACK")
            throw error
        }
        checkpoint("indexes-committed")
        state.phase = "completed"
        state.finishedAt = new Date().toISOString()
        saveState(paths, state)
        mayReleaseLock = true
        return state
    } catch (error) {
        if (!stateStarted) {
            mayReleaseLock = true
            throw error
        }
        state.phase = "failed"
        state.finishedAt = new Date().toISOString()
        state.error = error instanceof Error ? error.message : String(error)
        // A commit followed by a reporting failure is deliberately blocked for
        // review; the tool never replaces the database.
        try {
            saveState(paths, state)
            mayReleaseLock = !state.ddlCommitted && !db?.inTransaction
        } catch (stateError) {
            throw new Error(`${state.error}；维护记录保存失败，保留维护锁：${String(stateError)}`)
        }
        throw error
    } finally {
        // A failed close must also retain the startup-blocking lock.
        if (db?.open) db.close()
        if (mayReleaseLock) releaseOwnedLock(paths, id)
    }
}

async function main(): Promise<void> {
    const args = process.argv.slice(2)
    const command = args[0] && !args[0].startsWith("--") ? args.shift() : "preview"
    if (command !== "preview" && command !== "apply") throw new Error("支持命令：preview / apply")
    const values = new Map<string, string>()
    let offline = false
    while (args.length) {
        const argument = args.shift()!
        if (argument === "--offline" && !offline) { offline = true; continue }
        if (!["--project", "--confirm", "--confirm-database"].includes(argument)
            || values.has(argument) || !args[0] || args[0].startsWith("--")) throw new Error(`无效或重复参数：${argument}`)
        values.set(argument, args.shift()!)
    }
    const paths = maintenancePaths(values.get("--project"))
    const result = command === "preview" ? previewCleanupIndexes(paths) : await applyCleanupIndexes(paths, {
        offline, confirm: values.get("--confirm") ?? "", confirmDatabase: values.get("--confirm-database") ?? "",
    }, stage => console.error(`[CLEANUP-INDEXES] ${stage}`))
    console.log(JSON.stringify(result, null, 2))
}

if (require.main === module) void main().catch(error => {
    console.error(error instanceof Error ? error.message : String(error))
    process.exitCode = 1
})
