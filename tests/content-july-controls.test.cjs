'use strict'
const {test, after}=require('node:test')
const assert=require('node:assert/strict')
const fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const Sqlite=require('better-sqlite3')
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'july-controls-'))
process.env.DATA_DIR=path.join(temporary,'data');process.env.CN_WRITER_THREAD='0'
const {initializeDatabase}=require('../out/data')
const {getDb}=require('../out/data/db')
initializeDatabase()
const ops=require('../out/lib/content-operations')
const {ContentOperationsStore,initializeContentOperationsSchema}=require('../out/lib/content-operations-store')
const {defaultContentDecision,requiresManualContentControl}=require('../out/lib/content-operations-defaults')
const {applyJulyContentPlanOfflineSync,julyContentPlan}=require('../out/lib/content-operations-bootstrap')
const now=Date.parse('2026-10-21T00:00:00Z')
function fixture(overrides={}) {
    const db=new Sqlite(':memory:');initializeContentOperationsSchema(db)
    db.exec('CREATE TABLE progress(id INTEGER PRIMARY KEY, progress INTEGER, claimed INTEGER, stock INTEGER);INSERT INTO progress VALUES(14,11,1,7)')
    const runtime=ops.contentOperations().runtimeDefinitions
    const store=new ContentOperationsStore(db,ops.contentCatalog,ops.contentCapabilities,
        row=>overrides[row.key]??runtime.get(row.key),undefined,undefined,undefined,defaultContentDecision)
    const apply=(extra={})=>applyJulyContentPlanOfflineSync(store,{expectedRevision:store.revision(),expectedCatalogDigest:store.digest,nowMs:now,...extra})
    return {db,store,apply}
}
after(()=>{getDb().close();fs.rmSync(temporary,{recursive:true})})
test('fixed July plan covers native parent and child windows without turning shop proof into whole-event proof',()=>{
    assert.equal(julyContentPlan.referenceDate,'2025-07-20')
    const parentControls=julyContentPlan.controls.filter(r=>r.key.includes('_event:')&&!r.key.startsWith('pass_')&&r.actionOverrides.exchange)
    const productControls=julyContentPlan.controls.filter(r=>r.evidence.startsWith('Exact old/current winning item+mapping'))
    assert.equal(parentControls.length,29);assert.equal(productControls.length,1023)
    assert.equal(julyContentPlan.controls.length,1113)
    const parentKeys=new Set(parentControls.map(r=>r.key))
    for(const id of [250601,250602,250603,250604,250605,250606])
        assert.ok(parentKeys.has(`carnival_event:${id}`),`missing carnival parent ${id}`)
    assert.ok(parentKeys.has('rush_event:700099'))
    const productKeys=new Set(productControls.map(r=>r.key))
    for(const id of [11000276,11000277,11000278,11000279,11000280,11000281,11000282,11000283,11000286,11000287])
        assert.ok(productKeys.has(`event_item_shop:${id}`),`missing reviewed product ${id}`)
    for(const id of [11000050,11000051,11000054,11000055])
        assert.ok(productKeys.has(`event_item_shop:${id}`),`general atlas mana_a product ${id}`)
    for(const id of [...Array.from({length:17},(_,i)=>9700101+i),9700199])
        assert.ok(productKeys.has(`event_item_shop:${id}`),`missing reviewed rush product ${id}`)
    for(const id of Array.from({length:9},(_,i)=>9700121+i)) {
        assert.ok(!productKeys.has(`event_item_shop:${id}`),`unreviewed sibling ${id}`)
        assert.equal(ops.contentDecision('event_item_shop',id,'exchange',now),false)
    }
    for(const control of [...parentControls,...productControls]) {
        const row=ops.contentCatalog.rows.find(r=>r.key===control.key)
        const receipt=row.exactDefinitionEvidence??row.currentParentDefinitionEvidence
        assert.ok(receipt,control.key)
        assert.equal(receipt.key,control.key)
        assert.equal(ops.contentOperations().runtimeDefinitions.get(control.key).matchesCatalog,true,control.key)
        if(parentKeys.has(control.key)) {
            assert.equal(control.actionOverrides.enter.enabled,true)
            assert.ok(control.actionOverrides.enter.questKeys.length>0)
        } else assert.deepEqual(Object.keys(control.actionOverrides).sort(),['exchange','visible'])
        assert.equal(control.actionOverrides.exchange.endsAtMs,null)
    }
    assert.equal(julyContentPlan.controls.filter(r=>r.key.startsWith('gacha:')).length,28)
    for(const [key,allowed,closed] of [['tower_dungeon_event:1','20:1381','20:1001'],
        ['score_attack_event:1','27:1101','27:1055'],['challenge_dungeon_event:1','13:1018','13:1020']]) {
        const enter=julyContentPlan.controls.find(r=>r.key===key).actionOverrides.enter
        assert.ok(enter.questKeys.includes(allowed),allowed)
        assert.ok(!enter.questKeys.includes(closed),closed)
    }
    const advent=julyContentPlan.controls.find(r=>r.key==='advent_event:200076').actionOverrides.enter.questKeys
    assert.ok(advent.includes('7:200076001'));assert.ok(advent.includes('8:200076001'))
    const pass=julyContentPlan.controls.find(r=>r.key==='pass_card_event:14')
    assert.deepEqual(pass.actionOverrides.enter.missionKeys,['6:53','6:54','6:55','6:56','7:53','7:54','7:55','8:80','8:81','8:82','8:83','8:84','8:85'])
    assert.equal(pass.actionOverrides.claim.missionKeys.length,14)
    assert.equal(julyContentPlan.controls.find(r=>r.key==='pass_card_event:15').actionOverrides.enter.enabled,false)
    assert.ok(!julyContentPlan.controls.some(r=>r.key==='gacha:990003'))
})
test('production defaults refuse unreviewed new entries regardless of original dates, preserve core systems and qualified rights',()=>{
    const store=ops.contentOperations()
    for(const date of [Date.parse('2025-07-20T04:00:00Z'),now,Date.parse('2050-01-01T00:00:00Z')]) {
        assert.equal(store.allowed('gacha:1704','enter',date),false)
        assert.equal(store.allowed('pass_card_event:15','enter',date),false)
    }
    assert.equal(store.allowed('gacha:1704','exchange',now),true)
    assert.equal(store.allowed('pass_card_event:15','claim',now),true)
    assert.equal(ops.contentDecision('gacha',987654321,'enter',now),false)
    assert.equal(ops.contentQuestDecision(1,1000001,now),null)
    assert.equal(ops.contentQuestDecision(2,1001002,now),null)
    const core=ops.contentCatalog.rows.find(r=>r.type==='mission_daily'&&!requiresManualContentControl(r))
    assert.ok(core);assert.equal(store.allowed(core.key,'enter',now),null)
    const defaults=store.snapshot(now).default_policy
    assert.ok(defaults.actions.enter.closed_keys.includes('gacha:1704'))
    assert.ok(defaults.actions.claim.qualified_rights_keys.includes('pass_card_event:15'))
    assert.ok(defaults.actions.enter.legacy_keys.includes(core.key),'known permanent core is distinguishable from an unknown new row')
    const coreShop=ops.contentCatalog.rows.find(r=>r.type==='general_shop'&&!requiresManualContentControl(r))
    assert.ok(coreShop);assert.ok(defaults.actions.exchange.legacy_keys.includes(coreShop.key))
    assert.ok(!defaults.actions.enter.legacy_keys.includes('gacha:1704'))
    assert.equal(store.list({search:'gacha:1704',limit:1}).rows[0].effectiveFlags.enter,false)
    const fixed=store.list({search:'gacha:1704',candidatesOnly:true,limit:1})
    assert.equal(fixed.rows[0].key,'gacha:1704','fixed-day candidates do not use the old capture-time windowCandidate')
    assert.equal(fixed.rows[0].windowCandidate,false,'the historical capture evidence remains distinguishable')
    assert.equal(ops.contentQuestDecision(26,2080001,now),null,'independent permanent core boss retains its native rule')
    assert.equal(ops.contentQuestDecision(26,987654321,now),false,'unknown seasonal quests do not inherit the core exception')
})
test('initial plan is atomic, permanent after legacy end dates and idempotent without resetting later operator choices',t=>{
    const {db,store,apply}=fixture();t.after(()=>db.close())
    const before=db.prepare('SELECT * FROM progress').all()
    assert.equal(apply().applied,true);assert.equal(store.revision(),julyContentPlan.controls.length)
    for(const [key,action] of [['pass_card_event:14','enter'],['challenge_dungeon_event:1','enter'],['gacha:80001','enter']]) {
        assert.equal(store.allowed(key,action,Date.parse('2301-01-01T00:00:00Z')),true)
    }
    assert.equal(store.scopedAllowed('challenge_dungeon_event:1','quest','13:1017','enter',now),true)
    assert.equal(store.scopedAllowed('challenge_dungeon_event:1','quest','13:1018','enter',now),true)
    assert.equal(store.scopedAllowed('challenge_dungeon_event:1','quest','13:1020','enter',now),false)
    assert.equal(store.scopedAllowed('pass_card_event:14','mission','7:55','enter',now),true)
    assert.equal(store.scopedAllowed('pass_card_event:14','mission','7:56','enter',now),false)
    assert.equal(store.scopedAllowed('pass_card_event:14','mission','7:55','claim',now),true)
    const patch=enabled=>store.update('pass_card_event:14',{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'operator participation only',
        actionOverrides:{enter:{enabled,endsAtMs:null,readiness:'verified',evidence:'same reviewed scope'}}},now)
    const original=store.state('pass_card_event:14').instanceId
    patch(false);assert.equal(store.allowed('pass_card_event:14','enter',now),false)
    assert.equal(store.allowed('pass_card_event:14','claim',now),true)
    assert.equal(apply().applied,false);assert.equal(store.allowed('pass_card_event:14','enter',now),false)
    patch(true);assert.equal(store.state('pass_card_event:14').instanceId,original)
    assert.deepEqual(db.prepare('SELECT * FROM progress').all(),before)
})
test('missing definitions, unsupported types, changed plan and CAS conflicts leave no partial bootstrap',t=>{
    const bad=fixture({'pass_card_event:14':{digest:'changed',matchesCatalog:false}});t.after(()=>bad.db.close())
    assert.throws(()=>bad.apply(),/定义|资源/)
    assert.equal(bad.store.revision(),0)
    assert.equal(bad.db.prepare('SELECT count(*) n FROM content_operations_state').get().n,0)
    assert.ok(!bad.db.prepare("SELECT 1 FROM sqlite_master WHERE name='content_operations_initialization'").get())
    const good=fixture();t.after(()=>good.db.close())
    assert.throws(()=>good.apply({expectedRevision:1}),/版本/);assert.equal(good.store.revision(),0)
    const badPlan=JSON.parse(JSON.stringify(julyContentPlan));badPlan.referenceDate='2025-08-01'
    assert.throws(()=>good.apply({plan:badPlan}),/身份/)
    good.apply()
    const changed=JSON.parse(JSON.stringify(julyContentPlan));changed.controls.pop()
    assert.throws(()=>good.apply({plan:changed}),/不同初始化/)
})
