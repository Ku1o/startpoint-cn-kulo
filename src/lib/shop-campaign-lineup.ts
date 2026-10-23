import campaigns from "../../assets/shop_select_item_campaign.json"
import itemCampaigns from "../../assets/shop_item_campaign.json"
import { getPlayerShopCampaignLineupSync } from "../data/domains/shop-campaign-lineup"
import { getShopItemSync } from "./assets"
import { shopContentDecision } from "./content-economy-operations"
import { isShopItemAvailable } from "./shop-sales"

interface Campaign { availableFrom: string; availableUntil: string; lineupIds: number[] }
interface ItemCampaign { campaignId: number; lineupId?: number }
const definitions = campaigns as Record<string, Record<string, Campaign>>
const memberships = itemCampaigns as Record<string, Record<string, ItemCampaign>>

export function isShopItemInSelectedLineupSync(playerId: number, shopType: number, itemId: number): boolean {
    const membership = memberships[String(shopType)]?.[String(itemId)]
    return !membership || membership.lineupId === undefined
        || getPlayerShopCampaignLineupSync(playerId, shopType, membership.campaignId) === membership.lineupId
}

/** Availability follows existing per-product operations and historical periods. */
export function validateShopCampaignSelection(shopType: number, campaignId: number, lineupId: number | null,
    now: Date, realNowMs = Date.now()): "valid" | "invalid" | "unavailable" {
    const campaign = definitions[String(shopType)]?.[String(campaignId)]
    if (![4, 7].includes(shopType) || !Number.isSafeInteger(campaignId) || campaignId <= 0 || !campaign
        || (lineupId !== null && (!Number.isSafeInteger(lineupId) || !campaign.lineupIds.includes(lineupId)))) return "invalid"
    const relevant = Object.entries(memberships[String(shopType)] ?? {}).filter(([, item]) => item.campaignId === campaignId
        && (lineupId === null || item.lineupId === lineupId))
    return relevant.some(([id]) => {
        const item = getShopItemSync(shopType, Number(id))
        return item !== null && (shopContentDecision(shopType, Number(id), "exchange", realNowMs) ?? isShopItemAvailable(item, now))
    }) ? "valid" : "unavailable"
}
