import catalogData from "../../assets/content_catalog.json"
import { loadContentHistoryDefinitionRuntime } from "./content-history-definition-runtime"
import { loadContentNativeIdentities } from "./content-native-identities-runtime"
import { getDb } from "../data/db"
import { serverGachas } from "./content-master"
import { ContentAction, ContentCatalog, ContentCatalogRow, ContentOperationsStore, initializeContentOperationsSchema } from "./content-operations-store"
import type { Database } from "better-sqlite3"
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import path from "node:path"
import { contentEconomyCapabilities } from "./content-economy-operations"
import { getMultiSpecialExchangeCampaignDefinition } from "./multi-special-exchange"
import { defaultContentDecision, unknownContentDecision, unknownQuestContentDecision, unknownMissionContentDecision } from "./content-operations-defaults"
import { matchCampaignDefinition, matchExactDefinition, type ExactDefinitionEvidence, type CurrentParentDefinitionEvidence,
    type ExactDefinitionRow } from "./content-definition-evidence"
import { getContentBoxAssociation, getContentBoxAssociations, isContentBoxAssociationIndexAvailable } from "./content-box-associations"

export const contentCatalog = catalogData as ContentCatalog
const stores = new WeakMap<Database, ContentOperationsStore>()
const questParents = new Set(Object.values(contentCatalog.questMap))
const nativeShopOwners = new Set(contentCatalog.rows.filter(row => row.type === "event_item_shop" && row.parentKey)
    .flatMap(row => [row.key, row.parentKey!]))
const shopParents = new Set(contentCatalog.rows.flatMap(row => row.parentKey ? [row.parentKey] : []))
const missionParents = new Map(Object.entries(contentCatalog.missionMap ?? {}))
for (const row of contentCatalog.rows) for (const member of row.missionKeys ?? []) missionParents.set(member, row.key)
const capturedSources = new Map<string, string | null>()
const historicalEvidence = loadContentHistoryDefinitionRuntime()
const precomputedNativeIdentities = loadContentNativeIdentities()
let historicalCatalogMatches: boolean | undefined
function historicalCatalogIsCurrent(): boolean {
    if (historicalCatalogMatches === undefined) {
        try {
            historicalCatalogMatches = historicalEvidence.schemaVersion === 1
                && historicalEvidence.source.catalogSha256 === createHash("sha256")
                    .update(readFileSync(path.resolve(__dirname, "../../assets/content_catalog.json"))).digest("hex")
        } catch { historicalCatalogMatches = false }
    }
    return historicalCatalogMatches
}
function canonicalEvidence(value: unknown): string {
    if (Array.isArray(value)) return `[${value.map(canonicalEvidence).join(",")}]`
    if (value && typeof value === "object") return `{${Object.keys(value).sort()
        .map(key => `${JSON.stringify(key)}:${canonicalEvidence((value as Record<string, unknown>)[key])}`).join(",")}}`
    return JSON.stringify(value)
}
function reviewedExistingLoaderRebind(row: ContentCatalogRow): { digest: string; matchesCatalog: boolean } | null {
    if (!historicalCatalogIsCurrent()) return null
    const candidate = historicalEvidence.existingEvidenceRebind?.[row.key]
    if (!candidate || candidate.status !== "candidate_requires_reviewed_loader_transition"
        || candidate.nativeRowMatchesCatalog !== true || candidate.dependencyDigestUnchanged !== true) return null
    const field = candidate.kind === "exact" ? "exactDefinitionEvidence" : candidate.kind === "currentParent" ? "currentParentDefinitionEvidence" : null
    const previous = field && (row as ExactDefinitionRow)[field]
    if (!previous || canonicalEvidence(previous) !== canonicalEvidence(candidate.previousEvidence)) return null
    const { loaders: oldLoaders, ...oldProof } = previous
    const { loaders: nextLoaders, ...nextProof } = candidate.evidence
    if (canonicalEvidence(oldProof) !== canonicalEvidence(nextProof)) return null
    // This one loader transition is reviewed against the real native getter
    // matrix and HTTP settlement/quota cases. All original semantic dependency
    // digests and the 18-reviewed/9-excluded parent scopes remain unchanged.
    const originalLoaders = ["src/lib/assets.ts", "src/lib/content-master.ts", "src/lib/shop-sales.ts", "src/lib/multi-special-exchange.ts"]
    if (Object.keys(oldLoaders).sort().join() !== [...originalLoaders].sort().join()
        || Object.keys(nextLoaders).sort().join() !== [...originalLoaders, "src/lib/content-quest-rules.ts", "src/lib/content-shop-rules.ts"].sort().join()
        || oldLoaders["src/lib/assets.ts"] !== "c106054a9be76b83f0bfb94829059c6318ff8365c31d3dff12ce012fa619945d"
        || nextLoaders["src/lib/assets.ts"] !== "62261d5109f8da542fd007c7720e0611e88766fc2c0d35a03b6cbb4512a85150"
        || nextLoaders["src/lib/content-quest-rules.ts"] !== "99fae075b418ade8b9bc7ffaf86541a4e5d9bc18835f8dbcc3b0c323853c436f"
        || nextLoaders["src/lib/content-shop-rules.ts"] !== "571a3e897d165bbe25a92e9be1979e1ed0ce63e20eb9e9c6f2058aec479890a2"
        || originalLoaders.slice(1).some(source => oldLoaders[source] !== nextLoaders[source])) return null
    return matchExactDefinition({ ...row, [field!]: candidate.evidence }, path.resolve(__dirname, "../.."))
}
let nativeQuestIdentities: Map<string, string> | undefined = precomputedNativeIdentities.quests
function nativeQuestIdentity(key: string): string | undefined {
    if (!nativeQuestIdentities) {
        nativeQuestIdentities = new Map()
        try {
            const root = path.resolve(__dirname, "../..")
            const rules = JSON.parse(readFileSync(path.join(root, "assets/content_history_quest_rules.json"), "utf8"))
            const catalogSha256 = createHash("sha256").update(readFileSync(path.join(root, "assets/content_catalog.json"))).digest("hex")
            const manifestSha256 = createHash("sha256").update(readFileSync(path.join(root, "assets/asset-patch/manifest.json"))).digest("hex")
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
let nativeShopIdentities: Map<string, string> | undefined = precomputedNativeIdentities.shops
function nativeShopIdentity(key: string): string | undefined {
    if (!nativeShopIdentities) {
        nativeShopIdentities = new Map()
        try {
            const root = path.resolve(__dirname, "../..")
            const rules = JSON.parse(readFileSync(path.join(root, "assets/content_history_shop_rules.json"), "utf8"))
            const catalogSha256 = createHash("sha256").update(readFileSync(path.join(root, "assets/content_catalog.json"))).digest("hex")
            const manifestSha256 = createHash("sha256").update(readFileSync(path.join(root, "assets/asset-patch/manifest.json"))).digest("hex")
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
function runtimeDefinition(row: ContentCatalogRow): { digest: string; matchesCatalog: boolean } {
    const base = baseRuntimeDefinition(row)
    const questRequired = questParents.has(row.key), shopRequired = nativeShopOwners.has(row.key)
    if (!questRequired && !shopRequired) return base
    const native = questRequired ? nativeQuestIdentity(row.key) : undefined
    const shop = shopRequired ? nativeShopIdentity(row.key) : undefined
    return { digest: createHash("sha256").update(JSON.stringify({ base: base.digest, native: native ?? null, shop: shop ?? null })).digest("hex"),
        matchesCatalog: base.matchesCatalog && (!questRequired || native !== undefined) && (!shopRequired || shop !== undefined) }
}
function baseRuntimeDefinition(row: ContentCatalogRow): { digest: string; matchesCatalog: boolean } {
    const campaign = matchCampaignDefinition(row, path.resolve(__dirname, "../.."))
    if (campaign) return campaign
    const exact = matchExactDefinition(row, path.resolve(__dirname, "../.."))
    if (exact) return exact.matchesCatalog ? exact : reviewedExistingLoaderRebind(row) ?? exact
    const sources = row.definitionEvidence?.serverSources ?? []
    const identities = sources.map(source => {
        if (!capturedSources.has(source)) {
            let digest: string | null = null
            // Public definition sources only. Campaign ticket rules have no server master table.
            if ((/^assets\/[a-zA-Z0-9_/-]+\.json$/.test(source) && !source.split("/").includes(".."))
                || source === "src/lib/multi-special-exchange.ts") {
                try { digest = createHash("sha256").update(readFileSync(path.resolve(__dirname, "../..", source))).digest("hex") }
                catch { digest = null }
            }
            capturedSources.set(source, digest)
        }
        return [source, capturedSources.get(source)] as const
    })
    const original = { digest: createHash("sha256").update(JSON.stringify(identities)).digest("hex"),
        matchesCatalog: sources.length > 0 && !!row.serverDefinitionDigest && !!row.definitionEvidence
            && identities.every(([source, digest]) => !!digest && digest === contentCatalog.serverResources?.[source]?.sha256) }
    // Keep every working whole-table identity unchanged. A historical product
    // may instead have a separately reviewed native/server dependency receipt;
    // the existing exact matcher still checks its current data and loader hashes.
    if (original.matchesCatalog || !historicalEvidence.rows[row.key]) return original
    return historicalCatalogIsCurrent()
        ? matchExactDefinition({ ...row, exactDefinitionEvidence: historicalEvidence.rows[row.key] }, path.resolve(__dirname, "../..")) ?? original
        : original
}
const capabilityCache = new WeakMap<ContentCatalogRow, readonly ContentAction[]>()
export function contentCapabilities(row: ContentCatalogRow): readonly ContentAction[] {
    let result = capabilityCache.get(row)
    if (!result) { result = evaluateCapabilities(row); capabilityCache.set(row, result) }
    return result
}
function evaluateCapabilities(row: ContentCatalogRow): readonly ContentAction[] {
    // Advertise only guards implemented in final business write paths. Definition matching is not playable acceptance.
    if (row.type === "gacha" && !row.personalWindow && String(row.id) in serverGachas)
        return ["visible", "enter", ...(row.id === 100 ? ["claim" as const] : []), "exchange"]
    if (row.type === "gacha" && row.personalWindow && String(row.id) in serverGachas) return ["exchange"]
    const economy = contentEconomyCapabilities(row)
    if (economy !== null) return economy
    if (row.type === "multi_special_exchange_campaign") return getMultiSpecialExchangeCampaignDefinition(row.id) ? ["visible", "enter", "exchange"] : []
    if (questParents.has(row.key)) return ["visible", "enter", ...(row.type === "rush_event" ? ["claim" as const] : []),
        ...(shopParents.has(row.key) || getContentBoxAssociation(row.key)?.relationshipMatches ? ["exchange" as const] : [])]
    if (["active_mission_event", "collect_item_event", "mission_regular", "mission_daily", "mission_event"].includes(row.type)) return ["visible", "enter", "claim", ...(shopParents.has(row.key) ? ["exchange" as const] : [])]
    return []
}
const eventEntryKinds: Record<string, string> = {
    daily_week_event: "DailyWeekEvent", advent_event: "AdventEvent", story_event: "StoryEvent", ranking_event: "RankingEvent",
    challenge_dungeon_event: "ChallengeDungeonEvent", daily_exp_mana_event: "DailyExpManaEvent", world_story_event: "WorldStoryEvent",
    tower_dungeon_event: "TowerDungeonEvent", expert_single_event: "ExpertSingleEvent", carnival_event: "CarnivalEvent", raid_event: "RaidEvent",
    rush_event: "RushEvent", solo_time_attack_event: "SoloTimeAttackEvent", hard_multi_event: "HardMultiEvent", score_attack_event: "ScoreAttackEvent",
}
function clientEntry(row: ContentCatalogRow): { kind: string; id: number } | null {
    const kind = row.type === "gacha" ? "gacha" : eventEntryKinds[row.type]
    return kind ? { kind, id: row.id } : null
}
/** Android method grafts are an offline candidate; iOS is not integrated and device acceptance is separate. */
export function contentClientCapabilities(row: ContentCatalogRow): readonly ContentAction[] {
    let actions: readonly ContentAction[] = []
    if (row.type === "gacha") actions = ["visible", "enter", ...(row.id === 100 ? ["claim" as const] : []), "exchange"]
    else if (eventEntryKinds[row.type] || ["active_mission_event", "pass_card_event", "box_gacha", "mission_regular", "mission_daily", "mission_event"].includes(row.type))
        actions = ["visible", "enter", ...(shopParents.has(row.key) || getContentBoxAssociation(row.key)?.parentKey === row.key
            && getContentBoxAssociation(row.key)?.relationshipMatches ? ["exchange" as const] : [])]
    else if (row.type === "collect_item_event") actions = ["visible", "enter", "exchange"]
    else if (["general_shop", "treasure_shop", "star_grain_shop", "boss_coin_shop", "event_item_shop", "multi_special_exchange_campaign"].includes(row.type)) actions = ["visible", "exchange"]
    else if (["special_exchange_campaign", "start_dash_exchange_campaign"].includes(row.type)) actions = ["exchange"]
    return actions.filter(action => contentCapabilities(row).includes(action))
}
export function contentOperations(): ContentOperationsStore {
    const db = getDb()
    let store = stores.get(db)
    if (!store) {
        initializeContentOperationsSchema(db)
        store = createContentOperationsStore(db)
        stores.set(db, store)
    }
    return store
}
/** Explicit offline callers supply their own connection; this never opens or initializes a database. */
export function createContentOperationsStore(db: Database): ContentOperationsStore {
    return new ContentOperationsStore(db, contentCatalog, contentCapabilities, runtimeDefinition, clientEntry, contentClientCapabilities,
        { android: "offline_candidate", ios: "not_integrated" }, defaultContentDecision, {
            associations: getContentBoxAssociations(), available: isContentBoxAssociationIndexAvailable(),
            // A missing/damaged index must not silently turn a known box owner
            // into an independent event. These native families have no shop
            // children exactly when their content is served by the box route.
            requiredKeys: contentCatalog.rows.filter(row => row.type === "box_gacha" || row.type === "raid_event"
                || row.type === "world_story_event" && !nativeShopOwners.has(row.key)).map(row => row.key),
        })
}
export function contentDecision(type: string, id: number, action: ContentAction, nowMs: number): boolean | null {
    // The first business request must apply the same defaults as later snapshots.
    // Store creation initializes only global control tables; an absent table grants no seasonal access.
    const store = contentOperations()
    if (!store.rows.has(`${type}:${id}`)) return unknownContentDecision(type, action)
    const result = store.allowed(`${type}:${id}`, action, nowMs)
    if (result === null && type === "pass_card_event" && (action === "visible" || action === "enter")) {
        const managed = store.activeManagedPass(nowMs)
        if (managed && managed !== `${type}:${id}`) return false
    }
    return result
}
export function contentQuestDecision(category: number, questId: number, realNowMs = Date.now()): boolean | null {
    const key = contentCatalog.questMap[`${category}:${questId}`]
    if (!key) return unknownQuestContentDecision(category, questId)
    return contentOperations().scopedAllowed(key, "quest", `${category}:${questId}`, "enter", realNowMs)
}
export function isContentQuestOpenAt(category: number, questId: number, realNowMs = Date.now()): boolean {
    return contentQuestDecision(category, questId, realNowMs) ?? true
}
export function contentMissionDecision(category: number, missionId: number, action: ContentAction, realNowMs = Date.now()): boolean | null {
    const member = `${category}:${missionId}`
    const key = missionParents.get(member)
    if (!key) {
        const definition = category === 1 || category === 2
            ? (require("./mission/master-data") as typeof import("./mission/master-data")).getMissionMasterDefinition(category, missionId)
            : undefined
        return unknownMissionContentDecision(category, definition?.enableEnd)
    }
    const scoped = contentOperations().scopedAllowed(key, "mission", member, action, realNowMs)
    if (scoped !== null) return scoped
    const row = contentOperations().rows.get(key)!
    return contentDecision(row.type, row.id, action, realNowMs)
}
