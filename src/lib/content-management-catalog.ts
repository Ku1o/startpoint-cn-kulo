import { statSync } from "node:fs"
import path from "node:path"
import type { ContentCatalogRow, ContentOperationsStore } from "./content-operations-store"

const memberTypes = new Set(["general_shop", "treasure_shop", "star_grain_shop", "boss_coin_shop", "event_item_shop", "mission_regular", "mission_daily", "mission_event", "shop_product"])
export const isContentManagementMember = (type: string) => memberTypes.has(type) || type.startsWith("mission_")
type Source = { signature: string; presentationReader: unknown; historyReader: unknown }
type Presentation = { group: string; typeLabel: string }
type Option = Readonly<{ value: string; label: string }>
interface CatalogView<P extends Presentation> {
    readonly parentKeys: readonly string[]
    readonly parents: readonly ContentCatalogRow[]
    presentation(row: ContentCatalogRow): P
    typeOptions(group: unknown): readonly Option[]
}
type Entry = { catalog: unknown; rows: unknown; digest: string; source: Source; view: CatalogView<Presentation> }
const cache = new WeakMap<object, Entry>(), MAX_CACHED_PARENTS = 2048
const root = path.resolve(__dirname, "../..")
const sources = ["content_catalog.json", "content_presentation.json", "content_history_readiness_runtime.json",
    "content_history_readiness.json", "content_box_associations.json", "content_thumbnails/index.json", "asset-patch/manifest.json"]

/** Metadata identities only; no large file reads, permission/state or TTL cache. */
export function contentManagementCatalogSignature(assetsRoot = path.join(root, "assets")): string {
    return sources.map(relative => {
        try {
            const stat = statSync(path.join(assetsRoot, relative), { bigint: true })
            return `${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeNs}:${stat.ctimeNs}`
        } catch { return "missing:" + relative }
    }).join("|")
}

/** One bounded static view per store. A new source identity replaces the previous
 * view immediately; no revision/operational permission graph is kept here.
 */
export function contentManagementCatalog<P extends Presentation>(store: ContentOperationsStore, source: Source,
    describe: (row: ContentCatalogRow) => P): CatalogView<P> {
    const old = cache.get(store)
    if (old && old.catalog === store.catalog && old.rows === store.catalog.rows && old.digest === store.digest
        && old.source.signature === source.signature && old.source.presentationReader === source.presentationReader
        && old.source.historyReader === source.historyReader) return old.view as CatalogView<P>
    const parents = store.catalog.rows.filter(row => !isContentManagementMember(row.type))
    const descriptions = new Map<string, P>(), labels = new Map<string, Map<string, Set<string>>>()
    const add = (group: string, row: ContentCatalogRow, value: P) => {
        let types = labels.get(group)
        if (!types) { types = new Map(); labels.set(group, types) }
        let names = types.get(row.type)
        if (!names) { names = new Set(); types.set(row.type, names) }
        names.add(value.typeLabel)
    }
    for (const row of parents) {
        const value = Object.freeze(describe(row))
        descriptions.set(row.key, value)
        add("all", row, value); add(value.group, row, value)
    }
    const options = new Map([...labels].map(([group, types]) => [group,
        Object.freeze([...types].map(([value, names]) => Object.freeze({ value, label: [...names].join(" / ") })))]))
    const empty = Object.freeze([]) as readonly Option[]
    const view: CatalogView<P> = {
        parents: Object.freeze(parents), parentKeys: Object.freeze(parents.map(row => row.key)),
        presentation: row => descriptions.get(row.key) ?? describe(row),
        typeOptions: group => options.get(typeof group === "string" && group !== "all" ? group : "all") ?? empty,
    }
    if (parents.length <= MAX_CACHED_PARENTS) cache.set(store, {
        catalog: store.catalog, rows: store.catalog.rows, digest: store.digest, source: { ...source }, view,
    })
    else cache.delete(store)
    return view
}
