import Database from "better-sqlite3"
import { readFileSync, statSync } from "fs"
import { parentPort, workerData } from "worker_threads"
import type {
    AdminDatabaseBackupErrorCode, AdminDatabaseBackupProgress, AdminDatabaseBackupWorkerData,
} from "../lib/admin-database-backup-worker"

const input = workerData as AdminDatabaseBackupWorkerData
const cancelFlag = new Int32Array(input.cancelBuffer)
let cancellation: { code: AdminDatabaseBackupErrorCode; error: string } | undefined
parentPort?.on("message", (message: { type?: string; code?: AdminDatabaseBackupErrorCode; error?: string }) => {
    if (message.type === "cancel") {
        cancellation = { code: message.code ?? "cancelled", error: message.error ?? "完整数据库备份已取消" }
    }
})

class BackupFailure extends Error {
    constructor(public readonly code: AdminDatabaseBackupErrorCode, message: string) { super(message) }
}

function walSize(): number {
    return statSync(`${input.databasePath}-wal`, { throwIfNoEntry: false })?.size ?? 0
}

function validateCapturedSelection(database: Database.Database): void {
    if (input.activeAccountState === undefined) return
    const state = JSON.parse(input.activeAccountState) as Record<string, unknown>
    if (!state || typeof state !== "object" || Array.isArray(state)) throw new BackupFailure("failed", "选档状态不是有效对象")
    const validId = (id: unknown): boolean => id === undefined || id === null || (Number.isSafeInteger(id) && Number(id) > 0)
    if (!validId(state.activePlayerId) || !validId(state.selectedAccountId)) throw new BackupFailure("failed", "选档状态包含无效 ID")
    if ((state.timeOffset !== undefined && state.timeOffset !== null && !Number.isSafeInteger(state.timeOffset))
        || (state.lastSetTime !== undefined && state.lastSetTime !== null
            && (typeof state.lastSetTime !== "string" || !Number.isFinite(Date.parse(state.lastSetTime))))) {
        throw new BackupFailure("failed", "选档状态的时间字段无效，未使用备用文件掩盖损坏")
    }
    if (state.activePlayerId != null && !database.prepare("SELECT 1 FROM players WHERE id=?").get(state.activePlayerId)) {
        throw new BackupFailure("failed", "捕获的当前存档不在数据库快照中，未制作混合备份")
    }
    if (state.selectedAccountId != null && !database.prepare("SELECT 1 FROM accounts WHERE id=?").get(state.selectedAccountId)) {
        throw new BackupFailure("failed", "捕获的当前账号不在数据库快照中，未制作混合备份")
    }
    if (state.defaultPlayers !== undefined && state.defaultPlayers !== null) {
        if (typeof state.defaultPlayers !== "object" || Array.isArray(state.defaultPlayers)) throw new BackupFailure("failed", "默认存档映射无效")
        const belongs = database.prepare("SELECT 1 FROM players WHERE id=? AND account_id=?")
        for (const [account, player] of Object.entries(state.defaultPlayers)) {
            if (!/^[1-9]\d*$/.test(account) || !Number.isSafeInteger(Number(account)) || !validId(player) || player == null
                || !belongs.get(player, Number(account))) {
                throw new BackupFailure("failed", "捕获的默认存档归属与数据库快照不一致，未制作混合备份")
            }
        }
    }
}

function assertVersionUnchanged(): void {
    if (input.versionSidecar && readFileSync(input.versionSidecar.filename).toString("base64") !== input.versionSidecar.contents) {
        throw new BackupFailure("failed", "数据库版本文件在捕获后变化，未制作混合版本备份")
    }
}

async function main(): Promise<void> {
    let database: Database.Database | undefined
    let destination: Database.Database | undefined
    let initialWalBytes = walSize()
    let lastAdvanceAt = Date.now()
    let maximumCopiedPages = 0
    let lastSentAt = 0
    let totalPages = 0
    let currentPhase: AdminDatabaseBackupProgress["phase"] = "opening"
    const guard = (): void => {
        if (Atomics.load(cancelFlag, 0) || cancellation) {
            throw new BackupFailure(cancellation?.code ?? "cancelled", cancellation?.error ?? "完整数据库备份已取消")
        }
        if (Date.now() - input.startedAt >= input.timeoutMs) throw new BackupFailure("timeout", "完整数据库备份超过总时限，已取消")
        if (currentPhase !== "verifying") {
            if (Date.now() - lastAdvanceAt >= input.stallTimeoutMs) throw new BackupFailure("stalled", "完整数据库备份长时间没有有效进展，已取消")
            if (walSize() - initialWalBytes > input.maxWalGrowthBytes) throw new BackupFailure("wal-growth", "备份期间 WAL 增长超过安全上限，已取消")
        }
    }
    const progress = (phase: AdminDatabaseBackupProgress["phase"], remainingPages: number, force = false): void => {
        const now = Date.now()
        if (!force && now - lastSentAt < 100) return
        lastSentAt = now
        currentPhase = phase
        const walBytes = walSize()
        parentPort?.postMessage({ type: "progress", progress: {
            phase, totalPages, remainingPages, copiedPages: Math.max(0, totalPages - remainingPages),
            elapsedMs: now - input.startedAt, walBytes, walGrowthBytes: Math.max(0, walBytes - initialWalBytes),
        } satisfies AdminDatabaseBackupProgress })
    }
    try {
        guard()
        progress("opening", 0, true)
        database = new Database(input.databasePath, { readonly: true, fileMustExist: true, timeout: 100 })
        database.pragma("query_only = ON")
        if (database.pragma("journal_mode", { simple: true }) !== "wal") {
            throw new BackupFailure("not-wal", "在线完整备份只支持已启用 WAL 的数据库；未修改源库模式，请安排维护窗口")
        }
        guard()
        assertVersionUnchanged()
        database.exec("BEGIN")
        // BEGIN alone is deferred. This actual read pins the WAL snapshot before
        // any progress callback can allow concurrent gameplay to change it.
        database.prepare("SELECT count(*) FROM sqlite_schema").get()
        const snapshotPinnedAt = new Date().toISOString()
        assertVersionUnchanged()
        validateCapturedSelection(database)
        totalPages = Number(database.pragma("page_count", { simple: true }))
        initialWalBytes = walSize()
        lastAdvanceAt = Date.now()
        progress("copying", totalPages, true)
        guard()
        const copied = await database.backup(input.destinationPath, { progress(info) {
            totalPages = info.totalPages
            const copiedPages = info.totalPages - info.remainingPages
            if (copiedPages > maximumCopiedPages) {
                maximumCopiedPages = copiedPages
                lastAdvanceAt = Date.now()
            }
            guard()
            progress("copying", info.remainingPages)
            return 100
        } })
        // Release the source snapshot before checking the destination. The large
        // verification scan must not keep the live WAL pinned unnecessarily.
        database.exec("ROLLBACK")
        database.close()
        database = undefined
        totalPages = copied.totalPages
        lastAdvanceAt = Date.now()
        progress("verifying", 0, true)
        guard()
        destination = new Database(input.destinationPath, { readonly: true, fileMustExist: true, timeout: 100 })
        const rows = destination.pragma("quick_check") as { quick_check: string }[]
        if (rows.length !== 1 || rows[0].quick_check !== "ok") {
            throw new BackupFailure("failed", "完整数据库备份完整性检查失败，未允许后续删除")
        }
        destination.close()
        destination = undefined
        guard()
        parentPort?.postMessage({ type: "completed", result: {
            totalPages, elapsedMs: Date.now() - input.startedAt, quickCheck: "ok", snapshot: true,
            snapshotPinnedAt, sidecarValidated: input.activeAccountState !== undefined,
        } })
    } finally {
        if (destination?.open) destination.close()
        if (database?.inTransaction) database.exec("ROLLBACK")
        if (database?.open) database.close()
    }
}

void main().catch(error => {
    const code = error instanceof BackupFailure ? error.code
        : /^SQLITE_(?:BUSY|LOCKED)/.test(String(error?.code)) ? "busy" : "failed"
    parentPort?.postMessage({ type: "failed", code, error: error instanceof Error ? error.message : String(error) })
    process.exitCode = 1
}).finally(() => parentPort?.close())
