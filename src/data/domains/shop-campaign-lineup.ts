import { getDb } from "../db"

export function getPlayerShopCampaignLineupSync(playerId: number, shopType: number, campaignId: number): number | null {
    return (getDb().prepare(`SELECT lineup_id FROM players_shop_campaign_lineups
        WHERE player_id=? AND shop_type=? AND campaign_id=?`).get(playerId, shopType, campaignId) as { lineup_id: number } | undefined)?.lineup_id ?? null
}

/** The caller owns the player transaction; a different choice never overwrites progress. */
export function selectPlayerShopCampaignLineupSync(playerId: number, shopType: number, campaignId: number,
    lineupId: number, selectedAtMs = Date.now()): "inserted" | "unchanged" | "conflict" {
    const inserted = getDb().prepare(`INSERT OR IGNORE INTO players_shop_campaign_lineups
        (player_id,shop_type,campaign_id,lineup_id,selected_at) VALUES(?,?,?,?,?)`)
        .run(playerId, shopType, campaignId, lineupId, selectedAtMs).changes === 1
    return inserted ? "inserted" : getPlayerShopCampaignLineupSync(playerId, shopType, campaignId) === lineupId ? "unchanged" : "conflict"
}
