import { existsSync } from "./file-exists";
import { lstatSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "fs"
import { createHash } from "crypto"
import path from "path"
import {
    AdminDatabaseBackupError, backupDatabaseInWorker,
    type AdminDatabaseBackupOptions, type AdminDatabaseBackupProgress,
} from "./admin-database-backup-worker"
export type { AdminDatabaseBackupOptions, AdminDatabaseBackupProgress } from "./admin-database-backup-worker"

export interface AdminDatabaseBackupResult {
    directory: string
    name: string
}

export interface PlayerImportBackupCleanupResult {
    retainedBackups: number
    removedBackups: number
    backupCleanupError: string | null
}

const PLAYER_IMPORT_BACKUP_NAME = /^player-import-[1-9]\d*-\d{8}-\d{6}-\d{3}$/

export function getDatabaseDirectory(): string {
    return process.env.DATA_DIR
        ? path.resolve(process.env.DATA_DIR)
        : path.resolve(__dirname, "../../.database")
}

function createBackupStamp(): string {
    const now = new Date()
    const pad = (value: number, width = 2) => String(value).padStart(width, "0")
    return [
        `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`,
        `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`,
        pad(now.getMilliseconds(), 3),
    ].join("-")
}

export async function createFullDatabaseBackup(
    prefix: string,
    metadata: Record<string, unknown> = {},
    options: AdminDatabaseBackupOptions = {},
): Promise<AdminDatabaseBackupResult> {
    if (!/^[a-z0-9-]+$/.test(prefix)) throw new Error("Database backup prefix is invalid")
    const databaseDir = getDatabaseDirectory()
    const name = `${prefix}-${createBackupStamp()}`
    const directory = path.join(databaseDir, "admin-backups", name)
    mkdirSync(path.dirname(directory), { recursive: true })
    mkdirSync(directory)
    const statePath = path.join(databaseDir, "active_account.json")
    const createdAt = new Date().toISOString()
    let lastProgress: AdminDatabaseBackupProgress | undefined
    let sidecars: { capturedAt: string; versionSha256: string; activeAccountSha256: string | null } | undefined
    const writeInfo = (status: "running" | "completed" | "failed", extra: Record<string, unknown> = {}): void => {
        writeFileSync(path.join(directory, "backup-info.json"), JSON.stringify({
            ...metadata,
            createdAt,
            type: prefix,
            status,
            database: "wdfp_data.db",
            databaseVersion: "wdfp_data.db.version",
            includesActiveAccountState: sidecars?.activeAccountSha256 !== null && sidecars !== undefined,
            sidecars,
            progress: lastProgress,
            ...extra,
        }, null, 2), "utf8")
    }
    try {
        writeInfo("running")
        const versionPath = path.join(databaseDir, "wdfp_data.db.version")
        if (!existsSync(versionPath)) throw new Error("Database version file is missing: wdfp_data.db.version")
        const versionBytes = readFileSync(versionPath)
        const stateBytes = existsSync(statePath) ? readFileSync(statePath) : null
        sidecars = {
            capturedAt: new Date().toISOString(),
            versionSha256: createHash("sha256").update(versionBytes).digest("hex"),
            activeAccountSha256: stateBytes ? createHash("sha256").update(stateBytes).digest("hex") : null,
        }
        writeInfo("running")
        const result = await backupDatabaseInWorker(path.join(databaseDir, "wdfp_data.db"), path.join(directory, "wdfp_data.db"), {
            ...options,
            activeAccountState: stateBytes?.toString("utf8"),
            versionSidecar: { filename: versionPath, contents: versionBytes.toString("base64") },
            onProgress: progress => { lastProgress = progress; options.onProgress?.(progress) },
        })
        writeFileSync(path.join(directory, "wdfp_data.db.version"), versionBytes)
        if (stateBytes) writeFileSync(path.join(directory, "active_account.json"), stateBytes)
        writeInfo("completed", { finishedAt: new Date().toISOString(), verification: result })
        return { directory, name }
    } catch (error) {
        const failure = error instanceof AdminDatabaseBackupError ? error
            : new AdminDatabaseBackupError("failed", error instanceof Error ? error.message : String(error))
        failure.backupDirectory = directory
        failure.backupName = name
        try { writeInfo("failed", { finishedAt: new Date().toISOString(), errorCode: failure.code, error: failure.message }) }
        catch (metadataError) { console.error("[ADMIN] failed to record unsuccessful database backup", metadataError) }
        throw failure
    }
}

export function createPlayerImportSnapshotBackup(
    playerId: number,
    snapshot: unknown,
    metadata: Record<string, unknown> = {},
): AdminDatabaseBackupResult {
    if (!Number.isSafeInteger(playerId) || playerId < 1) throw new Error("Player ID is invalid")
    const databaseDir = getDatabaseDirectory()
    const name = `player-import-${playerId}-${createBackupStamp()}`
    const backupRoot = path.resolve(databaseDir, "admin-backups")
    const directory = path.resolve(backupRoot, name)
    if (path.dirname(directory) !== backupRoot || !PLAYER_IMPORT_BACKUP_NAME.test(name)) {
        throw new Error("Player-import backup path is invalid")
    }
    mkdirSync(backupRoot, { recursive: true })
    mkdirSync(directory)
    try {
        writeFileSync(path.join(directory, "player-save.json"), JSON.stringify(snapshot), "utf8")
        writeFileSync(
            path.join(directory, "backup-info.json"),
            JSON.stringify({
                createdAt: new Date().toISOString(),
                type: "player-import",
                targetPlayerId: playerId,
                backupScope: "player-archive",
                snapshot: "player-save.json",
                snapshotVersion: 2,
                includesFullDatabase: false,
                ...metadata,
            }, null, 2),
            "utf8",
        )
    } catch (error) {
        if (path.dirname(directory) === backupRoot && PLAYER_IMPORT_BACKUP_NAME.test(name)) {
            rmSync(directory, { recursive: true, force: true })
        }
        throw error
    }
    return { directory, name }
}

export function cleanupPlayerImportBackups(
    currentBackupDirectory: string,
    keepCount = 5,
): PlayerImportBackupCleanupResult {
    if (!Number.isSafeInteger(keepCount) || keepCount < 1 || keepCount > 100) {
        throw new Error("Player-import backup keep count is invalid")
    }

    const backupRoot = path.resolve(getDatabaseDirectory(), "admin-backups")
    const resolvedCurrent = path.resolve(currentBackupDirectory)
    const currentName = path.basename(resolvedCurrent)
    if (
        path.dirname(resolvedCurrent) !== backupRoot ||
        !PLAYER_IMPORT_BACKUP_NAME.test(currentName) ||
        !existsSync(resolvedCurrent) ||
        !lstatSync(resolvedCurrent).isDirectory() ||
        lstatSync(resolvedCurrent).isSymbolicLink()
    ) {
        throw new Error("Current player-import backup directory is invalid")
    }

    const candidates = readdirSync(backupRoot, { withFileTypes: true })
        .filter(entry => entry.isDirectory() && !entry.isSymbolicLink() && PLAYER_IMPORT_BACKUP_NAME.test(entry.name))
        .map(entry => {
            const absolutePath = path.resolve(backupRoot, entry.name)
            return {
                name: entry.name,
                absolutePath,
                mtimeMs: lstatSync(absolutePath).mtimeMs,
            }
        })
        .sort((left, right) => right.mtimeMs - left.mtimeMs || right.name.localeCompare(left.name))

    const retained = new Set<string>([resolvedCurrent])
    for (const candidate of candidates) {
        if (retained.size >= keepCount) break
        retained.add(candidate.absolutePath)
    }

    let removedBackups = 0
    const cleanupErrors: string[] = []
    for (const candidate of candidates) {
        if (retained.has(candidate.absolutePath)) continue
        if (
            path.dirname(candidate.absolutePath) !== backupRoot ||
            !PLAYER_IMPORT_BACKUP_NAME.test(candidate.name)
        ) {
            cleanupErrors.push(`${candidate.name}: 路径校验失败`)
            continue
        }
        try {
            rmSync(candidate.absolutePath, { recursive: true, force: true })
            removedBackups++
        } catch (error) {
            cleanupErrors.push(`${candidate.name}: ${error instanceof Error ? error.message : String(error)}`)
        }
    }

    return {
        retainedBackups: candidates.length - removedBackups,
        removedBackups,
        backupCleanupError: cleanupErrors.length > 0 ? cleanupErrors.join("；") : null,
    }
}
