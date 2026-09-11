import { getGenericShopItemsSync } from "./assets"
import { serverEventShops } from "./content-master"
import { ShopType, ShopItems } from "./types/shop"
import { ShopItemRewardType, EquipmentItemShopItemReward } from "./types/rewards"
import { BoxGachaRewardType } from "./types/box-gacha"
import bossCoinShopItems from "../../assets/boss_coin_shop.json"
import boxRewardData from "../../assets/box_reward.json"
import generalShopWhitelist from "../../assets/cdn_general_shop_whitelist.json"

interface ShopSource { shopType: ShopType; shopItemId: number }
interface SourceIndex {
    shops: Map<string, ShopSource[]>
    boxes: Map<string, number[]>
}

let sourceIndex: SourceIndex | undefined

function getIndex(): SourceIndex {
    if (sourceIndex) return sourceIndex
    const shops = new Map<string, ShopSource[]>()
    const boxes = new Map<string, number[]>()
    const generalKeys = new Set(generalShopWhitelist)
    const append = (shopType: ShopType, items: ShopItems) => {
        for (const [rawId, item] of Object.entries(items)) {
            const shopItemId = Number(rawId)
            if (shopType === ShopType.GENERAL && !generalKeys.has(shopItemId)) continue
            for (const reward of item.rewards) {
                if (![ShopItemRewardType.ITEM, ShopItemRewardType.EQUIPMENT].includes(reward.type)) continue
                const key = `${reward.type}:${(reward as EquipmentItemShopItemReward).id}`
                const list = shops.get(key) ?? []
                if (!list.some(x => x.shopType === shopType && x.shopItemId === shopItemId)) {
                    list.push({ shopType, shopItemId })
                    shops.set(key, list)
                }
            }
        }
    }
    for (const type of [ShopType.GENERAL, ShopType.STAR_GRAIN, ShopType.TREASURE]) {
        append(type, getGenericShopItemsSync(type) ?? {})
    }
    for (const events of Object.values(serverEventShops)) {
        for (const items of Object.values(events)) append(ShopType.EVENT_ITEM, items as ShopItems)
    }
    for (const items of Object.values(bossCoinShopItems)) append(ShopType.BOSS_COIN, items as ShopItems)
    for (const [boxId, stages] of Object.entries(boxRewardData)) {
        for (const stage of Object.values(stages)) {
            for (const reward of Object.values(stage) as { type: number; id?: number }[]) {
                const type = reward.type === BoxGachaRewardType.ITEM ? ShopItemRewardType.ITEM
                    : reward.type === BoxGachaRewardType.EQUIPMENT ? ShopItemRewardType.EQUIPMENT : null
                if (type === null || reward.id === undefined) continue
                const key = `${type}:${reward.id}`
                const list = boxes.get(key) ?? []
                if (!list.includes(Number(boxId))) list.push(Number(boxId))
                boxes.set(key, list)
            }
        }
    }
    // Imported shop masters are immutable for the process lifetime. Only cache
    // source IDs; availability, quantities and player state are resolved per call.
    return sourceIndex = { shops, boxes }
}

export function getHowToGetSources(equipment: boolean, id: number) {
    const index = getIndex()
    const key = `${equipment ? ShopItemRewardType.EQUIPMENT : ShopItemRewardType.ITEM}:${id}`
    return { shops: index.shops.get(key) ?? [], boxes: index.boxes.get(key) ?? [] }
}
