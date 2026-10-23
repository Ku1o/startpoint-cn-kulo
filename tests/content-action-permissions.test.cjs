'use strict'
const {test}=require('node:test'), assert=require('node:assert/strict'), Sqlite=require('better-sqlite3')
const {ContentOperationsStore,initializeContentOperationsSchema,CONTENT_ACTIONS}=require('../out/lib/content-operations-store')
const now=Date.parse('2026-10-13T00:00:00Z')
const action=(enabled=true,extra={})=>({enabled,endsAtMs:null,readiness:'verified',evidence:'isolated exact action proof',...extra})
const enterKeys=['6:57','6:58','6:59','6:60','7:57','7:58','8:86','8:87','8:88','8:89','8:90','8:91']
const claimKeys=[...enterKeys,'7:59','7:60']
function fixture(t){
 const db=new Sqlite(':memory:');t.after(()=>db.close());initializeContentOperationsSchema(db)
 const row=(type,id)=>({key:`${type}:${id}`,type,id,name:'synthetic',source:'fixture',originalStartMs:1,originalEndMs:2,originalExchangeEndMs:3,windowCandidate:true,browseCandidate:true})
 const catalog={schemaVersion:1,source:{assetVersion:'fixture',manifestSha256:'fixture'},baselineTimeMs:1,baselineEvidence:'fixture',resources:{},missing:[],questMap:{},missionMap:Object.fromEntries(claimKeys.map(member=>[member,'pass_card_event:15'])),rows:[row('gacha',1),row('pass_card_event',15)]}
 const store=new ContentOperationsStore(db,catalog,()=>CONTENT_ACTIONS)
 const update=(key,body)=>store.update(key,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'isolated action test',...body},now)
 return {db,catalog,store,update}
}
test('fresh draw-only override leaves exchange and other absent actions on their original policy',t=>{
 const {store,update}=fixture(t);update('gacha:1',{actionOverrides:{enter:action()}})
 assert.equal(store.allowed('gacha:1','enter',now),true);assert.equal(store.allowed('gacha:1','exchange',now),null)
 assert.equal(store.allowed('gacha:1','claim',now),null);assert.equal(store.allowed('gacha:1','visible',now),null)
 const snapshot=store.snapshot(now);assert.equal(snapshot.schema_version,2)
 assert.deepEqual(Object.keys(snapshot.states[0].actions),['enter']);assert.equal('exchange' in snapshot.states[0],false)
 assert.deepEqual(store.list().rows[0].effectiveFlags,{enter:true})
})
test('independent 12 enter and 14 claim scopes preserve historical pattern85 claims without new facts',t=>{
 const {store,update}=fixture(t)
 update('pass_card_event:15',{actionOverrides:{visible:action(),enter:action(true,{missionKeys:enterKeys}),claim:action(true,{missionKeys:claimKeys})}})
 for(const member of enterKeys)assert.equal(store.scopedAllowed('pass_card_event:15','mission',member,'enter',now),true)
 for(const member of claimKeys)assert.equal(store.scopedAllowed('pass_card_event:15','mission',member,'claim',now),true)
 for(const member of ['7:59','7:60'])assert.equal(store.scopedAllowed('pass_card_event:15','mission',member,'enter',now),false)
 update('pass_card_event:15',{actionOverrides:{enter:action(false,{missionKeys:enterKeys})}})
 assert.equal(store.scopedAllowed('pass_card_event:15','mission','7:59','claim',now),true)
 assert.equal(store.allowed('pass_card_event:15','exchange',now),null)
 assert.deepEqual(store.snapshot(now).states[0].actions.claim.mission_keys,[...claimKeys].sort())
})
test('legacy flags retain whole-row semantics and conversion preserves every untouched old action and scope',t=>{
 const {store,update}=fixture(t)
 const before=update('pass_card_event:15',{readiness:'verified',evidence:'legacy evidence',flags:{visible:true,enter:true,claim:true},endsAtMs:now+1000,missionKeys:claimKeys})
 assert.equal(store.allowed(before.key,'exchange',now),false)
 update(before.key,{actionOverrides:{enter:action(true,{missionKeys:enterKeys})}})
 const state=store.state(before.key)
 assert.equal(state.actionOverrides.claim.enabled,true);assert.equal(state.actionOverrides.claim.evidence,'legacy evidence')
 assert.equal(state.actionOverrides.claim.endsAtMs,now+1000);assert.deepEqual(state.actionOverrides.claim.missionKeys,[...claimKeys].sort())
 assert.equal(store.scopedAllowed(before.key,'mission','7:59','claim',now),true)
 assert.equal(store.allowed(before.key,'claim',now+1001),false);assert.equal(store.allowed(before.key,'enter',now+1001),true)
 assert.throws(()=>update(before.key,{flags:{enter:false}}),/分别修改动作/)
})
test('read-only readiness review never takes over an action or changes independent action proof',t=>{
 const {store,update}=fixture(t);update('gacha:1',{readiness:'verified',evidence:'review only'})
 assert.equal(store.state('gacha:1').controlled,false);assert.equal(store.snapshot(now).states.length,0)
 update('gacha:1',{actionOverrides:{enter:action()}})
 update('gacha:1',{readiness:'blocked',evidence:'independent metadata review'})
 assert.equal(store.allowed('gacha:1','enter',now),true);assert.equal(store.allowed('gacha:1','exchange',now),null)
})
test('malformed, unsupported, foreign or incomplete action scope and stale CAS reject atomically',t=>{
 const {db,store,update}=fixture(t)
 for(const bad of [{reset:action()},{enter:{enabled:true}},{enter:action(true,{readiness:'unverified'})},{enter:action(true,{endsAtMs:now})},{enter:action(true,{missionKeys:['6:57','6:57']})},{enter:action(true,{missionKeys:['6:999']})},{enter:action(true,{missionKeys:[]})},{enter:action()}])
  assert.throws(()=>update('pass_card_event:15',{actionOverrides:bad}))
 assert.equal(store.revision(),0);assert.equal(db.prepare('SELECT count(*) n FROM content_operations_audit').get().n,0)
 update('gacha:1',{actionOverrides:{enter:action()}})
 assert.throws(()=>update('gacha:1',{expectedRevision:0,actionOverrides:{enter:action(false)}}),/刷新/)
 assert.equal(store.allowed('gacha:1','enter',now),true)
 const unsupported=new ContentOperationsStore(db,store.catalog,()=>['visible'])
 assert.equal(unsupported.allowed('gacha:1','enter',now),false)
 assert.throws(()=>unsupported.update('gacha:1',{expectedRevision:1,catalogDigest:unsupported.digest,reason:'unsupported',actionOverrides:{enter:action()}},now),/尚未接通/)
})
test('action recheck cannot refresh another stale proof; persisted corruption stays closed',t=>{
 const {db,store,catalog,update}=fixture(t);update('gacha:1',{actionOverrides:{enter:action(),exchange:action()}})
 const changed=new ContentOperationsStore(db,{...catalog,rows:catalog.rows.map(row=>({...row,definitionDigest:'changed'}))},()=>CONTENT_ACTIONS)
 assert.equal(changed.allowed('gacha:1','exchange',now),false)
 changed.update('gacha:1',{expectedRevision:changed.revision(),catalogDigest:changed.digest,reason:'only enter rechecked',actionOverrides:{enter:action()}},now)
 assert.equal(changed.allowed('gacha:1','enter',now),true);assert.equal(changed.allowed('gacha:1','exchange',now),false)
 const value=changed.state('gacha:1');value.actionOverrides.enter.enabled='true'
 db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(value),'gacha:1')
 assert.equal(changed.allowed('gacha:1','enter',now),false);assert.equal(changed.allowed('gacha:1','claim',now),false)
 assert.equal(changed.state('gacha:1').integrityError,'invalid_persisted_state')
})
test('each action expires independently and remains controlled after expiry',t=>{
 const {store,update}=fixture(t);update('gacha:1',{actionOverrides:{enter:action(true,{endsAtMs:now+1000}),exchange:action()}})
 assert.equal(store.allowed('gacha:1','enter',now+1001),false);assert.equal(store.allowed('gacha:1','exchange',now+1001),true)
 assert.equal(store.snapshot(now+1001).states[0].actions.enter.enabled,false)
})
function rehearsal(){
 const digest='a'.repeat(64),key='gacha:1',actions=['visible','enter','exchange']
 const observation=(action,availability='available')=>({key,action,availability,source:'explicit synthetic inventory'})
 return {mode:'scenario',identity:{catalogFileSha256:digest,catalogDigest:digest,manifestSha256:digest,assetVersion:'fixture',referenceBusinessTimeMs:now,referenceCapturedAtUtc:'2026-10-13T00:00:00Z',runtimeMemoryClockVerified:false},rows:[{key,capabilities:actions}],observedBefore:actions.map(a=>observation(a)),legacyAfter:actions.map(a=>observation(a)),proposedAfter:[{key,controlled:true,catalogDigest:digest,actionOverrides:{enter:action()}}],evidence:[{key,action:'enter',status:'verified',source:'synthetic draw proof',catalogDigest:digest}],proposedTimeMs:now,completeness:{currentAvailabilityInventoryComplete:false,playerEntitlementsPreserved:false,runtimeClockVerified:false,clientRuntimeVerified:false}}
}
test('rehearsal uses old-policy after for absent actions and does not manufacture exchange closure',()=>{
 const input=rehearsal(),evaluate=require('../out/lib/content-cutover-preflight').evaluateContentCutoverPreflight,result=evaluate(input)
 assert.equal(result.decision,'scenario_only');assert.equal(result.lost.length,0)
 assert.equal(result.differences.find(row=>row.action==='exchange').strategy,'legacy')
 assert.equal(result.differences.find(row=>row.action==='enter').strategy,'action_override')
 input.legacyAfter=input.legacyAfter.filter(row=>row.action!=='exchange')
 assert.equal(evaluate(input).decision,'reject');assert.equal(evaluate(input).differences.find(row=>row.action==='exchange').after,'unknown')
})
test('action closure needs prior proof and separate evidence; unknown is never enabled',()=>{
 const input=rehearsal(),evaluate=require('../out/lib/content-cutover-preflight').evaluateContentCutoverPreflight
 input.observedBefore.find(row=>row.action==='exchange').availability='unknown'
 input.proposedAfter[0].actionOverrides.exchange=action(false)
 assert.ok(evaluate(input).blockers.some(value=>value.startsWith('action_closure_without_before_proof:')))
 input.proposedAfter[0].actionOverrides.exchange=action(true,{readiness:'unverified'})
 assert.ok(evaluate(input).blockers.some(value=>value.startsWith('invalid_input:action_readiness:')))
})
test('atomic caller rollback undoes partial state, revision and audit together',t=>{
 const {db,store,update}=fixture(t)
 assert.throws(()=>db.transaction(()=>{update('gacha:1',{actionOverrides:{enter:action()}});throw new Error('caller abort')})(),/caller abort/)
 assert.equal(store.revision(),0);assert.equal(store.allowed('gacha:1','enter',now),null)
 assert.equal(db.prepare('SELECT count(*) n FROM content_operations_audit').get().n,0)
})
test('omitted action member fields preserve the exact prior scope through close and reopen',t=>{
 const {store,update}=fixture(t);update('pass_card_event:15',{actionOverrides:{enter:action(true,{missionKeys:enterKeys})}})
 update('pass_card_event:15',{actionOverrides:{enter:action(false)}})
 update('pass_card_event:15',{actionOverrides:{enter:action()}})
 assert.deepEqual(store.state('pass_card_event:15').actionOverrides.enter.missionKeys,[...enterKeys].sort())
 assert.equal(store.scopedAllowed('pass_card_event:15','mission','7:59','enter',now),false)
})
