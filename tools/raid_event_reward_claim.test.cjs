require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const databaseDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "raid-event-reward-claim-db-"))
const previousDataDirectory = process.env.DATA_DIR
const previousDatabaseDirectory = process.env.WDFP_DATABASE_DIR
process.env.DATA_DIR = databaseDirectory
delete process.env.WDFP_DATABASE_DIR
let db

function cleanup() {
    if (db?.open) db.close()
    fs.rmSync(databaseDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
    if (previousDatabaseDirectory === undefined) delete process.env.WDFP_DATABASE_DIR
    else process.env.WDFP_DATABASE_DIR = previousDatabaseDirectory
}

process.once("exit", cleanup)

const { initializeDatabase } = require("../src/data")
const { getDb } = require("../src/data/db")
const { insertAccountSync } = require("../src/data/domains/account")
const { insertDefaultPlayerSync } = require("../src/data/domains/player")
const { getPlayerItemSync } = require("../src/data/domains/item")
const {
    claimRaidEventOverallRewardsSync,
    getRaidEventGlobalBossSync,
    recordRaidEventClearSync,
} = require("../src/lib/raidEventGlobal")
const { getRaidEventProgressRule } = require("../src/lib/raid-event-config")
const { getQuestFromCategorySync } = require("../src/lib/assets")
const { QuestCategory } = require("../src/lib/types")
const { calculateClearRank } = require("../src/lib/quest/finish/quest-calc")

initializeDatabase()
db = getDb()

const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "test",
    idpId: `raid-event-reward-${randomUUID()}`,
    status: "normal",
})
const playerId = insertDefaultPlayerSync(account.id).id
const abyssTicketBefore = getPlayerItemSync(playerId, 999014) ?? 0

const rawRaidQuests = require("../assets/raid_event_quest.json")
assert.equal(Object.keys(rawRaidQuests).length, 50)
assert.equal(Object.values(rawRaidQuests).every(quest =>
    quest.bRankTime === 0
    && quest.aRankTime === 0
    && quest.sRankTime === 0
    && quest.sPlusRankTime === 0
), true, "All official Raid quests must use no-rank settlement")

const officialRaidQuest = getQuestFromCategorySync(QuestCategory.RAID_EVENT, 7002)
assert.equal(calculateClearRank(60_000, officialRaidQuest), null)
assert.deepEqual(
    {
        rankPointReward: officialRaidQuest.rankPointReward,
        characterExpReward: officialRaidQuest.characterExpReward,
        manaReward: officialRaidQuest.manaReward,
        poolExpReward: officialRaidQuest.poolExpReward,
    },
    {
        rankPointReward: 556,
        characterExpReward: 1830,
        manaReward: 1980,
        poolExpReward: 1830,
    },
    "Raid quests must use the official no-rank result mode and reward columns",
)

const firstClaim = claimRaidEventOverallRewardsSync(playerId, 7, 300)
assert.equal(firstClaim.receivedUpTo, 300)
assert.deepEqual(
    firstClaim.rewardList.find(reward => reward.kind === 1 && reward.kind_id === 999014),
    { kind: 1, kind_id: 999014, number: 25 },
    "The 300-kill reward must contain 25 Abyss ten-pull tickets",
)
assert.equal(
    firstClaim.rewardList.every(reward => [1, 3, 8].includes(reward.kind)),
    true,
    "Raid summary rewards must use client remote kind values",
)
assert.equal(getPlayerItemSync(playerId, 999014), abyssTicketBefore + 25)

assert.deepEqual(
    claimRaidEventOverallRewardsSync(playerId, 7, 300),
    { receivedUpTo: 300, rewardList: [] },
    "The same overall rewards must not be granted twice",
)

assert.equal(getRaidEventGlobalBossSync(7).requiredKillCount, 30000)
assert.deepEqual(getRaidEventProgressRule(7), {
    requiredKillCount: 30000,
    questWeights: {
        7001: 51, 7002: 255,
        7003: 1, 7004: 3, 7005: 30, 7006: 180,
        7007: 1, 7008: 3, 7009: 26, 7010: 157,
        7011: 1, 7012: 3, 7013: 22, 7014: 135,
        7015: 1, 7016: 3, 7017: 18, 7018: 115,
        7019: 1, 7020: 3, 7021: 15, 7022: 97,
        7023: 1, 7024: 3, 7025: 12, 7026: 80,
    },
})
assert.equal(
    recordRaidEventClearSync({
        eventId: 7,
        playId: "invalid-quest",
        playerId,
        questId: 7999,
    }).counted,
    false,
    "Unsupported quests must not contribute to the communal boss",
)

const firstClear = recordRaidEventClearSync({
    eventId: 7,
    playId: "same-play-id",
    playerId,
    questId: 7002,
})
assert.equal(firstClear.counted, true)
assert.equal(firstClear.boss.weightedKillCount, 255)
assert.equal(firstClear.boss.hpPercentage, 99.2)
assert.equal(
    recordRaidEventClearSync({
        eventId: 7,
        playId: "same-play-id",
        playerId,
        questId: 7002,
    }).counted,
    false,
    "The same play_id must only contribute once",
)

const ledgerForeignKeys = db.prepare(
    `PRAGMA foreign_key_list(raid_event_global_kill_ledger)`,
).all()
assert.equal(ledgerForeignKeys.length, 0, "Global clear receipts must not cascade with player deletion")
db.prepare(`DELETE FROM players WHERE id = ?`).run(playerId)
assert.equal(
    db.prepare(`SELECT COUNT(*) AS count FROM raid_event_global_kill_ledger WHERE event_id = 7`).get().count,
    1,
    "Global play_id receipt must survive player deletion",
)

const insertReceipt = db.prepare(`INSERT INTO raid_event_global_kill_ledger
    (event_id, play_id, player_id, quest_id, created_at)
    VALUES (7, ?, ?, 7002, ?)`)
db.transaction(() => {
    for (let index = 2; index <= 117; index++) {
        insertReceipt.run(`private-threshold-${index}`, playerId, index)
    }
})()
db.prepare(`DELETE FROM raid_event_global_state WHERE event_id = 7`).run()
assert.deepEqual(getRaidEventGlobalBossSync(7), {
    hpPercentage: 0.6,
    totalKillCount: 0,
    weightedKillCount: 29835,
    requiredKillCount: 30000,
})

insertReceipt.run("private-threshold-118", playerId, 118)
db.prepare(`DELETE FROM raid_event_global_state WHERE event_id = 7`).run()
assert.deepEqual(getRaidEventGlobalBossSync(7), {
    hpPercentage: 100,
    totalKillCount: 1,
    weightedKillCount: 0,
    requiredKillCount: 30000,
})
db.prepare(`UPDATE raid_event_global_state
    SET total_kill_count = 999,
        weighted_kill_count = 29999,
        calculation_version = 4
    WHERE event_id = 7`).run()
assert.deepEqual(
    getRaidEventGlobalBossSync(7),
    {
        hpPercentage: 100,
        totalKillCount: 1,
        weightedKillCount: 0,
        requiredKillCount: 30000,
    },
    "Version 4 state must be rebuilt from the ledger with the version 5 threshold",
)
assert.equal(
    db.prepare(`SELECT calculation_version
        FROM raid_event_global_state
        WHERE event_id = 7`).get().calculation_version,
    5,
)

console.log("raid event reward claim tests passed")
cleanup()
process.removeListener("exit", cleanup)
