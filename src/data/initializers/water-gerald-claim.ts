import type { Database } from "better-sqlite3"

export function initializeWaterGeraldClaim(db: Database): void {
    db.exec(`CREATE TABLE IF NOT EXISTS players_water_gerald_claims (
        player_id INTEGER NOT NULL PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
        claimed_at INTEGER NOT NULL CHECK(claimed_at >= 0)
    )`)
}
