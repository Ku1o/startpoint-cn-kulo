import { getDb } from "../data/db"
import { getPlayerStartDashExchangeCampaignsSync } from "../data/domains/campaign"
import { getGachaSync } from "./assets"
import { SPECIAL_EXCHANGE_DEFINITIONS, START_DASH_EXCHANGE_DEFINITIONS } from "./exchange-campaign-definitions"

export interface SpecialExchangeEntitlement { campaign_id: number; status: number }

export function getSpecialExchangeEntitlementsSync(playerId: number): SpecialExchangeEntitlement[] {
    return getDb().prepare("SELECT campaign_id, status FROM players_special_exchange_campaigns WHERE player_id=? ORDER BY campaign_id")
        .all(playerId) as SpecialExchangeEntitlement[]
}

/** A balance is never proof of participation: several campaigns reuse the same ticket. */
export function getExchangeEntitlementSync(playerId: number, campaignId: number, startDash: boolean) {
    if (startDash) {
        const state = getPlayerStartDashExchangeCampaignsSync(playerId).find(row => row.campaignId === campaignId)
        const definition = START_DASH_EXCHANGE_DEFINITIONS[String(campaignId)]
        if (!state || !definition || !definition.terms.includes(state.termIndex)) return null
        const gacha = getGachaSync(state.gachaId)
        if (!gacha || !gacha.pool || gacha.type !== 0) return null
        const excluded = new Set(definition.exclude[String(state.termIndex)] ?? [])
        // Native StartDash selects non-limited 4/5-star entries from the saved gacha,
        // then removes the campaign/term exclusions. Never use a current pool instead.
        const entries = Object.values(gacha.pool).flat()
        for (const row of entries) if (row.isLimited) excluded.add(row.id)
        const rewardIds = [...new Set(entries
            .filter(row => (row.rank === 4 || row.rank === 5) && !excluded.has(row.id))
            .map(row => row.id))]
        return { status: state.status, ticketItemId: definition.ticketItemId, rewardType: 0, rewardIds }
    }
    const state = getSpecialExchangeEntitlementsSync(playerId).find(row => row.campaign_id === campaignId)
    const definition = SPECIAL_EXCHANGE_DEFINITIONS[String(campaignId)]
    return state && definition ? { status: state.status, ...definition } : null
}

export function matchesExchangeReceiptSync(playerId: number, campaignId: number, startDash: boolean, rewardType: number, rewardId: number): boolean {
    return !!getDb().prepare(`SELECT 1 FROM players_exchange_campaign_receipts
        WHERE player_id=? AND campaign_type=? AND campaign_id=? AND reward_type=? AND reward_id=?`)
        .get(playerId, startDash ? "start_dash" : "special", campaignId, rewardType, rewardId)
}

export function completeExchangeEntitlementSync(playerId: number, campaignId: number, startDash: boolean, rewardType: number, rewardId: number): void {
    const table = startDash ? "players_start_dash_exchange_campaigns" : "players_special_exchange_campaigns"
    const result = getDb().prepare(`UPDATE ${table} SET status=3 WHERE player_id=? AND campaign_id=? AND status=2`)
        .run(playerId, campaignId)
    if (result.changes !== 1) throw new Error("Exchange entitlement changed before completion")
    getDb().prepare(`INSERT INTO players_exchange_campaign_receipts(campaign_type,campaign_id,reward_type,reward_id,player_id)
        VALUES(?,?,?,?,?)`).run(startDash ? "start_dash" : "special", campaignId, rewardType, rewardId, playerId)
}
