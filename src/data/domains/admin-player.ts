import { getDb } from "../db"

export interface AdminPlayerSummary {
    readonly id: number
    readonly accountId: number
    readonly name: string
    readonly comment: string
    readonly degreeId: number
}

/**
 * Loads the lightweight player fields needed by the account overview in one query.
 */
export function getAllAdminPlayerSummariesSync(): AdminPlayerSummary[] {
    const rows = getDb().prepare(`
        SELECT id, account_id, name, comment, degree_id
        FROM players
        ORDER BY id
    `).all() as Array<{
        id: number
        account_id: number
        name: string
        comment: string | null
        degree_id: number | null
    }>

    return rows.map(row => ({
        id: row.id,
        accountId: row.account_id,
        name: row.name,
        comment: row.comment ?? "",
        degreeId: row.degree_id ?? 0,
    }))
}
