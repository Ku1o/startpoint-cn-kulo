import shopRules from "../../assets/content_history_shop_rules.json"
import questRules from "../../assets/content_history_quest_rules.json"
import { isShopItemAvailable } from "./shop-sales"

const parentKey = "challenge_dungeon_event:1"
const shops = shopRules as unknown as { products: Record<string, { parentKey: string; source: { raw: string[] } }> }
const quests = questRules as unknown as { quests: Record<string, { nativeEligibility?: { start_time?: string } }> }
// These are the seven native three-difficulty beast periods, also enforced by
// nativePresentationScopeError. Match products by native dates, never ID aliases.
const periods = Array.from({ length: 7 }, (_, index) => ({
    firstQuest: 1020 + index * 3,
    start: quests.quests[`13:${1020 + index * 3}`]?.nativeEligibility?.start_time,
}))
const productPeriods = new Map<number, { period: number; from: string; until: string | null }>()
for (const [key, rule] of Object.entries(shops.products)) {
    if (rule.parentKey !== parentKey) continue
    const from = rule.source.raw[26], until = rule.source.raw[27]
    const period = periods.reduce((previous, candidate, index) =>
        candidate.start !== undefined && from >= candidate.start ? index : previous, -1)
    if (period < 0 || (period < 6 && from !== periods[period].start)) continue
    productPeriods.set(Number(key.slice("event_item_shop:".length)), { period, from, until: until === "(None)" ? null : until })
}

/** A reopened historical period keeps its original IDs and purchase ledger.
 * The permanent final period still has mutually exclusive monthly sale rows. */
export function challengeShopPeriodAllows(itemId: number, shownQuestKeys: readonly string[] | null | undefined, now: Date): boolean {
    if (!Array.isArray(shownQuestKeys)) return false
    const selected = periods.flatMap((period, index) => shownQuestKeys.some(key =>
        [0, 1, 2].some(offset => key === `13:${period.firstQuest + offset}`)) ? [index] : [])
    if (selected.length !== 1) return false
    const product = productPeriods.get(itemId)
    if (!product || product.period !== selected[0]) return false
    return product.period < 6 || isShopItemAvailable({ costs: [], rewards: [], stock: 0,
        availableFrom: product.from, availableUntil: product.until }, now)
}
