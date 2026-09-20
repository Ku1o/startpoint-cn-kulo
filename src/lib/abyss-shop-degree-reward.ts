import { readFileSync } from "node:fs"
import path from "node:path"
import { getDb } from "../data/db"
import {
    getPlayerShopPurchaseCountSync,
} from "../data/domains/shopPurchase"
import { grantPlayerDegreeSync } from "../data/domains/degree"
import { ShopType } from "./types"

export const ABYSS_SHOP_DEGREE_ID = 9_911_001
export const ABYSS_SHOP_TICKET_IDS = Object.freeze([9_700_116, 9_700_117] as const)
export const ABYSS_SHOP_REQUIRED_PURCHASES = 9_999
export const ABYSS_SHOP_DEGREE_CONFIG_PATH = path.resolve(
    __dirname, "..", "..", "assets", "abyss_shop_degree_reward.json",
)

interface RewardOptions {
    configPath?: string
}

/** Both ticket products must reach the threshold independently. */
export function isAbyssShopDegreeEligible(singleCount: number, tenfoldCount: number): boolean {
    return [singleCount, tenfoldCount].every(count => (
        Number.isSafeInteger(count) && count >= ABYSS_SHOP_REQUIRED_PURCHASES
    ))
}

/** Keep the reward closed until its server config and client resources are published. */
export function abyssShopDegreeRewardEnabled(
    configPath: string = ABYSS_SHOP_DEGREE_CONFIG_PATH,
): boolean {
    try {
        const raw: unknown = JSON.parse(readFileSync(configPath, "utf8"))
        if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return false
        const config = raw as Record<string, unknown>
        return config.schema_version === 1
            && config.enabled === true
            && config.degree_id === ABYSS_SHOP_DEGREE_ID
            && config.required_purchases === ABYSS_SHOP_REQUIRED_PURCHASES
            && Array.isArray(config.shop_item_ids)
            && config.shop_item_ids.length === ABYSS_SHOP_TICKET_IDS.length
            && config.shop_item_ids.every((id, index) => id === ABYSS_SHOP_TICKET_IDS[index])
    } catch {
        return false
    }
}

function grantEligibleAbyssShopDegreeSync(playerId: number): number[] {
    const db = getDb()
    if (!db.prepare("SELECT id FROM players WHERE id = ?").get(playerId)) return []
    const counts = ABYSS_SHOP_TICKET_IDS.map(id => getPlayerShopPurchaseCountSync(playerId, id))
    if (!isAbyssShopDegreeEligible(counts[0], counts[1])) return []
    return grantPlayerDegreeSync(playerId, ABYSS_SHOP_DEGREE_ID) ? [ABYSS_SHOP_DEGREE_ID] : []
}

/** Checks persisted purchase counters only; ticket inventory is deliberately ignored. */
export function grantAbyssShopDegreeRewardSync(
    playerId: number,
    options: RewardOptions = {},
): number[] {
    if (!Number.isSafeInteger(playerId) || playerId <= 0
        || !abyssShopDegreeRewardEnabled(options.configPath)) return []
    return getDb().transaction(() => grantEligibleAbyssShopDegreeSync(playerId))()
}

/** The shop route calls this after counters change, inside its purchase transaction. */
export function grantPurchasedAbyssShopDegreeRewardSync(
    playerId: number,
    shopType: number,
    purchases: readonly { shopItemId: number }[],
    options: RewardOptions = {},
): number[] {
    const targetsTicket = shopType === ShopType.EVENT_ITEM && purchases.some(entry =>
        ABYSS_SHOP_TICKET_IDS.some(id => id === entry.shopItemId))
    return targetsTicket ? grantAbyssShopDegreeRewardSync(playerId, options) : []
}
