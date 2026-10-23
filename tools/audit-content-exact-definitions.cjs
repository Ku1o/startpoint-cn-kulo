'use strict'
// Compare former and current effective dependency sets before recording precise receipts.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),Module=require('node:module'),ts=require('typescript')
const args=process.argv.slice(2),get=name=>args[args.indexOf('--'+name)+1]
for(const name of ['repo','previous','closure','resources','review','output'])if(!args.includes('--'+name))throw Error('missing --'+name)
const root=path.resolve(get('repo')),previous=path.resolve(get('previous')),output=path.resolve(get('output'))
const read=p=>JSON.parse(fs.readFileSync(p,'utf8')),sha=x=>crypto.createHash('sha256').update(x).digest('hex')
const filename=path.join(root,'src/lib/content-definition-evidence.ts'),instance=new Module(filename,module)
instance.require=name=>name==='./exchange-campaign-definitions'
 ? (()=>{const source=path.join(root,'src/lib/exchange-campaign-definitions.ts'),child=new Module(source,instance)
    child._compile(ts.transpileModule(fs.readFileSync(source,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,source)
    return child.exports})()
 : Module.prototype.require.call(instance,name)
instance._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,filename)
const {captureExactDefinition:capture,stableDefinitionJson:stable,exactDefinitionHash:hash}=instance.exports
const catalog=read(path.join(root,'assets/content_catalog.json')),oldCatalog=read(path.join(previous,'assets/content_catalog.json'))
const oldRows=new Map(oldCatalog.rows.map(r=>[r.key,r])),rows=new Map(catalog.rows.map(r=>[r.key,r]))
const closure=read(get('closure')),resources=read(get('resources')),review=read(get('review'))
if(args.includes('--additional')){
 const additional=read(get('additional'))
 if(additional.source.manifestSha256!==resources.source.manifestSha256)throw Error('resource chain changed between audits')
 const replaced=new Set(additional.products.map(product=>product.key))
 closure.products=closure.products.filter(product=>!replaced.has(product.key)).concat(additional.products)
 for(const [logical,current] of Object.entries(additional.resourceIdentities)){
  const previous=catalog.resources[logical]
  resources.resources[logical]={previous,current,unchanged:!!previous&&previous.sha256===current.sha256}
 }
 for(const product of additional.products)resources.productClosures[product.key]={verified:product.status==='verified',failures:[...product.issues,...product.missingRefs]}
}
const pending=new Set(review.rows.filter(r=>r.group==='july_pending_review').map(r=>r.key))
const priorProducts=new Map(closure.products.map(r=>[r.key,r])),plan=read(path.join(root,'assets/content_july_controls.json'))
const originalKeys=new Set(plan.controls.map(r=>r.key)),comparisons=[],blocked=[],selected=[]
const loaderStatements=(base)=>{
 const source=fs.readFileSync(path.join(base,'src/lib/assets.ts'),'utf8'),ast=ts.createSourceFile('assets.ts',source,ts.ScriptTarget.Latest,true)
 const names=new Set(['getShopItemSync','getGenericShopItemsSync','getEventShopItemsSync','getBossCoinShopItemsSync','addShopCompatibilityPeriod','addShopCompatibilityPeriodToItems','RUSH_RERUN_SHOP_PERIODS'])
 const imports=['treasureShopItems','equipmentEnhancementShopItems','bossCoinShopItems','bossCoinShopItemCategoryMap','generalShopItems','starGrainShopItems','eventItemShopIdMap','eventItemShopItems']
 return ast.statements.filter(s=>ts.isImportDeclaration(s)&&imports.some(n=>new RegExp('\\b'+n+'\\b').test(s.getText(ast)))
  || (ts.isFunctionDeclaration(s)&&names.has(s.name?.text)) || (ts.isVariableStatement(s)&&s.declarationList.declarations.some(d=>names.has(d.name.getText(ast))))).map(s=>s.getText(ast)).join('\n')
}
const oldLoader=loaderStatements(previous),newLoader=loaderStatements(root)
if(oldLoader!==newLoader)throw Error('shop loader imports/functions/compatibility changed; manual semantic review required')
for(const file of ['src/lib/content-master.ts','src/lib/shop-sales.ts','src/lib/multi-special-exchange.ts'])
 if(!fs.readFileSync(path.join(previous,file)).equals(fs.readFileSync(path.join(root,file))))throw Error('loader changed: '+file)
const proofCache=new Map()
const previousInputs=new Map(),currentInputs=new Map()
let currentParentProof=null
if(args.includes('--current-parent')){
 const review=read(get('current-parent')),key=review.parent,old=oldRows.get(key),row=rows.get(key)
 if(key!=='rush_event:700099'||!old||!row||old.definitionDigest!==row.definitionDigest||old.definitionEvidence?.status!=='matched'
    ||review.oldChildrenAndMappingsUnchanged!==true||review.newChildrenAbsentFromCatalog!==true)throw Error('current parent review is not applicable')
 const before=capture(old,previous,previousInputs),after=capture(row,root,currentInputs)
 if(!before||!after)throw Error('current parent dependency capture missing')
 const childKey='assets/event_item_shop.json#11/700099',mapKey='assets/event_item_shop_id_map.json#parent:11:700099'
 const oldChildren=before.dependencies[childKey],newChildren=after.dependencies[childKey]
 const oldMap=before.dependencies[mapKey],newMap=after.dependencies[mapKey]
 const added=Object.keys(newChildren).filter(id=>!Object.hasOwn(oldChildren,id)).sort()
 const existing=Object.keys(oldChildren).sort()
 if(stable(added)!==stable(review.addedChildren)||stable(existing)!==stable(review.oldChildren)
    ||Object.keys(newChildren).length!==existing.length+added.length
    ||Object.keys(newMap).length!==Object.keys(oldMap).length+added.length
    ||existing.some(id=>stable(oldChildren[id])!==stable(newChildren[id])||stable(oldMap[id])!==stable(newMap[id])))
    throw Error('current parent child or mapping set differs from review')
 for(const id of added){
  if(rows.has(`event_item_shop:${id}`)||newMap[id]?.eventType!==11||Number(newMap[id]?.eventId)!==700099)
   throw Error('new parent child is catalogued or differently mapped: '+id)
 }
 const changed=Object.keys({...before.dependencies,...after.dependencies}).filter(source=>stable(before.dependencies[source])!==stable(after.dependencies[source]))
 if(stable(changed.sort())!==stable([childKey,mapKey].sort()))throw Error('parent changed beyond reviewed child set')
 for(const source of row.definitionSources)if(!resources.resources[source]?.unchanged)throw Error('current parent resource changed: '+source)
 const receipt={schemaVersion:1,key,definitionDigest:row.definitionDigest,dependencyDigest:after.digest,
  loaders:after.loaders,previousServerDefinitionDigest:old.serverDefinitionDigest,
  reviewedExistingChildren:existing,newUncataloguedChildren:added}
 currentParentProof={key,receipt,added,existing,digest:hash({key,dependencyDigest:after.digest,loaders:after.loaders})}
}
const evidenceFor=row=>{
 if(proofCache.has(row.key))return proofCache.get(row.key)
 const old=oldRows.get(row.key)
 if(!old||old.definitionDigest!==row.definitionDigest||old.definitionEvidence?.status!=='matched')return {reason:'previous client/server definition not matched'}
 for(const source of old.definitionEvidence.serverSources)
  if(sha(fs.readFileSync(path.join(previous,source)))!==oldCatalog.serverResources[source]?.sha256)return {reason:'previous source no longer matches captured evidence: '+source}
 const before=capture(old,previous,previousInputs),after=capture(row,root,currentInputs)
 if(!before||!after)return {reason:'precise dependency selector unsupported'}
 const changed=Object.keys({...before.dependencies,...after.dependencies}).filter(k=>stable(before.dependencies[k])!==stable(after.dependencies[k]))
 comparisons.push({key:row.key,beforeDigest:before.digest,afterDigest:after.digest,unchanged:!changed.length,changedDependencies:changed,
  dependencies:Object.keys(after.dependencies),oldLoaderSha256:before.loaders,newLoaderSha256:after.loaders})
 if(changed.length)return {reason:'effective dependency changed',details:changed}
 const receipt={schemaVersion:1,key:row.key,oldDefinitionMatched:true,definitionDigest:row.definitionDigest,dependencyDigest:after.digest,loaders:after.loaders,previousServerDefinitionDigest:old.serverDefinitionDigest}
 const result={receipt,digest:hash({key:row.key,dependencyDigest:after.digest,loaders:after.loaders})}
 proofCache.set(row.key,result)
 return result
}
const candidateProducts=closure.products.filter(p=>pending.has(p.key))
for(const product of candidateProducts){
 const row=rows.get(product.key)
 if(product.status!=='verified'){blocked.push({key:row.key,reason:'prior action/resource audit incomplete',issues:product.issues,missing:product.missingRefs});continue}
 if(!resources.productClosures[row.key]?.verified){blocked.push({key:row.key,reason:'current resource closure incomplete',details:resources.productClosures[row.key]});continue}
 if(row.parentKey){
  const parent=rows.get(row.parentKey)
  if(!pending.has(parent.key)&&!originalKeys.has(parent.key)){blocked.push({key:row.key,reason:'parent outside reviewed fixed-day target',parent:parent.key});continue}
  const badResource=parent.definitionSources.filter(l=>!resources.resources[l]?.unchanged)
  if(badResource.length){blocked.push({key:row.key,reason:'parent resource changed',details:badResource});continue}
 }
 const proof=evidenceFor(row)
 if(!proof.receipt){blocked.push({key:row.key,...proof});continue}
 if(row.parentKey){const proof=evidenceFor(rows.get(row.parentKey));if(!proof.receipt&&row.parentKey!==currentParentProof?.key){blocked.push({key:row.key,reason:'parent exact dependencies changed',details:proof});continue}}
 row.exactDefinitionEvidence=proof.receipt
 selected.push({row,product,proof})
}
const parentKeys=[...new Set(selected.map(s=>s.row.parentKey).filter(Boolean))]
const add=(row,actions,evidence)=>{
 if(originalKeys.has(row.key))return
 plan.controls.push({key:row.key,group:'permanent',expectedDefinitionDigest:row.definitionDigest,expectedServerDefinitionDigest:row.serverDefinitionDigest,evidence,
  actionOverrides:Object.fromEntries(actions.map(action=>[action,{enabled:true,endsAtMs:null,readiness:'verified',evidence}]))})
 originalKeys.add(row.key)
}
for(const key of parentKeys){
 const row=rows.get(key),proof=evidenceFor(row)
 if(key===currentParentProof?.key)row.currentParentDefinitionEvidence=currentParentProof.receipt
 else row.exactDefinitionEvidence=proof.receipt
 add(row,['visible','exchange'],'Exact fixed-day shop parent/complete child-set review; enables shop exchange only; quest participation remains independently closed')
}
for(const {row} of selected)add(row,['visible','exchange'],'Exact old/current winning item+mapping comparison; current common-chain row/thumbnail/reference proof; original durable stock/payment rules retained; device acceptance separate')
// Repair unchanged historical multi-special receipts too, without adding a July entry.
for(const row of catalog.rows.filter(r=>r.type==='multi_special_exchange_campaign')){
 const proof=evidenceFor(row)
 if(proof.receipt)row.exactDefinitionEvidence=proof.receipt
 else blocked.push({key:row.key,...proof})
}
// A separately reviewed historic shop remains outside the fixed-July bootstrap.
if(args.includes('--extra-master')&&args.includes('--extra-art')){
 const master=read(get('extra-master')),art=read(get('extra-art'))
 const product=rows.get('event_item_shop:700000'),parent=rows.get('rush_event:700001')
 const primary=master['master/shop/event_item_shop.orderedmap/700000']
 if(!primary||sha(JSON.stringify(primary.rows[0]))!==product.definitionDigest
    ||primary.tableSha256!==resources.resources['master/shop/event_item_shop.orderedmap']?.current?.sha256)
    throw Error('700000 current shop master row or table differs')
 for(const id of [49100,2370001]){
  const entry=master[`master/item/item.orderedmap/${id}`]
  if(!entry||entry.tableSha256!==resources.resources['master/item/item.orderedmap']?.current?.sha256)
    throw Error('700000 referenced current item master differs: '+id)
 }
 if(Object.keys(art).length<3||Object.values(art).some(entry=>entry.validFrame!==true))throw Error('700000 art frames unverified')
 for(const row of [product,parent]){
  const proof=evidenceFor(row)
  if(!proof.receipt)throw Error('700000 exact dependency changed: '+row.key+' '+JSON.stringify(proof))
  row.exactDefinitionEvidence=proof.receipt
 }
}
plan.sourceEvidence.exactShopDefinitionAuditSha256=hash({comparisons,sourceManifest:resources.source.manifestSha256,shopLoaderSemanticSha256:sha(newLoader)})
const groups={}
for(const item of blocked){groups[item.reason]??=[];groups[item.reason].push(item.key)}
const result={schemaVersion:1,scope:'isolated catalog/plan review only; no live activation',referenceDate:'2025-07-20',
 previousRoot:previous,currentRoot:root,closureFileSha256:sha(fs.readFileSync(get('closure'))),additionalProductsFileSha256:args.includes('--additional')?sha(fs.readFileSync(get('additional'))):null,currentManifestSha256:resources.source.manifestSha256,
 independentExact:args.includes('--extra-master')?{keys:['event_item_shop:700000','rush_event:700001'],
  currentMasterReceiptSha256:sha(fs.readFileSync(get('extra-master'))),currentArtReceiptSha256:sha(fs.readFileSync(get('extra-art'))),includedInJulyPlan:false}:null,
 currentParentReview:currentParentProof?{key:currentParentProof.key,reviewFileSha256:sha(fs.readFileSync(get('current-parent'))),
  retainedChildren:currentParentProof.existing,newUncataloguedChildren:currentParentProof.added,questParticipationIncluded:false}:null,
 loaderSemantics:{shopImportsAndFunctionsEqual:true,sha256:sha(newLoader),fullCurrentFilesBound:true},
 selectedProducts:selected.map(s=>s.row.key),selectedParents:parentKeys,planControls:plan.controls.length,comparisons,blocked,blockedGroups:groups,
 remainingCandidates:review.rows.filter(r=>r.group==='july_pending_review'&&!originalKeys.has(r.key)).map(r=>({key:r.key,
  reason:blocked.find(b=>b.key===r.key)?.reason??(r.key.startsWith('event_item_shop:')?'no prior exact product resource/rule audit':'mode-specific gameplay/mission/transaction proof incomplete'),
  capabilities:r.capabilities,priorGaps:r.gaps})),
 runtimeAndDeviceAvailabilityVerified:false}
fs.mkdirSync(output,{recursive:true})
fs.writeFileSync(path.join(output,'exact-definition-audit.json'),JSON.stringify(result,null,2)+'\n')
if(args.includes('--apply')){
 fs.writeFileSync(path.join(root,'assets/content_catalog.json'),JSON.stringify(catalog,null,2)+'\n')
 fs.writeFileSync(path.join(root,'assets/content_july_controls.json'),JSON.stringify(plan,null,2)+'\n')
}
console.log(JSON.stringify({selectedProducts:selected.length,selectedParents:parentKeys.length,planControls:plan.controls.length,remainingCandidates:result.remainingCandidates.length,blockedGroups:Object.fromEntries(Object.entries(groups).map(([k,v])=>[k,v.length])),applied:args.includes('--apply')}))
