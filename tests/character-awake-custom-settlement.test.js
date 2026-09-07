const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-awake-custom-settlement-"))
process.env.DATA_DIR = temporaryDataDir

const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const {
    insertDefaultPlayerCharacterSync,
    insertPlayerCharacterManaNodesSync,
} = require("../out/data/domains/character")
const { getPlayerCharacterAwakeUnlocksSync } = require("../out/data/domains/character_awake")
const { getCharacterManaNodesSync } = require("../out/lib/assets")
const {
    getAwakeBattleMissionIds,
    settleAwakeMissionCandidates,
} = require("../out/lib/mission")

const CHARACTER_ID = 151045

test("自制觉醒任务按1/3/5次通关结算并幂等解锁一板", () => {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    insertDefaultPlayerCharacterSync(player.id, CHARACTER_ID)
    insertPlayerCharacterManaNodesSync(
        player.id,
        CHARACTER_ID,
        Object.keys(getCharacterManaNodesSync(CHARACTER_ID, 1)).map(Number),
    )
    getDb().prepare(`
        INSERT INTO players_character_quest_clears (
            player_id, character_id, clear_count, multi_count,
            leader_clear_count, leader_multi_count, leader_power_flip_count
        ) VALUES (?, ?, 5, 0, 0, 0, 0)
    `).run(player.id, CHARACTER_ID)

    const missionIds = getAwakeBattleMissionIds([CHARACTER_ID])
    assert.deepEqual(missionIds, [1510451, 1510452, 1510453, 1510454])
    const first = settleAwakeMissionCandidates(
        player.id,
        missionIds,
        new Date("2025-01-01T12:00:00.000Z"),
    )
    assert.deepEqual(
        first.missionInfo.map(entry => entry.mission_id).sort((a, b) => a - b),
        missionIds,
    )
    assert.deepEqual(
        getPlayerCharacterAwakeUnlocksSync(player.id).get(String(CHARACTER_ID)),
        { 1: 1 },
    )

    const itemAmounts = Object.fromEntries([13, 14, 15, 16].map(itemId => [
        itemId,
        getDb().prepare("SELECT amount FROM players_items WHERE player_id = ? AND id = ?")
            .get(player.id, itemId)?.amount ?? 0,
    ]))
    assert.deepEqual(itemAmounts, { 13: 10, 14: 5, 15: 3, 16: 1 })

    const repeated = settleAwakeMissionCandidates(
        player.id,
        missionIds,
        new Date("2025-01-01T12:00:00.000Z"),
    )
    assert.deepEqual(repeated.missionInfo, [])
    assert.deepEqual(Object.fromEntries([13, 14, 15, 16].map(itemId => [
        itemId,
        getDb().prepare("SELECT amount FROM players_items WHERE player_id = ? AND id = ?")
            .get(player.id, itemId)?.amount ?? 0,
    ])), itemAmounts)
})
