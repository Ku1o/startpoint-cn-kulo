'use strict'
if(process.env.STARPOINT_TEST_COMPILED!=='1')require('ts-node/register/transpile-only')
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path')
const root=path.join(__dirname,'../assets'),closed=[10000320,10000302]
function walk(value,where,visit){if(!value||typeof value!=='object')return;visit(value,where);for(const[k,v]of Object.entries(value))if(v&&typeof v==='object')walk(v,where+'/'+k,visit)}
function forbiddenPoolMembers(pool,banned){const found=[];walk(pool,'',(row,where)=>{
 for(const key of ['id','character_id','characterId'])if(banned.has(row[key]))found.push({where,key,id:row[key]})
 for(const key of Object.keys(row))if(banned.has(Number(key)))found.push({where,key,id:Number(key)})
 if(Array.isArray(row))for(const value of row)if(typeof value==='number'&&banned.has(value))found.push({where,id:value})
});return found}
test('all regular JSON producers exclude both overlimit materials while preserving their definitions and costs',()=>{
 const files=fs.readdirSync(root).filter(f=>f.endsWith('.json')&&!f.startsWith('content')&&/reward|shop|exchange|campaign/.test(f))
 const found=[]
 for(const file of files)walk(JSON.parse(fs.readFileSync(path.join(root,file),'utf8')),'',(row,where)=>{
  if(closed.includes(row.id)&&!/(?:^|\/)(?:costs?|requirements?|materials?)(?:\/|$)/i.test(where))found.push({file,where,row})
 })
 assert.deepEqual(found,[])
 const names={...require('../assets/item_lookup.json'),...require('../assets/item_lookup_cnmod.json')}
 for(const id of closed)assert.ok(names[id],'Existing item definition must survive: '+id)
 assert.ok(require('../assets/character_overlimit.json'))
 const upgrades=require('../assets/equipment_enhancement_shop.json')
 assert.ok(Object.values(upgrades).some(row=>row.costs?.some(cost=>cost.id===10000302)),'Existing paradox-core consumption must remain')
})
test('closed characters stay defined and owned-compatible but do not appear in ordinary pools',()=>{
 const characters={...require('../assets/character.json'),...require('../assets/character_rank_p5b.json')}
 const pools=require('../'+(process.env.STARPOINT_TEST_COMPILED==='1'?'out':'src')+'/lib/content-master').serverGachas
 const bossIds=[119950,119951,119970,129950,129951,129970,139950,139951,139970,149950,149951,149970,159950,159951,159970,169950,169951,169970,179970,179981,179982,179983,179984,179985,179986]
 for(const id of [...bossIds,139988])assert.ok(characters[id],'Do not delete a saved character identity: '+id)
 const hits=[]
 for(const[id,pool]of Object.entries(pools)){
  const serialized=JSON.stringify(pool)
  for(const closedId of [129989,139988])if(new RegExp('"'+closedId+'"\\s*:|"(?:id|characterId|character_id)"\\s*:\\s*'+closedId+'(?:[,}])').test(serialized))hits.push({pool:id,character:closedId})
 }
 assert.deepEqual(hits,[])
 for(const poolId of [990001,990002]){
  const serialized=JSON.stringify(pools[poolId]),banned=new Set(bossIds),found=forbiddenPoolMembers(pools[poolId],banned)
  assert.deepEqual(found,[],'Closed members in effective merged pool '+poolId)
  const regression=structuredClone(pools[poolId]);regression.pool['1'].push({id:179981,rank:5,odds:1})
  assert.ok(forbiddenPoolMembers(regression,banned).some(hit=>hit.id===179981),'Numeric array-object IDs must be detected, unlike the retired key-only regex')
  assert.match(serialized,/169980/,'Abyss beast must remain')
 }
 assert.equal(require('../assets/boss_coin_shop.json')['97'],undefined)
})
test('GM weapons and Beretta have no regular minting source; owned-weapon enhancement data does not mint copies',()=>{
 const banned=new Set([139988,5139881,5990001,5990002,5990003,5990004,5990005,5990006]),hits=[]
 const files=fs.readdirSync(root).filter(f=>f.endsWith('.json')&&!f.startsWith('content')&&/reward|shop|exchange|campaign/.test(f)&&f!=='equipment_enhancement_shop.json')
 for(const file of files)walk(JSON.parse(fs.readFileSync(path.join(root,file),'utf8')),'',(row,where)=>{
  if(banned.has(row.id)&&!/(?:^|\/)(?:costs?|requirements?|materials?)(?:\/|$)/i.test(where))hits.push({file,where,id:row.id})
 })
 assert.deepEqual(hits,[])
 const upgrades=Object.values(require('../assets/equipment_enhancement_shop.json')).filter(row=>row.equipmentId===5139881)
 assert.ok(upgrades.length)
 for(const row of upgrades)assert.deepEqual(row.rewards,[],'Enhancement records must not produce a restricted base weapon')
})
