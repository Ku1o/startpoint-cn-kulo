import type { Database } from "better-sqlite3"

export function initializeBondTokenExchange(db: Database): void {
    db.exec(`CREATE TABLE IF NOT EXISTS players_bond_token_exchanges (
        player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        equipment_id INTEGER NOT NULL,
        exchange_count INTEGER NOT NULL CHECK(exchange_count >= 0),
        PRIMARY KEY(player_id, equipment_id)
    )`)
}
