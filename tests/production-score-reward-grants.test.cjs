'use strict'
if(process.env.STARPOINT_TEST_COMPILED!=='1') require('ts-node/register/transpile-only')
const {test,before,after}=require('node:test'),assert=require('node:assert/strict')
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto')
const parent=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||os.tmpdir())
fs.mkdirSync(parent,{recursive:true});const directory=fs.mkdtempSync(path.join(parent,'production-score-'))
Object.assign(process.env,{DATA_DIR:directory,CN_WRITER_THREAD:'0',GAME_VERBOSE_LOGS:'false',GAME_ROUTINE_LOGS:'off'})
const compiled=process.env.STARPOINT_TEST_COMPILED==='1',load=p=>require('../'+(compiled?'out':'src')+'/'+p)
const score=require('../assets/score_reward_cnmod.json'),originalRandom=crypto.randomInt
let db,boxes=9,exactRoll=0
before(()=>{load('data').initializeDatabase();db=load('data/db').getDb();assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(directory))
  crypto.randomInt=(min,max)=>max===undefined?0:max===12?boxes:max===10000?exactRoll:max===100?99:min
})
after(async()=>{crypto.randomInt=originalRandom;await load('lib/seed-validator').default.close();if(db?.open)db.close();fs.rmSync(directory,{recursive:true})})
function player(){const account=load('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'production-score',idpId:crypto.randomUUID(),status:'normal'});return load('data/domains/player').insertDefaultPlayerSync(account.id).id}
function grant(pid,group,quest,mode,accomplished=true,boost=false){return db.transaction(()=>load('lib/quest').givePlayerScoreRewardsSync(pid,group,score[group],boost,3,{questId:quest,mode,accomplished}))()}
test('solo and multi both credit every distinct hell chest and initial character, with duplicate compensation once per copy',()=>{
 process.env.DROP_MULTIPLIER='1'
 for(const mode of ['solo','multi'])for(const count of [9,10,11]){
  boxes=count;exactRoll=0;const pid=player(),first=grant(pid,30009705,300097005,mode)
  const candyRows=first.drop_score_reward_ids.filter(row=>row.index<=11)
  assert.equal(candyRows.length,count);assert.deepEqual(candyRows.map(row=>row.index),Array.from({length:count},(_,i)=>i+1))
  assert.ok(candyRows.every(row=>row.number===20));assert.equal(load('data/domains/item').getPlayerItemSync(pid,10009701),count*20)
  assert.deepEqual(first.joined_character_id_list,[149985]);assert.equal(load('data/domains/character').getPlayerCharacterSync(pid,149985).stack,0)
  const second=grant(pid,30009705,300097005,mode);assert.deepEqual(second.joined_character_id_list,[])
  assert.equal(load('data/domains/character').getPlayerCharacterSync(pid,149985).stack,1)
 }
})
test('existing drop multipliers and consumed boost apply to the base box count without altering character odds',()=>{
 process.env.DROP_MULTIPLIER='3';boxes=9;exactRoll=400;const pid=player(),result=grant(pid,30009705,300097005,'multi',true,true)
 assert.equal(load('data/domains/item').getPlayerItemSync(pid,10009701),9*20*3*2)
 assert.ok(result.drop_score_reward_ids.filter(row=>row.index<=11).every(row=>row.number===120))
 assert.equal(load('data/domains/character').getPlayerCharacterSync(pid,149985),null)
 const superPid=player();grant(superPid,30009704,300097004,'solo',true,true)
 assert.equal(load('data/domains/item').getPlayerItemSync(superPid,10009701),20*3*2)
 process.env.DROP_MULTIPLIER='1'
})
test('failed solo and multi clears cannot grant new boxes or new characters; EX legacy rows remain intact',()=>{
 boxes=11;exactRoll=0
 for(const mode of ['solo','multi']){
  const pid=player(),hell=grant(pid,30009705,300097005,mode,false)
  assert.equal(load('data/domains/item').getPlayerItemSync(pid,10009701),null)
  assert.equal(load('data/domains/character').getPlayerCharacterSync(pid,149985),null)
  assert.equal(hell.drop_rare_reward_ids.some(row=>row.group_id===30009713),false)
  const ex=grant(pid,50105,6004002,mode,false)
  assert.equal(load('data/domains/character').getPlayerCharacterSync(pid,159991),null)
  assert.equal(ex.drop_score_reward_ids.length,require('../assets/score_reward.json')['50105'].filter(row=>row.type===0).length)
 }
})
test('midautumn exact boundary and first-acquisition response apply to the EX target only',()=>{
 const pid=player();exactRoll=1000;grant(pid,50105,6004002,'solo');assert.equal(load('data/domains/character').getPlayerCharacterSync(pid,159991),null)
 exactRoll=999;const result=grant(pid,50105,6004002,'solo');assert.deepEqual(result.joined_character_id_list,[159991])
 assert.ok(result.drop_rare_reward_ids.some(row=>row.group_id===600400210&&row.number===1))
})
test('a later reward error rolls back all newly credited candy and character data',()=>{
 const pid=player();boxes=11;exactRoll=0
 assert.throws(()=>db.transaction(()=>{load('lib/quest').givePlayerScoreRewardsSync(pid,30009705,score['30009705'],false,3,{questId:300097005,mode:'solo',accomplished:true});throw Error('late failure')})(),/late failure/)
 assert.equal(load('data/domains/item').getPlayerItemSync(pid,10009701),null)
 assert.equal(load('data/domains/character').getPlayerCharacterSync(pid,149985),null)
})
