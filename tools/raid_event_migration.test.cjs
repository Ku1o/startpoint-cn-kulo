require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const sqlite3 = require("better-sqlite3")
const { updateAfterInit } = require("../src/data/updaters/wdfpData")

const db = new sqlite3(":memory:")
db.pragma("foreign_keys = OFF")
db.exec(`
    CREATE TABLE players (id INTEGER PRIMARY KEY);
    CREATE TABLE raid_event_global_kill_ledger (
        event_id INTEGER NOT NULL,
        play_id TEXT NOT NULL,
        player_id INTEGER NOT NULL,
        quest_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (event_id, play_id),
        FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE
    );
    CREATE INDEX idx_raid_event_global_kill_ledger_event_quest
        ON raid_event_global_kill_ledger (event_id, quest_id);
    INSERT INTO players (id) VALUES (1);
    INSERT INTO raid_event_global_kill_ledger
        (event_id, play_id, player_id, quest_id, created_at)
        VALUES (7, 'migration-play', 1, 7002, 123);
`)

updateAfterInit(db, 8)

assert.equal(db.pragma("foreign_key_list(raid_event_global_kill_ledger)").length, 0)
assert.deepEqual(
    db.prepare(`SELECT event_id, play_id, player_id, quest_id, created_at
        FROM raid_event_global_kill_ledger`).get(),
    {
        event_id: 7,
        play_id: "migration-play",
        player_id: 1,
        quest_id: 7002,
        created_at: 123,
    },
)
assert.equal(
    db.prepare(`SELECT COUNT(*) AS count FROM sqlite_master
        WHERE type = 'index' AND name = 'idx_raid_event_global_kill_ledger_event_quest'`
    ).get().count,
    1,
)

db.close()
console.log("raid event migration tests passed")
