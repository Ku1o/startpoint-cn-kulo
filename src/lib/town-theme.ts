import path from "node:path"
import type { Database } from "better-sqlite3"
import { loadTownThemeCatalog, type TownThemeCatalog } from "./town-theme-catalog"
import { TownThemeStore, type TownPresentationSnapshot } from "./town-theme-store"

let catalog: TownThemeCatalog | undefined
const stores = new WeakMap<Database, TownThemeStore>()
/** Called once at route registration. First standalone load is also safe and bounded. */
export function townThemeCatalog(): TownThemeCatalog {
    return catalog ??= loadTownThemeCatalog(path.resolve(__dirname, "../../assets"))
}
export function townThemeStore(): TownThemeStore {
    const db = (require("../data/db") as typeof import("../data/db")).getDb()
    let store = stores.get(db)
    if (!store) { store = new TownThemeStore(db, townThemeCatalog()); stores.set(db, store) }
    return store
}
/** A bad optional presentation policy must never prevent a normal successful login. */
export function townThemeLoginSnapshot(nowMs = Date.now()): TownPresentationSnapshot {
    try { return townThemeStore().snapshot(nowMs) }
    catch { return { schema_version: 1, revision: 0, mode: "auto", theme_id: null, town_content_id: null, catalog_digest: townThemeCatalog().digest } }
}
