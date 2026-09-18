import type { Database } from "better-sqlite3"

/** Optional in older V1/V2 saves; no historical clears or reward flags are removed. */
export function initializeAbyssTowerProgress(database: Database): void {
    const columns = database.prepare("PRAGMA table_info(players_rush_events)").all() as { name: string }[]
    if (!columns.some(column => column.name === "tower_revision")) {
        database.exec("ALTER TABLE players_rush_events ADD COLUMN tower_revision TEXT")
    }
}
