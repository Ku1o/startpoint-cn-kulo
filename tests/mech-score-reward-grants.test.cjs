'use strict'
if(process.env.STARPOINT_TEST_COMPILED!=='1')require('ts-node/register/transpile-only')
const {test,before,after}=require('node:test'),assert=require('node:assert/strict')
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto')
const parent=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||os.tmpdir())
fs.mkdirSync(parent,{recursive:true});const directory=fs.mkdtempSync(path.join(parent,'mech-score-'))
Object.assign(process.env,{DATA_DIR:directory,CN_WRITER_THREAD:'0',GAME_VERBOSE_LOGS:'false',GAME_ROUTINE_LOGS:'off'})
const compiled=process.env.STARPOINT_TEST_COMPILED==='1',load=p=>require('../'+(compiled?'out':'src')+'/'+p)
const originalRandom=crypto.randomInt
// Explicit historical identities; the expected materials must not be derived from the repair.
const mechs=[
  [1001001,11000930,7000010,700010,40402,40408],
  [1002001,11000931,7000011,700011,40403,40409],
  [1003001,11000932,7000012,700012,40404,40410],
  [1004001,11000933,7000013,700013,40401,40407],
  [1005001,11000934,7000014,700014,40406,40412],
  [1006001,11000935,7000015,700015,40405,40411],
]
let db,roll=0
before(()=>{
  load('data').initializeDatabase();db=load('data/db').getDb()
  assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(directory))
  crypto.randomInt=(min,max)=>max===100?roll:max===undefined?0:min
})
after(async()=>{
  crypto.randomInt=originalRandom
  await load('lib/seed-validator').default.close()
  if(db?.open)db.close()
  fs.rmSync(directory,{recursive:true})
})
function player(){
  const account=load('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'mech-score',idpId:crypto.randomUUID(),status:'normal'})
  return load('data/domains/player').insertDefaultPlayerSync(account.id).id
}
function grant(pid,questId,mode,boost=false,questOverride){
  const quest=questOverride??load('lib/assets').getHardMultiEventQuest(questId)
  return db.transaction(()=>load('lib/quest').givePlayerScoreRewardsSync(pid,quest.scoreRewardGroupId,quest.scoreRewardGroup,
    boost,quest.element,{questId,mode,accomplished:true}))()
}

test('all six mech quests restore historical gear and core grants for solo and multi',()=>{
  process.env.DROP_MULTIPLIER='1';roll=0
  for(const mode of ['solo','multi'])for(const [questId,nativeGroup,groupId,rareGroup,gear,core]of mechs){
    const quest=load('lib/assets').getHardMultiEventQuest(questId)
    assert.equal(quest.scoreRewardGroupId,nativeGroup,'exercise the current projected quest')
    const pid=player(),result=grant(pid,questId,mode)
    assert.deepEqual(result.drop_score_reward_ids,[{group_id:groupId,index:1,number:1}],String(questId))
    assert.deepEqual(result.drop_rare_reward_ids,[{group_id:rareGroup,index:1,number:1}],String(questId))
    assert.deepEqual(result.items,{[gear]:1,[core]:1})
    assert.equal(load('data/domains/item').getPlayerItemSync(pid,gear),1)
    assert.equal(load('data/domains/item').getPlayerItemSync(pid,core),1)
    for(const id of [49300,10000092,10000093])assert.equal(load('data/domains/item').getPlayerItemSync(pid,id),null)
  }
})

test('gear keeps the old drop multiplier and consumed boost while cores keep the old probability and single count',()=>{
  process.env.DROP_MULTIPLIER='3'
  for(const mode of ['solo','multi'])for(const [questId,,groupId,rareGroup,gear,core]of mechs){
    roll=10;const pid=player(),hit=grant(pid,questId,mode,true)
    assert.deepEqual(hit.drop_score_reward_ids,[{group_id:groupId,index:1,number:6}])
    assert.deepEqual(hit.drop_rare_reward_ids,[{group_id:rareGroup,index:1,number:1}])
    assert.equal(load('data/domains/item').getPlayerItemSync(pid,gear),6)
    assert.equal(load('data/domains/item').getPlayerItemSync(pid,core),1)
    roll=11;const missPid=player(),miss=grant(missPid,questId,mode)
    assert.deepEqual(miss.drop_rare_reward_ids,[])
    assert.equal(load('data/domains/item').getPlayerItemSync(missPid,gear),3)
    assert.equal(load('data/domains/item').getPlayerItemSync(missPid,core),null)
  }
})

test('other quest/group combinations and already restored legacy rewards retain their original behavior',()=>{
  process.env.DROP_MULTIPLIER='1';roll=99
  const assets=load('lib/assets'),quest=assets.getHardMultiEventQuest(1001001)
  const foreign=grant(player(),1002001,'multi',false,quest)
  assert.ok(foreign.drop_score_reward_ids.length>1)
  assert.ok(foreign.drop_score_reward_ids.every(row=>row.group_id===11000930))
  const ranking=assets.getQuestFromCategorySync(11,1001001)
  const rankingResult=grant(player(),1001001,'solo',false,ranking)
  assert.ok(rankingResult.drop_score_reward_ids.every(row=>row.group_id===ranking.scoreRewardGroupId))
  assert.ok(!rankingResult.items[40402])
  const legacy=grant(player(),1001001,'multi',false,{scoreRewardGroupId:7000010,scoreRewardGroup:assets.getScoreRewardGroup(7000010)})
  assert.deepEqual(legacy.drop_score_reward_ids,[{group_id:7000010,index:1,number:1}])
})

test('a later settlement failure rolls back restored materials',()=>{
  process.env.DROP_MULTIPLIER='1';roll=0
  const pid=player(),quest=load('lib/assets').getHardMultiEventQuest(1001001)
  assert.throws(()=>db.transaction(()=>{
    load('lib/quest').givePlayerScoreRewardsSync(pid,quest.scoreRewardGroupId,quest.scoreRewardGroup,false,quest.element,
      {questId:1001001,mode:'multi',accomplished:true})
    throw Error('late settlement failure')
  })(),/late settlement failure/)
  assert.equal(load('data/domains/item').getPlayerItemSync(pid,40402),null)
  assert.equal(load('data/domains/item').getPlayerItemSync(pid,40408),null)
})
