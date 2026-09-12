import { getDb } from "../db"
import { getAbyssTimeRevision, isAbyssFiniteQuest } from "../../lib/abyss-time-revision"
import { resolvePlayerIdSync } from "../activeAccount"

export interface AbyssRecordFinish {
    category: number; questId: number; revision?: string | null
    viewerId: number; elapsedTimeMs: number; startedAtMs?: number; nowMs: number
    accomplished: boolean; registered: boolean; matchingPlay: boolean; isMulti: boolean
}

/** Called inside the settlement transaction, never by save import or progress reads. */
export function recordAbyssFloorFinishSync(finish: AbyssRecordFinish): boolean {
    const current = getAbyssTimeRevision()
    if (!isAbyssFiniteQuest(finish.category, finish.questId) || !current || finish.revision !== current
        || !finish.accomplished || !finish.registered || !finish.matchingPlay || finish.isMulti
        || !Number.isSafeInteger(finish.viewerId) || finish.viewerId <= 0
        || !Number.isSafeInteger(finish.elapsedTimeMs) || finish.elapsedTimeMs <= 0
        || finish.elapsedTimeMs > 2147483647
        || !Number.isFinite(finish.startedAtMs) || !Number.isFinite(finish.nowMs)
        || finish.startedAtMs! > finish.nowMs
        // Allow transport/whole-second start timestamp tolerance, not future play time.
        || finish.elapsedTimeMs > finish.nowMs - finish.startedAtMs! + 5000) return false
    return getDb().prepare(`INSERT INTO abyss_floor_records
        (revision, quest_id, elapsed_time_ms, viewer_id, recorded_at_ms) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(revision, quest_id) DO UPDATE SET
            elapsed_time_ms=excluded.elapsed_time_ms, viewer_id=excluded.viewer_id,
            recorded_at_ms=excluded.recorded_at_ms
        WHERE excluded.elapsed_time_ms < abyss_floor_records.elapsed_time_ms`)
        .run(current, finish.questId, finish.elapsedTimeMs, finish.viewerId, finish.nowMs).changes > 0
}

export function getAbyssFloorRecordSync(revision: string, questId: number): number | null {
    const row = getDb().prepare(`SELECT elapsed_time_ms FROM abyss_floor_records
        WHERE revision=? AND quest_id=?`).get(revision, questId) as { elapsed_time_ms: number } | undefined
    return row?.elapsed_time_ms ?? null
}

/** Resolve the record's public viewer identity like the public player profile.
 * No login tokens, account fields or player IDs are returned to callers.
 */
export function getAbyssFloorRecordDetailsSync(revision: string, questId: number): {
    bestTimeMs: number; holderName: string | null
} | null {
    const db = getDb()
    const row = db.prepare(`SELECT r.elapsed_time_ms, s.account_id
        FROM abyss_floor_records r
        LEFT JOIN sessions s ON s.token=CAST(r.viewer_id AS TEXT) AND s.type=2
        WHERE r.revision=? AND r.quest_id=?`).get(revision, questId) as {
            elapsed_time_ms: number; account_id: number | null
        } | undefined
    if (!row) return null
    const playerId = row.account_id === null ? null : resolvePlayerIdSync(row.account_id)
    const profile = playerId === null ? undefined : db.prepare('SELECT name FROM players WHERE id=?')
        .get(playerId) as { name: string } | undefined
    return { bestTimeMs: row.elapsed_time_ms, holderName: profile?.name || null }
}
