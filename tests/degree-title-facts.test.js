const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-degree-title-facts-test-"))
process.env.DATA_DIR = temporaryDataDir

const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const { givePlayerItemSync, setPlayerItemSync } = require("../out/data/domains/item")
const { hasPlayerDegreeSync } = require("../out/data/domains/degree")
const {
    getPlayerCategoryMissionsSync,
    updatePlayerCategoryMissionSync,
} = require("../out/data/domains/mission")
const { addMissionCounterSync } = require("../out/lib/mission/counters")
const { countNewAbilitySoulEquipments } = require("../out/lib/mission/ability-soul-facts")
const { recordBattleMissionDimensions } = require("../out/lib/mission/battle-dimensions")
const { summarizeBattleStatistics } = require("../out/lib/mission/events")
const { settleMissionCategories } = require("../out/lib/mission/settlement")

const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "leiting",
    idpId: "",
    status: "normal",
})
const player = insertDefaultPlayerSync(account.id)

function statistics(overrides = {}) {
    return {
        dashCount: 0,
        powerFlipCount: 0,
        powerFlipLv3Count: 0,
        skillCount: 0,
        maxComboCount: 0,
        maxSkillChainCount: 0,
        feverCount: 0,
        feverTimeMs: 0,
        weakenEnemyCount: 0,
        clearEnemyBuffCount: 0,
        clearSelfDebuffCount: 0,
        buffCompanionCount: 0,
        healCompanionCount: 0,
        emotionCount: 0,
        enemyKillCount: 0,
        weakPointDestroyCount: 0,
        coffinReduceCount: 0,
        damageDealMax: 0,
        revivalCoffinMax: 0,
        ...overrides,
    }
}

function record(mode, clearTimeMs, score, stats = statistics()) {
    recordBattleMissionDimensions({
        type: "battle_finish",
        playerId: player.id,
        questCategory: mode === "single" ? 1 : 2,
        questId: mode === "single" ? 1001001 : 1001001,
        accomplished: true,
        mode,
        clearRank: 5,
        clearTimeMs,
        score,
        partyCharacterIds: [],
        unisonCharacterIds: [],
        statistics: stats,
    })
}

test("battle payload maximum fields use the client master-data names", () => {
    const summary = summarizeBattleStatistics({
        zones: [
            { damage_deal_max: 1_000_000, max_coffin_count_by_revival: 12 },
            { damage_deal_max: 5_000_000, max_coffin_count_by_revival: 30 },
        ],
    })
    assert.equal(summary.damageDealMax, 5_000_000)
    assert.equal(summary.revivalCoffinMax, 30)
})

test("ability-soul edits count only newly occupied or changed slots", () => {
    assert.equal(countNewAbilitySoulEquipments([null, 10, 20], [1, 10, 21]), 2)
    assert.equal(countNewAbilitySoulEquipments([1, 2, 3], [1, 2, 3]), 0)
    assert.equal(countNewAbilitySoulEquipments([1, 2, 3], [null, 2, null]), 0)
})

test("multi records cannot unlock single-only time and score titles", () => {
    record("multi", 1000, 99_999_999)
    settleMissionCategories(player.id, [{ category: 5, missionIds: [14000, 15020] }], new Date())
    let progress = getPlayerCategoryMissionsSync(player.id, 5)
    assert.equal(progress["14000"]?.progress ?? 0, 0)
    assert.equal(progress["15020"]?.progress ?? 0, 0)

    record("single", 5000, 10_000_000)
    settleMissionCategories(player.id, [{ category: 5, missionIds: [14000, 15020] }], new Date())
    progress = getPlayerCategoryMissionsSync(player.id, 5)
    assert.equal(progress["14000"].progress, 10_000_000)
    assert.equal(progress["15020"].progress, 1)
})

test("single fever time title progress keeps the master-data millisecond unit", () => {
    const missionIds = [17000, 17010, 17020]
    record("single", 1000, 0, statistics({ feverTimeMs: 63_000 }))

    // Reproduce the progress persisted by the former seconds conversion.
    for (const missionId of missionIds) {
        updatePlayerCategoryMissionSync(player.id, 5, missionId, 63)
    }

    settleMissionCategories(player.id, [{ category: 5, missionIds }], new Date())
    let progress = getPlayerCategoryMissionsSync(player.id, 5)
    for (const missionId of missionIds) {
        assert.equal(progress[String(missionId)].progress, 63_000)
        assert.equal(hasPlayerDegreeSync(player.id, missionId), false)
    }

    record("single", 1000, 0, statistics({ feverTimeMs: 117_000 }))
    settleMissionCategories(player.id, [{ category: 5, missionIds }], new Date())
    progress = getPlayerCategoryMissionsSync(player.id, 5)
    assert.equal(progress["17000"].progress, 180_000)
    assert.equal(progress["17010"].progress, 180_000)
    assert.equal(progress["17020"].progress, 180_000)
    assert.equal(hasPlayerDegreeSync(player.id, 17000), true)
    assert.equal(hasPlayerDegreeSync(player.id, 17010), false)
    assert.equal(hasPlayerDegreeSync(player.id, 17020), false)

    record("single", 1000, 0, statistics({ feverTimeMs: 420_000 }))
    settleMissionCategories(player.id, [{ category: 5, missionIds }], new Date())
    progress = getPlayerCategoryMissionsSync(player.id, 5)
    assert.equal(progress["17000"].progress, 180_000)
    assert.equal(progress["17010"].progress, 600_000)
    assert.equal(progress["17020"].progress, 600_000)
    assert.equal(hasPlayerDegreeSync(player.id, 17010), true)
    assert.equal(hasPlayerDegreeSync(player.id, 17020), false)

    record("single", 1000, 0, statistics({ feverTimeMs: 3_000_000 }))
    settleMissionCategories(player.id, [{ category: 5, missionIds }], new Date())
    progress = getPlayerCategoryMissionsSync(player.id, 5)
    assert.equal(progress["17020"].progress, 3_600_000)
    assert.equal(hasPlayerDegreeSync(player.id, 17020), true)
})

test("maximum damage and revival coffin facts unlock their title missions", () => {
    record("single", 60_000, 0, statistics({
        damageDealMax: 5_000_000,
        revivalCoffinMax: 30,
    }))
    settleMissionCategories(player.id, [{
        category: 5,
        missionIds: [35000, 35010, 35020, 39000],
    }], new Date())
    const progress = getPlayerCategoryMissionsSync(player.id, 5)
    assert.equal(progress["35000"].progress, 1_000_000)
    assert.equal(progress["35010"].progress, 5_000_000)
    assert.equal(progress["35020"].progress, 5_000_000)
    assert.equal(progress["39000"].progress, 30)
})

test("lifetime craft-stone collection survives spending", () => {
    givePlayerItemSync(player.id, 100000, 1000)
    setPlayerItemSync(player.id, 100000, 0)
    settleMissionCategories(player.id, [{ category: 5, missionIds: [41000] }], new Date())
    assert.equal(getPlayerCategoryMissionsSync(player.id, 5)["41000"].progress >= 1000, true)
})

test("zero-exp characters no longer count as level 60 and ability-soul use is persistent", () => {
    settleMissionCategories(player.id, [{ category: 5, missionIds: [3000] }], new Date())
    assert.equal(getPlayerCategoryMissionsSync(player.id, 5)["3000"]?.progress ?? 0, 0)

    addMissionCounterSync(player.id, {
        dimension: "party.ability_soul_equip",
        scopeType: "lifetime",
        scopeKey: "all",
        qualifier: {},
    }, 3)
    settleMissionCategories(player.id, [{ category: 5, missionIds: [8000] }], new Date())
    assert.equal(getPlayerCategoryMissionsSync(player.id, 5)["8000"].progress, 3)
})
