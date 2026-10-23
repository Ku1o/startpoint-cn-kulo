'use strict'
const {test}=require('node:test'), assert=require('node:assert/strict'), Sqlite=require('better-sqlite3')
const {ContentOperationsStore,initializeContentOperationsSchema,CONTENT_ACTIONS}=require('../out/lib/content-operations-store')
const at=Date.parse('2026-10-13T00:00:00Z')
const open={readiness:'verified',evidence:'isolated evidence fixture',flags:{visible:true,enter:true,claim:true,exchange:false},endsAtMs:null}
function fixture(t) {
    const db=new Sqlite(':memory:');t.after(()=>db.close());initializeContentOperationsSchema(db)
    db.exec('CREATE TABLE retained_progress(id PRIMARY KEY, progress, received); INSERT INTO retained_progress VALUES(1017,8,1)')
    const row=(type,id,extra={})=>({key:`${type}:${id}`,type,id,name:'fixture',originalStartMs:1,originalEndMs:2,originalExchangeEndMs:3,windowCandidate:true,browseCandidate:true,source:'master/event',...extra})
    const catalog={schemaVersion:1,source:{assetVersion:'fixture',manifestSha256:'fixture'},baselineTimeMs:at,baselineEvidence:'fixture',missing:[],
        rows:[row('challenge_dungeon_event',1),row('challenge_dungeon_event',2),row('pass_card_event',15,{missionKeys:['6:60','7:57']}),row('mission_daily',14,{missionKeys:['2:14']})],
        questMap:{'13:1017':'challenge_dungeon_event:1','13:1018':'challenge_dungeon_event:1','13:2001':'challenge_dungeon_event:2'},missionMap:{'6:60':'pass_card_event:15','7:57':'pass_card_event:15','2:14':'mission_daily:14'},resources:{'master/reward':{sha256:'first'}}}
    const store=new ContentOperationsStore(db,catalog,()=>CONTENT_ACTIONS,undefined,row=>({kind:'fixture',id:row.id}),()=>['visible','enter'])
    const update=(key,input)=>store.update(key,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'isolated verification',...input},at)
    return {db,catalog,store,update}
}
test('exact quest evidence does not open the other quest in the same event',t=>{
    const {store,update}=fixture(t)
    update('challenge_dungeon_event:1',{...open,questKeys:['13:1017']})
    assert.equal(store.scopedAllowed('challenge_dungeon_event:1','quest','13:1017','enter',at),true)
    assert.equal(store.scopedAllowed('challenge_dungeon_event:1','quest','13:1018','enter',at),false)
    assert.equal(store.allowed('challenge_dungeon_event:2','enter',at),null)
    const full=store.snapshot(at)
    assert.equal(full.states.length,1);assert.deepEqual(full.states[0].quest_keys,['13:1017'])
    assert.deepEqual(full.catalog[0].quest_keys,['13:1017','13:1018'])
    assert.deepEqual(full.catalog[0].client_actions,['visible','enter']);assert.ok(full.catalog[0].server_actions.includes('claim'))
})
test('recording evidence alone never takes over a wired legacy entry',t=>{
    const {store,update}=fixture(t)
    const review=update('challenge_dungeon_event:1',{readiness:'verified',evidence:'one exact quest reviewed',questKeys:['13:1017']})
    assert.equal(review.controlled,false);assert.equal(store.allowed(review.key,'enter',at),null)
    assert.equal(store.snapshot(at).states.length,0)
    update(review.key,{flags:{visible:true,enter:true}})
    assert.equal(store.scopedAllowed(review.key,'quest','13:1018','enter',at),false)
})
test('cross-parent, duplicate, malformed and empty participating scopes are rejected atomically',t=>{
    const {db,store,update}=fixture(t)
    for(const questKeys of [['13:2001'],['13:1017','13:1017'],['1017'],[]]) assert.throws(()=>update('challenge_dungeon_event:1',{...open,questKeys}))
    assert.throws(()=>update('pass_card_event:15',{...open,missionKeys:['2:14']}))
    assert.throws(()=>update('mission_daily:14',{...open,questKeys:null}))
    assert.equal(store.revision(),0);assert.equal(db.prepare('SELECT count(*) n FROM content_operations_audit').get().n,0)
})
test('scope edits and close/reopen keep instance, progress and omitted scope; null explicitly selects all defined members',t=>{
    const {db,store,update}=fixture(t), saved=db.prepare('SELECT * FROM retained_progress').all()
    const first=update('pass_card_event:15',{...open,missionKeys:['6:60']})
    update('pass_card_event:15',{flags:{enter:false}})
    assert.equal(store.scopedAllowed('pass_card_event:15','mission','6:60','claim',at),true)
    assert.equal(store.scopedAllowed('pass_card_event:15','mission','7:57','claim',at),false)
    update('pass_card_event:15',{flags:{enter:true}})
    assert.deepEqual(store.state('pass_card_event:15').missionKeys,['6:60'])
    update('pass_card_event:15',{missionKeys:null})
    assert.equal(store.scopedAllowed('pass_card_event:15','mission','7:57','enter',at),true)
    assert.equal(store.state('pass_card_event:15').instanceId,first.instanceId)
    assert.deepEqual(db.prepare('SELECT * FROM retained_progress').all(),saved)
})
test('corrupt persisted scope cannot grant a cross-parent mission',t=>{
    const {db,store,update}=fixture(t)
    update('pass_card_event:15',{...open,missionKeys:['6:60']})
    const state=store.state('pass_card_event:15');state.missionKeys=['2:14']
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(state),state.key)
    assert.equal(store.state(state.key).integrityError,'invalid_persisted_state')
    assert.equal(store.scopedAllowed(state.key,'mission','2:14','claim',at),false)
})
test('auxiliary definition resource changes invalidate an existing verification',t=>{
    const {db,catalog,update}=fixture(t)
    catalog.rows[0].definitionSources=['master/reward']
    const initial=new ContentOperationsStore(db,catalog,()=>CONTENT_ACTIONS)
    initial.update('challenge_dungeon_event:1',{expectedRevision:0,catalogDigest:initial.digest,reason:'fixture',...open,questKeys:['13:1017']},at)
    const changed=new ContentOperationsStore(db,{...catalog,resources:{'master/reward':{sha256:'second'}}},()=>CONTENT_ACTIONS)
    assert.equal(changed.allowed('challenge_dungeon_event:1','enter',at),false)
    assert.equal(changed.list().rows[0].stale,true)
})
test('removing a controlled definition publishes a closed tombstone and no stale entry',t=>{
    const {db,catalog,update}=fixture(t)
    update('challenge_dungeon_event:1',{...open,questKeys:['13:1017']})
    const changed=new ContentOperationsStore(db,{...catalog,rows:catalog.rows.slice(1)},()=>CONTENT_ACTIONS)
    const full=changed.snapshot(at)
    assert.equal(full.full_snapshot,true);assert.equal(full.states[0].enter,false);assert.equal(full.catalog.length,0)
})
