import { ShopItem, ShopType } from "./types/shop"

// Keep the existing persisted keys: the two Fantasy shop screens share stock,
// while these GENERAL products must not consume STAR_GRAIN purchase history.
const GENERAL_EQUIPMENT_SCOPED_PURCHASE_KEYS = new Map([
    [100008, -8_100_008],
    [110005, -8_110_005],
    [110006, -8_110_006],
])
const MODE15_SHARED_EVENT_PURCHASE_KEYS = new Map(
    Array.from({ length: 14 }, (_, index) => [
        [9_700_201 + index, -9_702_001 - index],
        [9_700_301 + index, -9_702_001 - index],
    ] as const).flat(),
)

export function getShopPurchaseKey(shopType: number, shopItemId: number): number {
    if (shopType === ShopType.EVENT_ITEM) {
        return MODE15_SHARED_EVENT_PURCHASE_KEYS.get(shopItemId) ?? shopItemId
    }
    if (shopType === ShopType.GENERAL) {
        return GENERAL_EQUIPMENT_SCOPED_PURCHASE_KEYS.get(shopItemId) ?? shopItemId
    }
    return shopItemId
}

export function isShopItemAvailable(item: ShopItem, now: Date): boolean {
    const periods = [{ availableFrom: item.availableFrom, availableUntil: item.availableUntil },
        ...(item.compatibilityPeriods ?? [])]
    return periods.some(period => {
        if (period.availableFrom && new Date(period.availableFrom.replace(' ', 'T') + 'Z') > now) return false
        if (period.availableUntil && new Date(period.availableUntil.replace(' ', 'T') + 'Z') < now) return false
        return true
    })
}

export function getClientTotalPurchaseNum(
    shopType: number, itemId: number, purchased: number, stock: number | undefined,
): number {
    // Preserve the legacy item-5000 client limit workaround used by the shop.
    if (shopType === ShopType.EVENT_ITEM && itemId === 5000 && stock !== undefined && stock > 2) {
        return purchased - (stock - 2)
    }
    return purchased
}

export function buildShopSalesEntry(
    shopType: number, itemId: number, item: ShopItem,
    purchasedMap: Record<number, number>, degreeOwned = false,
) {
    const purchased = purchasedMap[getShopPurchaseKey(shopType, itemId)] ?? 0
    const stockQuantity = degreeOwned ? 0
        : (item.stock !== undefined ? Math.max(0, item.stock - purchased) : -1)
    return {
        shop_item_id: itemId,
        stock_quantity: stockQuantity,
        today_purchase_num: purchased,
        this_month_purchase_num: purchased,
        total_purchase_num: getClientTotalPurchaseNum(shopType, itemId, purchased, item.stock),
        group_info: {
            group_total_stock_quantity: stockQuantity,
            group_total_purchase_num: purchased,
            multi_stage: false,
        },
        shop_type: shopType,
    }
}
