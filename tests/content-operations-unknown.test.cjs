const {test}=require('node:test'),assert=require('node:assert/strict')
const policy=require('../out/lib/content-operations-defaults')
test('unknown seasonal missions are closed while permanent core missions retain their rules',()=>{
 for(const category of [0,3,4,6,7,8])assert.equal(policy.unknownMissionContentDecision(category),false)
 for(const category of [1,2,5,9,10])assert.equal(policy.unknownMissionContentDecision(category),null)
 assert.equal(policy.unknownMissionContentDecision(2,'2027-01-01 00:00:00'),false)
 assert.equal(policy.unknownMissionContentDecision(2,'2200-01-01 00:00:00'),null)
 assert.equal(policy.unknownMissionContentDecision(1,'broken-date'),false)
})
test('unknown shop products cannot inherit a purchase date or parent approval',()=>{
 for(const type of ['event_item_shop','boss_coin_shop','general_shop','star_grain_shop','treasure_shop']) {
  assert.equal(policy.unknownContentDecision(type,'visible'),false)
  assert.equal(policy.unknownContentDecision(type,'exchange'),false)
 }
})
test('unknown event quests fail closed while explicit core quest families and ordinary hard bosses retain their rules',()=>{
 for(const category of [6,7,8,10,11,13,14,18,19,20,21,22,23,24,25,26,27])assert.equal(policy.unknownQuestContentDecision(category,999999999),false)
 for(const category of [1,2,3,4,9,15,16])assert.equal(policy.unknownQuestContentDecision(category,999999999),null)
 for(const id of [2080001,2035001,2056001])assert.equal(policy.unknownQuestContentDecision(26,id),null)
 assert.equal(policy.unknownQuestContentDecision(26,2080002),false)
})
test('current MOD/abyss effective quest rows remain explicitly mapped rather than borrowing the unknown fallback',()=>{
 const catalog=require('../assets/content_catalog.json')
 for(const key of ['24:700098001','24:700099001','24:700100001','7:300098001'])assert.ok(catalog.questMap[key],key)
})
