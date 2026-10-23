'use strict'
const {test}=require('node:test'),assert=require('node:assert/strict'),Sqlite=require('better-sqlite3')
const {createContentOperationsStore}=require('../out/lib/content-operations')
const {initializeContentOperationsSchema}=require('../out/lib/content-operations-store')
const {applyJulyContentPlanOfflineSync,upgradeJulyContentPlanOfflineSync,julyContentPlan,LEGACY_JULY_PLAN_DIGEST}=require('../out/lib/content-operations-bootstrap')
const now=Date.parse('2026-10-21T00:00:00Z')
const newKeys=new Set(['gacha:1704','gacha:1705','gacha:1706','gacha:1707','gacha:1708','gacha:1709','gacha:1710','gacha:25043',
    'daily_week_event:19','challenge_dungeon_event:2','daily_exp_mana_event:1','tower_dungeon_event:1',
    'expert_single_event:1','expert_single_event:2','raid_event:7','rush_event:700011','rush_event:700012','rush_event:700013',
    'rush_event:700014','rush_event:700015','rush_event:700016','rush_event:700017','rush_event:700100','solo_time_attack_event:1',
    'hard_multi_event:1001','hard_multi_event:1002','hard_multi_event:1003','hard_multi_event:1004','hard_multi_event:1005','hard_multi_event:1006',
    'active_mission_event:1','active_mission_event:2','active_mission_event:150','box_gacha:28',
    'special_exchange_campaign:11','special_exchange_campaign:12','special_exchange_campaign:50020','start_dash_exchange_campaign:1'])
function fixture(t) {
    const db=new Sqlite(':memory:');t.after(()=>db.close());initializeContentOperationsSchema(db)
    db.exec('CREATE TABLE saved_progress(id INTEGER PRIMARY KEY,progress INTEGER,claimed INTEGER,stock INTEGER); INSERT INTO saved_progress VALUES(1,99,1,7)')
    const store=createContentOperationsStore(db),old=JSON.parse(JSON.stringify(julyContentPlan))
    old.controls=old.controls.filter(row=>!newKeys.has(row.key))
    assert.equal(old.controls.length,1075)
    for(const row of old.controls) {
        if(row.key==='challenge_dungeon_event:1')row.actionOverrides.enter.questKeys=['13:1017']
        else if(row.key==='pass_card_event:14')row.actionOverrides.enter.missionKeys=row.actionOverrides.enter.missionKeys.filter(key=>!['7:55','8:81','8:85'].includes(key))
        else if(row.key.includes('_event:')&&!row.key.startsWith('pass_')&&row.actionOverrides.exchange) {
            delete row.actionOverrides.enter;delete row.actionOverrides.claim
        }
    }
    applyJulyContentPlanOfflineSync(store,{expectedRevision:0,expectedCatalogDigest:store.digest,nowMs:now,plan:old})
    // Synthetic legacy shape. The actual legacy file is separately exercised through the offline CLI backup path.
    db.prepare('UPDATE content_operations_initialization SET plan_digest=?,catalog_digest=?').run(LEGACY_JULY_PLAN_DIGEST,'93ab67365cb9959c9ab737f74574a21dc460c300743ad3c1537e6512670aa765')
    const upgrade=(extra={})=>upgradeJulyContentPlanOfflineSync(store,{expectedRevision:store.revision(),expectedCatalogDigest:store.digest,nowMs:now,...extra})
    return {db,store,upgrade}
}
test('legacy seed upgrade merges only unchanged initial actions and preserves operator closes, publication and player progress',t=>{
    const {db,store,upgrade}=fixture(t),before=db.prepare('SELECT * FROM saved_progress').all()
    store.update('gacha:2',{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'Operator deliberately closed one pool',
        actionOverrides:{enter:{enabled:false,endsAtMs:null,readiness:'verified',evidence:'Operator override'}}},now)
    store.setPublished('world_story_event:400001',{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'Operator took event offline',published:false},now)
    const closed=JSON.stringify(store.state('gacha:2').actionOverrides.enter),instance=store.state('world_story_event:400001').instanceId
    const result=upgrade()
    assert.equal(result.applied,true);assert.ok(result.preservedOperatorKeys.includes('gacha:2'))
    assert.equal(JSON.stringify(store.state('gacha:2').actionOverrides.enter),closed)
    assert.equal(store.state('world_story_event:400001').published,false)
    assert.equal(store.state('world_story_event:400001').instanceId,instance)
    assert.equal(store.allowed('world_story_event:400001','enter',now),false)
    store.setPublished('world_story_event:400001',{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'Operator returns original event',published:true},now)
    assert.equal(store.allowed('world_story_event:400001','enter',now),true)
    assert.equal(store.allowed('rush_event:700100','enter',now),true)
    assert.equal(store.scopedAllowed('challenge_dungeon_event:1','quest','13:1018','enter',now),true)
    assert.equal(store.scopedAllowed('challenge_dungeon_event:1','quest','13:1020','enter',now),false)
    for(const member of ['7:55','8:81','8:85'])assert.equal(store.scopedAllowed('pass_card_event:14','mission',member,'enter',now),true)
    assert.equal(store.scopedAllowed('pass_card_event:14','mission','7:56','enter',now),false)
    assert.equal(db.prepare('SELECT count(*) n FROM content_operations_state').get().n,julyContentPlan.controls.length)
    assert.deepEqual(db.prepare('SELECT * FROM saved_progress').all(),before)
    const revision=store.revision();assert.equal(upgrade().applied,false);assert.equal(store.revision(),revision)
    db.prepare('DELETE FROM content_operations_state WHERE content_key=?').run('rush_event:700100')
    assert.throws(()=>upgrade(),/缺失|损坏/,'a current marker cannot hide lost state or reapply over operator choices')
    assert.equal(store.revision(),revision)
})
test('upgrade CAS and a missing initialization audit fail before any state or progress changes',t=>{
    const {db,store,upgrade}=fixture(t),revision=store.revision()
    assert.throws(()=>upgrade({expectedRevision:revision-1}),/版本/)
    db.prepare('DELETE FROM content_operations_audit WHERE revision=1').run()
    assert.throws(()=>upgrade(),/审计/)
    assert.equal(store.revision(),revision)
    assert.equal(db.prepare('SELECT count(*) n FROM content_operations_state').get().n,1075)
    assert.equal(store.state('rush_event:700100'),null)
    assert.deepEqual(db.prepare('SELECT * FROM saved_progress').all(),[{id:1,progress:99,claimed:1,stock:7}])
})
