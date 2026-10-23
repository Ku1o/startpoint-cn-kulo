'use strict'
const {test,before,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'content-action-http-'))
process.env.DATA_DIR=directory;process.env.GACHA_SEED_DIR=path.join(directory,'seeds');process.env.CN_WRITER_THREAD='0'
process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false';process.env.MULTI_REALTIME_PROCESS='0'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
require('../out/data').initializeDatabase()
const db=require('../out/data/db').getDb(),players=require('../out/data/domains/player'),missions=require('../out/data/domains/mission')
const operations=require('../out/lib/content-operations'),coordinator=require('../out/lib/persistence-coordinator'),transaction=coordinator.runPersistenceTransaction
const stages=require('../out/lib/mission/stages'),pass=require('../out/data/domains/pass-card'),gachas=require('../out/data/domains/gacha')
const enterKeys=['6:57','6:58','6:59','6:60','7:57','7:58','8:86','8:87','8:88','8:89','8:90','8:91'],claimKeys=[...enterKeys,'7:59','7:60']
const action=(enabled=true,extra={})=>({enabled,endsAtMs:null,readiness:'verified',evidence:'synthetic exact action HTTP fixture',...extra})
const control=(key,body)=>{const s=operations.contentOperations();return s.update(key,{expectedRevision:s.revision(),catalogDigest:s.digest,reason:'synthetic HTTP verification',...body},Date.now())}
let app,playerId,viewerId,cookie
const post=(url,body={})=>app.inject({method:'POST',url,payload:{viewer_id:viewerId,...body}})
const decode=response=>{assert.equal(response.statusCode,200,response.body);return unpack(Buffer.from(response.body,'base64'))}
const missionRecords=()=>Object.fromEntries([6,7,8].map(category=>[category,missions.getPlayerCategoryMissionsSync(playerId,category)]))
before(async()=>{
 assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory)+path.sep))
 const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'action-http',idpId:'fixture',status:'normal'})
 playerId=players.insertDefaultPlayerSync(account.id).id;viewerId=868000000+playerId
 require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,playerId)
 db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewerId),account.id,'2099-01-01T00:00:00Z')
 db.prepare('INSERT INTO players_pass_cards(player_id,event_id,point,is_buy,login_baseline) VALUES(?,15,10000,1,3)').run(playerId)
 for(const member of claimKeys){const [category,id]=member.split(':').map(Number);const target=stages.getMissionFinalTargetProgress(category,id);assert.ok(target>0);missions.updatePlayerCategoryMissionSync(playerId,category,id,target+11)}
 const auth=Fastify({logger:false}),previous=process.env.ADMIN_PANEL_PASSWORD;process.env.ADMIN_PANEL_PASSWORD='synthetic-action-password'
 try {require('../out/lib/management-auth').installManagementAuth(auth);const response=await auth.inject({method:'POST',url:'/admin-login',payload:{password:process.env.ADMIN_PANEL_PASSWORD}});assert.equal(response.statusCode,200,response.body);cookie=response.headers['set-cookie'].split(';')[0]}
 finally {await auth.close();if(previous===undefined)delete process.env.ADMIN_PANEL_PASSWORD;else process.env.ADMIN_PANEL_PASSWORD=previous}
 app=Fastify({logger:false});app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
 await app.register(require('../out/routes/api/mission').default,{prefix:'/mission'})
 await app.register(require('../out/routes/api/passCard').default,{prefix:'/pass'})
 await app.register(require('../out/routes/api/gacha').default,{prefix:'/gacha'})
 await app.register(require('../out/routes/web_api/content').default,{prefix:'/admin-content'})
 await app.ready()
})
after(async()=>{coordinator.runPersistenceTransaction=transaction;if(app)await app.close();await require('../out/lib/seed-validator').default.close();if(db.open)db.close();fs.rmSync(directory,{recursive:true})})
test('authenticated HTTP PATCH is metadata-only until an explicit action, with strict scopes and CAS',async()=>{
 const store=operations.contentOperations(),key='gacha:2',request=body=>app.inject({method:'PATCH',url:'/admin-content/'+encodeURIComponent(key),headers:{cookie},payload:{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'HTTP review',...body}})
 assert.equal((await request({readiness:'verified',evidence:'HTTP read-only verification'})).statusCode,200)
 assert.equal(store.allowed(key,'enter',Date.now()),false,'metadata review never overrides default-denied participation');assert.equal(store.snapshot(Date.now()).states.some(state=>state.key===key),false)
 const revision=store.revision();assert.equal((await request({actionOverrides:{enter:action(false)}})).statusCode,200)
 assert.equal(store.allowed(key,'enter',Date.now()),false);assert.equal(store.allowed(key,'exchange',Date.now()),true,'accrued exchange rights remain independently qualified')
 assert.equal((await request({expectedRevision:revision,actionOverrides:{enter:action()}})).statusCode,409)
 const before=store.revision()
 const bad=await app.inject({method:'PATCH',url:'/admin-content/pass_card_event%3A15',headers:{cookie},payload:{expectedRevision:before,catalogDigest:store.digest,reason:'bad exact scope',actionOverrides:{claim:action(true,{missionKeys:['7:99999']})}}})
 assert.equal(bad.statusCode,400);assert.equal(store.revision(),before)
})
test('fresh draw-only override preserves actual nonempty legacy exchange, payment and durable receipt',async()=>{
 const rule={key:'gacha:80000',rewardKind:'character',eligibleRewardIds:[111004]}
 const gid=+rule.key.split(':')[1];control(rule.key,{actionOverrides:{enter:action()}})
 assert.equal(operations.contentDecision('gacha',gid,'exchange',Date.now()),true,'existing exchange points keep separate qualified rights')
 gachas.insertPlayerGachaInfoSync(playerId,{gachaId:gid,isAccountFirst:false,isDailyFirst:false,gachaExchangePoint:500})
 const body={gacha_id:gid,[rule.rewardKind+'_id']:rule.eligibleRewardIds[0],request_id:'partial-old-exchange',api_count:1},url='/gacha/exchange_'+rule.rewardKind
 decode(await post(url,body));assert.equal(gachas.getPlayerGachaInfoSync(playerId,gid).gachaExchangePoint,250)
 control(rule.key,{actionOverrides:{enter:action(false)}})
 decode(await post(url,body));assert.equal(gachas.getPlayerGachaInfoSync(playerId,gid).gachaExchangePoint,250)
})
test('real mission HTTP exposes 14 claim scopes while only 12 participate; closed facts and historic progress persist',async()=>{
 control('pass_card_event:15',{actionOverrides:{visible:action(true,{missionKeys:claimKeys}),enter:action(true,{missionKeys:enterKeys}),claim:action(true,{missionKeys:claimKeys})}})
 for(const member of enterKeys){const [category,id]=member.split(':').map(Number);assert.equal(operations.contentMissionDecision(category,id,'enter'),true)}
 for(const member of ['7:59','7:60']){const [category,id]=member.split(':').map(Number);assert.equal(operations.contentMissionDecision(category,id,'enter'),false);assert.equal(operations.contentMissionDecision(category,id,'claim'),true)}
 const before=missionRecords(), response=decode(await post('/mission/get_mission_progress',{category_list:[6,7,8].map(category=>({category,event_id:15}))}))
 const rows=response.data.mission_progress_list.filter(row=>claimKeys.includes(`${row.mission_category}:${row.mission_id}`));assert.equal(rows.length,14)
 for(const id of [59,60]){const record=missions.getPlayerCategoryMissionsSync(playerId,7)[id];assert.equal(record.progress,before[7][id].progress);assert.ok(Object.keys(record.stages).length>0,'historic pattern85 earned stages claimed')}
 assert.equal(pass.getPlayerPassCardStateSync(playerId,15).isBuy,true)
 control('pass_card_event:15',{actionOverrides:{enter:action(false,{missionKeys:enterKeys})}})
 const frozen=missionRecords(),snapshots=db.prepare('SELECT * FROM players_periodic_snapshots WHERE player_id=?').all(playerId)
 decode(await post('/mission/get_mission_progress',{category_list:[6,7,8].map(category=>({category,event_id:15}))}))
 assert.deepEqual(missionRecords(),frozen);assert.deepEqual(db.prepare('SELECT * FROM players_periodic_snapshots WHERE player_id=?').all(playerId),snapshots)
})
test('claim action rechecks after queueing, then existing bought-track receipt replays after closure',async()=>{
 const reward=841;assert.equal(require('../out/lib/pass-card').getPassCardRewardDefinition(reward).eventId,15)
 const body={pass_card_id:15,all_receive:[reward]},saved=pass.getPlayerPassCardRewardRecordsSync(playerId,15)
 let queued=false;coordinator.runPersistenceTransaction=async(context,fn,options)=>{if(context.operation==='receive_pass_card'){queued=true;control('pass_card_event:15',{actionOverrides:{claim:action(false,{missionKeys:claimKeys})}})}return transaction(context,fn,options)}
 try {const response=await post('/pass/receive_all',body);assert.equal(response.statusCode,400,response.body);assert.equal(queued,true);assert.deepEqual(pass.getPlayerPassCardRewardRecordsSync(playerId,15),saved)}
 finally {coordinator.runPersistenceTransaction=transaction}
 control('pass_card_event:15',{actionOverrides:{claim:action(true,{missionKeys:claimKeys})}})
 decode(await post('/pass/receive_all',body));const records=pass.getPlayerPassCardRewardRecordsSync(playerId,15);assert.ok(records.some(row=>row.rewardId===reward&&row.isReceived1===1&&row.isReceived2===1))
 const items=db.prepare('SELECT * FROM players_items WHERE player_id=? ORDER BY id').all(playerId),state=pass.getPlayerPassCardStateSync(playerId,15)
 control('pass_card_event:15',{actionOverrides:{claim:action(false,{missionKeys:claimKeys})}})
 decode(await post('/pass/receive_all',body));assert.deepEqual(pass.getPlayerPassCardRewardRecordsSync(playerId,15),records);assert.deepEqual(db.prepare('SELECT * FROM players_items WHERE player_id=? ORDER BY id').all(playerId),items)
 assert.deepEqual(pass.getPlayerPassCardStateSync(playerId,15),state)
})
