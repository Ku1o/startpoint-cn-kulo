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
    getPlayerCategoryMissionsForScopesSync,
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

test("scoped reads merge duplicate scopes and isolate players, categories and unselected stages", () => {
    const other=insertDefaultPlayerSync(account.id)
    updatePlayerCategoryMissionSync(player.id,1,31001,8)
    updatePlayerCategoryMissionSync(player.id,1,31002,9)
    updatePlayerCategoryMissionSync(player.id,2,31001,4)
    updatePlayerCategoryMissionSync(other.id,1,31001,99)
    updatePlayerCategoryMissionStageSync(player.id,1,1,31001,true)
    updatePlayerCategoryMissionStageSync(player.id,1,2,31001,false)
    updatePlayerCategoryMissionStageSync(player.id,1,1,31002,true)
    updatePlayerCategoryMissionStageSync(other.id,1,3,31001,true)
    const scopes=[{category:1,missionIds:[31001,31001]},
        {category:1,missionIds:[31002,NaN]}, {category:2,missionIds:[31001]}, {category:3,missionIds:[]}]
    const selected=getPlayerCategoryMissionsForScopesSync(player.id,scopes)
    const full=getPlayerCategoryMissionsForCategoriesSync(player.id,[1,2])
    assert.deepEqual(selected,{'1':{'31001':full['1']['31001'],'31002':full['1']['31002']},
        '2':{'31001':full['2']['31001']},'3':{}})
    assert.deepEqual(getPlayerCategoryMissionsForScopesSync(player.id,[{category:1,missionIds:[31001]}]),
        {'1':{'31001':{progress:8,stages:{'1':true,'2':false}}}})
    assert.deepEqual(getPlayerCategoryMissionsForScopesSync(player.id,[]),{})
    const db=require('../out/data/db').getDb()
    assert.throws(()=>db.transaction(()=>{
        updatePlayerCategoryMissionSync(player.id,1,31001,50)
        assert.equal(getPlayerCategoryMissionsForScopesSync(player.id,[scopes[0]])['1']['31001'].progress,50)
        throw Error('rollback')
    })(),/rollback/)
    assert.equal(getPlayerCategoryMissionsForScopesSync(player.id,[scopes[0]])['1']['31001'].progress,8)
})

test("scoped and category-wide settlement produce identical progress and rewards", () => {
    const db=require('../out/data/db').getDb()
    const subject=insertDefaultPlayerSync(account.id)
    updatePlayerSync({id:subject.id,maxComboAchieved:200})
    const run=enabled=>{
        let result,state
        const previous=process.env.MISSION_SCOPED_READS
        process.env.MISSION_SCOPED_READS=enabled?'true':'false'
        try {
            assert.throws(()=>db.transaction(()=>{
                result=settleMissionCategories(subject.id,[{category:1,missionIds:[1]}],new Date())
                state=getPlayerCategoryMissionsForCategoriesSync(subject.id,[1])
                throw Error('restore fixture')
            })(),/restore fixture/)
        } finally {
            if(previous===undefined)delete process.env.MISSION_SCOPED_READS
            else process.env.MISSION_SCOPED_READS=previous
        }
        return {result,state}
    }
    assert.deepEqual(run(true),run(false))
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
