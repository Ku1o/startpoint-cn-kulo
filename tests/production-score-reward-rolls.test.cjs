'use strict'
if(process.env.STARPOINT_TEST_COMPILED!=='1') require('ts-node/register/transpile-only')
const {test}=require('node:test'),assert=require('node:assert/strict')
const runtime=process.env.STARPOINT_TEST_COMPILED==='1'?'out':'src'
const {rollExactScoreRewardChance,selectScoreRewardRows}=require('../'+runtime+'/lib/score-reward-rolls')
const score=require('../assets/score_reward_cnmod.json'),rare=require('../assets/rare_score_reward_cnmod.json')

test('the complete 10000-roll domain gives exactly 4% and 10%, including both boundaries',()=>{
  for(const [chance,hits] of [[0,0],[400,400],[1000,1000],[10000,10000]]){
    let actual=0;for(let roll=0;roll<10000;roll++)actual+=Number(rollExactScoreRewardChance(chance,roll))
    assert.equal(actual,hits)
  }
  for(const invalid of [-1,10001,0.5,NaN])assert.throws(()=>rollExactScoreRewardChance(invalid,0))
  assert.throws(()=>rollExactScoreRewardChance(400,10000))
})
test('hell serializes 9, 10 or 11 unique 20-candy chest rows and retains all other rewards',()=>{
  const master=score['30009705'],before=JSON.stringify(master)
  const nonCandy=master.filter(row=>row.id!==10009701)
  for(const boxes of [9,10,11]){
    const chosen=selectScoreRewardRows(30009705,master,300097005,()=>boxes,true)
    const candy=chosen.filter(row=>row.id===10009701)
    assert.equal(candy.length,boxes);assert.equal(new Set(candy.map(row=>row.position)).size,boxes)
    assert.equal(candy.reduce((sum,row)=>sum+row.count,0),boxes*20)
    assert.deepEqual(chosen.filter(row=>row.id!==10009701),nonCandy)
  }
  assert.equal(JSON.stringify(master),before)
  for(const invalid of [8,12,9.5])assert.throws(()=>selectScoreRewardRows(30009705,master,300097005,()=>invalid,true))
})
test('unrelated quests keep the exact same master and legacy extraction behavior',()=>{
  const master=score['30009705']
  assert.equal(selectScoreRewardRows(30009705,master,1,undefined,true),master)
  assert.equal(selectScoreRewardRows(1,master,300097005,undefined,true),master)
  assert.equal(selectScoreRewardRows(30009704,score['30009704'],300097004,undefined,true),score['30009704'])
  assert.equal(score['30009704'].filter(row=>row.id===10009701).reduce((n,row)=>n+row.count,0),20)
})
test('failed or unproven clears omit only newly introduced clear-only drops',()=>{
  for(const accomplished of [false,undefined]){
    const hell=selectScoreRewardRows(30009705,score['30009705'],300097005,()=>{throw Error('failed clears must not roll boxes')},accomplished)
    assert.equal(hell.some(row=>row.id===10009701||row.id===30009713),false)
    assert.deepEqual(hell,score['30009705'].filter(row=>!row.requires_clear))
    const ex=selectScoreRewardRows(50105,score['50105'],6004002,undefined,accomplished)
    assert.deepEqual(ex,require('../assets/score_reward.json')['50105'])
  }
})
test('new character pools keep EX materials and close overlimit output without deleting input costs',()=>{
  assert.equal(score['30009705'].find(row=>row.id===30009713).chance_basis_points,400)
  assert.deepEqual(rare['30009713'].map(row=>row.id),[149985])
  assert.deepEqual(score['50105'].slice(0,-1),require('../assets/score_reward.json')['50105'])
  assert.equal(score['50105'].at(-1).chance_basis_points,1000)
  assert.equal(rare['600400210'][0].id,159991)
  assert.equal(rare['12199320'],undefined)
  assert.equal(score['12100088'].some(row=>row.id===12199320),false)
  const enhancement=require('../assets/equipment_enhancement_shop.json')
  assert.ok(Object.values(enhancement).some(row=>row.costs.some(cost=>cost.id===10000302)))
})
