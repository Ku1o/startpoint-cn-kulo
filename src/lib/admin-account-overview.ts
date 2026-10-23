import type { Database } from "better-sqlite3"
import { accountHasNote } from "./admin-account-cleanup"

export interface AdminAccountSelection {
    activePlayerId: number | null
    defaultPlayers: Readonly<Record<number, number>>
}

interface AccountBase { id: number; admin_note: string | null; username: string | null; takeover_configured: number }
interface PlayerBrief { id: number; accountId: number; name: string; comment: string; degreeId: number }
interface Binding { account_id: number; device_id: number }
interface Viewer { account_id: number; token: string }
interface Transfer {
    target_account_id: number; source_viewer_id: string | null; old_device_id: number | null
    new_device_id: number; source_player_count: number; transferred_at: string; source: string
}

export interface AdminAccountSummary {
    accountCount: number
    saveCount: number
    unnotedAccountCount: number
    unnotedSaveCount: number
}

/** Counts belong to all accounts, never just a visible page or search result. */
export function readAdminAccountSummary(database: Database): AdminAccountSummary {
    const accounts = database.prepare("SELECT id, admin_note FROM accounts").all() as Array<{ id: number; admin_note: string | null }>
    const counts = new Map((database.prepare("SELECT account_id, COUNT(*) AS count FROM players GROUP BY account_id").all() as Array<{ account_id: number; count: number }>).map(row => [row.account_id, row.count]))
    const summary = { accountCount: accounts.length, saveCount: 0, unnotedAccountCount: 0, unnotedSaveCount: 0 }
    for (const account of accounts) {
        const count = counts.get(account.id) ?? 0
        summary.saveCount += count
        if (!accountHasNote({ id: account.id, adminNote: account.admin_note })) {
            summary.unnotedAccountCount++
            summary.unnotedSaveCount += count
        }
    }
    return summary
}

function grouped<T>(rows: T[], key: (row: T) => number): Map<number, T[]> {
    const result = new Map<number, T[]>()
    for (const row of rows) {
        const id = key(row), values = result.get(id) ?? []
        values.push(row); result.set(id, values)
    }
    return result
}

function readRelated(database: Database, ids?: readonly number[]) {
    const where = ids ? ` WHERE account_id IN (${ids.map(() => "?").join(",")})` : ""
    const args = ids ? [...ids] : []
    const players = database.prepare(`SELECT id, account_id AS accountId, name, COALESCE(comment,'') AS comment, COALESCE(degree_id,0) AS degreeId FROM players${where} ORDER BY id`).all(...args) as PlayerBrief[]
    const bindings = database.prepare(`SELECT account_id, device_id FROM device_bindings${where}`).all(...args) as Binding[]
    const viewers = database.prepare(`SELECT account_id, token FROM sessions WHERE type=2${ids ? ` AND account_id IN (${ids.map(() => "?").join(",")})` : ""} ORDER BY rowid`).all(...args) as Viewer[]
    const firstViewer = new Map<number, string>()
    for (const viewer of viewers) if (!firstViewer.has(viewer.account_id)) firstViewer.set(viewer.account_id, viewer.token)
    return { players: grouped(players, player => player.accountId), bindings: grouped(bindings, binding => binding.account_id), firstViewer }
}

/** JS case folding and full joined text preserve the old browser search, including Unicode. */
export function findAdminAccountIds(database: Database, query: string): number[] {
    const accounts = database.prepare("SELECT id, admin_note, username FROM accounts ORDER BY id DESC").all() as Array<{ id: number; admin_note: string | null; username: string | null }>
    const related = readRelated(database)
    const normalized = query.trim().toLowerCase()
    return accounts.filter(account => [
        account.id, related.firstViewer.get(account.id) ?? null, account.admin_note, account.username || null,
        ...(related.bindings.get(account.id) ?? []).map(binding => binding.device_id),
        ...(related.players.get(account.id) ?? []).flatMap(player => [player.id, player.name, player.comment]),
    ].filter(value => value != null).join(" ").toLowerCase().includes(normalized)).map(account => account.id)
}

function readAccountRows(database: Database, selection: AdminAccountSelection, ids?: readonly number[], management = true) {
    if (ids && ids.length === 0) return []
    const marks = ids?.map(() => "?").join(","), args = ids ? [...ids] : []
    const accounts = database.prepare(`SELECT id, admin_note, username,
        CASE WHEN takeover_password IS NOT NULL AND takeover_password<>'' THEN 1 ELSE 0 END AS takeover_configured
        FROM accounts${ids ? ` WHERE id IN (${marks})` : ""} ORDER BY id DESC`).all(...args) as AccountBase[]
    const related = readRelated(database, ids)
    const loginByAccount = new Map<number, { bound: boolean; boundAt: number | null; sessionExpiresAt: number | null }>()
    const transfers = new Map<number, Transfer>()
    if (management) {
        const hasTable = (name: string) => Boolean(database.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(name))
        if (hasTable("player_login_credentials") && hasTable("player_login_sessions")) {
            const rows = database.prepare(`SELECT c.account_id,c.created_at,s.expires_at FROM player_login_credentials c
                JOIN accounts a ON a.id=c.account_id LEFT JOIN player_login_sessions s
                ON s.account_id=c.account_id AND s.expires_at>? AND a.status='normal'
                ${ids ? `WHERE c.account_id IN (${marks})` : ""}`).all(Date.now(), ...args) as Array<{ account_id: number; created_at: number; expires_at: number | null }>
            for (const row of rows) loginByAccount.set(row.account_id, { bound: true, boundAt: row.created_at, sessionExpiresAt: row.expires_at })
        }
        if (hasTable("account_transfer_audit")) {
            const rows = database.prepare(`SELECT target_account_id,source_viewer_id,old_device_id,new_device_id,source_player_count,transferred_at,source
                FROM account_transfer_audit WHERE id IN (SELECT MAX(id) FROM account_transfer_audit ${ids ? `WHERE target_account_id IN (${marks})` : ""} GROUP BY target_account_id)`).all(...args) as Transfer[]
            for (const row of rows) transfers.set(row.target_account_id, row)
        }
    }
    return accounts.map(account => {
        const players = related.players.get(account.id) ?? [], playerIds = players.map(player => player.id)
        const savedDefault = selection.defaultPlayers[account.id]
        const defaultPlayerId = savedDefault && playerIds.includes(savedDefault) ? savedDefault : playerIds[0] ?? null
        const base = {
            id: account.id, viewerId: related.firstViewer.get(account.id) ?? null, note: account.admin_note ?? null,
            bindings: (related.bindings.get(account.id) ?? []).map(binding => ({ deviceId: binding.device_id })),
            saveCount: players.length, defaultPlayerId, defaultPlayerName: players.find(player => player.id === defaultPlayerId)?.name ?? null,
            players, playerIds,
        }
        if (!management) return base
        const transfer = transfers.get(account.id)
        return {
            ...base, loginUsername: account.username || null, takeoverConfigured: Boolean(account.takeover_configured),
            playerLogin: loginByAccount.get(account.id) ?? { bound: false, boundAt: null, sessionExpiresAt: null },
            latestTransfer: transfer ? { abolishedViewerId: transfer.source_viewer_id, oldDeviceId: transfer.old_device_id, newDeviceId: transfer.new_device_id, discardedSaveCount: transfer.source_player_count, transferredAt: transfer.transferred_at, source: transfer.source } : null,
            activePlayerId: selection.activePlayerId,
            players: players.map(player => ({ ...player, isDefault: player.id === defaultPlayerId, isActive: player.id === selection.activePlayerId })),
        }
    })
}

export function readAdminAccountPage(database: Database, selection: AdminAccountSelection, page: number, pageSize: number, query: string) {
    const summary = readAdminAccountSummary(database)
    const matches = query.trim() ? findAdminAccountIds(database, query) : null
    const total = matches?.length ?? summary.accountCount
    const currentPage = Math.min(page, Math.max(1, Math.ceil(total / pageSize)))
    const offset = (currentPage - 1) * pageSize
    const ids = matches ? matches.slice(offset, offset + pageSize)
        : (database.prepare("SELECT id FROM accounts ORDER BY id DESC LIMIT ? OFFSET ?").all(pageSize, offset) as Array<{ id: number }>).map(row => row.id)
    return { rows: readAccountRows(database, selection, ids), total, page: currentPage, pageSize, summary }
}

export function readAdminAccountDetail(database: Database, selection: AdminAccountSelection, id: number) {
    return readAccountRows(database, selection, [id])[0] ?? null
}

export function readAdminAccountTargets(database: Database, selection: AdminAccountSelection) {
    const accounts = readAccountRows(database, selection, undefined, false)
    return { accounts, accountCount: accounts.length, saveCount: accounts.reduce((sum, account) => sum + account.saveCount, 0) }
}
