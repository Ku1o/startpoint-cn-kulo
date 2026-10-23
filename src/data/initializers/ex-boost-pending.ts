import type { Database } from "better-sqlite3"

export function initializeExBoostPendingSchema(database: Database): void {
    database.exec(`CREATE TABLE IF NOT EXISTS players_ex_boost_pending_draws (
        player_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
        draw_id TEXT NOT NULL,
        character_id INTEGER NOT NULL,
        status_id INTEGER NOT NULL,
        ability_id_list TEXT NOT NULL,
        cost_item_id INTEGER NOT NULL,
        cost_item_count INTEGER NOT NULL
    )`)
}
