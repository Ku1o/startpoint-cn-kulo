'use strict'
const {test,before,after}=require('node:test'),assert=require('node:assert/strict')
const fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'content-multi-http-'))
process.env.DATA_DIR=directory;process.env.GACHA_SEED_DIR=path.join(directory,'seeds')
process.env.MULTI_REALTIME_PROCESS='0';process.env.MULTI_REALTIME_OWNER_CHILD='0';process.env.CN_WRITER_THREAD='0'
process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false'
const out=process.env.STARPOINT_TEST_OUT_DIR
if(!out)throw Error('Use the current isolated build via STARPOINT_TEST_OUT_DIR')
const load=name=>require(path.join(out,name)),interval=global.setInterval
global.setInterval=(...args)=>{const timer=interval(...args);timer.unref();return timer}
const db=load('data/db').getDb(),rooms=load('multi/room/manager'),sessions=load('multi/state/SessionManager').sessionManager
const admissions=load('multi/room/admission').roomAdmissionRegistry,operations=load('lib/content-operations')
const coordinator=load('lib/persistence-coordinator'),transaction=coordinator.runPersistenceTransaction
const contracts=load('multi/state/battle-contract'),pins=load('multi/coordinator/room-start-claims')
global.setInterval=interval
const gateway=()=>load('multi/coordinator/default-runtime').getRoomCommandGateway()
let sequence=0,app,parent,questKey,category,questId
function player(){
    const n=++sequence,account=load('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'multi-ops',idpId:`fixture-${n}`,status:'normal'})
    const p=load('data/domains/player').insertDefaultPlayerSync(account.id),viewerId=881000000+n
    load('data/activeAccount').saveAccountDefaultPlayer(account.id,p.id)
    load('data/domains/session').insertSessionWithTokenSync({token:String(viewerId),accountId:account.id,type:2,expires:new Date(Date.now()+86400000)})
    load('lib/character').givePlayerCharacterSync(p.id,111001)
    return {...p,viewerId}
}
function control(flags){
    const store=operations.contentOperations()
    store.update(parent.key,{expectedRevision:store.revision(),catalogDigest:store.digest,readiness:'verified',
        evidence:'synthetic mapped multiplayer fixture, no device acceptance',reason:'isolated fixture',endsAtMs:null,
        questKeys:[questKey],...(parent.missionKeys?.length?{missionKeys:[parent.missionKeys[0]]}:{}),flags},Date.now())
}
const open=()=>control({visible:true,enter:true}),close=()=>control({enter:false})
const post=(url,p,body={})=>app.inject({method:'POST',url,payload:{viewer_id:p.viewerId,...body}})
const create=p=>post('/create_room',p,{category,quest_id:questId,party_id:1})
const select=(p,r)=>post('/select_room',p,{room_number:r.room_number,category,quest_id:questId,accepted_type:1})
const makeRoom=host=>rooms.createRoom(host.viewerId,host.id,1,category,questId,0,111001)
async function prepareGuest(guest,r,rescueSelection=false){
    const projection=await gateway().execute('lobby.query',{viewerId:guest.viewerId,roomNumber:r.room_number})
    return gateway().execute('lobby.select.prepare',{roomNumber:r.room_number,viewerId:guest.viewerId,identity:projection.identity,
        category,questId,rescueSelection,guestAllowed:true,mode15Closed:false,mode15Helper:false,hostNewbie:false})
}
const start=(p,r,id)=>post('/start',p,{category,quest_id:questId,party_id:1,use_boost_point:false,use_boss_boost_point:false,
    is_auto_start_mode:false,room_number:r.room_number,mate_player_ids:[],mate_party_ids:[],client_battle_party:{},play_id:id})
const cleanup=r=>{if(r)sessions.commitRoomDisband(r.room_number,'ops_test_cleanup')}
function durable(p){return {player:load('data/domains/player').getPlayerSync(p.id),active:load('data/domains/quest_active').getPlayerActiveQuestSync(p.id)}}
before(async()=>{
    assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory)+path.sep))
    for(const [key,parentKey]of Object.entries(operations.contentCatalog.questMap)){
        const [c,id]=key.split(':').map(Number)
        if(![7,8].includes(c))continue
        const row=operations.contentCatalog.rows.find(row=>row.key===parentKey),quest=load('lib/assets').getQuestFromCategorySync(c,id)
        if(row?.definitionEvidence?.status==='matched'&&operations.contentCapabilities(row).includes('enter')&&quest&&'rankPointReward'in quest){
            parent=row;questKey=key;category=c;questId=id;break
        }
    }
    assert.ok(parent,'actual mapped multiplayer quest with supported parent')
    app=require('fastify')({logger:false})
    app.addHook('onSend',(_req,reply,payload,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')&&typeof payload==='object'?JSON.stringify(payload):payload))
    load('multi/http/lobby').registerLobbyRoutes(app);load('multi/http/battle').registerBattleRoutes(app)
    await app.ready()
})
after(async()=>{
    coordinator.runPersistenceTransaction=transaction
    if(app)await app.close()
    gateway().close();await load('lib/seed-validator').default.close();if(db.open)db.close()
    assert.ok(path.resolve(directory).startsWith(path.resolve(os.tmpdir())+path.sep));fs.rmSync(directory,{recursive:true})
})

test('closed mapped content blocks new lobby create/guest select while the original host remains recoverable',async()=>{
    const host=player(),guest=player(),r=makeRoom(host)
    try{
        close()
        assert.equal((await create(host)).json().data_headers.result_code,4507)
        const denied=await select(guest,r);assert.equal(denied.statusCode,200,denied.body)
        assert.equal(denied.json().data.port,0);assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),false)
        const returning=await select(host,r);assert.equal(returning.statusCode,200,returning.body)
        assert.ok(returning.json().data.port>0);assert.equal(rooms.getRoom(r.room_number),r)
    }finally{cleanup(r)}
})
test('create closure after owner prepare cancels its attempt without creating or cleaning hosted rooms',async t=>{
    const host=player(),old=makeRoom(host),transport=gateway(),execute=transport.execute.bind(transport)
    let created
    open()
    t.mock.method(transport,'execute',async(kind,payload,options)=>{
        const result=await execute(kind,payload,options)
        if(kind==='lobby.create.prepare'){created=result;close()}
        return result
    })
    try{
        const response=await create(host);assert.equal(response.statusCode,200,response.body)
        assert.equal(response.json().data_headers.result_code,4507)
        assert.equal(created?.status,'prepared');assert.ok(created.attemptId)
        assert.deepEqual(rooms.getRoomsHostedBy(host.viewerId),[old])
        assert.equal(rooms.getRoom(old.room_number),old,'failed takeover does not clean the original idle room')
    }finally{t.mock.restoreAll();for(const r of rooms.getRoomsHostedBy(host.viewerId))cleanup(r)}
})
test('guest closure after owner acknowledgement releases its pending admission without changing the host',async t=>{
    const host=player(),guest=player(),r=makeRoom(host),transport=gateway(),execute=transport.execute.bind(transport)
    let accepted=false
    open()
    t.mock.method(transport,'execute',async(kind,payload,options)=>{
        const result=await execute(kind,payload,options)
        if(kind==='lobby.select.prepare'){accepted=result.status==='prepared';close()}
        return result
    })
    try{
        const response=await select(guest,r);assert.equal(response.statusCode,200,response.body)
        assert.equal(accepted,true);assert.equal(response.json().data.port,0)
        assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),false)
        assert.equal(rooms.getRoom(r.room_number),r);assert.ok(r.member_viewer_ids.includes(host.viewerId))
    }finally{t.mock.restoreAll();cleanup(r)}
})
test('an older cancelled selection cannot release the same guest newer successful reservation',async t=>{
    const host=player(),guest=player(),r=makeRoom(host),transport=gateway(),execute=transport.execute.bind(transport)
    let injected=false,newer
    open()
    t.mock.method(transport,'execute',async(kind,payload,options)=>{
        const result=await execute(kind,payload,options)
        if(kind==='lobby.select.prepare'&&!injected){
            injected=true;newer=await select(guest,r);close()
        }
        return result
    })
    try{
        const old=await select(guest,r);assert.equal(old.statusCode,200,old.body)
        assert.equal(old.json().data.port,0);assert.equal(newer.statusCode,200,newer.body)
        assert.ok(newer.json().data.port>0);assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),true)
    }finally{t.mock.restoreAll();cleanup(r)}
})
test('a pending unconfirmed prepare cannot be claimed by TCP before permission recheck',async t=>{
    const host=player(),guest=player(),r=makeRoom(host),transport=gateway(),execute=transport.execute.bind(transport)
    let claimResult
    open()
    t.mock.method(transport,'execute',async(kind,payload,options)=>{
        const result=await execute(kind,payload,options)
        if(kind==='lobby.select.prepare'){
            claimResult=admissions.claim(r.room_number,r.lobby_generation,guest.viewerId,'fixture-live-tcp');close()
        }
        return result
    })
    try{
        const response=await select(guest,r);assert.equal(response.statusCode,200,response.body)
        assert.deepEqual(claimResult,{ok:false,reason:'pending'});assert.equal(response.json().data.port,0)
        assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),false)
    }finally{t.mock.restoreAll();cleanup(r)}
})
test('a newer cancelled selection preserves a guest previously confirmed reservation and claimed TCP connection',async t=>{
    const host=player(),guest=player(),r=makeRoom(host),transport=gateway(),execute=transport.execute.bind(transport)
    open()
    try{
        const accepted=await select(guest,r);assert.equal(accepted.statusCode,200,accepted.body);assert.ok(accepted.json().data.port>0)
        let prepared
        t.mock.method(transport,'execute',async(kind,payload,options)=>{
            const result=await execute(kind,payload,options)
            if(kind==='lobby.select.prepare'){prepared=result;close()}
            return result
        })
        const retry=await select(guest,r);assert.equal(retry.statusCode,200,retry.body)
        assert.equal(prepared.status,'ready','an already confirmed reservation is not converted to a new pending attempt')
        assert.ok(retry.json().data.port>0);assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),true)
        t.mock.restoreAll()
        assert.equal(admissions.claim(r.room_number,r.lobby_generation,guest.viewerId,'fixture-confirmed-tcp').ok,true)
        const closed=await select(guest,r);assert.equal(closed.statusCode,200,closed.body)
        assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),true)
        assert.deepEqual(admissions.claim(r.room_number,r.lobby_generation,guest.viewerId,'fixture-confirmed-tcp'),{ok:true,kind:'idempotent'})
    }finally{t.mock.restoreAll();cleanup(r)}
})
test('cancelled rescue selection does not mark rescue eligibility or consume a delivered notice',async t=>{
    const host=player(),guest=player(),r=makeRoom(host),transport=gateway(),execute=transport.execute.bind(transport)
    const recruitment=load('multi/recruitment')
    open();recruitment.publishRandomRecruitment(r.room_number)
    assert.equal(recruitment.takeRandomRecruitments(guest.viewerId,1,()=>true).length,1)
    t.mock.method(transport,'execute',async(kind,payload,options)=>{
        const result=await execute(kind,payload,options)
        if(kind==='lobby.select.prepare')close()
        return result
    })
    try{
        const response=await post('/select_room',guest,{room_number:r.room_number,category,quest_id:questId,accepted_type:2})
        assert.equal(response.statusCode,200,response.body);assert.equal(response.json().data.port,0)
        assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),false)
        assert.equal(sessions.isRescueGuest(r.room_number,guest.viewerId),false)
        assert.equal(recruitment.wasRandomRecruitmentAcceptedBy(r.room_number,guest.viewerId),false)
        assert.equal(recruitment.wasRandomRecruitmentDeliveredTo(r.room_number,guest.viewerId),true)
    }finally{t.mock.restoreAll();cleanup(r)}
})
test('owner prepare leases expire without admitting a guest or consuming rescue side effects',async t=>{
    const host=player(),guest=player(),r=makeRoom(host),recruitment=load('multi/recruitment')
    let now=Date.now();t.mock.method(Date,'now',()=>now)
    recruitment.publishRandomRecruitment(r.room_number);recruitment.takeRandomRecruitments(guest.viewerId,1,()=>true)
    try{
        const prepared=await prepareGuest(guest,r,true);assert.equal(prepared.status,'prepared')
        assert.equal(admissions.hasReservedAttempt(r.room_number,r.lobby_generation,guest.viewerId,prepared.attemptId),true)
        now+=6000
        const expired=await gateway().execute('lobby.select.commit',{attemptId:prepared.attemptId,viewerId:guest.viewerId})
        assert.equal(expired.status,'expired');assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),false)
        assert.equal(sessions.isRescueGuest(r.room_number,guest.viewerId),false)
        assert.equal(recruitment.wasRandomRecruitmentAcceptedBy(r.room_number,guest.viewerId),false)
    }finally{t.mock.restoreAll();cleanup(r)}
})
test('owner attempt commands reject foreign viewers and tokens without consuming the rightful reservation',async()=>{
    const host=player(),guest=player(),other=player(),r=makeRoom(host)
    try{
        const prepared=await prepareGuest(guest,r);assert.equal(prepared.status,'prepared')
        assert.equal(await gateway().execute('lobby.select.cancel',{attemptId:prepared.attemptId,viewerId:other.viewerId}),false)
        assert.equal((await gateway().execute('lobby.select.commit',{attemptId:prepared.attemptId,viewerId:other.viewerId})).status,'expired')
        assert.equal(await gateway().execute('lobby.select.cancel',{attemptId:'foreign-token',viewerId:guest.viewerId}),false)
        assert.equal(admissions.hasReservedAttempt(r.room_number,r.lobby_generation,guest.viewerId,prepared.attemptId),true)
        const committed=await gateway().execute('lobby.select.commit',{attemptId:prepared.attemptId,viewerId:guest.viewerId})
        assert.equal(committed.status,'ready');assert.equal(admissions.has(r.room_number,r.lobby_generation,guest.viewerId),true)
    }finally{cleanup(r)}
})
test('a stale room identity cannot commit prepared rescue side effects',async()=>{
    const host=player(),guest=player(),r=makeRoom(host),recruitment=load('multi/recruitment')
    recruitment.publishRandomRecruitment(r.room_number);recruitment.takeRandomRecruitments(guest.viewerId,1,()=>true)
    try{
        const prepared=await prepareGuest(guest,r,true);assert.equal(prepared.status,'prepared')
        r.lifecycle.version++
        const stale=await gateway().execute('lobby.select.commit',{attemptId:prepared.attemptId,viewerId:guest.viewerId})
        assert.equal(stale.status,'stale');assert.equal(sessions.isRescueGuest(r.room_number,guest.viewerId),false)
        assert.equal(recruitment.wasRandomRecruitmentAcceptedBy(r.room_number,guest.viewerId),false)
    }finally{cleanup(r)}
})
test('new multi starts close before prepare and at final transaction without durable writes or orphan room claims',async t=>{
    const host=player(),r=makeRoom(host),transport=gateway(),execute=transport.execute.bind(transport)
    const before=durable(host);let prepared=0,cancelled=0
    t.mock.method(transport,'execute',async(kind,payload,options)=>{
        if(kind==='battle.start.prepare')prepared++
        if(kind==='battle.play.cancel')cancelled++
        return execute(kind,payload,options)
    })
    try{
        close()
        assert.equal((await start(host,r,'closed-before-prepare')).json().data_headers.result_code,4050)
        assert.equal(prepared,0);assert.deepEqual(durable(host),before)
        open()
        coordinator.runPersistenceTransaction=async(context,fn,options)=>{
            if(context.domain==='multi-settlement'&&context.operation==='start')close()
            return transaction(context,fn,options)
        }
        const response=await start(host,r,'closed-in-queue');assert.equal(response.statusCode,200,response.body)
        assert.equal(response.json().data_headers.result_code,4050);assert.equal(prepared,1);assert.equal(cancelled,1)
        assert.deepEqual(durable(host),before);assert.equal(pins.hasRoomStartClaims(r),false)
        assert.equal(contracts.findBattlePlayBinding(r,host.viewerId,host.id,'closed-in-queue'),undefined)
    }finally{coordinator.runPersistenceTransaction=transaction;t.mock.restoreAll();cleanup(r)}
})
test('a durable registered multi play replays after closure and preserves its saved identity',async()=>{
    const host=player(),r=makeRoom(host),playId='registered-before-close'
    try{
        open()
        const first=await start(host,r,playId);assert.equal(first.statusCode,200,first.body)
        assert.equal(first.json().data.play_id,playId)
        const saved=durable(host);close()
        const replay=await start(host,r,playId);assert.equal(replay.statusCode,200,replay.body)
        assert.equal(replay.json().data.play_id,playId)
        const actual=durable(host)
        // The baseline multi-start route re-inserts an already registered
        // active quest, refreshing startedAtMs. Preserve the existing contract
        // while checking balances and every durable play identity field.
        assert.ok(actual.active.startedAtMs>=saved.active.startedAtMs)
        assert.deepEqual({...actual,active:{...actual.active,startedAtMs:saved.active.startedAtMs}},saved)
        assert.equal(pins.hasRoomStartClaims(r),false)
    }finally{cleanup(r)}
})
