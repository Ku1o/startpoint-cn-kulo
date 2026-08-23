require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const { execFileSync } = require("node:child_process")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const sqlite3 = require("better-sqlite3")

const databaseDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "raid-event-reset-db-"))
const previousDataDirectory = process.env.DATA_DIR
process.env.DATA_DIR = databaseDirectory
let db

function cleanup() {
    if (db?.open) db.close()
    fs.rmSync(databaseDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
}

process.once("exit", cleanup)

const { initializeDatabase } = require("../src/data")
const { getDb } = require("../src/data/db")
const { insertAccountSync } = require("../src/data/domains/account")
const {
    getDefaultPlayerPartyGroupsSync,
    insertDefaultPlayerSync,
} = require("../src/data/domains/player")
const { insertPlayerPartyGroupListSync } = require("../src/data/domains/party")
const { PartyCategory } = require("../src/data/types")
const {
    previewRaidEventResetSync,
    resetRaidEventSync,
} = require("../src/lib/raid-event-reset")

initializeDatabase()
db = getDb()

function makePlayer(label) {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `${label}-${randomUUID()}`,
        status: "normal",
    })
    return insertDefaultPlayerSync(account.id).id
}

const player1 = makePlayer("raid-reset-1")
const player2 = makePlayer("raid-reset-2")
insertPlayerPartyGroupListSync(
    player1,
    getDefaultPlayerPartyGroupsSync(PartyCategory.RAID),
)
const raidPartyCountBefore = db.prepare(`
    SELECT COUNT(*) AS count FROM players_parties
    WHERE player_id = ? AND category = ?
`).get(player1, PartyCategory.RAID).count
const itemBefore = db.prepare(`
    SELECT amount FROM players_items WHERE player_id = ? AND id = 100000
`).get(player1)?.amount ?? 0

db.transaction(() => {
    db.prepare(`INSERT INTO raid_event_global_state
        (event_id, total_kill_count, weighted_kill_count, calculation_version, updated_at)
        VALUES (7, 12, 345, 4, 1)`).run()
    db.prepare(`INSERT INTO raid_event_global_kill_ledger
        (event_id, play_id, player_id, quest_id, created_at)
        VALUES (7, 'reset-test-play', ?, 7001, 1)`).run(player1)
    db.prepare(`INSERT INTO players_raid_event_overall_rewards
        (player_id, event_id, received_up_to, updated_at)
        VALUES (?, 7, 10, 1)`).run(player1)
    db.prepare(`INSERT INTO players_quest_progress
        (section, quest_id, finished, player_id)
        VALUES (23, 7001, 1, ?), (23, 8001, 1, ?), (22, 7001, 1, ?)`
    ).run(player1, player1, player1)
    db.prepare(`INSERT INTO players_drawn_quests
        (category_id, quest_id, odds_id, player_id)
        VALUES (23, 7001, 5, ?), (23, 8001, 5, ?)`
    ).run(player1, player1)
    db.prepare(`INSERT INTO players_category_missions
        (category, id, progress, player_id)
        VALUES (3, 400093, 1, ?), (3, 400092, 1, ?)`
    ).run(player1, player1)
    db.prepare(`INSERT INTO players_category_mission_stages
        (category, id, status, player_id, mission_id)
        VALUES (3, 1, 1, ?, 400093), (3, 1, 1, ?, 400092)`
    ).run(player1, player1)
    db.prepare(`INSERT INTO players_rush_events
        (player_id, event_id) VALUES (?, 7), (?, 8)`
    ).run(player1, player1)
    db.prepare(`INSERT INTO players_rush_events_cleared_folders
        (player_id, event_id, folder_id) VALUES (?, 7, 1), (?, 8, 1)`
    ).run(player1, player1)
    db.prepare(`INSERT INTO players_rush_events_played_parties
        (player_id, event_id, round, battle_type) VALUES (?, 7, 7001, 1), (?, 8, 8001, 1)`
    ).run(player1, player1)
    db.prepare(`INSERT INTO players_active_quests
        (player_id, play_id, quest_id, category, event_id)
        VALUES (?, 'raid-active', 7001, 23, 7), (?, 'other-active', 8001, 23, 8)`
    ).run(player1, player2)
})()

assert.deepEqual(previewRaidEventResetSync(db, 7), {
    globalState: 1,
    globalKillLedger: 1,
    overallRewardReceipts: 1,
    questProgress: 1,
    drawnQuests: 1,
    eventMissions: 1,
    eventMissionStages: 1,
    rushCompatibilityState: 1,
    rushClearedFolders: 1,
    rushPlayedParties: 1,
    activeQuests: 1,
})
assert.deepEqual(resetRaidEventSync(db, 7), {
    globalState: 1,
    globalKillLedger: 1,
    overallRewardReceipts: 1,
    questProgress: 1,
    drawnQuests: 1,
    eventMissions: 1,
    eventMissionStages: 1,
    rushCompatibilityState: 1,
    rushClearedFolders: 1,
    rushPlayedParties: 1,
    activeQuests: 1,
})
assert.deepEqual(previewRaidEventResetSync(db, 7), {
    globalState: 0,
    globalKillLedger: 0,
    overallRewardReceipts: 0,
    questProgress: 0,
    drawnQuests: 0,
    eventMissions: 0,
    eventMissionStages: 0,
    rushCompatibilityState: 0,
    rushClearedFolders: 0,
    rushPlayedParties: 0,
    activeQuests: 0,
})

assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_quest_progress
    WHERE player_id = ? AND ((section = 23 AND quest_id = 8001) OR (section = 22 AND quest_id = 7001))`
).get(player1).count, 2)
assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_rush_events
    WHERE player_id = ? AND event_id = 8`).get(player1).count, 1)
assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_category_missions
    WHERE player_id = ? AND category = 3 AND id = 400092`).get(player1).count, 1)
assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_category_mission_stages
    WHERE player_id = ? AND category = 3 AND mission_id = 400092`).get(player1).count, 1)
assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_active_quests
    WHERE player_id = ? AND event_id = 8`).get(player2).count, 1)
assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_parties
    WHERE player_id = ? AND category = ?`).get(player1, PartyCategory.RAID).count, raidPartyCountBefore)
assert.equal(db.prepare(`SELECT amount FROM players_items
    WHERE player_id = ? AND id = 100000`).get(player1)?.amount ?? 0, itemBefore)

// Exercise the standalone maintenance command, including its automatic backup.
db.prepare(`INSERT INTO raid_event_global_state
    (event_id, total_kill_count, weighted_kill_count, calculation_version, updated_at)
    VALUES (7, 1, 2, 4, 3)`).run()
db.close()
execFileSync(process.execPath, [
    path.join(__dirname, "reset_raid_event.cjs"),
    "--data-dir", databaseDirectory,
    "--event-id", "7",
    "--apply",
    "--server-stopped",
    "--confirm", "RESET-RAID-7",
], { stdio: "pipe" })
db = new sqlite3(path.join(databaseDirectory, "wdfp_data.db"))
assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM raid_event_global_state
    WHERE event_id = 7`).get().count, 0)
const backupRoot = path.join(databaseDirectory, "admin-backups")
const backupDirectories = fs.readdirSync(backupRoot, { withFileTypes: true })
    .filter(entry => entry.isDirectory() && entry.name.startsWith("raid-event-reset-7-"))
assert.equal(backupDirectories.length, 1)
assert.equal(fs.existsSync(path.join(
    backupRoot,
    backupDirectories[0].name,
    "wdfp_data.db",
)), true)

console.log("raid event reset tests passed")
cleanup()
process.removeListener("exit", cleanup)
