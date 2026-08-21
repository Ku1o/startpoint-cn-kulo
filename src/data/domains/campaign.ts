import { getDb } from "../db";
import {
    PlayerPeriodicRewardPoint,
    PlayerStartDashExchangeCampaign,
    PlayerMultiSpecialExchangeCampaign,
    RawPlayerStartDashExchangeCampaign,
    RawPlayerMultiSpecialExchangeCampaign,
} from "../types";

// ─── Periodic Reward Points ───

/**
 * Gets all of a player's periodic reward points.
 * 
 * @param playerId The ID of the player.
 * @returns A list of the player's periodic reward points
 */
export function getPlayerPeriodicRewardPointsSync(
    playerId: number
): PlayerPeriodicRewardPoint[] {
    const db = getDb();
    return db.prepare(`
    SELECT id, point
    FROM players_periodic_reward_points
    WHERE player_id = ?
    `).all(playerId) as PlayerPeriodicRewardPoint[]
}

function insertPlayerPeriodicRewardPointsSync(
    playerId: number,
    periodicReward: PlayerPeriodicRewardPoint
) {
    const db = getDb();
    db.prepare(`
    INSERT INTO players_periodic_reward_points (id, point, player_id)
    VALUES (?, ?, ?)
    `).run(periodicReward.id, periodicReward.point, playerId)
}

export function insertPlayerPeriodicRewardPointsListSync(
    playerId: number,
    periodicRewards: PlayerPeriodicRewardPoint[]
) {
    const db = getDb();
    db.transaction(() => {
        for (const periodicReward of periodicRewards) {
            insertPlayerPeriodicRewardPointsSync(playerId, periodicReward)
        }
    })()
}

// ─── Start Dash Exchange Campaign ───

/**
 * Gets the progress of a player's start dash exchange campaigns.
 * 
 * @param playerId The player's ID.
 * @returns The status of the player's start dash exchange campaigns.
 */
export function getPlayerStartDashExchangeCampaignsSync(
    playerId: number
): PlayerStartDashExchangeCampaign[] {
    const db = getDb();
    const rawCampaigns = db.prepare(`
    SELECT campaign_id, gacha_id, term_index, status, period_start_time, period_end_time
    FROM players_start_dash_exchange_campaigns
    WHERE player_id = ?
    `).all(playerId) as RawPlayerStartDashExchangeCampaign[]

    return rawCampaigns.map(raw => ({
        campaignId: raw.campaign_id,
        gachaId: raw.gacha_id,
        termIndex: raw.term_index,
        status: raw.status,
        periodStartTime: new Date(raw.period_start_time),
        periodEndTime: new Date(raw.period_end_time)
    }))
}

function insertPlayerStartDashExchangeCampaignSync(
    playerId: number,
    campaign: PlayerStartDashExchangeCampaign
) {
    const db = getDb();
    db.prepare(`
    INSERT INTO players_start_dash_exchange_campaigns (campaign_id, gacha_id, term_index, status, period_start_time, period_end_time, player_id)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
        campaign.campaignId, campaign.gachaId, campaign.termIndex,
        campaign.status,
        campaign.periodStartTime.toISOString(),
        campaign.periodEndTime.toISOString(),
        playerId
    )
}

export function insertPlayerStartDashExchangeCampaignsSync(
    playerId: number,
    campaigns: PlayerStartDashExchangeCampaign[]
) {
    const db = getDb();
    db.transaction(() => {
        for (const campaign of campaigns) {
            insertPlayerStartDashExchangeCampaignSync(playerId, campaign)
        }
    })()
}

// ─── Multi Special Exchange Campaign ───

/**
 * Gets the progress of a player's multi special exchange campaigns.
 * 
 * @param playerId The player's ID.
 * @returns The status of the player's multi special exchange campaigns.
 */
export function getPlayerMultiSpecialExchangeCampaignsSync(
    playerId: number
): PlayerMultiSpecialExchangeCampaign[] {
    const db = getDb();
    const rawCampaigns = db.prepare(`
    SELECT campaign_id, status, ticket_item_id
    FROM players_multi_special_exchange_campaigns
    WHERE player_id = ?
    `).all(playerId) as RawPlayerMultiSpecialExchangeCampaign[]

    return rawCampaigns.map(raw => ({
        campaignId: raw.campaign_id,
        status: raw.status,
        ticketItemId: raw.ticket_item_id,
    }))
}

function insertPlayerMultiSpecialExchangeCampaignSync(
    playerId: number,
    campaign: PlayerMultiSpecialExchangeCampaign
) {
    const db = getDb();
    db.prepare(`
    INSERT INTO players_multi_special_exchange_campaigns (campaign_id, status, ticket_item_id, player_id)
    VALUES (?, ?, ?, ?)
    `).run(campaign.campaignId, campaign.status, campaign.ticketItemId ?? null, playerId)
}

export function updatePlayerMultiSpecialExchangeCampaignSync(
    playerId: number,
    campaign: PlayerMultiSpecialExchangeCampaign,
): void {
    getDb().prepare(`
        INSERT INTO players_multi_special_exchange_campaigns
            (campaign_id, status, ticket_item_id, player_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(campaign_id, player_id) DO UPDATE SET
            status = excluded.status,
            ticket_item_id = excluded.ticket_item_id
    `).run(campaign.campaignId, campaign.status, campaign.ticketItemId ?? null, playerId)
}

export function insertPlayerMultiSpecialExchangeCampaignsSync(
    playerId: number,
    campaigns: PlayerMultiSpecialExchangeCampaign[]
) {
    const db = getDb();
    db.transaction(() => {
        for (const campaign of campaigns) {
            insertPlayerMultiSpecialExchangeCampaignSync(playerId, campaign)
        }
    })()
}
