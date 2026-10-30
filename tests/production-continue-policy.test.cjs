'use strict'
if(process.env.STARPOINT_TEST_COMPILED!=='1')require('ts-node/register/transpile-only')
const {test,before,after}=require('node:test'),assert=require('node:assert/strict')
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto')
const parent=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||os.tmpdir());fs.mkdirSync(parent,{recursive:true})
const directory=fs.mkdtempSync(path.join(parent,'production-continue-'))
Object.assign(process.env,{DATA_DIR:directory,CN_WRITER_THREAD:'0',GAME_VERBOSE_LOGS:'false',GAME_ROUTINE_LOGS:'off'})
const load=p=>require('../'+(process.env.STARPOINT_TEST_COMPILED==='1'?'out':'src')+'/'+p)
const policy=load('lib/quest-continue-policy'),active=load('data/domains/quest_active'),players=load('data/domains/player')
let app,db
before(async()=>{load('data').initializeDatabase();db=load('data/db').getDb();assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(directory))
 app=require('fastify')({logger:false});app.addHook('onSend',(_req,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')&&typeof body==='object'?JSON.stringify(body):body))
 await app.register(load('routes/api/singleBattleQuest').default,{prefix:'/single'});await app.ready()
})
after(async()=>{await app?.close();await load('lib/seed-validator').default.close();if(db?.open)db.close();fs.rmSync(directory,{recursive:true})})
function fixture(category,questId){const account=load('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'continue-policy',idpId:crypto.randomUUID(),status:'normal'})
 const player=players.insertDefaultPlayerSync(account.id),viewer=875000000+player.id,play=crypto.randomUUID()
 load('data/activeAccount').saveAccountDefaultPlayer(account.id,player.id)
 db.prepare('INSERT INTO sessions(token,account_id,expires,type)VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00Z')
 players.updatePlayerSync({id:player.id,freeVmoney:100,vmoney:100})
 active.insertPlayerActiveQuestSync(player.id,{playerId:player.id,questId,category,playId:play,isMulti:false,isMultiHost:false,useBossBoostPoint:false,useBoostPoint:false,isAutoStartMode:false,continueCount:0,startedAtMs:Date.now(),clockVersion:1})
 return{id:player.id,viewer,play,category,questId}
}
const post=p=>app.inject({method:'POST',url:'/single/play_continue',payload:{viewer_id:p.viewer,category:p.category,quest_id:p.questId,play_id:p.play,api_count:1,statistics:{zones:[{continue_count:0}]}}})
test('only decoded highest five-boss seven rows and hell pumpkin are forbidden',()=>{
 for(const id of [1099051,1099052,1099053,1099054,1099055,1099056,1099057])assert.equal(policy.isQuestContinueForbidden(2,id),true)
 for(const id of [1099001,1099002,1099023,1099031,1099039])assert.equal(policy.isQuestContinueForbidden(2,id),false)
 for(const category of [7,8]){assert.equal(policy.isQuestContinueForbidden(category,300097005),true);for(const id of [300097001,300097002,300097003,300097004])assert.equal(policy.isQuestContinueForbidden(category,id),false)}
 assert.equal(policy.isQuestContinueForbidden(1,300097005),false)
})
test('real HTTP highest-tier rejection does not charge or increment an active run',async()=>{
 for(const [category,id]of [[2,1099051],[2,1099057],[7,300097005]]){const p=fixture(category,id),before=players.getPlayerSync(p.id),run=active.getPlayerActiveQuestSync(p.id)
  const response=await post(p);assert.equal(response.statusCode,400,response.body);assert.match(response.body,/difficulty/)
  assert.deepEqual(players.getPlayerSync(p.id),before);assert.deepEqual(active.getPlayerActiveQuestSync(p.id),run)
 }
})
test('lower-tier native rules and existing fifty-vmoney debit/retry remain unchanged',async()=>{
 const p=fixture(7,300097004),first=await post(p);assert.equal(first.statusCode,200,first.body)
 assert.equal(players.getPlayerSync(p.id).freeVmoney,50);assert.equal(active.getPlayerActiveQuestSync(p.id).continueCount,1)
 const retried=await post(p);assert.equal(retried.statusCode,200,retried.body)
 assert.equal(players.getPlayerSync(p.id).freeVmoney,50);assert.equal(active.getPlayerActiveQuestSync(p.id).continueCount,1)
})
