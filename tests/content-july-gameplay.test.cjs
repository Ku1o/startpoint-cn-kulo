'use strict'
const {test,before,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const fixtureRoot=path.resolve(process.env.JULY_OFFLINE_FIXTURE_ROOT||os.tmpdir())
fs.mkdirSync(fixtureRoot,{recursive:true})
const directory=fs.mkdtempSync(path.join(fixtureRoot,'july-gameplay-'))
process.env.DATA_DIR=directory;process.env.GACHA_SEED_DIR=path.join(directory,'seeds')
fs.mkdirSync(process.env.GACHA_SEED_DIR)
process.env.CN_WRITER_THREAD='0';process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
const {initializeDatabase}=require('../out/data'),{getDb}=require('../out/data/db')
const players=require('../out/data/domains/player'),missions=require('../out/data/domains/mission')
const passes=require('../out/data/domains/pass-card'),gachas=require('../out/data/domains/gacha')
const items=require('../out/data/domains/item'),assets=require('../out/lib/assets')
const operations=require('../out/lib/content-operations')
const {applyJulyContentPlanOfflineSync,julyContentPlan}=require('../out/lib/content-operations-bootstrap')
const coordinator=require('../out/lib/persistence-coordinator'),transaction=coordinator.runPersistenceTransaction
const clock=require('../out/utils'),seed=require('../out/lib/seed-validator').default
const quests=require('../out/data/domains/quest_active')
const poolId=1704,personalPoolId=80001,eventKey='challenge_dungeon_event:1',category=13,questId=1017
const future=Date.parse('2051-01-01T00:00:00Z'),originalOffset=clock.getLegacyTimeOffset()
let app,db,p,viewer,pool,goldenState,playerTables
const quote=name=>'"'+name.replaceAll('"','""')+'"'
function post(url,body) {return app.inject({method:'POST',url,payload:{viewer_id:viewer,...body}})}
function decode(response) {assert.equal(response.statusCode,200,response.body);return unpack(Buffer.from(response.body,'base64'))}
function snapshot() {
    return Object.fromEntries(playerTables.map(({name,owner})=>[name,
        db.prepare(`SELECT * FROM ${quote(name)} WHERE ${quote(owner)}=?`).all(p.id)
            .sort((left,right)=>JSON.stringify(left).localeCompare(JSON.stringify(right)))]))
}
function golden() {return {mission:missions.getPlayerCategoryMissionsSync(p.id,6)['53'],
    pass:passes.getPlayerPassCardStateSync(p.id,15),receipts:passes.getPlayerPassCardRewardRecordsSync(p.id,15),
    retainedItem:items.getPlayerItemSync(p.id,14040)}}
function enter(key,enabled) {
    const store=operations.contentOperations()
    return store.update(key,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'Isolated reviewed-July gameplay gate',
        actionOverrides:{enter:{enabled,endsAtMs:null,readiness:'verified',evidence:'Same reviewed original instance and retained scope'}}},Date.now())
}
function apply() {
    const store=operations.contentOperations()
    return applyJulyContentPlanOfflineSync(store,{expectedRevision:store.revision(),expectedCatalogDigest:store.digest,nowMs:Date.now(),
        offlineGuard:{kind:'approved-offline-file',databasePath:fs.realpathSync(db.name),allowedRoot:fixtureRoot}})
}
const draw=()=>post('/gacha/exec',{gacha_id:poolId,payment_type:1,type:1,number_of_exec:1})
function start(playId,id=questId) {return post('/single/start',{category,quest_id:id,party_id:1,play_id:playId,
    use_boost_point:false,use_boss_boost_point:false,is_auto_start_mode:false,api_count:1})}
function finish(playId) {return post('/single/finish',{category,quest_id:questId,play_id:playId,continue_count:0,
    elapsed_time_ms:1000,score:12345,add_mana:0,is_accomplished:true,is_restored:false,api_count:2,
    statistics:{clear_phase:1,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],
        equipments:[null,null,null],ability_soul_ids:[null,null,null]},zones:[]}})}
before(async()=>{
    initializeDatabase();db=getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(directory))
    // This process has no committed clock. Use the supported legacy fixture
    // offset so the final queued transaction also captures a post-expiry date.
    clock.setServerTimeOffset(future-Date.now())
    const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'july-gameplay',idpId:'fixture',status:'normal'})
    p=players.insertDefaultPlayerSync(account.id);viewer=890000000+p.id
    require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,p.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00Z')
    players.updatePlayerSync({id:p.id,freeVmoney:10000,vmoney:5000})
    missions.updatePlayerCategoryMissionSync(p.id,6,53,11);missions.updatePlayerCategoryMissionStageSync(p.id,6,1,53,true)
    passes.addPlayerPassCardPointSync(p.id,15,777)
    db.prepare('UPDATE players_pass_cards SET is_buy=1 WHERE player_id=? AND event_id=15').run(p.id)
    passes.setPlayerPassCardRewardReceivedSync(p.id,15,841,true,true)
    items.setPlayerItemSync(p.id,14040,7)
    gachas.insertPlayerGachaInfoSync(p.id,{gachaId:poolId,isAccountFirst:false,isDailyFirst:false,gachaExchangePoint:9})
    gachas.insertPlayerGachaInfoSync(p.id,{gachaId:personalPoolId,isAccountFirst:false,isDailyFirst:false,gachaExchangePoint:9})
    playerTables=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all()
        .map(({name})=>({name,columns:db.prepare(`PRAGMA table_info(${quote(name)})`).all().map(column=>column.name)}))
        .filter(row=>row.name==='players'||row.columns.includes('player_id'))
        .map(row=>({name:row.name,owner:row.name==='players'?'id':'player_id'}))
    goldenState=golden()
    pool=assets.getGachaSync(poolId)
    assert.ok(julyContentPlan.controls.some(row=>row.key===`gacha:${poolId}`))
    assert.equal(pool.paymentType,0);assert.equal(pool.singleCost,150)
    assert.ok(clock.getServerDate().getTime()>Date.parse(pool.endDate.replace(' ','T')+'+08:00'))
    app=Fastify({logger:false})
    app.addHook('onSend',(_request,reply,body,done)=>done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
    await app.register(require('../out/routes/api/gacha').default,{prefix:'/gacha'})
    await app.register(require('../out/routes/api/singleBattleQuest').default,{prefix:'/single'})
    await app.ready()
})
after(async()=>{
    coordinator.runPersistenceTransaction=transaction
    if(app)await app.close();await seed.close();if(db?.open)db.close()
    clock.setServerTimeOffset(originalOffset)
    assert.equal(path.dirname(fs.realpathSync(directory)),fs.realpathSync(fixtureRoot))
    fs.rmSync(directory,{recursive:true})
})

test('actual offline July bootstrap opens the reviewed pool and exact event quest without changing nonempty progress',()=>{
    assert.equal(operations.contentDecision('gacha',poolId,'enter',Date.now()),false)
    const saved=snapshot(),result=apply()
    assert.equal(result.applied,true);assert.equal(result.controls,julyContentPlan.controls.length)
    assert.equal(db.prepare('SELECT COUNT(*) n FROM content_operations_state').get().n,result.controls)
    assert.deepEqual(snapshot(),saved)
    assert.equal(operations.contentDecision('gacha',poolId,'enter',Date.now()),true)
    assert.equal(operations.contentQuestDecision(category,questId),true)
    assert.equal(operations.contentQuestDecision(category,1020),false)
    assert.deepEqual(golden(),goldenState)
})

test('reviewed ordinary pool1704 draws after expiry; personal pool80001 still requires personal qualification',async()=>{
    const personalBefore=snapshot()
    assert.equal(operations.contentDecision('gacha',personalPoolId,'enter',Date.now()),true)
    const denied=await post('/gacha/exec',{gacha_id:personalPoolId,payment_type:1,type:1,number_of_exec:1})
    assert.equal(denied.statusCode,400)
    assert.match(denied.json().message,/Personal gacha period qualification/)
    assert.deepEqual(snapshot(),personalBefore,'operator entry cannot grant personal eligibility or consume existing points')
    assert.equal(gachas.getPlayerGachaInfoSync(p.id,personalPoolId).gachaExchangePoint,9)
    const before=players.getPlayerSync(p.id)
    const history=db.prepare('SELECT COUNT(*) n FROM players_receive_history WHERE player_id=?').get(p.id).n
    const result=decode(await draw())
    assert.equal(result.data_headers.result_code,1)
    assert.equal(result.data.draw.length,1)
    const allowedIds=new Set(Object.values(pool.pool).flat().map(row=>row.id))
    assert.ok(allowedIds.has(result.data.draw[0].character_id))
    assert.ok(require('../out/data/domains/character').getPlayerCharacterSync(p.id,result.data.draw[0].character_id))
    assert.equal(players.getPlayerSync(p.id).freeVmoney,before.freeVmoney-pool.singleCost)
    assert.equal(players.getPlayerSync(p.id).vmoney,before.vmoney)
    assert.equal(gachas.getPlayerGachaInfoSync(p.id,poolId).gachaExchangePoint,10)
    assert.equal(db.prepare('SELECT COUNT(*) n FROM players_receive_history WHERE player_id=?').get(p.id).n,history+1)
    assert.deepEqual(golden(),goldenState)
})

test('reviewed pool final-queue closure charges nothing; bootstrap replay and reopen do not reset points',async()=>{
    const store=operations.contentOperations(),instance=store.state(`gacha:${poolId}`).instanceId,saved=snapshot()
    let queued=false
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{
        if(context.operation==='draw') {queued=true;enter(`gacha:${poolId}`,false)}
        return transaction(context,fn,options)
    }
    try {assert.equal((await draw()).statusCode,400);assert.equal(queued,true)}
    finally {coordinator.runPersistenceTransaction=transaction}
    assert.deepEqual(snapshot(),saved)
    assert.equal(apply().applied,false)
    assert.equal(operations.contentDecision('gacha',poolId,'enter',Date.now()),false)
    enter(`gacha:${poolId}`,true)
    assert.equal(store.state(`gacha:${poolId}`).instanceId,instance)
    assert.deepEqual(snapshot(),saved)
    assert.equal(decode(await draw()).data.draw.length,1)
    assert.equal(gachas.getPlayerGachaInfoSync(p.id,poolId).gachaExchangePoint,11)
    assert.deepEqual(golden(),goldenState)
})

test('all eight fixed-day pools omitted by the old capture really draw, close without charging and reopen with counts intact',async()=>{
    for(const id of [1704,1705,1706,1707,1708,1709,1710,25043]) {
        const definition=assets.getGachaSync(id),key=`gacha:${id}`
        assert.ok(julyContentPlan.controls.some(row=>row.key===key),key)
        const exec=()=>post('/gacha/exec',{gacha_id:id,payment_type:1,type:1,number_of_exec:1})
        const before=players.getPlayerSync(p.id),points=gachas.getPlayerGachaInfoSync(p.id,id)?.gachaExchangePoint??0
        const result=decode(await exec())
        assert.equal(result.data_headers.result_code,1,key)
        const draws=result.data[definition.type===0?'draw':'draw_equipment']
        assert.equal(draws.length,1,key)
        const allowed=new Set(Object.values(definition.pool).flat().map(row=>row.id))
        assert.ok(allowed.has(draws[0][definition.type===0?'character_id':'equipment_id']),key)
        assert.equal(players.getPlayerSync(p.id).freeVmoney,before.freeVmoney-definition.singleCost,key)
        assert.equal(gachas.getPlayerGachaInfoSync(p.id,id).gachaExchangePoint,points+1,key)
        const saved=snapshot(),instance=operations.contentOperations().state(key).instanceId
        enter(key,false)
        assert.equal((await exec()).statusCode,400,key)
        assert.deepEqual(snapshot(),saved,key+' close cannot charge or consume a draw')
        enter(key,true)
        assert.equal(operations.contentOperations().state(key).instanceId,instance,key)
        assert.equal(decode(await exec()).data[definition.type===0?'draw':'draw_equipment'].length,1,key)
        assert.equal(gachas.getPlayerGachaInfoSync(p.id,id).gachaExchangePoint,points+2,key)
        assert.equal(players.getPlayerSync(p.id).freeVmoney,before.freeVmoney-2*definition.singleCost,key)
    }
    assert.deepEqual(golden(),goldenState)
})

test('target-day event13:1017 starts; future child period remains closed and final-queue closure preserves its battle',async()=>{
    const siblingBefore=snapshot()
    assert.equal(decode(await start('july-denied-sibling',1020)).data_headers.result_code,4050)
    assert.deepEqual(snapshot(),siblingBefore)
    assert.equal(decode(await start('july-reviewed-event')).data_headers.result_code,1)
    const active=quests.getPlayerActiveQuestSync(p.id)
    assert.equal(active.category,13);assert.equal(active.questId,1017);assert.equal(active.playId,'july-reviewed-event')
    const saved=snapshot();let queued=false
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{
        if(context.domain==='single-quest'&&context.operation==='start') {queued=true;enter(eventKey,false)}
        return transaction(context,fn,options)
    }
    try {assert.equal(decode(await start('july-denied-queued-event')).data_headers.result_code,4050);assert.equal(queued,true)}
    finally {coordinator.runPersistenceTransaction=transaction}
    assert.deepEqual(snapshot(),saved)
    assert.deepEqual(quests.getPlayerActiveQuestSync(p.id),active)
    const result=decode(await finish(active.playId))
    assert.equal(result.data_headers.result_code,1)
    assert.equal(quests.getPlayerActiveQuestSync(p.id),null)
    const progress=db.prepare('SELECT * FROM players_quest_progress WHERE player_id=? AND section=13 AND quest_id=1017').get(p.id)
    assert.equal(progress.finished,1)
    const after=snapshot()
    assert.deepEqual(decode(await finish(active.playId)),result)
    assert.deepEqual(snapshot(),after,'registered pre-closure battle settles exactly once')
    const instance=operations.contentOperations().state(eventKey).instanceId
    enter(eventKey,true)
    assert.equal(operations.contentOperations().state(eventKey).instanceId,instance)
    assert.equal(operations.contentQuestDecision(category,1020),false,'reopening retains exact target-day child scope')
    assert.deepEqual(snapshot(),after)
    assert.equal(decode(await start('july-reopened-event')).data_headers.result_code,1)
    assert.deepEqual(db.prepare('SELECT * FROM players_quest_progress WHERE player_id=? AND section=13 AND quest_id=1017').get(p.id),progress)
    assert.deepEqual(golden(),goldenState)
})
