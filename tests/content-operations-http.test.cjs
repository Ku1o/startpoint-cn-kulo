'use strict'
const {test,before,after}=require('node:test')
const assert=require('node:assert/strict')
const fs=require('node:fs'), os=require('node:os'), path=require('node:path'), crypto=require('node:crypto')
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'content-operations-http-'))
process.env.DATA_DIR=temporary;process.env.GACHA_SEED_DIR=path.join(temporary,'seeds');fs.mkdirSync(process.env.GACHA_SEED_DIR)
process.env.CN_WRITER_THREAD='0'
process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
const {initializeDatabase}=require('../out/data')
const {getDb}=require('../out/data/db')
const players=require('../out/data/domains/player')
const operations=require('../out/lib/content-operations')
const coordinator=require('../out/lib/persistence-coordinator')
const originalTransaction=coordinator.runPersistenceTransaction
const seed=require('../out/lib/seed-validator').default
let app, playerId, viewerId, accessToken, adminCookie, baselineFiles
const paths=['assets/asset-patch/manifest.json','assets/content_catalog.json','assets/pass_card_event.json']
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(path.resolve(__dirname,'..',file))).digest('hex')
function control(key,body={}) { const s=operations.contentOperations();return s.update(key,{expectedRevision:s.revision(),catalogDigest:s.digest,reason:'isolated test',...body},Date.now()) }
function post(url,body) { return app.inject({method:'POST',url,payload:{viewer_id:viewerId,...body}}) }
function adminRequest(request) {
    return app.inject(typeof request==='string'?{url:request,headers:{cookie:adminCookie}}:
        {...request,headers:{...request.headers,cookie:adminCookie}})
}
function balances() { return getDb().prepare('SELECT vmoney,free_vmoney FROM players WHERE id=?').get(playerId) }
function clockState() {
    return Object.fromEntries(['server_time_migration_config','player_time_state','player_time_migration_ledger'].map(table=>[
        table,getDb().prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(table)
            ? getDb().prepare(`SELECT * FROM ${table}`).all():null,
    ]))
}
function decode(response) { assert.equal(response.statusCode,200,response.body);return unpack(Buffer.from(response.body,'base64')) }
const open={readiness:'verified',evidence:'isolated fixture only',flags:{visible:true,enter:true,exchange:true},endsAtMs:null}
before(async()=>{
    baselineFiles=paths.map(hash);initializeDatabase()
    assert.ok(fs.realpathSync(getDb().name).startsWith(fs.realpathSync(temporary)+path.sep))
    const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'test',idpId:'content-operations',status:'normal'})
    playerId=players.insertDefaultPlayerSync(account.id).id;viewerId=840000000+playerId
    require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,playerId)
    players.updatePlayerSync({id:playerId,vmoney:10000,freeVmoney:10000})
    getDb().prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewerId),account.id,'2099-01-01T00:00:00.000Z')
    accessToken='content-operations-zat'
    getDb().prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,0)').run(accessToken,account.id,'2099-01-01T00:00:00.000Z')
    // Auth sessions live in the same process; use the real login route on a separate
    // fixture app so its broad management guard does not cover the legacy game /load.
    const authApp=Fastify({logger:false})
    const previousPassword=process.env.ADMIN_PANEL_PASSWORD
    process.env.ADMIN_PANEL_PASSWORD='content-operations-fixture-password'
    try {
        require('../out/lib/management-auth').installManagementAuth(authApp)
        const login=await authApp.inject({method:'POST',url:'/admin-login',payload:{password:process.env.ADMIN_PANEL_PASSWORD}})
        assert.equal(login.statusCode,200,login.body)
        adminCookie=login.headers['set-cookie'].split(';')[0]
    } finally {
        await authApp.close()
        if(previousPassword===undefined)delete process.env.ADMIN_PANEL_PASSWORD
        else process.env.ADMIN_PANEL_PASSWORD=previousPassword
    }
    app=Fastify({logger:false})
    app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
    await app.register(require('../out/routes/web_api/content').default,{prefix:'/admin-content'})
    await app.register(require('../out/routes/cn/load').default,{prefix:'/cn'})
    await app.register(require('../out/routes/api/index').default,{prefix:'/legacy'})
    await app.register(require('../out/routes/api/gacha').default,{prefix:'/gacha'})
    await app.register(require('../out/routes/api/singleBattleQuest').default,{prefix:'/single'})
    await app.ready()
})
after(async()=>{
    coordinator.runPersistenceTransaction=originalTransaction
    if(app)await app.close();await seed.close();getDb().close()
    assert.deepEqual(paths.map(hash),baselineFiles,'operations never rewrite catalog, master or manifest')
    assert.equal(path.dirname(fs.realpathSync(temporary)),fs.realpathSync(os.tmpdir()))
    fs.rmSync(temporary,{recursive:true})
})
test('catalog API searches history, validates pagination and refuses unsafe activation',async()=>{
    assert.equal((await app.inject('/admin-content/')).statusCode,401,'plugin protects legacy mounts without a global guard')
    assert.equal((await app.inject({method:'PATCH',url:'/admin-content/gacha%3A1',payload:{reason:'unauthorized'}})).statusCode,401)
    const response=await adminRequest('/admin-content/?search=gacha%3A1&limit=20')
    assert.equal(response.statusCode,200,response.body);const data=response.json()
    assert.ok(data.rows.some(r=>r.key==='gacha:1'));assert.ok(data.total>0)
    assert.equal((await adminRequest('/admin-content/?limit=NaN')).statusCode,400)
    const invalid=await adminRequest({method:'PATCH',url:'/admin-content/gacha%3A1',payload:{expectedRevision:data.revision,catalogDigest:data.catalogDigest,reason:'not verified',flags:{visible:true}}})
    assert.equal(invalid.statusCode,409,invalid.body)
    const saved=await adminRequest({method:'PATCH',url:'/admin-content/gacha%3A1',payload:{expectedRevision:data.revision,catalogDigest:data.catalogDigest,reason:'fixture verified',...open}})
    assert.equal(saved.statusCode,200,saved.body)
    assert.equal((await adminRequest({method:'PATCH',url:'/admin-content/gacha%3A1',payload:{expectedRevision:data.revision,catalogDigest:data.catalogDigest,reason:'stale edit',flags:{enter:false}}})).statusCode,409)
})
test('production content admin prefix is covered by management authentication',async()=>{
    const protectedApp=Fastify({logger:false})
    require('../out/lib/management-auth').installManagementAuth(protectedApp)
    await protectedApp.register(require('../out/routes/web_api/content').default,{prefix:'/api/content'})
    try {
        for (const request of [
            {method:'GET',url:'/api/content/'},
            {method:'PATCH',url:'/api/content/gacha%3A1',payload:{reason:'unauthorized'}},
        ]) {
            const response=await protectedApp.inject(request)
            assert.equal(response.statusCode,401,response.body)
        }
    } finally { await protectedApp.close() }
})
test('authenticated refresh returns explicit full state including closed entries',async()=>{
    for (const viewer_id of [null,'123',-1,0,1.5]) {
        assert.equal((await post('/cn/content_operations',{viewer_id})).statusCode,400)
    }
    assert.equal((await post('/cn/content_operations',{viewer_id:accessToken})).statusCode,400)
    assert.equal((await post('/cn/content_operations',{viewer_id:999999999})).statusCode,401)
    control('gacha:1',{flags:{enter:false}})
    const state=decode(await post('/cn/content_operations',{})).data.content_operations
    assert.equal(state.full_snapshot,true);assert.equal(state.states.find(s=>s.key==='gacha:1').enter,false)
    assert.equal(state.states.find(s=>s.key==='gacha:1').exchange,true)
})
test('both login routes include full explicit operations without migrating player clocks',async()=>{
    const before=clockState()
    for (const [url,body] of [['/cn/load',{}],['/legacy/load',{access_token:accessToken}]]) {
        const state=decode(await post(url,body)).data.content_operations
        assert.equal(state.full_snapshot,true)
        assert.equal(state.states.find(s=>s.key==='gacha:1').enter,false)
        assert.equal(state.states.find(s=>s.key==='gacha:1').exchange,true)
    }
    assert.deepEqual(clockState(),before)
})
test('gacha operator close is checked inside queued transaction without charging or resetting state',async()=>{
    control('gacha:1',open);const before=balances()
    let reached=false
    coordinator.runPersistenceTransaction=async(ctx,fn,options)=>{
        if(ctx.operation==='draw'){reached=true;control('gacha:1',{flags:{enter:false}})}
        return originalTransaction(ctx,fn,options)
    }
    try{
        const response=await post('/gacha/exec',{gacha_id:1,payment_type:1,type:1,number_of_exec:1})
        assert.equal(response.statusCode,400,response.body);assert.match(response.body,/not available/)
        assert.equal(reached,true);assert.deepEqual(balances(),before)
        assert.equal(require('../out/data/domains/gacha').getPlayerGachaInfoSync(playerId,1),null)
    }finally{coordinator.runPersistenceTransaction=originalTransaction}
})
test('closed gacha rejects before planning or queueing',async()=>{
    control('gacha:1',{flags:{enter:false}})
    let queued=false
    coordinator.runPersistenceTransaction=async(ctx,fn,options)=>{
        if(ctx.operation==='draw')queued=true
        return originalTransaction(ctx,fn,options)
    }
    try {
        const before=balances()
        assert.equal((await post('/gacha/exec',{gacha_id:1,payment_type:1,type:1,number_of_exec:1})).statusCode,400)
        assert.equal(queued,false)
        assert.deepEqual(balances(),before)
    } finally { coordinator.runPersistenceTransaction=originalTransaction }
})
test('character and equipment exchange recheck closure, preserve points, and replay committed receipt',async()=>{
    const gachas=require('../out/data/domains/gacha')
    const {getGachaSync}=require('../out/lib/assets')
    for (const type of [0,1]) {
        const row=operations.contentCatalog.rows.find(row=>{
            if(row.type!=='gacha'||row.definitionEvidence?.status!=='matched'
                ||!operations.contentCapabilities(row).includes('exchange'))return false
            const gacha=getGachaSync(row.id)
            return gacha?.type===type&&Object.values(gacha.pool).some(pool=>pool.some(item=>item.isExchangeable))
        })
        assert.ok(row,`ordinary exchange fixture type=${type}`)
        const gacha=getGachaSync(row.id)
        const reward=Object.values(gacha.pool).flat().find(item=>item.isExchangeable)
        const operation=type===0?'gacha_exchange_character':'gacha_exchange_equipment'
        const route=type===0?'/gacha/exchange_character':'/gacha/exchange_equipment'
        const body={gacha_id:row.id,[type===0?'character_id':'equipment_id']:reward.id,api_count:1,request_id:`ops-${type}`}
        const existing=gachas.getPlayerGachaInfoSync(playerId,row.id)
        if(existing)gachas.updatePlayerGachaInfoSync(playerId,{gachaId:row.id,gachaExchangePoint:500})
        else gachas.insertPlayerGachaInfoSync(playerId,{gachaId:row.id,isAccountFirst:false,isDailyFirst:false,gachaExchangePoint:500})
        control(row.key,open)
        let queued=false
        coordinator.runPersistenceTransaction=async(ctx,fn,options)=>{
            if(ctx.operation===operation){queued=true;control(row.key,{flags:{exchange:false}})}
            return originalTransaction(ctx,fn,options)
        }
        try {
            const response=await post(route,body)
            assert.equal(response.statusCode,400,response.body)
            assert.match(response.body,/exchange is closed/)
            assert.equal(queued,true)
            assert.equal(gachas.getPlayerGachaInfoSync(playerId,row.id).gachaExchangePoint,500)
            queued=false
            assert.equal((await post(route,body)).statusCode,400)
            assert.equal(queued,false,'closed before queueing')
        } finally { coordinator.runPersistenceTransaction=originalTransaction }
        control(row.key,open)
        const settled=decode(await post(route,body))
        assert.equal(gachas.getPlayerGachaInfoSync(playerId,row.id).gachaExchangePoint,250)
        control(row.key,{flags:{exchange:false}})
        const replay=decode(await post(route,body))
        assert.deepEqual(replay.data,settled.data,'a completed payment receipt remains replayable after closure')
        assert.equal(gachas.getPlayerGachaInfoSync(playerId,row.id).gachaExchangePoint,250)
    }
})
test('queued tower closure preserves the previously registered legacy battle',async()=>{
    control('tower_dungeon_event:1',{...open,flags:{visible:true,enter:true}})
    const quests=require('../out/data/domains/quest_active')
    quests.insertPlayerActiveQuestSync(playerId,{playerId,category:20,questId:1001,playId:'legacy-tower-play',
        useBoostPoint:false,useBossBoostPoint:false,isAutoStartMode:false,isMulti:false,isMultiHost:false,
        continueCount:0,startedAtMs:require('../out/utils').getServerDate().getTime()-1000,partySlot:1})
    getDb().prepare('UPDATE players_active_quests SET clock_version=0 WHERE player_id=?').run(playerId)
    const before=quests.getPlayerActiveQuestSync(playerId)
    const playerBefore=players.getPlayerSync(playerId)
    let queued=false
    coordinator.runPersistenceTransaction=async(ctx,fn,options)=>{
        if(ctx.domain==='single-quest'&&ctx.operation==='start'){queued=true;control('tower_dungeon_event:1',{flags:{enter:false}})}
        return originalTransaction(ctx,fn,options)
    }
    try {
        const response=decode(await post('/single/start',{category:20,quest_id:1001,party_id:1,play_id:'denied-queued-tower',
            use_boost_point:false,use_boss_boost_point:false,is_auto_start_mode:false,api_count:1}))
        assert.equal(response.data_headers.result_code,4050)
        assert.equal(queued,true)
        assert.deepEqual(quests.getPlayerActiveQuestSync(playerId),before)
        assert.deepEqual(players.getPlayerSync(playerId),playerBefore)
    } finally { coordinator.runPersistenceTransaction=originalTransaction }
    const finish={category:20,quest_id:1001,play_id:before.playId,
        continue_count:0,elapsed_time_ms:1000,score:12345,add_mana:0,is_accomplished:true,is_restored:true,api_count:2,
        statistics:{clear_phase:1,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],equipments:[null,null,null],ability_soul_ids:[null,null,null]},zones:[]}}
    const settled=decode(await post('/single/finish',finish))
    assert.equal(settled.data_headers.result_code,1)
    assert.equal(quests.getPlayerActiveQuestSync(playerId),null)
    const afterPlayer=players.getPlayerSync(playerId)
    const progress=getDb().prepare('SELECT * FROM players_quest_progress WHERE player_id=? ORDER BY section,quest_id').all(playerId)
    const replay=decode(await post('/single/finish',finish))
    assert.deepEqual(replay,settled,'version-0 registered battle retains durable finish replay after closure')
    assert.deepEqual(players.getPlayerSync(playerId),afterPlayer)
    assert.deepEqual(getDb().prepare('SELECT * FROM players_quest_progress WHERE player_id=? ORDER BY section,quest_id').all(playerId),progress)
})
test('manual permanent tower starts after master expiry, closing only blocks new starts',async()=>{
    control('tower_dungeon_event:1',{...open,flags:{visible:true,enter:true}})
    const expired=Date.parse('2040-01-01T00:00:00Z')
    assert.equal(operations.isContentQuestOpenAt(20,1001,expired),true)
    const body={category:20,quest_id:1001,party_id:1,play_id:'content-operator-tower',use_boost_point:false,use_boss_boost_point:false,is_auto_start_mode:false,api_count:1}
    const started=decode(await post('/single/start',body))
    assert.equal(started.data_headers.result_code,1)
    const active=require('../out/data/domains/quest_active').getPlayerActiveQuestSync(playerId)
    control('tower_dungeon_event:1',{flags:{visible:false,enter:false}})
    assert.equal(operations.isContentQuestOpenAt(20,1001,expired),false)
    const denied=decode(await post('/single/start',{...body,play_id:'closed-tower',api_count:2}))
    assert.notEqual(denied.data_headers.result_code,1)
    assert.deepEqual(require('../out/data/domains/quest_active').getPlayerActiveQuestSync(playerId),active)
    const finish={...body,continue_count:0,elapsed_time_ms:1000,score:12345,add_mana:0,is_accomplished:true,is_restored:false,api_count:3,
        statistics:{clear_phase:1,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],equipments:[null,null,null],ability_soul_ids:[null,null,null]},zones:[]}}
    const settled=decode(await post('/single/finish',finish))
    assert.equal(settled.data_headers.result_code,1)
    const progress=()=>getDb().prepare('SELECT * FROM players_quest_progress WHERE player_id=? ORDER BY section,quest_id').all(playerId)
    const after=progress();assert.ok(after.some(row=>row.quest_id===1001))
    decode(await post('/single/finish',finish))
    assert.deepEqual(progress(),after,'closed old battle settles once without resetting progress')
    control('tower_dungeon_event:1',{...open,flags:{visible:true,enter:true}})
    const reopened=decode(await post('/single/start',{...body,play_id:'reopened-tower',api_count:4}))
    assert.equal(reopened.data_headers.result_code,1)
    assert.deepEqual(progress(),after,'reopening keeps completed progress')
})

test('operator deadlines use real time while the legacy content clock remains offset',()=>{
    const now=Date.now(),deadline=now+60000
    control('tower_dungeon_event:1',{...open,flags:{visible:true,enter:true},endsAtMs:deadline})
    const oldBusinessTime=Date.parse('2025-07-18T00:00:00Z')
    require('../out/utils').withServerClock(oldBusinessTime,()=>{
        assert.equal(operations.isContentQuestOpenAt(20,1001,deadline-1),true)
        assert.equal(operations.isContentQuestOpenAt(20,1001,deadline+1),false)
        assert.equal(operations.isContentQuestOpenAt(20,1001),true,'real time does not use captured legacy clock')
    },oldBusinessTime-now)
})
test('global controls survive player save export/import and do not alter V2 fingerprint',()=>{
    const snapshots=require('../out/data/snapshots/player-snapshot')
    const exports=Object.keys(snapshots)
    assert.ok(exports.includes('createPlayerSaveSnapshotV2Sync'))
    const first=snapshots.createPlayerSaveSnapshotV2Sync(playerId,getDb())
    assert.ok(first.data.tables.players_quest_progress.rows.length>0)
    const progress=getDb().prepare('SELECT * FROM players_quest_progress WHERE player_id=? ORDER BY section,quest_id').all(playerId)
    const oldPlay=require('../out/data/domains/quest_active').getPlayerActiveQuestSync(playerId)
    assert.ok(oldPlay,'nonempty excluded battle fixture')
    assert.ok(!Object.keys(first.data.tables).some(k=>k.startsWith('content_operations')))
    const saved=operations.contentOperations().snapshot(Date.now())
    const restored=snapshots.restorePlayerSaveSnapshotV2Sync(first,playerId,{},getDb())
    assert.equal(snapshots.createPlayerSaveSnapshotV2Sync(playerId,getDb()).schemaFingerprint,first.schemaFingerprint)
    assert.deepEqual(getDb().prepare('SELECT * FROM players_quest_progress WHERE player_id=? ORDER BY section,quest_id').all(playerId),progress)
    const activePolicy=first.summary.excludedState.find(entry=>entry.tables.includes('players_active_quests'))
    assert.equal(activePolicy.policy,'reset','baseline archive contract deliberately clears incomplete battle registrations')
    assert.ok(restored.resetTables.includes('players_active_quests'))
    assert.equal(require('../out/data/domains/quest_active').getPlayerActiveQuestSync(playerId),null)
    const after=operations.contentOperations().snapshot(saved.server_time_ms)
    assert.deepEqual(after,saved)
})
