import type { Database } from "better-sqlite3"

export function initializeAbyssRecords(db: Database): void {
    // Public server history, deliberately not a cascading player relation.
    // viewer_id is an attribution snapshot, not a portable-save owner.
    db.exec(`CREATE TABLE IF NOT EXISTS abyss_floor_records (
        revision TEXT NOT NULL,
        quest_id INTEGER NOT NULL CHECK (quest_id BETWEEN 700099001 AND 700099098),
        elapsed_time_ms INTEGER NOT NULL CHECK (elapsed_time_ms > 0),
        viewer_id INTEGER NOT NULL,
        recorded_at_ms INTEGER NOT NULL,
        PRIMARY KEY (revision, quest_id)
    ) WITHOUT ROWID`)
}
