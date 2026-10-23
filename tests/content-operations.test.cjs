'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const Sqlite = require('better-sqlite3')
const { initializeContentOperationsSchema, ContentOperationsStore, CONTENT_ACTIONS } = require('../out/lib/content-operations-store')
const now = Date.parse('2026-10-11T00:00:00Z')
function fixture() {
    const db = new Sqlite(':memory:')
    db.exec('CREATE TABLE players(id INTEGER PRIMARY KEY); CREATE TABLE progress(player_id INTEGER, content_id INTEGER, cleared INTEGER, claimed INTEGER, stock INTEGER); INSERT INTO players VALUES(1); INSERT INTO progress VALUES(1,15,7,3,8)')
    initializeContentOperationsSchema(db)
    // Baseline eligibility is recomputed from native dates at fixed July 20, not these legacy hints.
    const row = (type,id,current=false) => ({ key:`${type}:${id}`,type,id,name:`历史内容 ${id}`,
        originalStartMs:current?Date.parse('2025-07-19T00:00:00Z'):1,
        originalEndMs:current?Date.parse('2025-07-22T00:00:00Z'):2,
        originalExchangeEndMs:current?Date.parse('2025-07-23T00:00:00Z'):3,
        windowCandidate:current,browseCandidate:current,source:'fixture' })
    const catalog = { schemaVersion:1,source:{assetVersion:'fixture',manifestSha256:'fixture'},baselineTimeMs:1,baselineEvidence:'fixture',
        rows:[row('gacha',1,true),row('gacha',2),row('pass_card_event',15,true),row('pass_card_event',16),row('raid_event',1)],questMap:{},missing:[],resources:{} }
    const store = new ContentOperationsStore(db,catalog,r => r.type==='raid_event' ? [] : CONTENT_ACTIONS)
    function update(key,body={}) { return store.update(key,{ expectedRevision:store.revision(),catalogDigest:store.digest,reason:'isolated verification',...body },now) }
    return { db,store,update,catalog }
}
const open = { readiness:'verified',evidence:'fixture resource and rule evidence',flags:{visible:true,enter:true,claim:true,exchange:true},endsAtMs:null }

test('initialization never auto-opens current or historical candidates',t => {
    const {db,store}=fixture();t.after(()=>db.close())
    assert.equal(store.revision(),0);assert.equal(store.allowed('gacha:1','enter',now),null)
    assert.equal(store.snapshot(now).states.length,0)
    assert.deepEqual(store.list({candidatesOnly:true}).rows.map(row=>row.key),['gacha:1','pass_card_event:15'])
    assert.equal(store.list({search:'内容 2'}).rows[0].key,'gacha:2')
})
test('unverified/broken/unsupported content cannot be opened; no partial audit',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close())
    assert.throws(()=>update('gacha:2',{flags:{visible:true,enter:true}}),/未验证/)
    assert.throws(()=>update('gacha:2',{...open,readiness:'blocked'}),/故障/)
    assert.throws(()=>update('raid_event:1',open),/尚未接通/)
    assert.equal(store.revision(),0);assert.equal(db.prepare('SELECT count(*) n FROM content_operations_audit').get().n,0)
})
test('current baseline needs fixed July window and explicit evidence; history never inherits readiness',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close())
    assert.throws(()=>update('gacha:2',{...open,readiness:'current_baseline'}),/历史内容/)
    assert.throws(()=>update('gacha:1',{...open,readiness:'current_baseline',evidence:''}),/核查依据/)
    update('gacha:1',{...open,readiness:'current_baseline'})
    assert.equal(store.allowed('gacha:1','enter',now+20*365*86400000),true)
    assert.equal(store.allowed('gacha:2','enter',now),null)
})
test('permanent open -> close -> reopen keeps instance, progress, claim and stock unchanged',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close())
    const before=db.prepare('SELECT * FROM progress').all()
    const original=update('gacha:1',open)
    update('gacha:1',{flags:{visible:false,enter:false,claim:false,exchange:false}})
    const closed=store.snapshot(now)
    assert.equal(closed.full_snapshot,true);assert.equal(closed.states[0].enter,false)
    const reopened=update('gacha:1',{flags:open.flags})
    assert.equal(reopened.instanceId,original.instanceId)
    assert.deepEqual(db.prepare('SELECT * FROM progress').all(),before)
    assert.equal(db.prepare('SELECT count(*) n FROM content_operations_audit').get().n,3)
})
test('participation closes independently from earned claim/exchange rights',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close());update('gacha:1',open)
    update('gacha:1',{flags:{enter:false}})
    assert.equal(store.allowed('gacha:1','enter',now),false)
    assert.equal(store.allowed('gacha:1','exchange',now),true)
})
test('optimistic concurrency rejects stale edit atomically',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close());update('gacha:1',open)
    assert.throws(()=>update('gacha:2',{...open,expectedRevision:0}),/刷新/)
    assert.equal(store.revision(),1);assert.equal(store.state('gacha:2'),null)
})
test('rollback undoes control, global revision and audit together',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close())
    assert.throws(()=>db.transaction(()=>{update('gacha:1',open);throw new Error('abort')})(),/abort/)
    assert.equal(store.revision(),0);assert.equal(store.state('gacha:1'),null)
    assert.equal(db.prepare('SELECT count(*) n FROM content_operations_audit').get().n,0)
})
test('finite deadline uses real epoch, expiry stays closed instead of falling back',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close());update('gacha:1',{...open,endsAtMs:now+1000})
    assert.equal(store.allowed('gacha:1','enter',now+1000),true)
    assert.equal(store.allowed('gacha:1','enter',now+1001),false)
    assert.equal(store.allowed('gacha:1','enter',NaN),false)
})
test('resource catalog change invalidates old verification; explicit recheck required',t=>{
    const {db,store,update,catalog}=fixture();t.after(()=>db.close());update('gacha:1',open)
    const changed=new ContentOperationsStore(db,{...catalog,resources:{fixture:{sha256:'changed-master'}}},()=>CONTENT_ACTIONS)
    assert.equal(changed.allowed('gacha:1','enter',now),false)
    assert.equal(changed.list().rows[0].stale,true)
    assert.throws(()=>changed.update('gacha:1',{expectedRevision:1,catalogDigest:store.digest,reason:'stale'},now),/目录/)
    assert.throws(()=>changed.update('gacha:1',{expectedRevision:1,catalogDigest:changed.digest,reason:'stale',flags:{enter:true}},now),/重新核查/)
})
test('unrelated catalog publication does not close already verified current content',t=>{
    const {db,store,update,catalog}=fixture();t.after(()=>db.close());update('gacha:1',open)
    const changed=new ContentOperationsStore(db,{...catalog,source:{assetVersion:'new',manifestSha256:'new'},baselineTimeMs:now},()=>CONTENT_ACTIONS)
    assert.notEqual(changed.digest,store.digest)
    assert.equal(changed.allowed('gacha:1','enter',now),true)
    assert.equal(changed.list().rows[0].stale,false)
})
test('only one pass entry can be published and switching preserves old progress',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close());update('pass_card_event:15',open)
    assert.throws(()=>update('pass_card_event:16',open),/一个通行证/)
    update('pass_card_event:15',{flags:{visible:false,enter:false}})
    update('pass_card_event:16',open)
    assert.equal(store.allowed('pass_card_event:15','claim',now),true)
    assert.equal(db.prepare('SELECT stock FROM progress').get().stock,8)
})
test('no instance reset, malformed flags, unknown actions or incomplete control accepted',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close())
    for(const bad of [{instanceId:'rerun'}, {flags:{visible:'true'}}, {flags:{reset:true}}, {expectedRevision:NaN}, {endsAtMs:now}, {...open,flags:{enter:true,visible:false}}]) {
        assert.throws(()=>update('gacha:1',bad))
    }
    assert.equal(store.revision(),0)
})

test('server rule changes invalidate verification even with unchanged client definitions',t=>{
    const {db,store,update,catalog}=fixture();t.after(()=>db.close());update('gacha:1',open)
    const changed=new ContentOperationsStore(db,{...catalog,rows:catalog.rows.map(row=>row.key==='gacha:1'?{...row,serverDefinitionDigest:'new-rules'}:row)},()=>CONTENT_ACTIONS)
    assert.equal(changed.allowed('gacha:1','enter',now),false)
    assert.equal(changed.list().rows[0].stale,true)
    assert.equal(changed.allowed('gacha:2','enter',now),null)
})

test('removed definitions and capabilities explicitly close previously controlled keys',t=>{
    const {db,store,update,catalog}=fixture();t.after(()=>db.close());update('gacha:1',open)
    const removed=new ContentOperationsStore(db,{...catalog,rows:catalog.rows.filter(row=>row.key!=='gacha:1')},()=>[])
    assert.equal(removed.allowed('gacha:1','enter',now),false)
    assert.deepEqual(removed.snapshot(now).states.map(s=>[s.key,s.enter]),[['gacha:1',false]])
    const unsupported=new ContentOperationsStore(db,catalog,()=>[])
    assert.equal(unsupported.snapshot(now).states[0].enter,false)
    update('raid_event:1',{readiness:'blocked',evidence:'not wired; review only'})
    assert.equal(store.snapshot(now).states.some(s=>s.key==='raid_event:1'),false)
    const removedReview=new ContentOperationsStore(db,{...catalog,rows:catalog.rows.filter(row=>row.key!=='raid_event:1')},row=>row.type==='raid_event'?[]:CONTENT_ACTIONS)
    assert.equal(removedReview.snapshot(now).states.some(s=>s.key==='raid_event:1'),false)
})

test('malformed persisted state stays closed, appears damaged, and needs explicit recheck',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close());update('gacha:1',open)
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run('{broken','gacha:1')
    assert.equal(store.allowed('gacha:1','enter',now),false)
    assert.equal(store.snapshot(now).states[0].enter,false)
    assert.equal(store.list().rows[0].state.integrityError,'invalid_persisted_state')
    assert.throws(()=>update('gacha:1',{flags:{visible:true,enter:true}}),/故障/)
    update('gacha:1',open)
    assert.equal(store.allowed('gacha:1','enter',now),true)
    assert.equal(store.state('gacha:1').integrityError,undefined)
})

test('audit pagination is stable and read-only across close and reopen',t=>{
    const {db,store,update}=fixture();t.after(()=>db.close());update('gacha:1',open)
    update('gacha:1',{flags:{enter:false}})
    update('gacha:2',open)
    const page=store.audit({limit:2})
    assert.deepEqual(page.rows.map(row=>row.revision),[3,2])
    assert.equal(page.rows[1].before.flags.enter,true)
    assert.equal(page.rows[1].after.flags.enter,false)
    assert.deepEqual(store.audit({beforeRevision:2}).rows.map(row=>row.revision),[1])
    assert.deepEqual(store.audit({key:'gacha:1'}).rows.map(row=>row.revision),[2,1])
    assert.equal(store.revision(),3)
})

test('wiring capabilities stay visible while missing definitions refuse activation',t=>{
    const {db,catalog}=fixture();t.after(()=>db.close())
    const mismatch=new ContentOperationsStore(db,{...catalog,rows:catalog.rows.map(row=>({...row,definitionEvidence:{status:'mismatch',serverSources:[],clientQuestMappings:0,serverQuestMatches:0,missingQuestKeys:[],issues:['fixture mismatch']}}))},()=>CONTENT_ACTIONS)
    assert.deepEqual(mismatch.list().rows[0].capabilities,CONTENT_ACTIONS)
    assert.throws(()=>mismatch.update('gacha:1',{expectedRevision:0,catalogDigest:mismatch.digest,reason:'fixture',...open},now),/定义/)
    assert.equal(mismatch.revision(),0)
})

test('two SQLite connections share revision and reopen preserves state and audit',t=>{
    const fs=require('node:fs'),os=require('node:os'),path=require('node:path')
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'content-state-restart-'))
    const file=path.join(dir,'synthetic.db')
    const f=fixture();const catalog=f.catalog;f.db.close()
    let first=new Sqlite(file),second=new Sqlite(file)
    t.after(()=>{if(first.open)first.close();if(second.open)second.close();fs.rmSync(dir,{recursive:true})})
    initializeContentOperationsSchema(first)
    const a=new ContentOperationsStore(first,catalog,()=>CONTENT_ACTIONS)
    const b=new ContentOperationsStore(second,catalog,()=>CONTENT_ACTIONS)
    const initial={expectedRevision:0,catalogDigest:a.digest,reason:'two connection fixture',...open}
    a.update('gacha:1',initial,now)
    assert.throws(()=>b.update('gacha:2',initial,now),/刷新/)
    assert.equal(b.revision(),1);assert.equal(b.state('gacha:2'),null)
    first.close();second.close()
    first=new Sqlite(file)
    const restarted=new ContentOperationsStore(first,catalog,()=>CONTENT_ACTIONS)
    initializeContentOperationsSchema(first)
    assert.equal(restarted.revision(),1)
    assert.equal(restarted.allowed('gacha:1','enter',now+86400000),true)
    assert.equal(restarted.audit().rows[0].after.instanceId,'gacha:1:original')
})

test('review-only state keeps legacy policy until an explicit wired takeover',t=>{
    const {db,store,update,catalog}=fixture();t.after(()=>db.close())
    update('raid_event:1',{readiness:'blocked',evidence:'unsupported review record'})
    assert.equal(store.allowed('raid_event:1','enter',now),null)
    const wired=new ContentOperationsStore(db,catalog,()=>CONTENT_ACTIONS)
    assert.equal(wired.allowed('raid_event:1','enter',now),null)
    assert.equal(wired.snapshot(now).states.some(s=>s.key==='raid_event:1'),false)
    wired.update('raid_event:1',{expectedRevision:1,catalogDigest:wired.digest,reason:'explicit wired takeover',readiness:'verified',evidence:'fixture',flags:open.flags},now)
    assert.equal(wired.allowed('raid_event:1','enter',now),true)
    assert.equal(wired.snapshot(now).states[0].key,'raid_event:1')
})

test('manual verified gacha can override a historical calendar mismatch only',t=>{
    const {db,catalog}=fixture();t.after(()=>db.close())
    const c={...catalog,rows:catalog.rows.map(row=>({...row,definitionEvidence:{status:'mismatch',serverSources:[],clientQuestMappings:0,serverQuestMatches:0,missingQuestKeys:[],issues:['startDate differs','endDate differs']}}))}
    const store=new ContentOperationsStore(db,c,()=>CONTENT_ACTIONS)
    assert.equal(store.list().rows[0].definitionReady,true)
    assert.throws(()=>store.update('gacha:1',{expectedRevision:0,catalogDigest:store.digest,reason:'calendar only',flags:open.flags},now),/未验证/)
    store.update('gacha:1',{expectedRevision:0,catalogDigest:store.digest,reason:'explicit acceptance',...open},now)
    assert.equal(store.allowed('gacha:1','enter',now+20*365*86400000),true)
    assert.equal(store.list().rows.find(r=>r.type==='pass_card_event').definitionReady,false)
})

test('runtime definition drift closes old state and rejects recheck against stale capture',t=>{
    const {db,catalog}=fixture();t.after(()=>db.close())
    const current=new ContentOperationsStore(db,catalog,()=>CONTENT_ACTIONS,()=>({digest:'captured',matchesCatalog:true}))
    current.update('gacha:1',{expectedRevision:0,catalogDigest:current.digest,reason:'fixture',...open},now)
    const changed=new ContentOperationsStore(db,catalog,()=>CONTENT_ACTIONS,()=>({digest:'new-runtime',matchesCatalog:false}))
    assert.equal(changed.allowed('gacha:1','enter',now),false)
    assert.equal(changed.list().rows[0].definitionReady,false)
    assert.equal(changed.list().rows[0].stale,true)
    assert.throws(()=>changed.update('gacha:1',{expectedRevision:1,catalogDigest:changed.digest,reason:'stale-capture',...open},now),/重导出/)
    assert.equal(changed.revision(),1)
})
