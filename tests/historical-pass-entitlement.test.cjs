const {test,before,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path')
const root=process.env.HISTORICAL_PASS_TEST_ROOT||path.resolve(__dirname,'../.test-data')
fs.mkdirSync(root,{recursive:true})
const directory=fs.mkdtempSync(path.join(root,'historical-pass-'))
process.env.DATA_DIR=directory;process.env.CN_WRITER_THREAD='0'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
const db=require('../out/data/db').getDb()
const players=require('../out/data/domains/player'),passes=require('../out/data/domains/pass-card')
const missions=require('../out/data/domains/mission'),master=require('../out/lib/mission/master-data')
const operations=require('../out/lib/content-operations')
const {initializeContentOperationsSchema}=require('../out/lib/content-operations-store')
let app
function control(key,input) {
    const store=operations.contentOperations()
    store.update(key,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'Isolated retained-pass HTTP test',...input},Date.now())
}
function action(enabled) {return {enabled,endsAtMs:null,readiness:'verified',evidence:'Exact original-instance persisted fixture'}}
function subject() {
    const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'retained-pass',idpId:'',status:'normal'})
    const p=players.insertDefaultPlayerSync(account.id),viewer=860000000+p.id
    require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,p.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00Z')
    return {...p,viewer}
}
function post(p,url,body={}) {return app.inject({method:'POST',url,payload:{viewer_id:p.viewer,...body}})}
function data(r) {assert.equal(r.statusCode,200,r.body);return unpack(Buffer.from(r.body,'base64')).data}
function tables(p) {
    return Object.fromEntries(['players_pass_cards','players_pass_card_rewards','players_periodic_snapshots',
        'players_category_missions','players_category_mission_stages','players_items'].map(table=>[table,
        db.prepare(`SELECT * FROM ${table} WHERE player_id=? ORDER BY rowid`).all(p.id)]))
}
const list=(p)=>post(p,'/get_retained_pass_cards')
before(async()=>{
    initializeContentOperationsSchema(db)
    // Production store/default policy, and the actual July controls for pass14/15.
    const plan=require('../assets/content_july_controls.json')
    for(const id of [14,15]) {
        const entry=plan.controls.find(row=>row.key===`pass_card_event:${id}`)
        assert.ok(entry)
        control(entry.key,{actionOverrides:entry.actionOverrides})
    }
    assert.equal(operations.contentDecision('pass_card_event',14,'visible',Date.now()),true)
    assert.equal(operations.contentDecision('pass_card_event',15,'visible',Date.now()),false)
    assert.equal(operations.contentDecision('pass_card_event',15,'enter',Date.now()),false)
    assert.equal(operations.contentDecision('pass_card_event',15,'claim',Date.now()),true)
    app=Fastify({logger:false})
    app.addHook('onSend',(_request,reply,body,done)=>done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
    await app.register(require('../out/routes/api/passCard').default)
    await app.ready()
})
after(async()=>{if(app)await app.close();db.close();fs.rmSync(directory,{recursive:true})})

test('history requires authentication and excludes empty, baseline-only and unknown cards without writes',async()=>{
    const p=subject()
    db.prepare('INSERT INTO players_pass_cards(player_id,event_id,point,is_buy,login_baseline) VALUES(?,?,?,?,?)').run(p.id,15,0,0,7)
    passes.setPlayerPassCardRewardReceivedSync(p.id,15,781,true,false)
    passes.setPlayerPassCardRewardReceivedSync(p.id,15,999999,true,false)
    passes.addPlayerPassCardPointSync(p.id,999999,100)
    const saved=tables(p)
    assert.equal((await app.inject({method:'POST',url:'/get_retained_pass_cards',payload:{viewer_id:1}})).statusCode,400)
    assert.deepEqual(data(await list(p)).retained_pass_card_list,[])
    assert.equal((await post(p,'/get_pass_card',{pass_card_id:15})).statusCode,400)
    assert.equal((await post(p,'/get_pass_card',{pass_card_id:999999})).statusCode,400)
    assert.equal((await post(p,'/receive_all',{pass_card_id:15})).statusCode,400)
    assert.equal((await post(p,'/receive_all',{pass_card_id:15,reward1_receive:[841]})).statusCode,400)
    assert.deepEqual(tables(p),saved)
})

test('hidden pass15 points remain reachable beside visible pass14 and free reward grants exactly once',async()=>{
    const p=subject();passes.addPlayerPassCardPointSync(p.id,15,1000)
    const saved=tables(p)
    const cards=data(await list(p)).retained_pass_card_list
    assert.deepEqual(cards,[{pass_card_id:15,point:1000,is_buy:false,all_received_record:[]}])
    assert.deepEqual(data(await post(p,'/get_pass_card',{pass_card_id:15})),{point:1000,is_buy:false,all_received_record:[]})
    assert.deepEqual(tables(p),saved,'history and direct get are read-only')
    assert.equal((await post(p,'/receive_all',{pass_card_id:15,reward2_receive:[841]})).statusCode,400)
    assert.deepEqual(tables(p),saved,'history does not invent premium purchase')
    const reward=data(await post(p,'/receive_all',{pass_card_id:15,reward1_receive:[841]}))
    assert.deepEqual(reward.item_list,{'999003':1})
    const received=tables(p)
    assert.deepEqual(data(await post(p,'/receive_all',{pass_card_id:15,reward1_receive:[841]})).item_list,{})
    assert.deepEqual(tables(p),received)
    assert.equal(passes.getPlayerPassCardStateSync(p.id,15).isBuy,false)
})

test('premium flags, old receipts and exact-instance mission progress qualify without creating state',async()=>{
    const bought=subject()
    db.prepare('INSERT INTO players_pass_cards(player_id,event_id,point,is_buy) VALUES(?,?,?,?)').run(bought.id,15,0,1)
    const boughtBefore=tables(bought)
    assert.equal(data(await list(bought)).retained_pass_card_list[0].is_buy,true)
    assert.deepEqual(tables(bought),boughtBefore)
    const premium=subject()
    db.prepare('INSERT INTO players_pass_cards(player_id,event_id,point,is_buy) VALUES(?,?,?,?)').run(premium.id,15,1000,1)
    passes.setPlayerPassCardRewardReceivedSync(premium.id,15,842,true,true)
    const before=tables(premium)
    assert.equal(data(await list(premium)).retained_pass_card_list[0].is_buy,true)
    assert.deepEqual(tables(premium),before)
    assert.deepEqual(data(await post(premium,'/receive_all',{pass_card_id:15,reward2_receive:[841]})).item_list,{'999001':1})
    assert.deepEqual(passes.getPlayerPassCardRewardRecordsSync(premium.id,15),[
        {rewardId:841,isReceived1:0,isReceived2:1},{rewardId:842,isReceived1:1,isReceived2:1}])
    const receipt=subject();passes.addPlayerPassCardPointSync(receipt.id,15,0)
    passes.setPlayerPassCardRewardReceivedSync(receipt.id,15,841,true,false)
    const receiptBefore=tables(receipt)
    assert.equal(data(await list(receipt)).retained_pass_card_list[0].pass_card_id,15)
    assert.deepEqual(tables(receipt),receiptBefore)
    const progress=subject()
    const definition=master.getMissionMasterDefinitions(6).find(row=>row.eventId===15)
    missions.updatePlayerCategoryMissionSync(progress.id,6,definition.missionId,11)
    const progressBefore=tables(progress)
    assert.equal(data(await list(progress)).retained_pass_card_list[0].pass_card_id,15)
    assert.equal(data(await post(progress,'/get_pass_card',{pass_card_id:15})).point,0)
    assert.deepEqual(tables(progress),progressBefore,'no synthetic point or login baseline')
})

test('closed claim gate hides historical state and rejects new rewards; reopen retains receipts and progress',async()=>{
    const p=subject();passes.addPlayerPassCardPointSync(p.id,15,1000)
    control('pass_card_event:15',{actionOverrides:{claim:action(false)}})
    const saved=tables(p)
    assert.deepEqual(data(await list(p)).retained_pass_card_list,[])
    assert.equal((await post(p,'/get_pass_card',{pass_card_id:15})).statusCode,400)
    assert.equal((await post(p,'/receive_all',{pass_card_id:15,reward1_receive:[841]})).statusCode,400)
    assert.deepEqual(tables(p),saved)
    control('pass_card_event:15',{actionOverrides:{claim:action(true)}})
    assert.equal(data(await list(p)).retained_pass_card_list[0].point,1000)
    assert.deepEqual(tables(p),saved)
})
