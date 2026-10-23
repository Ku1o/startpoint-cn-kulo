'use strict'
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript')
const root=path.resolve(__dirname,'..'),catalog=require('../assets/content_catalog.json')
const historyEvidence=require('../assets/content_history_definition_evidence.json')
const loaderNames=['src/lib/assets.ts','src/lib/content-master.ts','src/lib/shop-sales.ts','src/lib/multi-special-exchange.ts',
 'src/lib/content-quest-rules.ts','src/lib/content-shop-rules.ts']
const sha=file=>require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')
// Use the reviewed migration receipt; never recapture current bytes to bless a fixture.
function reviewedRow(key){
 const original=row(key),candidate=historyEvidence.existingEvidenceRebind[key]
 assert.ok(original&&candidate,key+' reviewed loader transition')
 const field=candidate.kind==='exact'?'exactDefinitionEvidence':'currentParentDefinitionEvidence'
 assert.equal(candidate.status,'candidate_requires_reviewed_loader_transition',key)
 assert.equal(candidate.nativeRowMatchesCatalog,true,key)
 assert.equal(candidate.dependencyDigestUnchanged,true,key)
 assert.deepEqual(candidate.previousEvidence,original[field],key+' complete previous proof')
 const {loaders:previous,...oldProof}=candidate.previousEvidence,{loaders:next,...newProof}=candidate.evidence
 assert.deepEqual(newProof,oldProof,key+' unchanged non-loader proof')
 assert.deepEqual(Object.keys(previous).sort(),loaderNames.slice(0,4).sort(),key)
 assert.deepEqual(Object.keys(next).sort(),[...loaderNames].sort(),key)
 assert.equal(previous['src/lib/assets.ts'],'c106054a9be76b83f0bfb94829059c6318ff8365c31d3dff12ce012fa619945d',key)
 for(const source of loaderNames)assert.equal(next[source],sha(source),key+' '+source)
 for(const source of loaderNames.slice(1,4))assert.equal(next[source],previous[source],key)
 return {...original,[field]:candidate.evidence}
}
function helper(overrides={}){
 const filename=path.join(root,'src/lib/content-definition-evidence.ts'),instance=new Module(filename,module),original=instance.require.bind(instance)
 instance.require=name=>name==='node:fs'?{...fs,
  readFileSync:(file,...args)=>Object.hasOwn(overrides,path.resolve(file))?overrides[path.resolve(file)]:fs.readFileSync(file,...args),
  openSync:(file,...args)=>fs.openSync(overrides.__openFiles?.[path.resolve(file)]??file,...args)}:
  name==='./exchange-campaign-definitions'?require('../out/lib/exchange-campaign-definitions'):original(name)
 instance._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,filename)
 return instance.exports
}
const row=key=>catalog.rows.find(r=>r.key===key)
function altered(file,mutate){const value=JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));mutate(value);return {[path.join(root,file)]:JSON.stringify(value)}}
function uploadMember(logical){const hash=require('node:crypto').createHash('sha1').update(logical+'K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy').digest('hex');return `production/upload/${hash.slice(0,2)}/${hash.slice(2)}`}
function zip(member,contents){
 const name=Buffer.from(member),body=Buffer.from(contents),local=Buffer.alloc(30),central=Buffer.alloc(46),end=Buffer.alloc(22)
 local.writeUInt32LE(0x04034b50,0);local.writeUInt16LE(20,4);local.writeUInt32LE(body.length,18);local.writeUInt32LE(body.length,22);local.writeUInt16LE(name.length,26)
 central.writeUInt32LE(0x02014b50,0);central.writeUInt16LE(20,4);central.writeUInt16LE(20,6);central.writeUInt32LE(body.length,20);central.writeUInt32LE(body.length,24);central.writeUInt16LE(name.length,28)
 end.writeUInt32LE(0x06054b50,0);end.writeUInt16LE(1,8);end.writeUInt16LE(1,10);end.writeUInt32LE(central.length+name.length,12);end.writeUInt32LE(local.length+name.length+body.length,16)
 return Buffer.concat([local,name,body,central,name,end])
}
test('reviewed precise receipts bind all six current loaders while original catalog proofs remain unchanged',()=>{
 const api=helper(),exact=catalog.rows.filter(r=>r.exactDefinitionEvidence)
 assert.equal(exact.length,1056)
 assert.equal(historyEvidence.source.catalogSha256,sha('assets/content_catalog.json'))
 const Database=require('better-sqlite3'),db=new Database(':memory:')
 try{
  const store=require('../out/lib/content-operations').createContentOperationsStore(db)
  for(const r of exact){
   assert.equal(api.matchExactDefinition(r,root).matchesCatalog,false,r.key+' old loader proof must remain stale alone')
   assert.equal(api.matchExactDefinition(reviewedRow(r.key),root).matchesCatalog,true,r.key)
   assert.equal(store.runtimeDefinitions.get(r.key).matchesCatalog,true,r.key+' compiled reviewed runtime')
  }
  for(const key of ['event_item_shop:700000','rush_event:700001','rush_event:700099'])
   assert.equal(api.matchExactDefinition(reviewedRow(key),root).matchesCatalog,true,key)
  for(const key of ['event_item_shop:5000','world_story_event:400001'])
   assert.notEqual(store.runtimeDefinitions.get(key).digest,api.matchExactDefinition(reviewedRow(key),root).digest,
    key+' compiled runtime also binds native shop/quest identity')
 }finally{db.close()}
 assert.equal(api.matchExactDefinition(row('gacha:80001'),root),null)
})
test('unrelated whole-table additions do not stale an unchanged product',()=>{
 assert.equal(helper().matchExactDefinition(reviewedRow('event_item_shop:5000'),root).matchesCatalog,true)
 const api=helper(altered('assets/event_item_shop.json',v=>{v['12']['1']['987654321']={costs:[],rewards:[],stock:1}}))
 assert.equal(api.matchExactDefinition(reviewedRow('event_item_shop:5000'),root).matchesCatalog,true)
})
test('effective row, parent mapping, absent overlay insertion and loader changes invalidate precise receipts',()=>{
 const original=reviewedRow('event_item_shop:5000')
 assert.equal(helper().matchExactDefinition(original,root).matchesCatalog,true,'negative cases start from a matching receipt')
 const mutations=[
  altered('assets/event_item_shop.json',v=>{v['12']['1']['5000'].stock+=1}),
  altered('assets/event_item_shop_id_map.json',v=>{v['5000'].eventId=2}),
  altered('assets/event_item_shop_id_map_rank_p5b.json',v=>{v['5000']={eventType:11,eventId:700099}}),
  ...loaderNames.map(source=>({[path.join(root,source)]:fs.readFileSync(path.join(root,source),'utf8')+'\n// different loader bytes\n'})),
 ]
 for(const mutation of mutations)assert.equal(helper(mutation).matchExactDefinition(original,root).matchesCatalog,false)
 const proof={...original,definitionDigest:'f'.repeat(64)}
 assert.equal(helper().matchExactDefinition(proof,root).matchesCatalog,false)
})
test('parent receipt binds the full sibling and mapping set without granting any quest action',()=>{
 const original=reviewedRow('score_attack_event:1')
 assert.equal(helper().matchExactDefinition(original,root).matchesCatalog,true)
 const api=helper(altered('assets/event_item_shop.json',v=>{v['12']['1']['987654321']={costs:[],rewards:[],stock:1}}))
 assert.equal(api.matchExactDefinition(original,root).matchesCatalog,false)
 const plan=require('../assets/content_july_controls.json'),parent=plan.controls.find(r=>r.key==='score_attack_event:1')
 assert.deepEqual(Object.keys(parent.actionOverrides).sort(),['enter','exchange','visible'])
 assert.ok(parent.actionOverrides.enter.questKeys.length>0,'quest participation now has its own reviewed scope')
 for(const key of parent.actionOverrides.enter.questKeys)assert.equal(catalog.questMap[key],parent.key)
 const Database=require('better-sqlite3'),db=new Database(':memory:'),storeApi=require('../out/lib/content-operations-store')
 try{
  storeApi.initializeContentOperationsSchema(db)
  const store=new storeApi.ContentOperationsStore(db,{...catalog,rows:[original]},()=>['visible','enter','exchange'],r=>helper().matchExactDefinition(r,root),
   undefined,undefined,undefined,require('../out/lib/content-operations-defaults').defaultContentDecision)
  const now=Date.now()
  store.update(original.key,{expectedRevision:0,catalogDigest:store.digest,reason:'reviewed exchange-only fixture',
   actionOverrides:{visible:{enabled:true,endsAtMs:null,readiness:'verified',evidence:'reviewed exact shop'},
    exchange:{enabled:true,endsAtMs:null,readiness:'verified',evidence:'reviewed exact shop'}}},now)
  assert.equal(store.allowed(original.key,'exchange',now),true)
  assert.equal(store.allowed(original.key,'enter',now),false,'a shop receipt does not grant independently reviewed quest participation')
 }finally{db.close()}
 const rush=reviewedRow('rush_event:700099')
 assert.deepEqual(rush.currentParentDefinitionEvidence.newUncataloguedChildren,
  Array.from({length:9},(_,i)=>String(9700121+i)))
 const changed=helper(altered('assets/event_item_shop.json',v=>{v['11']['700099']['9700121'].stock+=1}))
 assert.equal(changed.matchExactDefinition(rush,root).matchesCatalog,false)
 const rushControl=plan.controls.find(r=>r.key==='rush_event:700099')
 assert.deepEqual(Object.keys(rushControl.actionOverrides).sort(),['claim','enter','exchange','visible'])
 const reviewedProducts=plan.controls.filter(control=>row(control.key)?.parentKey===rush.key&&control.actionOverrides.exchange?.enabled)
 assert.deepEqual(reviewedProducts.map(control=>String(row(control.key).id)).sort(),
  [...rush.currentParentDefinitionEvidence.reviewedExistingChildren].sort())
 for(const id of rush.currentParentDefinitionEvidence.newUncataloguedChildren)
  assert.ok(!plan.controls.some(control=>control.key==='event_item_shop:'+id),'new sibling is not approved by the parent receipt')
})
test('all 8578 audited effective native event-shop accessors match the frozen review while changed rows stay excluded',()=>{
 const report=require('../assets/content_history_readiness.json'),products=report.childIndex.catalogChildren
 assert.equal(report.sourceSnapshot.catalogSha256,sha('assets/content_catalog.json'))
 assert.equal(report.sourceSnapshot.manifestSha256,sha('assets/asset-patch/manifest.json'))
 for(const source of ['assets/event_item_shop.json','assets/event_item_shop_id_map.json','assets/content_history_shop_rules.json',...loaderNames])
  assert.equal(report.sourceSnapshot.serverSources[source].sha256,sha(source),source+' reviewed source identity')
 const selected=Object.values(products).filter(p=>p.type==='event_item_shop'&&p.effectiveFieldAudit?.definitionFieldsMatched===true)
 assert.equal(selected.length,8578)
 const assets=require('../out/lib/assets'),ops=require('../out/lib/content-operations')
 for(const product of selected){
  const r=row(product.key),item=assets.getShopItemSync(4,r.id)
  assert.equal(product.nativeRowMatchesCatalog,true,product.key)
  const expected=product.effectiveFieldAudit.effectiveGetterValue
  // JSON snapshots omit only these optional undefined properties; preserve explicit zero/null values.
  assert.deepEqual(item,{...expected,dailyStock:expected.dailyStock,monthlyStock:expected.monthlyStock},product.key+' actual winning accessor')
  assert.ok(ops.contentCapabilities(r).includes('exchange'),product.key)
 }
 const selectedKeys=new Set(selected.map(p=>p.key))
 assert.ok(!selectedKeys.has('event_item_shop:59001010'))
 assert.ok(!selectedKeys.has('event_item_shop:9700118'))
 assert.equal(products['event_item_shop:9700118'].effectiveFieldAudit.definitionFieldsMatched,false)
 assert.ok(selectedKeys.has('event_item_shop:9700117'))
})
test('current CDN campaign receipts bind all 33 audited exchange rules',()=>{
 const api=helper(),campaigns=catalog.rows.filter(r=>r.campaignDefinitionEvidence)
 assert.equal(campaigns.length,33)
 for(const r of campaigns)assert.equal(api.matchCampaignDefinition(r,root).matchesCatalog,true,r.key)
 const bad={...campaigns[0],campaignDefinitionEvidence:{...campaigns[0].campaignDefinitionEvidence,runtimeDigest:'0'.repeat(64)}}
 assert.equal(api.matchCampaignDefinition(bad,root).matchesCatalog,false)
})
test('campaign winning bytes fail closed while unrelated CDN increments retain persisted exchange identity',()=>{
 const api=helper(),campaigns=catalog.rows.filter(r=>r.campaignDefinitionEvidence)
 const original=new Map(campaigns.map(r=>[r.key,api.matchCampaignDefinition(r,root)]))
 for(const r of campaigns)assert.equal(original.get(r.key).matchesCatalog,true,r.key)
 const previousCdnDir=process.env.CDN_DIR
 try{
  process.env.CDN_DIR=path.join(root,'.cdn')
  assert.deepEqual(helper().matchCampaignDefinition(campaigns[0],root),original.get(campaigns[0].key),'configured pristine CDN root')
 }finally{if(previousCdnDir===undefined)delete process.env.CDN_DIR;else process.env.CDN_DIR=previousCdnDir}
 const manifest=path.join(root,'assets/asset-patch/manifest.json')
 const whitespace=helper({[manifest]:fs.readFileSync(manifest,'utf8')+' '})
 for(const r of campaigns)assert.deepEqual(whitespace.matchCampaignDefinition(r,root),original.get(r.key),r.key+' whitespace-only manifest change')
 const fixture=fs.mkdtempSync(path.join(process.env.CONTENT_EXACT_TASK_ROOT,'campaign-chain-fixture-'))
 try{
  const unrelated=path.join(fixture,'unrelated.zip'),changed=path.join(fixture,'changed.zip'),broken=path.join(fixture,'broken.zip')
  fs.writeFileSync(unrelated,zip('production/upload/00/unrelated',Buffer.from('new unrelated icon')))
  const primary=Object.keys(campaigns[0].campaignDefinitionEvidence.currentMasterSources)[0]
  fs.writeFileSync(changed,zip(uploadMember(primary),Buffer.from('modified master bytes')))
  fs.writeFileSync(broken,Buffer.from('invalid zip'))
  const addPatch=(archive)=>{const data=JSON.parse(fs.readFileSync(manifest,'utf8'));data.patches.push({enabled:true,archive});return JSON.stringify(data)}
  const virtual=name=>path.join(root,'assets/asset-patch/active',name)
  const unrelatedApi=helper({[manifest]:addPatch('campaign-unrelated-fixture.zip'),__openFiles:{[virtual('campaign-unrelated-fixture.zip')]:unrelated}})
  for(const r of campaigns)assert.deepEqual(unrelatedApi.matchCampaignDefinition(r,root),original.get(r.key),r.key+' unrelated ZIP increment')
  const Database=require('better-sqlite3'),storeApi=require('../out/lib/content-operations-store'),db=new Database(':memory:')
  try{
   storeApi.initializeContentOperationsSchema(db)
   const one={...catalog,rows:[campaigns[0]],questMap:{},missionMap:{}}
   const makeStore=runtime=>new storeApi.ContentOperationsStore(db,one,()=>['exchange'],r=>runtime.matchCampaignDefinition(r,root))
   const before=makeStore(api),now=Date.now()
   before.update(campaigns[0].key,{expectedRevision:0,catalogDigest:before.digest,reason:'reviewed campaign exchange fixture',
    actionOverrides:{exchange:{enabled:true,endsAtMs:null,readiness:'verified',evidence:'reviewed campaign master'}}},now)
   assert.equal(before.allowed(campaigns[0].key,'exchange',now),true)
   const restarted=makeStore(unrelatedApi)
   assert.equal(restarted.contentDigests.get(campaigns[0].key),before.contentDigests.get(campaigns[0].key))
   assert.equal(restarted.allowed(campaigns[0].key,'exchange',now),true,'persisted exchange survives unrelated CDN increment')
  }finally{db.close()}
  const changedApi=helper({[manifest]:addPatch('campaign-changed-fixture.zip'),__openFiles:{[virtual('campaign-changed-fixture.zip')]:changed}})
  assert.equal(changedApi.matchCampaignDefinition(campaigns[0],root).matchesCatalog,false,'changed winning master fails closed')
  assert.notEqual(changedApi.matchCampaignDefinition(campaigns[0],root).digest,original.get(campaigns[0].key).digest)
  const mutable={}
  const sameProcess=helper(mutable)
  assert.deepEqual(sameProcess.matchCampaignDefinition(campaigns[0],root),original.get(campaigns[0].key))
  mutable[manifest]=addPatch('campaign-changed-fixture.zip')
  mutable.__openFiles={[virtual('campaign-changed-fixture.zip')]:changed}
  assert.equal(sameProcess.matchCampaignDefinition(campaigns[0],root).matchesCatalog,false,'manifest identity invalidates process cache')
  const allMasters=new Set(campaigns.flatMap(r=>Object.keys(r.campaignDefinitionEvidence.currentMasterSources)))
  assert.equal(allMasters.size,6)
  for(const logical of allMasters){
   const impacted=campaigns.find(r=>Object.hasOwn(r.campaignDefinitionEvidence.currentMasterSources,logical))
   fs.writeFileSync(changed,zip(uploadMember(logical),Buffer.from('modified '+logical)))
   const changedSource=helper({[manifest]:addPatch('campaign-changed-fixture.zip'),__openFiles:{[virtual('campaign-changed-fixture.zip')]:changed}})
   assert.equal(changedSource.matchCampaignDefinition(impacted,root).matchesCatalog,false,logical+' changed winning bytes')
  }
  const brokenApi=helper({[manifest]:addPatch('campaign-broken-fixture.zip'),__openFiles:{[virtual('campaign-broken-fixture.zip')]:broken}})
  assert.equal(brokenApi.matchCampaignDefinition(campaigns[0],root).matchesCatalog,false,'unreadable chain fails closed')
  fs.writeFileSync(changed,zip(uploadMember(primary),Buffer.from('modified master bytes')))
  const baseline=path.join(root,campaigns[0].campaignDefinitionEvidence.currentMasterArchives[primary])
  const baselineApi=helper({__openFiles:{[baseline]:changed}})
  assert.equal(baselineApi.matchCampaignDefinition(campaigns[0],root).matchesCatalog,false,'baseline bytes are reread, not trusted from receipt')
 }finally{
  for(const name of fs.readdirSync(fixture))fs.unlinkSync(path.join(fixture,name))
  fs.rmdirSync(fixture)
 }
})
