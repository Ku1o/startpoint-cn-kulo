const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-activity-degree-test-"))
process.env.DATA_DIR = temporaryDataDir

const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const { getDb } = require("../out/data/db")
const { hasPlayerDegreeSync } = require("../out/data/domains/degree")
const {
    getEligibleRankingDegreeIdsSync,
    getEligibleRaidDegreeIdsSync,
    getEligibleRushDegreeIds,
    grantEligibleRankingEventDegreesSync,
    grantEligibleRaidEventDegreesSync,
    grantEligibleRushEventDegreesSync,
} = require("../out/lib/activity-degree-rewards")

const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "leiting",
    idpId: "",
    status: "normal",
})
const player = insertDefaultPlayerSync(account.id)

test("ranking time titles are restored from the persisted best clear", () => {
    getDb().prepare(`
        INSERT INTO players_quest_progress
            (section, quest_id, finished, best_elapsed_time_ms, player_id)
        VALUES (11, 3001, 1, 35000, ?)
    `).run(player.id)

    assert.deepEqual(getEligibleRankingDegreeIdsSync(player.id, 3), [54100, 54110, 54120, 54130])
    assert.deepEqual(grantEligibleRankingEventDegreesSync(player.id, 3), [54100, 54110, 54120, 54130])
    assert.equal(hasPlayerDegreeSync(player.id, 54130), true)
    assert.equal(hasPlayerDegreeSync(player.id, 54140), false)
})

test("raid titles use the player's deduplicated clear ledger by difficulty", () => {
    const insert = getDb().prepare(`
        INSERT INTO raid_event_global_kill_ledger
            (event_id, play_id, player_id, quest_id, created_at)
        VALUES (7, ?, ?, 7002, ?)
    `)
    for (let index = 0; index < 10; index++) {
        insert.run(`degree-test-${index}`, player.id, Date.now() + index)
    }

    assert.deepEqual(getEligibleRaidDegreeIdsSync(player.id, 7), [63081])
    assert.deepEqual(grantEligibleRaidEventDegreesSync(player.id, 7), [63081])
    assert.equal(hasPlayerDegreeSync(player.id, 63081), true)
})

test("rush title reward ranges are evaluated against endless round, not leaderboard rank", () => {
    assert.deepEqual(getEligibleRushDegreeIds(700001, 1), [])
    assert.deepEqual(getEligibleRushDegreeIds(700001, 3), [64000])
    assert.deepEqual(getEligibleRushDegreeIds(700001, 5), [64001])
    assert.deepEqual(getEligibleRushDegreeIds(700001, 6), [64002])

    assert.deepEqual(grantEligibleRushEventDegreesSync(player.id, 700001, 6), [64002])
    assert.equal(hasPlayerDegreeSync(player.id, 64002), true)
})
