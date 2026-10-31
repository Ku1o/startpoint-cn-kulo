import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import path from "node:path"
import type { ContentCatalog } from "./content-operations-store"
import { readContentResourceSourceSync } from "./content-resource-source"

/** Compute once from the same JSON modules used by gameplay; no generated index
 * or separate source anchor is needed. Original keys, digest algorithm and order stay compatible.
 */
export function loadContentNativeIdentities(options: { root?: string; catalog?: ContentCatalog } = {}): {
    quests: Map<string, string>; shops: Map<string, string>
} {
    const resourceRoot = path.resolve(options.root ?? path.resolve(__dirname, "../.."))
    const contentCatalog: ContentCatalog = options.catalog ?? require(path.join(resourceRoot, "assets/content_catalog.json"))
    // This is required business provenance, including for non-native gacha controls.
    // Verify before the optional per-table identity branches can return closed maps.
    const resourceSource = readContentResourceSourceSync(resourceRoot)
    let nativeQuestIdentities: Map<string, string> | undefined = undefined
    function nativeQuestIdentity(key: string): string | undefined {
        if (!nativeQuestIdentities) {
            nativeQuestIdentities = new Map()
            try {
                const root = resourceRoot
                const rules = require(path.join(root, "assets/content_history_quest_rules.json"))
                const catalogSha256 = createHash("sha256").update(readFileSync(path.join(root, "assets/content_catalog.json"))).digest("hex")
                const { manifestSha256 } = resourceSource
                if (rules.schemaVersion !== 1 || rules.source?.manifestSha256 !== manifestSha256
                    || rules.source?.catalogSha256 !== catalogSha256 || !rules.quests) return undefined
                const adapter = createHash("sha256").update(readFileSync(path.join(root, "src/lib/content-quest-rules.ts"))).digest("hex")
                const assetsLoader = createHash("sha256").update(readFileSync(path.join(root, "src/lib/assets.ts"))).digest("hex")
                const staminaLoader = createHash("sha256").update(readFileSync(path.join(root, "src/lib/stamina-cost.ts"))).digest("hex")
                const groups = new Map<string, Array<[string, unknown]>>()
                for (const questKey of Object.keys(rules.quests).sort()) {
                    const rule = rules.quests[questKey]
                    if (!rule || typeof rule.parentKey !== "string") throw new Error("Invalid native quest owner")
                    if (!groups.has(rule.parentKey)) groups.set(rule.parentKey, [])
                    groups.get(rule.parentKey)!.push([questKey, rule])
                }
                for (const [parent, quests] of groups) nativeQuestIdentities.set(parent,
                    createHash("sha256").update(JSON.stringify({ adapter, assetsLoader, staminaLoader, manifestSha256, quests })).digest("hex"))
            } catch { nativeQuestIdentities.clear() }
        }
        return nativeQuestIdentities.get(key)
    }
    let nativeShopIdentities: Map<string, string> | undefined = undefined
    function nativeShopIdentity(key: string): string | undefined {
        if (!nativeShopIdentities) {
            nativeShopIdentities = new Map()
            try {
                const root = resourceRoot
                const rules = require(path.join(root, "assets/content_history_shop_rules.json"))
                const catalogSha256 = createHash("sha256").update(readFileSync(path.join(root, "assets/content_catalog.json"))).digest("hex")
                const { manifestSha256 } = resourceSource
                const members = contentCatalog.rows.filter(row => row.type === "event_item_shop" && row.parentKey)
                if (rules.schemaVersion !== 1 || rules.source?.catalogSha256 !== catalogSha256
                    || rules.source?.manifestSha256 !== manifestSha256 || !rules.products
                    || Object.keys(rules.products).sort().join() !== members.map(row => row.key).sort().join()) return undefined
                const code = ["src/lib/content-shop-rules.ts", "src/lib/assets.ts", "src/lib/shop-quota.ts", "src/lib/types/shop.ts"]
                    .map(source => [source, createHash("sha256").update(readFileSync(path.join(root, source))).digest("hex")])
                const groups = new Map<string, Array<[string, unknown]>>()
                const invalidParents = new Set<string>()
                for (const row of members.sort((a, b) => a.key.localeCompare(b.key))) {
                    const rule = rules.products[row.key], native = rule?.native
                    if (!native || rule.parentKey !== row.parentKey || !Number.isSafeInteger(native.buy_max_count)
                        || native.buy_max_count < 0 || typeof native.kind1_equipment_only_possession_one !== "boolean"
                        || [native.max_frequency, native.daily_stock, native.monthly_stock].some(value =>
                            value !== null && (!Number.isSafeInteger(value) || value < 0))) {
                        invalidParents.add(row.parentKey!); continue
                    }
                    nativeShopIdentities.set(row.key, createHash("sha256")
                        .update(JSON.stringify({ code, manifestSha256, rule })).digest("hex"))
                    if (!groups.has(row.parentKey!)) groups.set(row.parentKey!, [])
                    groups.get(row.parentKey!)!.push([row.key, rule])
                }
                for (const [parent, products] of groups) if (!invalidParents.has(parent))
                    nativeShopIdentities.set(parent, createHash("sha256")
                        .update(JSON.stringify({ code, manifestSha256, products })).digest("hex"))
            } catch { nativeShopIdentities.clear() }
        }
        return nativeShopIdentities.get(key)
    }
    nativeQuestIdentity(""); nativeShopIdentity("")
    return { quests: nativeQuestIdentities!, shops: nativeShopIdentities! }
}
