import type { Database } from "better-sqlite3"

export function initializeShopCampaignLineups(db: Database): void {
    db.exec(`CREATE TABLE IF NOT EXISTS players_shop_campaign_lineups (
        player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        shop_type INTEGER NOT NULL CHECK(shop_type IN(4,7)),
        campaign_id INTEGER NOT NULL CHECK(campaign_id>0),
        lineup_id INTEGER NOT NULL CHECK(lineup_id>0),
        selected_at INTEGER NOT NULL,
        PRIMARY KEY(player_id,shop_type,campaign_id)
    )`)
}
