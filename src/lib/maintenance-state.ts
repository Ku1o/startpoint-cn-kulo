import { randomUUID } from "crypto"
import type { Database } from "better-sqlite3"

export interface ReceiveHistoryPolicy { maxRows: number; maxDays: number; dailyHour: number; dailyMinute: number }
export const DEFAULT_HISTORY_POLICY: Readonly<ReceiveHistoryPolicy> = Object.freeze({ maxRows: 500, maxDays: 7, dailyHour: 4, dailyMinute: 30 })
export const HISTORY_JOB = "receive-history-retention"
const LEASE_MS = 120_000

export function initializeMaintenanceState(db: Database): void {
    db.exec(`CREATE TABLE IF NOT EXISTS server_maintenance_settings(name TEXT PRIMARY KEY,value_json TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS server_maintenance_jobs(
            name TEXT PRIMARY KEY,owner_token TEXT,lease_until INTEGER NOT NULL DEFAULT 0,
            last_started_at TEXT,last_completed_at TEXT,last_result_json TEXT,last_error TEXT) WITHOUT ROWID;`)
    db.prepare("INSERT OR IGNORE INTO server_maintenance_settings VALUES(?,?)").run(HISTORY_JOB,JSON.stringify(DEFAULT_HISTORY_POLICY))
    db.prepare("INSERT OR IGNORE INTO server_maintenance_jobs(name) VALUES(?)").run(HISTORY_JOB)
}

export function validateHistoryPolicy(value: unknown): ReceiveHistoryPolicy {
    if (!value || typeof value !== "object") throw new Error("领取历史保留配置无效")
    const p = value as ReceiveHistoryPolicy
    for (const [name, max] of [["maxRows", 100_000], ["maxDays", 3650], ["dailyHour", 23], ["dailyMinute", 59]] as const) {
        const min = name === "maxRows" || name === "maxDays" ? 1 : 0
        if (!Number.isSafeInteger(p[name]) || p[name] < min || p[name] > max) throw new Error(`领取历史配置无效：${name}`)
    }
    return {maxRows:p.maxRows,maxDays:p.maxDays,dailyHour:p.dailyHour,dailyMinute:p.dailyMinute}
}

export function readHistoryPolicy(db: Database): ReceiveHistoryPolicy {
    const row = db.prepare("SELECT value_json FROM server_maintenance_settings WHERE name=?").get(HISTORY_JOB) as {value_json:string} | undefined
    if (!row) throw new Error("领取历史持久化配置缺失")
    return validateHistoryPolicy(JSON.parse(row.value_json))
}

export function writeHistoryPolicy(db: Database, policy: ReceiveHistoryPolicy): void {
    const validated = validateHistoryPolicy(policy)
    db.prepare("INSERT INTO server_maintenance_settings VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value_json=excluded.value_json")
        .run(HISTORY_JOB, JSON.stringify(validated))
}

export interface MaintenanceLease { token: string; nextRefresh: number }

export function acquireHistoryLease(db: Database, now = Date.now()): MaintenanceLease | null {
    const token = randomUUID()
    const result = db.prepare(`UPDATE server_maintenance_jobs SET owner_token=?,lease_until=?,last_started_at=?,last_error=NULL
        WHERE name=? AND (owner_token IS NULL OR lease_until<=?)`).run(token,now+LEASE_MS,new Date(now).toISOString(),HISTORY_JOB,now)
    return result.changes === 1 ? {token,nextRefresh:now+20_000} : null
}

export function refreshHistoryLease(db: Database, lease: MaintenanceLease, now = Date.now()): void {
    if (now < lease.nextRefresh) return
    const result = db.prepare("UPDATE server_maintenance_jobs SET lease_until=? WHERE name=? AND owner_token=? AND lease_until>?")
        .run(now+LEASE_MS,HISTORY_JOB,lease.token,now)
    if (result.changes !== 1) throw new Error("历史维护锁已失效，停止当前批次")
    lease.nextRefresh = now+20_000
}

export function finishHistoryLease(db: Database, lease: MaintenanceLease, result: unknown, success: boolean, error: string | null = null): void {
    db.prepare(`UPDATE server_maintenance_jobs SET owner_token=NULL,lease_until=0,last_result_json=?,last_error=?,
        last_completed_at=CASE WHEN ? THEN ? ELSE last_completed_at END WHERE name=? AND owner_token=?`)
        .run(result === undefined ? null : JSON.stringify(result),error,success?1:0,new Date().toISOString(),HISTORY_JOB,lease.token)
}

export function isHistoryCatchupNeeded(db: Database, hour: number, minute: number, now = new Date()): boolean {
    const scheduled = new Date(now.getTime())
    scheduled.setHours(hour,minute,0,0)
    if (scheduled.getTime() > now.getTime()) scheduled.setDate(scheduled.getDate()-1)
    const row = db.prepare("SELECT last_completed_at FROM server_maintenance_jobs WHERE name=?").get(HISTORY_JOB) as {last_completed_at:string|null} | undefined
    return !row?.last_completed_at || !Number.isFinite(Date.parse(row.last_completed_at)) || Date.parse(row.last_completed_at)<scheduled.getTime()
}
