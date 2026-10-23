'use strict'
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path')
const {createHash}=require('node:crypto'),{spawnSync}=require('node:child_process')
const root=path.resolve(__dirname,'..'),read=name=>JSON.parse(fs.readFileSync(path.join(root,'assets',name),'utf8'))
const inventory=read('content_history_readiness.json'),catalog=read('content_catalog.json')
const proof=read('content_history_definition_evidence.json'),presentation=read('content_presentation.json')
const rows=new Map(inventory.rows.map(row=>[row.key,row])),sha=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex')

test('event-shop native projection closes 8579 catalog products, preserves optional zero, and confines uniqueness to the original flag',()=>{
    const document=read('content_history_shop_rules.json'),products=document.products
    assert.equal(document.schemaVersion,1)
    assert.equal(document.source.catalogSha256,sha(path.join(root,'assets/content_catalog.json')))
    assert.equal(document.source.manifestSha256,sha(path.join(root,'assets/asset-patch/manifest.json')))
    const expected=catalog.rows.filter(row=>row.type==='event_item_shop'&&rows.has(row.parentKey))
    assert.equal(expected.length,8579)
    assert.deepEqual(Object.keys(products).sort(),expected.map(row=>row.key).sort())
    const unique=['10001476','10003146','10004466','10004496','10004526','10004527','10005185','10005255','10005256'].map(id=>'event_item_shop:'+id)
    assert.deepEqual(document.summary.equipmentOnlyPossessionOneKeys,unique)
    assert.deepEqual(document.summary.excludedCurrentOnlyKeys,Array.from({length:9},(_,i)=>'event_item_shop:'+(9700121+i)))
    assert.deepEqual(document.summary.limitValueCounts,{
        buy_max_count:{null:0,zero:0,negative:0,positive:8579},max_frequency:{null:172,zero:0,negative:0,positive:8407},
        daily_stock:{null:8487,zero:0,negative:0,positive:92},monthly_stock:{null:8579,zero:0,negative:0,positive:0}})
    for(const row of expected){
        const node=products[row.key],native=node.native,raw=node.source.raw
        assert.equal(node.parentKey,row.parentKey,row.key)
        assert.equal(raw.length,51,row.key)
        assert.equal(native.buy_max_count,Number(raw[29]),row.key)
        assert.equal(native.max_frequency,raw[30]==='(None)'?null:Number(raw[30]),row.key)
        assert.equal(native.daily_stock,raw[31]==='(None)'?null:Number(raw[31]),row.key)
        assert.equal(native.monthly_stock,null,row.key)
        assert.equal(native.kind1_equipment_only_possession_one,raw[50]==='true',row.key)
        assert.equal(node.source.rowSha256,row.definitionDigest,row.key)
        if(native.kind1_equipment_only_possession_one)assert.equal(native.kind1.kind,4,row.key)
        assert.equal(node.source.columnsRef,'source.fieldSchema.columns')
        assert.equal(node.source.columnsSha256,document.source.fieldSchema.columnsSha256)
    }
    assert.deepEqual(document.source.fieldSchema.columns.buy_max_count,[29])
    assert.deepEqual(document.source.fieldSchema.columns.kind1_equipment_only_possession_one,[50])
    assert.equal(document.scope.defaultEnabled,false)
    assert.equal(document.scope.gameplayStatus,'unreviewed')
    const python=String.raw`import sys,json,importlib.util
sys.dont_write_bytecode=True
s=importlib.util.spec_from_file_location('history','tools/build-content-history-readiness.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
raw=json.load(open('assets/content_history_shop_rules.json',encoding='utf8'))['products']['event_item_shop:1']['source']['raw']
v=m.project_event_shop_native(raw);assert v['monthly_stock'] is None
zero=raw.copy();zero[29]='0';zero[30]='0';zero[31]='0';zero[50]='FALSE'
v=m.project_event_shop_native(zero);assert all(v[k]==0 for k in ['buy_max_count','max_frequency','daily_stock']);assert v['kind1_equipment_only_possession_one'] is False
negative=raw.copy();negative[30]='-1';assert m.project_event_shop_native(negative)['max_frequency']==-1
for column,bad in [(29,'(None)'),(30,''),(31,'NaN'),(50,'(None)'),(50,'1')]:
 mutated=raw.copy();mutated[column]=bad
 try:m.project_event_shop_native(mutated)
 except ValueError:continue
 raise AssertionError((column,bad))
print('projection_option_and_type_boundaries_passed')`
    const result=spawnSync('python',['-B','-c',python],{cwd:root,encoding:'utf8'})
    assert.equal(result.status,0,result.stderr)
    assert.match(result.stdout,/projection_option_and_type_boundaries_passed/)
})

test('history inventory exhausts all parents and children without changing July inputs or publishing',()=>{
    assert.equal(rows.size,1020)
    assert.deepEqual([...rows.keys()].sort(),Object.keys(presentation.rows).sort())
    assert.equal(inventory.defaultEnabled,false)
    assert.equal(inventory.sourceSnapshot.catalogSha256,sha(path.join(root,'assets/content_catalog.json')))
    assert.equal(inventory.sourceSnapshot.planSha256,sha(path.join(root,'assets/content_july_controls.json')))
    assert.equal(inventory.summary.plannedParents,90)
    assert.equal(inventory.summary.fixedJulyParents,89)
    assert.equal(inventory.summary.retainedClaimOnlyParents,1)
    assert.equal(inventory.summary.newParticipationParents,85)
    assert.equal(inventory.summary.exchangeOnlyPlannedParents,4)
    const expected=catalog.rows.filter(row=>!rows.has(row.key)).map(row=>row.key).sort()
    assert.equal(expected.length,18927)
    assert.deepEqual(Object.keys(inventory.childIndex.catalogChildren).sort(),expected)
    assert.equal(inventory.sourceSnapshot.imageBytesDecoded,0)
    assert.ok(inventory.sourceSnapshot.resourceMasterBytesRead<256*1024*1024)
    for(const row of rows.values()) {
        assert.equal(row.gameplayStatus,'unreviewed',row.key)
        assert.equal(row.configuration.defaultEnabledForNewHistory,false,row.key)
        assert.deepEqual(Object.keys(row.actions),['visible','enter','claim','exchange'])
    }
})

test('native category quest IDs retain exact owners, periods, reward references and explicit unresolved scene boundaries',()=>{
    const quests=inventory.childIndex.quests
    assert.equal(Object.keys(quests).length,3512)
    assert.deepEqual(Object.keys(quests).sort(),Object.keys(catalog.questMap).sort())
    assert.deepEqual(inventory.ownership.duplicateQuestParents,{})
    assert.deepEqual(inventory.ownership.catalogQuestOwnerDisagreements,{})
    assert.equal(inventory.ownership.excludedCurrentOnlyNativeParents.length,27)
    for(const [key,node] of Object.entries(quests)) {
        assert.deepEqual(node.parents,[catalog.questMap[key]],key)
        assert.ok(rows.get(node.parents[0]).dependencies.questKeys.includes(key),key)
        for(const reference of node.rewardDependencyKeys)assert.ok(inventory.childIndex.questRewards[reference],reference)
        for(const native of node.nativeRows) {
            assert.ok(/^[a-f0-9]{64}$/.test(native.rowSha256))
            assert.ok(Object.hasOwn(native,'originalStartMs')&&Object.hasOwn(native,'originalEndMs'))
        }
    }
    assert.equal(inventory.summary.sceneReferenceCounts.terrainLogicals,635)
    assert.deepEqual(inventory.summary.sceneReferenceCounts.terrainReadOrSyntaxFailures,{})
    assert.equal(inventory.summary.sceneReferenceCounts.questsWithCandidateFieldsOrFloors,2819)
    assert.equal(inventory.summary.sceneReferenceCounts.questsWithUnresolvedNativeLoaderMapping,0)
    assert.deepEqual(inventory.summary.sceneReferenceCounts.nativeKindCounts,{Battle:2819,Story:693})
})

test('all actual pool kinds and per-pool weighted odds are audited without inventing TODO pools or granting qualifications',()=>{
    assert.deepEqual(inventory.summary.gachaPageKindCounts,{'0':535,'1':20,'2':4,'3':4,'4':14,'5':1,'6':0,'7':0,'8':10})
    assert.deepEqual(inventory.summary.nativeUnimplementedPageKinds,{'6':[],'7':[]})
    assert.equal(inventory.summary.specialEligibilityGachaParents,53)
    for(const row of rows.values())if(row.type==='gacha') {
        assert.equal(row.gachaAudit.status,'verified_static',row.key)
        assert.equal(row.gachaAudit.nativeEntries,row.gachaAudit.serverEntries,row.key)
        assert.deepEqual(row.gachaAudit.absentRewardIds,[],row.key)
        assert.deepEqual(row.gachaAudit.issues,[],row.key)
    }
    for(const key of ['gacha:700000','gacha:80000','gacha:800000','gacha:900003'])assert.equal(rows.get(key).personalEligibility.required,true,key)
    const personal=[...rows.values()].filter(row=>row.type==='gacha'&&row.personalEligibility.personalTimeWindowRequired)
    assert.equal(personal.length,10)
    for(const row of personal) {
        assert.equal(row.actions.enter.blockers[0].code,'deferred_by_decision',row.key)
        assert.equal(row.retainedRights.grantNewPersonalPeriod,false,row.key)
        assert.equal(row.retainedRights.preserveCountersAndExchangePoints,true,row.key)
    }
    assert.equal(rows.get('gacha:100').personalEligibility.nativeCrazyTenTimesTicketItemId,999012)
    assert.equal(rows.get('gacha:100').actions.claim.scope.savedPaidSessionOnly,true)
})

test('task relations, exclusive passes and explicit business decisions are not replaced by guessed parent IDs',()=>{
    const missions=inventory.childIndex.missions
    assert.equal(Object.keys(missions).length,4648)
    assert.deepEqual(inventory.ownership.catalogMissionOwnerDisagreements,{})
    for(const [key,node] of Object.entries(missions)) {
        assert.equal(node.parentKey,catalog.missionMap[key])
        if([1,2,3].includes(node.category))assert.equal(node.relation,'independent_child',key)
        else assert.ok(rows.get(node.parentKey).dependencies.missionKeys.includes(key),key)
    }
    const deferred=rows.get('active_mission_event:150')
    assert.equal(deferred.actions.enter.status,'blocked')
    assert.equal(deferred.actions.enter.blockers[0].code,'deferred_by_decision')
    assert.equal(deferred.retainedRights.grantNewComebackQualification,false)
    assert.equal(deferred.retainedRights.existingClaimsOnly,true)
    const rescue=inventory.summary.decisions.successfulRescueFinishMissionKeys
    assert.equal(rescue.length,19)
    assert.ok(rescue.includes('7:56'))
    for(const key of rescue) {
        assert.equal(missions[key].relation,'parent_scoped')
        assert.equal(missions[key].ruleDecision.mode,'successful_rescue_finish_once')
    }
    for(const row of rows.values())if(row.type==='pass_card_event')assert.equal(row.exclusiveGroup,'pass-card-active-period')
})

test('supplemental receipts require actual native economics, stock, dates, parent mappings and existing reward definitions',()=>{
    assert.ok(proof.rows['event_item_shop:203001'])
    for(const [key,receipt] of Object.entries(proof.rows)) {
        const member=inventory.childIndex.catalogChildren[key]
        if(member) {
            const effective=proof.effectiveShopDefinitionEvidence?.rows[key]
            const audit=effective??member.fieldAudit
            assert.equal(member.nativeRowMatchesCatalog,true,key)
            if(!effective){assert.equal(member.staticStatus,'verified_static',key);assert.deepEqual(audit.review,[],key)}
            else {assert.equal(audit.definitionFieldsMatched,true,key);assert.equal(audit.evidence.httpBusinessVerified,false,key)}
            assert.deepEqual(audit.issues,[],key)
            assert.ok(Object.values(audit.matches).every(Boolean),key)
            assert.ok(audit.referenceChecks.every(item=>item.nativeAndServerPresent),key)
            assert.equal(receipt.dependencyDigest,member.preciseDependencyCapture.dependencyDigest,key)
        } else {
            const parent=rows.get(key)
            assert.equal(parent.type,'active_mission_event',key)
            assert.equal(parent.definition.nativeRowMatchesCatalog,true,key)
            assert.equal(parent.definition.currentStatus,'matched',key)
            assert.equal(Object.keys(receipt.loaders).length,10,key)
            assert.ok(receipt.loaders['src/lib/mission/active-reconciliation.ts'],key)
        }
        assert.equal(receipt.oldDefinitionMatched,true,key)
        assert.equal(receipt.previousServerDefinitionDigest,catalog.rows.find(row=>row.key===key).serverDefinitionDigest,key)
    }
})

test('actual effective shop definitions permit receipts without pretending daily and unique-equipment transactions were verified',()=>{
    const evidence=proof.effectiveShopDefinitionEvidence
    assert.ok(evidence)
    assert.equal(evidence.getterProof.staticOnly,true)
    assert.equal(evidence.getterProof.httpBusinessVerified,false)
    assert.equal(Object.keys(evidence.rows).length,8579)
    const issues=Object.entries(evidence.rows).filter(([,audit])=>!audit.definitionFieldsMatched).map(([key])=>key)
    assert.deepEqual(issues,[])
    assert.equal(Object.values(evidence.rows).filter(audit=>audit.status==='unreviewed').length,101)
    assert.equal(Object.values(evidence.rows).filter(audit=>audit.status==='verified_static').length,8478)
    for(const [key,audit] of Object.entries(evidence.rows)){
        assert.equal(audit.rawFieldAuditPreserved,true,key)
        if(audit.definitionFieldsMatched)assert.ok(proof.rows[key],key)
        if(audit.definitionFieldsMatched)for(const reason of audit.review)assert.ok(reason.includes('daily_stock')||reason.includes('装备唯一持有'),key)
    }
    const daily=evidence.rows['event_item_shop:10000']
    assert.equal(inventory.childIndex.catalogChildren['event_item_shop:10000'].fieldAudit.matches.cumulativeStock,false)
    assert.equal(daily.matches.cumulativeStock,true)
    assert.equal(daily.effectiveGetterValue.nativeStockLimits.lifetime,null)
    assert.equal(daily.matches.dailyStock,true)
    assert.ok(daily.review.some(reason=>reason.includes('daily_stock')))
    assert.ok(evidence.rows['event_item_shop:10001476'].review.some(reason=>reason.includes('装备唯一持有')))
    // The separately reviewed veteran product uses the original kind-6 display
    // placeholder while the server grants one exact title. Keep that exception
    // tied to its complete native row, price and reward, never all kind-6 items.
    const veteranKey='event_item_shop:9700118',veteran=evidence.rows[veteranKey]
    const veteranRowSha='b79a56c6b24c3c1cd8dd8ac799b49ea7095e0738475ff5cd6209bea4a3387001'
    assert.deepEqual(Object.entries(evidence.rows).filter(([,audit])=>audit.semanticBridge).map(([key])=>key),[veteranKey])
    assert.deepEqual(veteran.semanticBridge,{
        kind:'veteran_degree_display_placeholder',productId:9700118,degreeId:9900006,nativeRewardKind:6,serverRewardType:5,
        nativeRowSha256:veteranRowSha,scope:'Exact original native name/icon/description/price/limits; server degree grant is authoritative'})
    assert.equal(veteran.status,'verified_static');assert.deepEqual(veteran.review,[])
    assert.equal(veteran.evidence.staticOnly,true);assert.equal(veteran.evidence.httpBusinessVerified,false)
    assert.deepEqual(veteran.nativeRewards,[{type:6,count:1}],'native display placeholder evidence stays unchanged')
    assert.deepEqual(veteran.effectiveGetterValue.costs,[])
    assert.deepEqual(veteran.effectiveGetterValue.userCost,{amount:5000000,type:0})
    assert.deepEqual(veteran.effectiveGetterValue.rewards,[{count:1,id:9900006,type:5}])
    assert.deepEqual(veteran.effectiveGetterValue.nativeStockLimits,{perRequest:1,lifetime:1})
    assert.equal(proof.rows[veteranKey].oldDefinitionMatched,true)
    assert.equal(proof.rows[veteranKey].definitionDigest,veteranRowSha)
    assert.equal(catalog.rows.find(row=>row.key===veteranKey).definitionDigest,veteranRowSha)
})

test('synthetic product-proof contract rejects changed scopes, sources and logs and clears only its two reviewed rules', t => {
    const fixtureBase = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || require('node:os').tmpdir())
    fs.mkdirSync(fixtureBase, { recursive: true })
    const fixture = fs.mkdtempSync(path.join(fixtureBase, 'synthetic-product-proof-'))
    t.after(() => { assert.equal(path.dirname(fixture), fixtureBase); fs.rmSync(fixture, { recursive: true }) })
    const script = String.raw`import sys,pathlib,importlib.util,hashlib,json,copy
sys.dont_write_bytecode=True
s=importlib.util.spec_from_file_location('history','tools/build-content-history-readiness.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
root=pathlib.Path(sys.argv[1]).resolve();audit=root/'proofs';audit.mkdir()
sha=lambda data:hashlib.sha256(data).hexdigest()
required=['src/lib/shop-quota.ts','src/routes/api/shop.ts','src/routes/api/howToGet.ts','src/data/domains/shopPurchase.ts','src/lib/server-clock-state.ts','src/lib/persistence-coordinator.ts','src/lib/assets.ts','src/lib/content-shop-rules.ts','assets/content_history_shop_rules.json','src/lib/types/shop.ts']
freeze=[]
for relative in required:
 file=root/relative;file.parent.mkdir(parents=True,exist_ok=True);data=('SYNTHETIC proof-source fixture: '+relative).encode();file.write_bytes(data);freeze.append({'path':relative,'sha256':sha(data)})
log=audit/'synthetic.log';log.write_bytes(b'SYNTHETIC parser-contract fixture; not a real HTTP acceptance report\n')
rules={'products':{'event_item_shop:1':{'parentKey':'story_event:1','native':{'daily_stock':2}},'event_item_shop:2':{'parentKey':'story_event:2','native':{'daily_stock':None}}},'summary':{'equipmentOnlyPossessionOneKeys':['event_item_shop:2']}}
common={'schemaVersion':1,'staticRuleStatus':'passed','gameplayStatus':'actual_passed','sourceFreeze':freeze}
daily={**common,'status':'actual_passed','tests':{'total':7,'passed':7,'failed':0,'httpCases':6,'log':str(log),'logSha256':sha(log.read_bytes())},'scope':{'productKeys':list(rules['products']),'dailyStockKeys':['event_item_shop:1'],'monthlyStockKeys':[]}}
unique={**common,'validation':{'source':{'status':'actual_passed','tests':6,'registeredHttpTests':5,'log':str(log),'logSha256':sha(log.read_bytes())}},'products':[{'key':'event_item_shop:2','parentKey':'story_event:2'}]}
paths=[audit/'root-event-shop-quota-audit.json',audit/'server-event-shop-ownership-audit.json']
for file,data in zip(paths,[daily,unique]):file.write_text(json.dumps(data),encoding='utf8')
coverage,receipts,frozen=m.product_runtime_reviews(paths,root,rules)
assert coverage['daily_stock']=={'event_item_shop:1'} and coverage['equipment_unique_possession']=={'event_item_shop:2'} and len(frozen)==10
for key,label in [('event_item_shop:1','需要核对周期库存账本：daily_stock'),('event_item_shop:2','需要核对装备唯一持有规则')]:
 row={'issues':[],'review':[label],'status':'unreviewed'};result=m.apply_product_runtime_reviews(row,key,coverage,receipts)
 assert result['status']=='verified_static' and result['review']==[] and len(result['boundedTransactionEvidence'])==1
 assert row['review']==[label]
 row={'issues':['known native price mismatch'],'review':[label,'unproven unrelated rule'],'status':'mismatch'}
 result=m.apply_product_runtime_reviews(row,key,coverage,receipts)
 assert result['status']=='mismatch' and result['issues']==row['issues'] and result['review']==['unproven unrelated rule']
 assert m.apply_product_runtime_reviews(row,'general_shop:1',coverage,receipts)['review']==row['review']
for mutation,message in [('scope','scope differs'),('source','source changed'),('log','log changed')]:
 changed=copy.deepcopy(daily)
 if mutation=='scope':changed['scope']['dailyStockKeys']=[]
 elif mutation=='source':changed['sourceFreeze'][0]['sha256']='0'*64
 else:changed['tests']['logSha256']='0'*64
 paths[0].write_text(json.dumps(changed),encoding='utf8')
 try:m.product_runtime_reviews([paths[0]],root,rules)
 except ValueError as error:assert message in str(error),str(error)
 else:raise AssertionError(mutation+' was not rejected')
print('synthetic_exact_scopes_sources_logs_and_review_contract_passed')`
    const run = spawnSync('python', ['-B', '-c', script, fixture], { cwd: root, encoding: 'utf8' })
    assert.equal(run.status, 0, run.stderr)
    assert.match(run.stdout, /synthetic_exact_scopes_sources_logs_and_review_contract_passed/)
})

test('archived product HTTP proof preserves all 19 original source identities and exact daily/unique scopes', {
    skip: !process.env.STARPOINT_PRODUCT_PROOF_ARCHIVE && 'requires explicit STARPOINT_PRODUCT_PROOF_ARCHIVE containing the original complete HTTP-proof archive',
},t=>{
    const fixtureBase=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||require('node:os').tmpdir())
    fs.mkdirSync(fixtureBase,{recursive:true})
    const fixture=fs.mkdtempSync(path.join(fixtureBase,'history-product-proof-'))
    t.after(()=>{
        assert.equal(path.dirname(path.resolve(fixture)),fixtureBase)
        assert.ok(path.basename(fixture).startsWith('history-product-proof-'))
        fs.rmSync(fixture,{recursive:true})
    })
    const script=String.raw`import sys,copy,pathlib,importlib.util,hashlib,os,shutil
sys.dont_write_bytecode=True
s=importlib.util.spec_from_file_location('history','tools/build-content-history-readiness.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
current=pathlib.Path.cwd();root=pathlib.Path(os.environ['CONTENT_REVIEW_FIXTURE_ROOT']).resolve()
originals=pathlib.Path(os.environ.get('STARPOINT_PRODUCT_PROOF_ORIGINALS',current)).resolve()
task=pathlib.Path(os.environ['STARPOINT_PRODUCT_PROOF_ARCHIVE']).resolve();rules=m.load(current/'assets/content_history_shop_rules.json')
paths=[task/'root-event-shop-quota-audit.json',task/'server-event-shop-ownership-audit.json']
# The old ownership proof predates the separately reviewed veteran receipt.
# Restore only its real frozen inputs, rather than blessing today's file SHA.
old_evidence=task.parent/'veteran-exchange-fix-20261022/preimage/assets/content_history_definition_evidence.json'
digest=lambda file:hashlib.sha256(file.read_bytes()).hexdigest()
assert digest(old_evidence)=='67cea2433c0ee47aeab155655c5ca186651efbb085f708d559c76e0d3d7d5dc5'
frozen_sources={}
for evidence_path in paths:
 for record in m.load(evidence_path)['sourceFreeze']:
  relative,expected=record['path'],record['sha256'].lower()
  assert relative not in frozen_sources or frozen_sources[relative]==expected
  frozen_sources[relative]=expected
assert len(frozen_sources)==19
for relative,expected in frozen_sources.items():
 destination=root/relative
 assert destination.resolve().is_relative_to(root)
 source=old_evidence if relative=='assets/content_history_definition_evidence.json' else originals/relative
 assert digest(source)==expected,relative+' frozen fixture source mismatch'
 destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
 assert digest(destination)==expected,relative+' frozen fixture copy mismatch'
assert digest(current/'assets/content_history_definition_evidence.json')!=frozen_sources['assets/content_history_definition_evidence.json']
fixture_evidence=root/'assets/content_history_definition_evidence.json'
try:
 shutil.copyfile(current/'assets/content_history_definition_evidence.json',fixture_evidence)
 try:m.product_runtime_reviews(paths,root,rules)
 except ValueError as error:assert str(error)=='product transaction proof source changed: assets/content_history_definition_evidence.json'
 else:raise AssertionError('old source-HTTP proof must reject the newer evidence file')
finally:shutil.copyfile(old_evidence,fixture_evidence)
assert digest(fixture_evidence)==frozen_sources['assets/content_history_definition_evidence.json']
coverage,receipts,frozen=m.product_runtime_reviews(paths,root,rules)
assert len(coverage['daily_stock'])==92 and len(coverage['equipment_unique_possession'])==9
proof=m.load(root/'assets/content_history_definition_evidence.json');audits=proof['effectiveShopDefinitionEvidence']['rows']
for key,rule in [('event_item_shop:10000','daily_stock'),('event_item_shop:10001476','equipment_unique_possession')]:
 result=m.apply_product_runtime_reviews(audits[key],key,coverage,receipts);assert result['status']=='verified_static';assert result['boundedTransactionEvidence']
bad=copy.deepcopy(audits['event_item_shop:10000']);bad['issues']=['known native price mismatch'];bad['matches']['costs']=False;bad['review'].append('unproven unrelated rule')
result=m.apply_product_runtime_reviews(bad,'event_item_shop:10000',coverage,receipts);assert result['status']=='mismatch';assert result['issues']==bad['issues'];assert result['review']==['unproven unrelated rule']
assert m.apply_product_runtime_reviews(audits['event_item_shop:10000'],'general_shop:10000',coverage,receipts)['review']==audits['event_item_shop:10000']['review']
base=m.load(paths[0]);original_load=m.load
for mutation in ['scope','source','log']:
 changed=copy.deepcopy(base)
 if mutation=='scope':changed['scope']['dailyStockKeys'].pop()
 elif mutation=='source':changed['sourceFreeze'][0]['sha256']='0'*64
 else:changed['tests']['logSha256']='0'*64
 m.load=lambda p: changed
 try:m.product_runtime_reviews([paths[0]],root,rules)
 except ValueError:pass
 else:raise AssertionError(mutation)
m.load=original_load
same=copy.deepcopy(proof);same['effectiveShopDefinitionEvidence']['rows']['event_item_shop:10000']['review']=[]
assert m.equivalent_definition_receipts(proof,same)
same['rows']['event_item_shop:10000']['dependencyDigest']='0'*64;assert not m.equivalent_definition_receipts(proof,same)
print('exact_rule_scopes_and_semantic_receipt_preservation_passed')`
    const run=spawnSync('python',['-B','-c',script],{cwd:root,encoding:'utf8',env:{...process.env,CONTENT_REVIEW_FIXTURE_ROOT:fixture}})
    assert.equal(run.status,0,run.stderr)
    assert.match(run.stdout,/exact_rule_scopes_and_semantic_receipt_preservation_passed/)
})

test('current-only native products remain separate and do not revoke the reviewed old 700099 exchange scope',()=>{
    const extra=inventory.childIndex.currentOnlyChildren
    assert.equal(Object.keys(extra).length,135)
    assert.deepEqual(inventory.summary.currentOnlyChildTypes,{boss_coin_shop:126,event_item_shop:9})
    const parent=rows.get('rush_event:700099'),scope=parent.actions.exchange.scope
    assert.equal(scope.productKeys.length,18)
    assert.equal(scope.excludedUncataloguedProductKeys.length,9)
    assert.equal(scope.validRetainedExactProductKeys.length,18)
    assert.deepEqual(scope.productKeys,[...parent.retainedRights.reviewedExistingProductKeys].sort())
    for(const key of scope.excludedUncataloguedProductKeys) {
        assert.equal(extra[key].catalogPresent,false)
        assert.ok(!scope.productKeys.includes(key))
        assert.equal(proof.rows[key],undefined)
    }
})

test('native quest projection corrects actual server consumers and preserves explicit current policies',()=>{
    const rules=read('content_history_quest_rules.json'),quests=inventory.childIndex.quests
    assert.equal(rules.source.catalogSha256,inventory.sourceSnapshot.catalogSha256)
    assert.equal(rules.source.manifestSha256,inventory.sourceSnapshot.manifestSha256)
    assert.equal(rules.source.assetVersion,'1.4.258')
    assert.equal(Object.keys(rules.quests).length,3512)
    const fixed=Object.entries(rules.quests).filter(([,node])=>node.fields.fixedParty!==undefined)
    assert.equal(fixed.length,71)
    const repaired=fixed.filter(([key])=>quests[key].additionalConsumedFieldAudit.rawServerDifferences.some(change=>change.field==='fixedParty'))
    assert.equal(repaired.length,20)
    assert.deepEqual([...new Set(repaired.map(([,node])=>node.parentKey))].sort(),['story_event:200024','story_event:202012'])
    for(const [key,rule] of Object.entries(rules.quests)) {
        const node=quests[key],audit=node.additionalConsumedFieldAudit
        assert.equal(node.effectiveServerFieldParity.status,'passed',key)
        assert.deepEqual(audit.effectiveServerDifferences,[],key)
        assert.equal(node.nativeRewardStaticStatus,'passed',key)
        if(rule.kind==='Story')assert.deepEqual(Object.keys(rule.fields),['clearRewardId'],key)
        if(rule.fields.fixedParty!==undefined)assert.equal(node.effectiveServerDefinition.fixedParty,rule.fields.fixedParty,key)
        if(audit.forwardedTimeLimit)assert.equal(audit.forwardedTimeLimit.matchesNativeAt60Fps,true,key)
        if(!audit.nominalStamina.preservedPolicy)assert.equal(audit.nominalStamina.effectiveMatches,true,key)
        else assert.equal(audit.nominalStamina.effective.baseCost,audit.nominalStamina.server,key)
    }
    assert.equal(Object.keys(inventory.childIndex.questRewards).length,2759)
    assert.ok(Object.values(inventory.childIndex.questRewards).every(node=>node.staticStatus==='passed'))
})

test('loader rebind candidates retain complete old evidence and pass the actual unchanged matcher after the reviewed loader substitution',()=>{
    assert.equal(Object.keys(proof.existingEvidenceRebind).length,1057)
    for(const [key,candidate] of Object.entries(proof.existingEvidenceRebind)) {
        const {loaders:oldLoaders,...oldFields}=candidate.previousEvidence
        const {loaders:currentLoaders,...currentFields}=candidate.evidence
        assert.deepEqual(currentFields,oldFields,key)
        assert.equal(candidate.dependencyDigestUnchanged,true,key)
        assert.equal(candidate.currentMatcherAfterLoaderRebind.matchesCatalog,true,key)
        assert.equal(Object.keys(currentLoaders).length,6,key)
        assert.ok(currentLoaders['src/lib/content-quest-rules.ts'],key)
        assert.notDeepEqual(currentLoaders,oldLoaders,key)
    }
})

test('279 native quota identities retain existing lookup and the chosen success-only rule without rewriting Expert or old balances',()=>{
    const rules=read('content_history_quest_rules.json'),lookup=read('daily_challenge_point_lookup.json')
    const selected=Object.entries(inventory.childIndex.quests).filter(([,node])=>node.challengePointRule)
    assert.equal(selected.length,279)
    assert.equal(new Set(selected.flatMap(([,node])=>node.parents)).size,53)
    assert.deepEqual(inventory.summary.nativeChallengePointRules.existingServerRecoveryCounts,{'false':235,'true':44})
    for(const [key,node] of selected) {
        const quota=node.challengePointRule
        assert.equal(Number(rules.quests[key].nativeEligibility.daily_challenge_point_id),quota.pointId,key)
        assert.deepEqual(quota.existingServerLookup,{maxPoint:lookup[quota.pointId].maxPoint,isRecovery:lookup[quota.pointId].isRecovery},key)
        assert.equal(quota.ruleDecision.consumeAfterSuccessfulCompletion,1,key)
        assert.equal(quota.ruleDecision.failureRetryAllowed,true,key)
        assert.equal(quota.ruleDecision.preserveExistingExpertFailureConsumption,true,key)
        assert.equal(quota.ruleDecision.officialDeductionTimingVerified,false,key)
        assert.equal(quota.ruleDecision.retroactiveConsumption,false,key)
        assert.equal(quota.staticWiringStatus,'passed',key)
        assert.equal(rows.get(node.parents[0]).configuration.planned,false,key)
    }
    for(const row of rows.values())assert.ok(!row.actions.enter.blockers.some(blocker=>blocker.code==='quest_static_nativeChallengePointWiring'),row.key)
})

test('native shop-only collection pages do not acquire fictional task requirements and runtime definition checks cover every parent',()=>{
    const shopOnly=[...rows.values()].filter(row=>row.nativeEntry.collectKind===1)
    assert.equal(shopOnly.length,23)
    for(const row of shopOnly) {
        assert.equal(row.dependencies.missionKeys.length,0,row.key)
        assert.equal(row.actions.claim.status,'not_applicable',row.key)
        assert.equal(row.nativePage.kind,'collect_item_exchange_shop',row.key)
        assert.ok(!row.actions.enter.blockers.some(blocker=>blocker.code==='native_parent_mission_scope_empty'),row.key)
    }
    for(const key of ['collect_item_event:5','collect_item_event:80003']) {
        assert.equal(rows.get(key).actions.enter.status,'blocked',key)
        assert.ok(rows.get(key).actions.enter.blockers.some(blocker=>blocker.code==='native_shop_scope_empty'),key)
    }
    for(const row of rows.values()) {
        assert.equal(typeof row.runtimeDefinition.matchesCatalog,'boolean',row.key)
        if(!row.runtimeDefinition.matchesCatalog) {
            assert.ok(Object.values(row.actions).filter(action=>action.status!=='not_applicable').every(action=>action.status==='blocked'),row.key)
        }
    }
    assert.equal(inventory.summary.preciseProductReceipts,10693)
    assert.equal(inventory.summary.preciseParentReceipts,4)
    assert.deepEqual(inventory.summary.runtimeDefinitionCounts,{'true':1020})
    assert.deepEqual(inventory.summary.runtimeDefinitionBlockedKeys,[])
})

test('actual definition functions reject altered dependencies and retained scope while preserving valid whole-source priority',()=>{
    const script=String.raw`
import importlib.util,sys,json,copy,pathlib
sys.dont_write_bytecode=True
s=importlib.util.spec_from_file_location('history',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
root=pathlib.Path(sys.argv[2]);catalog=m.load(root/'assets/content_catalog.json');proof=m.load(root/'assets/content_history_definition_evidence.json')
keys=['active_mission_event:3','event_item_shop:203001','rush_event:700099']
baseline=m.runtime_receipts(root,[],runtime_catalog=catalog,runtime_evidence=proof,runtime_keys=keys)['runtimeDefinitions']
assert all(baseline[key]['matchesCatalog'] for key in keys)
bad=copy.deepcopy(proof)
for key in keys[:2]:bad['rows'][key]['dependencyDigest']='0'*64
bad['existingEvidenceRebind']['rush_event:700099']['evidence']['reviewedExistingChildren'].pop()
rejected=m.runtime_receipts(root,[],runtime_catalog=catalog,runtime_evidence=bad,runtime_keys=keys)['runtimeDefinitions']
assert not rejected[keys[1]]['matchesCatalog'] and not rejected[keys[2]]['matchesCatalog'],rejected
active=next(row for row in catalog['rows'] if row['key']==keys[0])
sources=active['definitionEvidence']['serverSources']
whole=bool(sources) and all(m.sha((root/path).read_bytes())==catalog['serverResources'][path]['sha256'] for path in sources)
assert rejected[keys[0]]['matchesCatalog']==whole,rejected
direct=m.runtime_receipts(root,[dict(active,exactDefinitionEvidence=bad['rows'][keys[0]])])['existingMatches'][keys[0]]
assert direct['matchesCatalog'] is False,direct
`
    const run=spawnSync('python',['-B','-c',script,path.join(root,'tools/build-content-history-readiness.py'),root],{encoding:'utf8'})
    assert.equal(run.status,0,run.stderr)
})

test('reviewed legacy loader transition rejects every unreviewed proof or loader change in the actual runtime functions',()=>{
    const script=String.raw`
import importlib.util,sys,copy,pathlib
sys.dont_write_bytecode=True
s=importlib.util.spec_from_file_location('history',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
root=pathlib.Path(sys.argv[2]);catalog=m.load(root/'assets/content_catalog.json');proof=m.load(root/'assets/content_history_definition_evidence.json')
key=next(key for key,value in proof['existingEvidenceRebind'].items() if value['kind']=='exact')
def check(c,p):return m.runtime_receipts(root,[],runtime_catalog=c,runtime_evidence=p,runtime_keys=[key])['runtimeDefinitions'][key]['matchesCatalog']
assert check(catalog,proof)
cases=[]
p=copy.deepcopy(proof);p['existingEvidenceRebind'][key]['previousEvidence']['oldDefinitionMatched']=False;cases.append(('previous proof',catalog,p))
p=copy.deepcopy(proof);p['existingEvidenceRebind'][key]['evidence']['dependencyDigest']='0'*64;cases.append(('non-loader next proof',catalog,p))
c=copy.deepcopy(catalog);p=copy.deepcopy(proof)
next(row for row in c['rows'] if row['key']==key)['exactDefinitionEvidence']['loaders']['src/lib/assets.ts']='0'*64
p['existingEvidenceRebind'][key]['previousEvidence']['loaders']['src/lib/assets.ts']='0'*64
cases.append(('unreviewed old assets identity',c,p))
for loader in ['src/lib/content-quest-rules.ts','src/lib/content-shop-rules.ts','src/lib/content-master.ts','src/lib/shop-sales.ts','src/lib/multi-special-exchange.ts']:
 p=copy.deepcopy(proof);p['existingEvidenceRebind'][key]['evidence']['loaders'][loader]='0'*64;cases.append(('unreviewed current loader '+loader,catalog,p))
p=copy.deepcopy(proof);p['existingEvidenceRebind'][key]['evidence']['loaders']['src/lib/unreviewed-extra.ts']='0'*64;cases.append(('extra loader',catalog,p))
for name,c,p in cases:assert check(c,p) is False,name
print('normal reviewed transition passed; '+str(len(cases))+' tamper variants rejected')
`
    const run=spawnSync('python',['-B','-c',script,path.join(root,'tools/build-content-history-readiness.py'),root],{encoding:'utf8'})
    assert.equal(run.status,0,run.stderr)
    assert.match(run.stdout,/9 tamper variants rejected/)
})

test('candidate-specific native entry bridges preserve the original missing routes without claiming gameplay or official positions',()=>{
    const missing=[...rows.values()].filter(row=>row.nativeEntry.originalStatus==='blocked_absent_original_route')
    assert.deepEqual(missing.map(row=>row.key).sort(),['advent_event:300098','rush_event:700017',
        ...[200100,200101,200102,200103,200104,200106,200107,200108,200109].map(id=>'world_story_event:'+id)].sort())
    for(const row of missing) {
        assert.equal(row.nativeEntry.status,'verified_controlled_bridge',row.key)
        assert.equal(row.actions.enter.status,'passed',row.key)
        assert.ok(!row.actions.enter.blockers.some(item=>item.code==='native_entry_missing'),row.key)
        assert.deepEqual(row.nativeEntry.originalRoutes,row.nativeEntry.routes,row.key)
        assert.equal(row.nativeEntry.controlledBridge.candidateSwfSha256,'2a01c4915c0f13f7a562bab4a38647068a1cece45af32add7dbc625149a0ccc7',row.key)
        assert.equal(row.nativeEntry.controlledBridge.candidateHelperAbcSha256,'d3ec8fc330e0050a0d1aae2eec8ec0ae8e808733fab2158689036990cc09a429',row.key)
        assert.equal(row.nativeEntry.controlledBridge.executedAssertionCount,115,row.key)
        assert.equal(row.nativeEntry.controlledBridge.platform,'android_candidate',row.key)
        assert.equal(row.gameplayStatus,'unreviewed',row.key)
        if(row.type==='world_story_event')assert.ok(row.dependencies.boxGachaKeys.includes(row.nativeEntry.controlledBridge.boxKey),row.key)
    }
    assert.equal(rows.get('rush_event:700017').nativeEntry.controlledBridge.officialOriginalPositionRecovered,false)
    assert.equal(inventory.summary.staticStatusCounts.verified_static,1007)
    assert.equal(inventory.summary.staticStatusCounts.unreviewed,13)
    assert.deepEqual(inventory.summary.runtimeCatalogDefinitionCounts,{true:15473,false:4474})
    assert.deepEqual(inventory.summary.runtimeCatalogBlockedTypeCounts,{boss_coin_shop:4473,event_item_shop:1})
    for(const row of rows.values()) {
        assert.ok(!Object.values(row.actions).some(action=>action.blockers.some(item=>item.code==='battle_scene_dependency_review')),row.key)
        if(row.dependencies.questKeys.length) {
            assert.equal(row.staticChecks.nativeFieldMapping.status,'passed',row.key)
            assert.equal(row.staticChecks.rewardMembersAndConversions.status,'passed',row.key)
            assert.ok(row.staticChecks.excludedFromStaticPass.includes('地形内敌人及物件完整运行语义'),row.key)
        }
    }
})

test('native Raid and ranking assets preserve original rule values and raw reward encodings',()=>{
    const rules=read('raid_event_rules.json'),overall=read('raid_event_overall_reward.json')
    const ranking=read('ranking_event_ranking_reward.json'),raidRanking=read('raid_event_ranking_reward.json')
    assert.equal(Object.keys(rules.events).length,7)
    assert.equal(rules.events['7'].nativeRequiredKillCount,76000,'native target is data, not a write to existing runtime scale')
    for(const event of Object.values(rules.events))assert.ok(Object.values(event.questKillCountWeights).every(value=>Number.isInteger(value)&&value>0))
    assert.equal(Object.keys(overall.rows).length,72)
    assert.deepEqual([...new Set(Object.values(overall.rows).map(value=>value[0][2]))].sort(),['0','1'])
    for(const key of ['1000','1001']) {
        assert.equal(ranking.events[key].length,9)
        assert.ok(ranking.events[key].every(row=>row.rewards.length===1&&row.rewards[0].kind===3&&row.rewards[0].id===null&&row.rewards[0].number===20000))
    }
    assert.equal(Object.keys(raidRanking.events).length,7)
    assert.ok(Object.values(raidRanking.events).every(rows=>rows.length===13))
})

test('generator refuses economic mismatches instead of laundering a fresh self-hash into a receipt',()=>{
    const script=String.raw`
import importlib.util,sys,copy
s=importlib.util.spec_from_file_location('history',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
raw=['(None)']*50
for i,v in {18:'40210',19:'100',29:'10',30:'10',32:'0',33:'999003',34:'1'}.items():raw[i]=v
schema={'cost_item1':[18,19],'buy_max_count':[29],'max_frequency':[30],'daily_stock':[31],'kind1':[32,33,34],'price':[15,16],'cost_item_schedule_id':[17]}
server={'costs':[{'id':40210,'amount':100}],'rewards':[{'type':0,'id':999003,'count':1}],'stock':10}
row={'key':'event_item_shop:203001','type':'event_item_shop'}
assert m.audit_product(row,raw,server,schema,{})['status']=='verified_static'
changed=copy.deepcopy(server);changed['rewards'][0]['count']=2
assert m.audit_product(row,raw,changed,schema,{})['status']=='mismatch'
changed=copy.deepcopy(server);changed['costs'][0]['amount']=99
assert m.audit_product(row,raw,changed,schema,{})['status']=='mismatch'
changed=copy.deepcopy(server);changed['stock']=11
assert m.audit_product(row,raw,changed,schema,{})['status']=='mismatch'
changed=copy.deepcopy(server);changed['maxFrequency']=1
assert m.audit_product(row,raw,changed,schema,{})['status']=='unreviewed'
`
    const run=spawnSync('python',['-B','-c',script,path.join(root,'tools/build-content-history-readiness.py')],{encoding:'utf8'})
    assert.equal(run.status,0,run.stderr)
})
