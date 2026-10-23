'use strict'
if (!process.env.STARPOINT_TEST_COMPILED_ROOT) require('ts-node/register/transpile-only')
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const compiled=process.env.STARPOINT_TEST_COMPILED_ROOT
const load=name=>require(compiled?path.join(compiled,name):path.resolve(__dirname,'../src',name))
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'daily-legacy-completion-'))
Object.assign(process.env,{DATA_DIR:directory,CN_WRITER_THREAD:'0',GAME_ROUTINE_LOGS:'off',GAME_VERBOSE_LOGS:'false'})
load('data').initializeDatabase()
const db=load('data/db').getDb(),players=load('data/domains/player'),missions=load('data/domains/mission')
assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(directory))
load('utils').setServerTime(new Date('2025-07-20T04:00:00Z'))
const oldIds=[1,3,4,6],targets=[[11,3],[13,1],[14,10],[16,50]]
let app,sequence=0
test.before(async()=>{
 app=require('fastify')()
 app.addHook('onSend',(_req,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?JSON.stringify(body):body))
 await app.register(load('routes/api/mission').default,{prefix:'/mission'});await app.ready()
})
test.after(async()=>{await app.close();if(db.open)db.close();assert.equal(path.dirname(directory),os.tmpdir());fs.rmSync(directory,{recursive:true})})
function fixture(){
 const account=load('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'test',idpId:'daily-legacy-'+(++sequence),status:'normal'})
 const player=players.insertDefaultPlayerSync(account.id),viewer=880000000+player.id
 db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00Z')
 load('lib/mission/snapshot').initializePeriodicMissionSnapshots(player.id,players.getPlayerSync(player.id))
 return {id:player.id,viewer}
}
function completed(p,id,amount){missions.updatePlayerCategoryMissionSync(p.id,2,id,amount);missions.updatePlayerCategoryMissionStageSync(p.id,2,1,id,true)}
function progress(p){return missions.getPlayerCategoryMissionsSync(p.id,2)}
async function read(p){const r=await app.inject({method:'POST',url:'/mission/get_mission_progress',payload:{viewer_id:p.viewer,category_list:[{category:2}]}});assert.equal(r.statusCode,200,r.body);assert.equal(r.json().data_headers.result_code,1);return r.json()}
const received=p=>db.prepare('SELECT * FROM players_receive_history WHERE player_id=? ORDER BY id').all(p.id)

test('completed claim-only historical generations cannot complete today with four current prerequisites at zero',async()=>{
 const p=fixture()
 for(const id of oldIds){assert.equal(load('lib/content-operations').contentMissionDecision(2,id,'enter'),false);completed(p,id,999)}
 const before=progress(p),money=players.getPlayerSync(p.id).freeVmoney,receipts=received(p)
 await read(p)
 const after=progress(p)
 for(const id of oldIds)assert.deepEqual(after[id],before[id],'historical counter and stage preserved')
 for(const[id]of targets)assert.equal(after[id]?.progress??0,0)
 assert.equal(after[17]?.progress??0,0);assert.notEqual(after[17]?.stages?.['1'],true)
 assert.equal(players.getPlayerSync(p.id).freeVmoney,money);assert.deepEqual(received(p),receipts)
})

test('only exact current prerequisite IDs count; any-battle and infinite-training do not replace stamina',async()=>{
 const p=fixture()
 for(const id of oldIds)completed(p,id,999)
 for(const[id,amount]of targets.filter(([id])=>id!==16))completed(p,id,amount)
 completed(p,800392,999);completed(p,10075,999)
 await read(p)
 assert.equal(progress(p)[17].progress,3);assert.notEqual(progress(p)[17].stages?.['1'],true)
 completed(p,16,50)
 const before=players.getPlayerSync(p.id).freeVmoney
 await read(p)
 assert.equal(progress(p)[17].progress,4);assert.equal(progress(p)[17].stages['1'],true)
 assert.equal(players.getPlayerSync(p.id).freeVmoney,before+35)
 const saved=progress(p),receipts=received(p),money=players.getPlayerSync(p.id).freeVmoney
 await read(p);await read(p)
 assert.deepEqual(progress(p),saved);assert.deepEqual(received(p),receipts);assert.equal(players.getPlayerSync(p.id).freeVmoney,money)
})

test('existing excess all-clear progress and received stages remain monotonic',async()=>{
 const p=fixture();completed(p,17,999)
 const saved=progress(p),receipts=received(p),money=players.getPlayerSync(p.id).freeVmoney
 await read(p)
 assert.deepEqual(progress(p),saved);assert.deepEqual(received(p),receipts);assert.equal(players.getPlayerSync(p.id).freeVmoney,money)
})

test('unreceived historical claim-only rewards retain their existing one-time settlement',async()=>{
 const p=fixture();missions.updatePlayerCategoryMissionSync(p.id,2,1,999)
 assert.notEqual(progress(p)[1].stages?.['1'],true)
 await read(p)
 assert.equal(progress(p)[1].progress,999);assert.equal(progress(p)[1].stages['1'],true)
 assert.equal(progress(p)[17]?.progress??0,0)
 const saved=progress(p),receipts=received(p),money=players.getPlayerSync(p.id).freeVmoney
 await read(p)
 assert.deepEqual(progress(p),saved);assert.deepEqual(received(p),receipts);assert.equal(players.getPlayerSync(p.id).freeVmoney,money)
})
