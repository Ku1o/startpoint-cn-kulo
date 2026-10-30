'use strict'
if(process.env.STARPOINT_TEST_COMPILED!=='1')require('ts-node/register/transpile-only')
const {test,before,after}=require('node:test'),assert=require('node:assert/strict')
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto')
const parent=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||os.tmpdir());fs.mkdirSync(parent,{recursive:true})
const directory=fs.mkdtempSync(path.join(parent,'closed-production-content-'))
Object.assign(process.env,{DATA_DIR:directory,CN_WRITER_THREAD:'0',MULTI_REALTIME_PROCESS:'0',MULTI_REALTIME_OWNER_CHILD:'0',GAME_VERBOSE_LOGS:'false',GAME_ROUTINE_LOGS:'off',GACHA_SEED_DIR:path.join(directory,'seeds')})
const load=p=>require('../'+(process.env.STARPOINT_TEST_COMPILED==='1'?'out':'src')+'/'+p)
const policy=require('../assets/quest_shop_availability_cnmod.json')
let db,app,players,items,active,assets,operations,identities,seed,restrictions
before(async()=>{
 load('data').initializeDatabase();db=load('data/db').getDb();assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(directory))
 players=load('data/domains/player');items=load('data/domains/item');active=load('data/domains/quest_active');assets=load('lib/assets')
 operations=load('lib/content-operations');identities=load('lib/gameplay-request-identity');seed=load('lib/seed-validator').default;restrictions=load('lib/content-release-restrictions')
 identities.initializeGameplayRequestIdentitySchemaSync(db)
 app=require('fastify')({logger:false});app.addHook('onSend',(_req,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')&&typeof body==='object'?JSON.stringify(body):body))
 await app.register(load('routes/api/singleBattleQuest').default,{prefix:'/single'})
 await app.register(async child=>load('multi/http/battle').registerBattleRoutes(child),{prefix:'/multi'})
 await app.register(load('routes/api/shop').default,{prefix:'/shop'});await app.ready()
})
after(async()=>{await app?.close();await seed?.close();if(db?.open)db.close();fs.rmSync(directory,{recursive:true})})
function fixture(){const a=load('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'closed-content',idpId:crypto.randomUUID(),status:'normal'}),p=players.insertDefaultPlayerSync(a.id),viewer=877000000+p.id
 load('data/activeAccount').saveAccountDefaultPlayer(a.id,p.id);db.prepare('INSERT INTO sessions(token,account_id,expires,type)VALUES(?,?,?,2)').run(String(viewer),a.id,'2099-01-01T00:00:00Z')
 players.updatePlayerSync({id:p.id,freeVmoney:100000000,vmoney:1000000,freeMana:10000,stamina:100})
 const token=db.transaction(()=>identities.issueGameplayLoginTokenSync(db,{accountId:a.id,viewerId:viewer,udid:'closed-'+viewer,expiresAt:Date.now()+86400000}))()
 return{id:p.id,viewer,token,seq:0}
}
const post=(p,url,body)=>app.inject({method:'POST',url,headers:{login_token:p.token},payload:{viewer_id:p.viewer,api_count:++p.seq,...body}})
function state(p){return{player:players.getPlayerSync(p.id),active:active.getPlayerActiveQuestSync(p.id),items:items.getPlayerItemsSync(p.id),
 purchases:db.prepare('SELECT * FROM players_shop_purchases WHERE player_id=? ORDER BY shop_item_id').all(p.id),
 progress:load('data/domains/quest').getPlayerQuestProgressSync(p.id)}}
const startBody=(category,quest)=>({category,quest_id:quest,play_id:crypto.randomUUID(),party_id:1,room_number:'',use_boost_point:false,use_boss_boost_point:false,is_auto_start_mode:false})
test('final candidate hard gates override an otherwise open store for all72 quests and54 products',()=>{
 const Store=load('lib/content-operations-store').ContentOperationsStore,allowed=Store.prototype.allowed,scoped=Store.prototype.scopedAllowed
 Store.prototype.allowed=()=>true;Store.prototype.scopedAllowed=()=>true
 try{
  for(const key of policy.managedQuestKeys){const[c,id]=key.split(':').map(Number);assert.equal(operations.contentQuestDecision(c,id),false);assert.ok(assets.getQuestFromCategorySync(c,id),'Keep quest definition '+key)}
  for(const key of policy.closedShopKeys){const id=Number(key.split(':')[1]);for(const action of ['visible','exchange'])assert.equal(load('lib/content-economy-operations').shopContentDecision(7,id,action),false)}
  assert.equal(load('lib/content-economy-operations').shopContentDecision(4,9730007,'exchange'),true,'Unrelated product remains governed by its original store')
  assert.equal(operations.contentQuestDecision(10,201011001),true,'Unrelated existing quest remains governed by its original parent')
 }finally{Store.prototype.allowed=allowed;Store.prototype.scopedAllowed=scoped}
})
test('real solo and multiplayer new-start paths reject all72 without changing wallet, inventory, stamina or progress',async()=>{
 const p=fixture(),before=state(p)
 for(const key of policy.managedQuestKeys){const[c,id]=key.split(':').map(Number)
  for(const route of ['/single/start','/multi/start']){const response=await post(p,route,startBody(c,id));assert.equal(response.statusCode,200,response.body);assert.equal(response.json().data_headers.result_code,4050,route+' '+key+' '+response.body)}
 }
 assert.deepEqual(state(p),before)
})
test('all54 original weapon products reject single and bulk purchases while owned equipment/progress survive',async()=>{
 const p=fixture()
 for(const key of policy.closedShopKeys){const id=Number(key.split(':')[1]),item=assets.getShopItemSync(7,id);assert.ok(item,'Retain original purchase identity '+id)
  for(const cost of item.costs??[])items.setPlayerItemSync(p.id,cost.id,1000000)
 }
 const weapon=policy.closedWeaponIds[0];load('lib/equipment').givePlayerEquipmentSync(p.id,weapon,1)
 const equipmentBefore=load('data/domains/equipment').getPlayerEquipmentListSync(p.id),before=state(p)
 for(const key of policy.closedShopKeys){const id=Number(key.split(':')[1]),response=await post(p,'/shop/buy',{shop_type:7,shop_item_id:id,number:1});assert.equal(response.statusCode,400,response.body);assert.match(response.body,/available/)}
 await post(p,'/shop/bulk_buy',{shop_type:7,buy_item_list:Object.fromEntries(policy.closedShopKeys.map(key=>[key.split(':')[1],1]))})
 assert.deepEqual(state(p),before);assert.deepEqual(load('data/domains/equipment').getPlayerEquipmentListSync(p.id),equipmentBefore)
})
test('actual full snapshot owns every closed key once and does not write player or control state',()=>{
 const store=operations.contentOperations(),before=db.prepare('SELECT total_changes() AS value').get().value,snapshot=store.snapshot(Date.now())
 const rows=snapshot.catalog.filter(row=>Array.isArray(row.quest_keys)),owners=new Map()
 for(const row of rows)for(const key of row.quest_keys){assert.equal(owners.has(key),false);owners.set(key,row.key)}
 const closed=snapshot.states.find(row=>row.key==='closed_boss_quests:1');assert.ok(closed)
 for(const key of policy.managedQuestKeys){assert.equal(owners.get(key),closed.key);for(const action of ['visible','enter'])assert.equal(closed.actions[action].enabled,false)}
 assert.equal(db.prepare('SELECT total_changes() AS value').get().value,before)
})
test('a legitimately registered old closed-boss run can finish and replay once after closure',async()=>{
 const p=fixture(),body=startBody(2,1080001),original=restrictions.isReleaseClosedQuest
 restrictions.isReleaseClosedQuest=()=>false
 try{const start=await post(p,'/single/start',body);assert.equal(start.statusCode,200,start.body);assert.ok(active.getPlayerActiveQuestSync(p.id))}finally{restrictions.isReleaseClosedQuest=original}
 assert.equal(operations.contentQuestDecision(2,1080001),false)
 const finish={category:2,quest_id:1080001,play_id:body.play_id,continue_count:0,elapsed_time_ms:1000,score:10000,add_mana:0,is_accomplished:true,is_restored:false,
  statistics:{clear_phase:1,max_combo_count:0,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],equipments:[null,null,null],ability_soul_ids:[null,null,null]},zones:[]}}
 const first=await post(p,'/single/finish',finish);assert.equal(first.statusCode,200,first.body);const paid=state(p)
 const second=await post(p,'/single/finish',finish);assert.equal(second.statusCode,200,second.body);assert.deepEqual(state(p),paid)
})
