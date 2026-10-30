'use strict'
if(process.env.STARPOINT_TEST_COMPILED!=='1')require('ts-node/register/transpile-only')
const {test}=require('node:test'),assert=require('node:assert/strict')
const policy=require('../assets/quest_shop_availability_cnmod.json')
const runtime=require('../'+(process.env.STARPOINT_TEST_COMPILED==='1'?'out':'src')+'/lib/content-release-restrictions')
function snapshot(){return{schema_version:2,full_snapshot:true,revision:17,catalog_digest:'fixture',server_time_ms:1,
 states:[{key:'hard_multi_event:2088',instance_id:'hard_multi_event:2088:original',quest_keys:['26:2088001','26:9000001'],
  actions:{visible:{enabled:true,ends_at_ms:null,quest_keys:null},enter:{enabled:true,ends_at_ms:null,quest_keys:['26:2088001','26:9000001']}}},
  {key:policy.closedShopKeys[0],instance_id:policy.closedShopKeys[0]+':original',actions:{visible:{enabled:true,ends_at_ms:null},exchange:{enabled:true,ends_at_ms:null}}}],
 catalog:[{key:'hard_multi_event:2088',type:'hard_multi_event',id:2088,entry:null,quest_keys:['26:2088001','26:9000001']}],
 default_policy:{version:1,explicit_actions_override_defaults:true,actions:Object.fromEntries(['visible','enter','claim','exchange'].map(action=>[action,{closed_keys:[],qualified_rights_keys:[policy.closedShopKeys[0]],legacy_keys:policy.closedShopKeys.slice(1)}]))}}}
test('frozen exact sets contain72 typed quests and54 initial products without category collisions',()=>{
 assert.equal(new Set(policy.managedQuestKeys).size,72);assert.equal(new Set(policy.closedShopKeys).size,54)
 assert.equal(policy.managedQuestKeys.filter(key=>key.startsWith('2:')).length,45)
 assert.equal(policy.managedQuestKeys.filter(key=>key.startsWith('26:')).length,27)
 for(const key of policy.managedQuestKeys){const[c,id]=key.split(':').map(Number);assert.equal(runtime.isReleaseClosedQuest(c,id),true);assert.equal(runtime.isReleaseClosedQuest(4,id),false)}
 for(const key of policy.closedShopKeys){const[type,id]=key.split(':');assert.equal(runtime.isReleaseClosedShop(type,Number(id)),true);assert.equal(runtime.isReleaseClosedShop('general_shop',Number(id)),false)}
})
test('full native snapshot explicitly closes all72, removes ambiguous owners and retains unrelated members without database writes',()=>{
 const original=snapshot(),before=structuredClone(original),result=runtime.projectReleaseClosedSnapshot(original)
 assert.deepEqual(original,before)
 const restriction=result.states.find(row=>row.key==='closed_boss_quests:1'),catalog=result.catalog.find(row=>row.key===restriction.key)
 assert.equal(restriction.instance_id,restriction.key+':original');assert.equal(catalog.entry,null)
 assert.deepEqual(new Set(catalog.quest_keys),new Set(policy.managedQuestKeys));assert.equal(catalog.quest_keys.length,72)
 for(const action of ['visible','enter']){assert.equal(restriction.actions[action].enabled,false);assert.deepEqual(restriction.actions[action].quest_keys,catalog.quest_keys)}
 const members=new Map()
 for(const row of result.catalog)for(const key of row.quest_keys??[]){assert.equal(members.has(key),false,'Native parser rejects ambiguous ownership: '+key);members.set(key,row.key)}
 for(const key of policy.managedQuestKeys)assert.equal(members.get(key),restriction.key)
 assert.deepEqual(result.catalog.find(row=>row.key==='hard_multi_event:2088').quest_keys,['26:9000001'])
 assert.deepEqual(result.states.find(row=>row.key==='hard_multi_event:2088').actions.enter.quest_keys,['26:9000001'])
 assert.equal(result.revision,17)
})
test('catalog additions or prior explicit shop opening cannot reopen54 products in the client snapshot',()=>{
 const result=runtime.projectReleaseClosedSnapshot(snapshot()),state=result.states.find(row=>row.key===policy.closedShopKeys[0])
 for(const action of ['visible','exchange']){
  assert.equal(state.actions[action].enabled,false)
  const defaults=result.default_policy.actions[action]
  for(const key of policy.closedShopKeys){assert.ok(defaults.closed_keys.includes(key));assert.equal(defaults.qualified_rights_keys.includes(key),false);assert.equal(defaults.legacy_keys.includes(key),false)}
 }
 assert.deepEqual(runtime.projectReleaseClosedSnapshot(result),result,'Projection is idempotent')
})
