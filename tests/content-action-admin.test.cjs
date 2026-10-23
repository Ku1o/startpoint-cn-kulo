'use strict'
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const ts=require('typescript'),Sqlite=require('better-sqlite3')
const source=fs.readFileSync(path.resolve(__dirname,'../admin/src/pages/ContentOperations.tsx'),'utf8')
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022},reportDiagnostics:true})
assert.ok(!compiled.diagnostics.some(item=>item.category===ts.DiagnosticCategory.Error))
const moduleValue={exports:{}};vm.runInNewContext(compiled.outputText,{module:moduleValue,exports:moduleValue.exports,require:()=>({})})
const {actionPatchFields:build,actionState,auditActionChanges}=moduleValue.exports,plain=value=>JSON.parse(JSON.stringify(value))
const now=Date.parse('2026-10-13T00:00:00Z'),draft={enabled:true,readiness:'verified',evidence:'exact synthetic action evidence',endsAtMs:null}
const enterKeys=['6:57','6:58','6:59','6:60','7:57','7:58','8:86','8:87','8:88','8:89','8:90','8:91'],claimKeys=[...enterKeys,'7:59','7:60']
const {ContentOperationsStore,initializeContentOperationsSchema,CONTENT_ACTIONS}=require('../out/lib/content-operations-store')
function fixture(t){
 const db=new Sqlite(':memory:');t.after(()=>db.close());initializeContentOperationsSchema(db)
 const catalog={schemaVersion:1,source:{assetVersion:'fixture',manifestSha256:'fixture'},baselineTimeMs:1,baselineEvidence:'fixture',resources:{},missing:[],questMap:{},missionMap:Object.fromEntries(claimKeys.map(member=>[member,'pass_card_event:15'])),rows:['gacha:1','pass_card_event:15'].map(key=>({key,type:key.split(':')[0],id:+key.split(':')[1],name:'synthetic',source:'fixture',originalStartMs:1,originalEndMs:2,originalExchangeEndMs:3,windowCandidate:true,browseCandidate:true}))}
 const store=new ContentOperationsStore(db,catalog,()=>CONTENT_ACTIONS),patch=(key,payload)=>store.update(key,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'admin exact action fixture',...plain(payload)},now)
 return {store,patch}
}
test('review default sends metadata only even if stale action draft or empty scope remains in memory',t=>{
 const {store,patch}=fixture(t),payload=build(undefined,draft,true,[],true,[])
 assert.deepEqual(plain(payload),{readiness:'verified',evidence:draft.evidence});patch('gacha:1',payload)
 assert.equal(store.allowed('gacha:1','enter',now),null);assert.equal(store.allowed('gacha:1','exchange',now),null)
})
test('single draw selection neither serializes absent exchange/claim nor takes them over',t=>{
 const {store,patch}=fixture(t),payload=plain(build('enter',draft,false,[],false,[]))
 assert.deepEqual(Object.keys(payload),['actionOverrides']);assert.deepEqual(Object.keys(payload.actionOverrides),['enter'])
 patch('gacha:1',payload);assert.equal(store.allowed('gacha:1','enter',now),true)
 assert.equal(store.allowed('gacha:1','exchange',now),null);assert.equal(store.allowed('gacha:1','claim',now),null)
 assert.equal(actionState(store.state('gacha:1'),'exchange'),undefined)
})
test('independent admin enter edit preserves existing 14 claims, old deadline and explicit audit ranges',t=>{
 const {store,patch}=fixture(t)
 const before=patch('pass_card_event:15',{readiness:'verified',evidence:'old claim proof',flags:{visible:true,enter:true,claim:true,exchange:false},endsAtMs:now+1000,missionKeys:claimKeys})
 const payload=build('enter',draft,false,[],true,enterKeys)
 const after=patch('pass_card_event:15',payload)
 assert.deepEqual(Object.keys(plain(payload).actionOverrides),['enter'])
 assert.equal(store.scopedAllowed(after.key,'mission','7:59','enter',now),false)
 assert.equal(store.scopedAllowed(after.key,'mission','7:59','claim',now),true)
 assert.equal(actionState(after,'claim').endsAtMs,now+1000)
 const changes=plain(auditActionChanges(before,after)),entered=changes.find(value=>value.action==='enter'),claimed=changes.find(value=>value.action==='claim')
 assert.deepEqual(entered.before.missionKeys,[...claimKeys].sort());assert.deepEqual(entered.after.missionKeys,[...enterKeys].sort())
 assert.deepEqual(claimed.before,claimed.after);assert.deepEqual(claimed.after.missionKeys,[...claimKeys].sort())
})
test('new member scope defaults empty and explicit whole-scope request is distinct from retaining old scope',t=>{
 const {store,patch}=fixture(t),empty=plain(build('enter',draft,false,[],true,[]))
 assert.deepEqual(empty.actionOverrides.enter.missionKeys,[]);assert.throws(()=>patch('pass_card_event:15',empty),/范围不能为空/)
 const scoped=build('enter',draft,false,[],true,enterKeys);patch('pass_card_event:15',scoped)
 const close=plain(build('enter',{...draft,enabled:false},false,[],false,[]))
 assert.equal('missionKeys' in close.actionOverrides.enter,false);patch('pass_card_event:15',close)
 patch('pass_card_event:15',build('enter',draft,false,[],false,[]))
 assert.equal(store.scopedAllowed('pass_card_event:15','mission','7:59','enter',now),false)
 const all=plain(build('claim',draft,false,[],true,null));assert.equal(all.actionOverrides.claim.missionKeys,null)
 patch('pass_card_event:15',all);assert.equal(store.scopedAllowed('pass_card_event:15','mission','7:59','claim',now),true)
})
test('claim-only admin edit retains existing enter and exchange; per-action evidence/deadline stay separate',t=>{
 const {store,patch}=fixture(t);patch('pass_card_event:15',build('enter',draft,false,[],true,enterKeys))
 const claim={...draft,evidence:'historical 14-task claim proof',endsAtMs:now+2000}
 patch('pass_card_event:15',build('claim',claim,false,[],true,claimKeys))
 assert.equal(store.allowed('pass_card_event:15','enter',now+2001),true);assert.equal(store.allowed('pass_card_event:15','claim',now+2001),false)
 assert.equal(store.allowed('pass_card_event:15','exchange',now),null)
 const changes=plain(auditActionChanges(null,store.state('pass_card_event:15')))
 assert.equal(changes.find(value=>value.action==='exchange').after,null)
 assert.equal(changes.find(value=>value.action==='claim').after.evidence,claim.evidence)
})
