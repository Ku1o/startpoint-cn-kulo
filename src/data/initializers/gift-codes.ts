import type { Database } from "better-sqlite3"

export function initializeGiftCodes(db: Database): void {
    // Codes and their rewards belong to this server, never to portable saves.
    // Codes are immutable and never deleted/reused; redemptions use the existing
    // target-local player_operation_receipts ledger.
    db.exec(`CREATE TABLE IF NOT EXISTS server_gift_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        note TEXT NOT NULL,
        rewards_json TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
        revision INTEGER NOT NULL DEFAULT 1,
        created_at INTEGER NOT NULL
    )`)
}
