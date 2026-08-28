import { getDb } from "../db"
import {
    BATTLE_HISTORY_COLUMNS,
    BattleHistoryProtocolRecord,
    battleHistoryProtocolValues,
} from "./battle-history"

// The legacy client has no paging and eagerly converts every returned record.
// Bound the combined practice-quest list while keeping the durable archive.
export const PRACTICE_BATTLE_HISTORY_CLIENT_LIMIT = 100

export interface PracticeBattleHistoryInsert extends BattleHistoryProtocolRecord {
    readonly playerId: number
    readonly playId: string
}

export function insertPlayerPracticeBattleHistorySync(
    record: PracticeBattleHistoryInsert,
): boolean {
    const placeholders = Array.from({ length: 31 }, () => "?").join(", ")
    const result = getDb().prepare(`
        INSERT OR IGNORE INTO players_practice_battle_history (
            player_id, play_id, ${BATTLE_HISTORY_COLUMNS}
        ) VALUES (${placeholders})
    `).run(record.playerId, record.playId, ...battleHistoryProtocolValues(record))
    return result.changes === 1
}

export function getPlayerPracticeBattleHistorySync(
    playerId: number,
): BattleHistoryProtocolRecord[] {
    return getDb().prepare(`
        SELECT ${BATTLE_HISTORY_COLUMNS}
        FROM players_practice_battle_history
        WHERE player_id = ? AND category_id = 15
        ORDER BY id DESC
        LIMIT ?
    `).all(playerId, PRACTICE_BATTLE_HISTORY_CLIENT_LIMIT) as BattleHistoryProtocolRecord[]
}
