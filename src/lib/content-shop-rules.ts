import data from "../../assets/content_history_shop_rules.json"
import type { ShopItem } from "./types/shop"

export interface ContentNativeShopRule {
    parentKey: string
    native: {
        buy_max_count: number | null
        max_frequency: number | null
        daily_stock: number | null
        monthly_stock: number | null
        kind1_equipment_only_possession_one: boolean
    }
}
const rules = data as unknown as { schemaVersion: number; products: Record<string, ContentNativeShopRule> }
const validLimit = (value: unknown): value is number | null => value === null || (Number.isSafeInteger(value) && Number(value) >= 0)
export function getContentNativeShopRule(shopType: number, itemId: number | string): ContentNativeShopRule | null {
    if (shopType !== 4 || rules.schemaVersion !== 1) return null
    const rule = rules.products[`event_item_shop:${itemId}`], native = rule?.native
    return native && typeof rule.parentKey === "string" && Number.isSafeInteger(native.buy_max_count)
        && Number(native.buy_max_count) >= 0 && validLimit(native.max_frequency)
        && validLimit(native.daily_stock) && validLimit(native.monthly_stock)
        && typeof native.kind1_equipment_only_possession_one === "boolean" ? rule : null
}

/** Project reviewed native limits only; never mutate public masters or costs/rewards. */
export function applyContentNativeShopRules(shopType: number, itemId: number | string, item: ShopItem): ShopItem {
    if (shopType !== 4 || !rules.products[`event_item_shop:${itemId}`]) return item
    const rule = getContentNativeShopRule(shopType, itemId)
    if (!rule) return { ...item, stock: 0, nativeStockLimits: { perRequest: 0, lifetime: 0 } }
    const native = rule.native
    return { ...item, stock: native.max_frequency ?? 0,
        dailyStock: native.daily_stock ?? undefined, monthlyStock: native.monthly_stock ?? undefined,
        nativeStockLimits: { perRequest: native.buy_max_count, lifetime: native.max_frequency },
        kind1EquipmentOnlyPossessionOne: native.kind1_equipment_only_possession_one }
}
