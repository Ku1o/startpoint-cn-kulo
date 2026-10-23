const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const testRoot = process.env.MISSION_TEST_ROOT || path.resolve(__dirname, '../.test-data')
fs.mkdirSync(testRoot,{recursive:true})
const directory = fs.mkdtempSync(path.join(testRoot, 'mission-preservation-'))
process.env.DATA_DIR = directory
const { getDb } = require('../out/data/db')
const db = getDb()
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync, getPlayerSync, updatePlayerSync, dailyResetPlayerDataSync } = require('../out/data/domains/player')
const mission = require('../out/data/domains/mission')
const { settleMissionCategoriesWithProgress } = require('../out/lib/mission/settlement')
const { initializeContentOperationsSchema } = require('../out/lib/content-operations-store')
const { contentOperations, contentMissionDecision } = require('../out/lib/content-operations')
const { getComputer } = require('../out/lib/mission/registry')
const account = insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'mission-preservation',idpId:'',status:'normal'})
const at = new Date('2025-07-20T04:00:00Z')
const scopes = [{category:6,eventId:14,missionIds:[53]}]
function player() { return insertDefaultPlayerSync(account.id) }
function state(p, category = 6, id = 53) { return mission.getPlayerCategoryMissionsSync(p.id,category)[String(id)] }
function seed(p, received=true) {
    mission.updatePlayerCategoryMissionSync(p.id,6,53,11)
    mission.updatePlayerCategoryMissionStageSync(p.id,6,1,53,received)
}
function settle(p, scope=scopes) { return settleMissionCategoriesWithProgress(p.id,scope,at) }
function control(flags) {
    const store=contentOperations()
    return store.update('pass_card_event:14', {expectedRevision:store.revision(), catalogDigest:store.digest,
        readiness:'verified',evidence:'Isolated nonempty mission preservation fixture',reason:'Exercise original instance gates',
        flags,endsAtMs:null},Date.now())
}
test.after(() => { db.close(); fs.rmSync(directory,{recursive:true}) })

test('ordinary participation keeps historical over-target progress and received stages', () => {
    const p=player();seed(p)
    const before=state(p)
    const first=settle(p)
    assert.equal(first.evaluatedProgress[0].progress,11)
    assert.deepEqual(state(p),before)
    assert.deepEqual(first.settlement.missionInfo,[])
    assert.deepEqual(settle(p).settlement.missionInfo,[])
})

test('claim-only grants a pending old stage once, preserves all progress and skips fact contexts', () => {
    initializeContentOperationsSchema(db)
    control({visible:true,enter:false,claim:true,exchange:false})
    assert.equal(contentMissionDecision(6,53,'enter'),false)
    const p=player();seed(p,false)
    const snapshots=db.prepare('SELECT * FROM players_periodic_snapshots WHERE player_id=? ORDER BY period_type').all(p.id)
    const computer=getComputer(6), original=computer.buildContext
    computer.buildContext=()=>{throw Error('Claim-only must not evaluate facts')}
    try {
        assert.equal(settle(p).settlement.missionInfo.length,1)
        assert.deepEqual(state(p),{progress:11,stages:{'1':true}})
        assert.deepEqual(settle(p).settlement.missionInfo,[])
        assert.deepEqual(db.prepare('SELECT * FROM players_periodic_snapshots WHERE player_id=? ORDER BY period_type').all(p.id),snapshots)
    } finally { computer.buildContext=original }
})

test('close and reopen preserve claims, prevent duplicate grants and create no closed pass baseline', () => {
    const p=player();seed(p,false)
    mission.updatePlayerCategoryMissionSync(p.id,7,53,17)
    mission.updatePlayerCategoryMissionStageSync(p.id,7,1,53,true)
    mission.updatePlayerCategoryMissionSync(p.id,8,80,29)
    mission.updatePlayerCategoryMissionStageSync(p.id,8,1,80,true)
    control({visible:false,enter:false,claim:false,exchange:false})
    const before=mission.getPlayerCategoryMissionsForCategoriesSync(p.id,[6,7,8])
    const tables=['players_periodic_snapshots','players_pass_cards']
    const rows=()=>tables.map(table=>db.prepare(`SELECT * FROM ${table} WHERE player_id=?`).all(p.id))
    const baselines=rows()
    for(const category of [6,7,8]) {
        const result=settle(p,[{category,eventId:14,missionIds:[category===8?80:53]}])
        assert.deepEqual(result.evaluatedProgress,[])
        assert.deepEqual(result.settlement.missionInfo,[])
    }
    assert.deepEqual(mission.getPlayerCategoryMissionsForCategoriesSync(p.id,[6,7,8]),before)
    assert.deepEqual(rows(),baselines)
    control({visible:true,enter:true,claim:true,exchange:false})
    assert.equal(settle(p).settlement.missionInfo.length,1)
    assert.deepEqual(state(p),{progress:11,stages:{'1':true}})
    assert.deepEqual(settle(p).settlement.missionInfo,[])
})

test('daily and weekly reset retain closed missions and all received stages', () => {
    control({visible:true,enter:false,claim:true,exchange:false})
    const p=player();seed(p)
    mission.updatePlayerCategoryMissionSync(p.id,7,53,17)
    mission.updatePlayerCategoryMissionStageSync(p.id,7,1,53,true)
    updatePlayerSync({id:p.id,lastLoginTime:new Date('2025-07-13T04:00:00Z'),timeOffset:0})
    const before=mission.getPlayerCategoryMissionsForCategoriesSync(p.id,[6,7])
    assert.equal(dailyResetPlayerDataSync(getPlayerSync(p.id),new Date('2025-07-21T04:00:00Z')),true)
    assert.deepEqual(mission.getPlayerCategoryMissionsForCategoriesSync(p.id,[6,7]),before)
    assert.equal(db.prepare("SELECT COUNT(*) AS n FROM players_periodic_snapshots WHERE player_id=? AND period_type='pass-week:14'").get(p.id).n,0)
    control({visible:true,enter:true,claim:true,exchange:false})
    assert.deepEqual(settle(p).settlement.missionInfo,[])
    assert.deepEqual(state(p),before['6']['53'])
})
