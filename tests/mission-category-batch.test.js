const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-mission-batch-test-"))
process.env.DATA_DIR = temporaryDataDir

const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const {
    getPlayerCategoryMissionsForCategoriesSync,
    getPlayerCategoryMissionsSync,
    updatePlayerCategoryMissionBatchSync,
    updatePlayerCategoryMissionStageBatchSync,
    updatePlayerCategoryMissionStageSync,
    updatePlayerCategoryMissionSync,
} = require("../out/data/domains/mission")
const { settleMissionCategories } = require("../out/lib/mission/settlement")
const { getContentSnapshot } = require("../out/content/runtime/content-snapshot")
const {
    getActiveMissionEventMasterDefinitions,
    getActiveMissionMasterDefinitions,
} = require("../out/lib/mission/active-master-data")
const {
    getActiveMissionRewardStageIds,
    getParsedActiveMissionDefinition,
    getParsedActiveMissionEventDefinition,
} = require("../out/lib/mission/active-core")

const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "leiting",
    idpId: "",
    status: "normal",
})
const player = insertDefaultPlayerSync(account.id)

test("multi-category mission reads preserve the existing category response shape", () => {
    updatePlayerCategoryMissionSync(player.id, 1, 101, 4)
    updatePlayerCategoryMissionStageSync(player.id, 1, 1, 101, true)
    updatePlayerCategoryMissionSync(player.id, 2, 202, 7)
    updatePlayerCategoryMissionStageSync(player.id, 2, 2, 202, false)

    const batched = getPlayerCategoryMissionsForCategoriesSync(player.id, [1, 2, 1])
    assert.deepEqual(batched["1"], getPlayerCategoryMissionsSync(player.id, 1))
    assert.deepEqual(batched["2"], getPlayerCategoryMissionsSync(player.id, 2))
    assert.equal(batched["3"], undefined)
})

test("batched progress and stage writes match the single-row domain behavior", () => {
    updatePlayerCategoryMissionBatchSync(player.id, [
        { category: 1, missionId: 101, progress: 8 },
        { category: 2, missionId: 203, progress: 3 },
    ])
    updatePlayerCategoryMissionStageBatchSync(player.id, [
        { category: 1, missionId: 101, stageId: 2, status: true },
        { category: 2, missionId: 203, stageId: 1, status: true },
    ])

    assert.deepEqual(getPlayerCategoryMissionsSync(player.id, 1)["101"], {
        progress: 8,
        stages: { "1": true, "2": true },
    })
    assert.deepEqual(getPlayerCategoryMissionsSync(player.id, 2)["203"], {
        progress: 3,
        stages: { "1": true },
    })
})

test("mission settlement still grants completed stages exactly once", () => {
    updatePlayerSync({ id: player.id, maxComboAchieved: 100 })
    const first = settleMissionCategories(
        player.id,
        [{ category: 1, missionIds: [1] }],
        new Date(),
    )
    const persisted = getPlayerCategoryMissionsSync(player.id, 1)["1"]
    assert.equal(persisted.progress, 100)
    assert.ok(first.missionInfo.length > 0)

    const second = settleMissionCategories(
        player.id,
        [{ category: 1, missionIds: [1] }],
        new Date(),
    )
    assert.deepEqual(second.missionInfo, [])
})

test("parsed Active Mission master data is reused within one immutable content snapshot", () => {
    const repository = getContentSnapshot().repository
    const mission = getActiveMissionMasterDefinitions(repository)[0]
    const event = getActiveMissionEventMasterDefinitions(repository)[0]
    assert.ok(mission)
    assert.ok(event)
    assert.strictEqual(
        getParsedActiveMissionDefinition(mission.missionId, repository),
        getParsedActiveMissionDefinition(mission.missionId, repository),
    )
    assert.strictEqual(
        getParsedActiveMissionEventDefinition(event.eventId, repository),
        getParsedActiveMissionEventDefinition(event.eventId, repository),
    )
    assert.strictEqual(
        getActiveMissionRewardStageIds(mission.missionId, repository),
        getActiveMissionRewardStageIds(mission.missionId, repository),
    )
})
