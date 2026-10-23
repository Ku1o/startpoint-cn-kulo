import { contentDecision } from "./content-operations"
import { isPassCardEventActiveAt, type PassCardEventDefinition } from "./pass-card"
import type { ContentAction } from "./content-operations-store"
import { ShopType } from "./types"
import { serverEventShopIdMap } from "./content-master"
import type { ContentCatalogRow } from "./content-operations-store"
import { getBoxOperationRules } from "./box-gacha-policy"
import { getPassCardEventDefinition, getPassCardRewardDefinition } from "./pass-card"
import passRewards from "../../assets/pass_card_reward.json"
import { SPECIAL_EXCHANGE_DEFINITIONS, START_DASH_EXCHANGE_DEFINITIONS } from "./exchange-campaign-definitions"
import { validShopQuotaRules } from "./shop-quota"

const shopTypes: Readonly<Record<number, string>> = {
    [ShopType.GENERAL]: "general_shop", [ShopType.STAR_GRAIN]: "star_grain_shop",
    [ShopType.TREASURE]: "treasure_shop", [ShopType.BOSS_COIN]: "boss_coin_shop",
    [ShopType.EVENT_ITEM]: "event_item_shop",
}
const shopParentTypes: Readonly<Record<number, string>> = {
    0: "advent_event", 2: "story_event", 4: "challenge_dungeon_event", 6: "world_story_event",
    9: "collect_item_event", 10: "carnival_event", 11: "rush_event", 12: "score_attack_event",
}

export function shopContentDecision(shopType: number, itemId: number, action: ContentAction, realNowMs = Date.now()): boolean | null {
    const type = shopTypes[shopType]
    const product = type ? contentDecision(type, itemId, action, realNowMs) : null
    const mapping = shopType === ShopType.EVENT_ITEM
        ? (serverEventShopIdMap as Record<string, { eventType: number; eventId: number }>)[String(itemId)] : undefined
    const parentType = mapping ? shopParentTypes[mapping.eventType] : undefined
    const parent = parentType && mapping ? contentDecision(parentType, mapping.eventId, action, realNowMs) : null
    if (product === false || parent === false) return false
    // A parent's open gate does not verify each product or its separate quotas.
    return product === true ? true : null
}

/** Explicit operations use real time; unmanaged content retains its existing business clock. */
export function isPassContentAvailable(event: PassCardEventDefinition, action: ContentAction, legacyAt: Date): boolean {
    return contentDecision("pass_card_event", event.eventId, action, Date.now())
        ?? isPassCardEventActiveAt(event, legacyAt)
}

/** Runtime wiring and complete rule availability; resource identities are checked by the global store. */
export function contentEconomyCapabilities(row: ContentCatalogRow): readonly ContentAction[] | null {
    if (row.type === "special_exchange_campaign") {
        const definition = SPECIAL_EXCHANGE_DEFINITIONS[String(row.id)]
        return definition && Number.isSafeInteger(definition.ticketItemId) && definition.ticketItemId > 0
            && [0, 1].includes(definition.rewardType) && definition.rewardIds.length > 0
            && definition.rewardIds.every(id => Number.isSafeInteger(id) && id > 0) ? ["exchange"] : []
    }
    if (row.type === "start_dash_exchange_campaign") {
        const definition = START_DASH_EXCHANGE_DEFINITIONS[String(row.id)]
        return definition && Number.isSafeInteger(definition.ticketItemId) && definition.ticketItemId > 0
            && definition.terms.length > 0 ? ["exchange"] : []
    }
    if (row.type === "pass_card_event") {
        const missionKeys = (row as ContentCatalogRow & { missionKeys?: string[] }).missionKeys
        const rewardIds = Object.entries(passRewards).filter(([, rows]) => Number(rows[0]?.[0]) === row.id).map(([id]) => Number(id))
        if (!getPassCardEventDefinition(row.id) || !missionKeys?.length || !rewardIds.length
            || rewardIds.some(id => {
                const reward = getPassCardRewardDefinition(id)
                return !reward || reward.level < 0 || [reward.reward1, reward.reward2].some(track =>
                    ![0, 1, 2, 3, 4, 5, 6].includes(track.kind) || track.amount < 0)
            })) return []
        return ["visible", "enter", "claim"]
    }
    const mapping = Object.entries(shopTypes).find(([, type]) => type === row.type)
    if (row.type !== "box_gacha" && !mapping) return null
    // Resolve lazily to avoid importing all quest and shop assets while modules initialize.
    const assets = require("./assets") as typeof import("./assets")
    if (row.type === "box_gacha") {
        const master = assets.getBoxGachaSync(row.id)
        const rules = master ? getBoxOperationRules(row, master.boxes) : null
        if (!master || !Number.isSafeInteger(master.redeemItemCount) || master.redeemItemCount <= 0 || !rules) return []
        return [...rules.values()].some(rule => rule.resetKind === 0) ? ["visible", "enter", "claim"] : ["visible", "enter"]
    }
    if (!mapping) return null
    const item = assets.getShopItemSync(Number(mapping[0]), row.id)
    if (!item || !validShopQuotaRules(item)) return []
    if (!Number.isSafeInteger(item.stock) || item.stock < 0 || !item.rewards.length
        || typeof item.availableFrom !== "string" || !Number.isFinite(Date.parse(item.availableFrom.replace(" ", "T") + "Z"))
        || (item.availableUntil !== null && (typeof item.availableUntil !== "string"
            || !Number.isFinite(Date.parse(item.availableUntil.replace(" ", "T") + "Z"))))
        || item.costs.some(cost => !Number.isSafeInteger(cost.id) || cost.id <= 0 || !Number.isSafeInteger(cost.amount) || cost.amount <= 0)
        || item.rewards.some(reward => ![0, 1, 2, 3, 4, 5].includes(reward.type))
        || (item.userCost && (![0, 1, 2].includes(item.userCost.type) || !Number.isSafeInteger(item.userCost.amount) || item.userCost.amount <= 0))) return []
    return ["visible", "exchange"]
}
