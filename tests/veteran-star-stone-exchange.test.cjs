'use strict'
const {test,before,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const {randomUUID}=require('node:crypto'),ts=require('typescript')
const root=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||os.tmpdir())
fs.mkdirSync(root,{recursive:true})
const directory=fs.mkdtempSync(path.join(root,'veteran-exchange-'))
Object.assign(process.env,{DATA_DIR:directory,GACHA_SEED_DIR:path.join(directory,'seeds'),TMP:directory,TEMP:directory,TMPDIR:directory,SQLITE_TMPDIR:directory,CN_WRITER_THREAD:'0',GAME_ROUTINE_LOGS:'off',GAME_VERBOSE_LOGS:'false'})
// Run current sources; never compile or replace a runtime out/ directory.
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true},fileName:filename}).outputText,filename)
const load=name=>require('../src/'+name+'.ts')
const operations=load('lib/content-operations'),assets=load('lib/assets'),players=load('data/domains/player')
const degrees=load('data/domains/degree'),purchases=load('data/domains/shopPurchase')
const coordinator=load('lib/persistence-coordinator'),transaction=coordinator.runPersistenceTransaction
const ITEM=9700118,DEGREE=9900006,PRICE=5000000,PARENT='rush_event:700099',KEY='event_item_shop:'+ITEM
let db,app,tables,nextViewer=89701180
const quote=value=>'"'+value.replaceAll('"','""')+'"'
function control(key,enabled=true){
 const store=operations.contentOperations()
 return store.update(key,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'Synthetic veteran title exchange regression',actionOverrides:{visible:{enabled,endsAtMs:null,readiness:'verified',evidence:'Exact 9700118 current native/server receipt; isolated fixture only'},exchange:{enabled,endsAtMs:null,readiness:'verified',evidence:'Exact 9700118 original price, reward and lifetime limit; isolated fixture only'}}},Date.now())
}
function publication(key,published){
 const store=operations.contentOperations();return store.setPublished(key,{expectedRevision:store.revision(),catalogDigest:store.digest,published,reason:'Synthetic publication regression; preserve save progress'},Date.now())
}
function fixture(free=PRICE,paid=0,accountId){
 if(!accountId)accountId=load('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'veteran-title-fixture',idpId:randomUUID(),status:'normal'}).id
 const player=players.insertDefaultPlayerSync(accountId),viewer=nextViewer++
 players.updatePlayerSync({id:player.id,freeVmoney:free,vmoney:paid})
 db.transaction(()=>load('lib/server-clock-state').ensurePlayerClockStateForLoadSync(player.id,db))()
 db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),accountId,'2099-01-01T00:00:00Z')
 return {id:player.id,accountId,viewer}
}
function post(player,url,body){
 load('data/activeAccount').saveAccountDefaultPlayer(player.accountId,player.id)
 return app.inject({method:'POST',url,payload:{viewer_id:player.viewer,api_count:1,...body}})
}
const buy=(player,number=1)=>post(player,'/shop/buy',{shop_type:4,shop_item_id:ITEM,number})
const bulk=(player,number=1)=>post(player,'/shop/bulk_buy',{shop_type:4,buy_item_list:{[ITEM]:number}})
async function sale(player){
 const response=await post(player,'/shop/get_sales_list',{shop_types:[4],event_list:[{event_type:11,event_ids:[700099]}],boss_coin_shop_category_ids:[],equipment_enhancement_shop_category_ids:[],browse_treasure_flag:false})
 assert.equal(response.statusCode,200,response.body)
 return response.json().data.sales_list.find(row=>row.shop_item_id===ITEM)
}
function snapshot(player){return Object.fromEntries(tables.map(({name,owner})=>[name,db.prepare(`SELECT * FROM ${quote(name)} WHERE ${quote(owner)}=?`).all(player.id).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)))]))}
const balance=player=>{const value=players.getPlayerSync(player.id);return {free:value.freeVmoney,paid:value.vmoney}}
function success(response){assert.equal(response.statusCode,200,response.body);return response.json().data}
function history(player){return purchases.getPlayerShopPurchaseCountSync(player.id,ITEM)}
function owns(player){return degrees.hasPlayerDegreeSync(player.id,DEGREE)}

before(async()=>{
 db=load('data/db').getDb();assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(directory))
 tables=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all().map(({name})=>({name,columns:db.prepare(`PRAGMA table_info(${quote(name)})`).all().map(row=>row.name)})).filter(row=>row.name==='players'||row.columns.includes('player_id')).map(row=>({name:row.name,owner:row.name==='players'?'id':'player_id'}))
 // A missing exact receipt must fail here. No mock or policy substitution can
 // make this suite pass while the actual operations store refuses this item.
 control(PARENT);control(KEY)
 app=require('fastify')({logger:false});app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?JSON.stringify(body):body))
 await app.register(load('routes/api/shop').default,{prefix:'/shop'})
 await app.register(load('routes/api/profile').default,{prefix:'/profile'});await app.ready()
})
after(async()=>{
 coordinator.runPersistenceTransaction=transaction
 if(app)await app.close();await load('lib/seed-validator').default.close();if(db?.open)db.close()
 assert.equal(path.dirname(directory),root);fs.rmSync(directory,{recursive:true})
})

test('the real definition gate admits only the reviewed original veteran contract and displays one unit',async()=>{
 const item=assets.getShopItemSync(4,ITEM),store=operations.contentOperations()
 assert.deepEqual(item.userCost,{amount:PRICE,type:0});assert.deepEqual(item.costs,[])
 assert.deepEqual(item.rewards,[{count:1,id:DEGREE,type:5}]);assert.equal(item.nativeStockLimits.lifetime,1)
 assert.equal(store.allowed(KEY,'visible',Date.now()),true);assert.equal(store.allowed(KEY,'exchange',Date.now()),true)
 const player=fixture(),row=await sale(player);assert.ok(row);assert.equal(row.stock_quantity,1);assert.equal(row.total_purchase_num,0)
})
test('single purchase spends free stones first, grants the title and preserves unrelated currency',async()=>{
 for(const [free,paid,expected] of [[PRICE+17,200,{free:17,paid:200}],[1250000,4000000,{free:0,paid:250000}]]){
  const player=fixture(free,paid),before=players.getPlayerSync(player.id),data=success(await buy(player))
  assert.deepEqual(balance(player),expected);assert.equal(owns(player),true);assert.equal(history(player),1)
  assert.deepEqual(data.degree_list,[{viewer_id:player.viewer,degree_id:DEGREE}])
  const current=players.getPlayerSync(player.id);for(const field of ['freeMana','paidMana','bondToken','starCrumb'])assert.equal(current[field],before[field])
  const row=await sale(player);assert.equal(row.stock_quantity,0);assert.equal(row.total_purchase_num,1)
 }
})
test('insufficient combined stones reject a single and skip a bulk with no player changes',async()=>{
 const player=fixture(1000000,3999999),before=snapshot(player)
 const single=await buy(player);assert.equal(single.statusCode,400);assert.match(single.body,/Not enough beads/);assert.deepEqual(snapshot(player),before)
 success(await bulk(player));assert.deepEqual(snapshot(player),before);assert.equal(owns(player),false);assert.equal(history(player),0)
})
test('bulk caps an oversized request to one purchase and keeps the same free-first payment and title response',async()=>{
 const player=fixture(2000000,8000000),data=success(await bulk(player,100))
 assert.deepEqual(balance(player),{free:0,paid:5000000});assert.equal(history(player),1);assert.equal(owns(player),true)
 assert.deepEqual(data.degree_list,[{viewer_id:player.viewer,degree_id:DEGREE}])
 const before=snapshot(player);assert.equal((await buy(player)).statusCode,400);success(await bulk(player,100));assert.deepEqual(snapshot(player),before)
})
test('the actual title-selection profile endpoint reads the persisted veteran title without repeat purchase',async()=>{
 const player=fixture(),initial=success(await post(player,'/profile/get_degree_list',{})).degree_ids
 assert.equal(initial.includes(DEGREE),false)
 success(await buy(player))
 for(let read=0;read<2;read++){
  const ids=success(await post(player,'/profile/get_degree_list',{})).degree_ids
  assert.equal(ids.filter(id=>id===DEGREE).length,1);assert.equal(history(player),1);assert.deepEqual(balance(player),{free:0,paid:0})
 }
 const existing=fixture();degrees.grantPlayerDegreeSync(existing.id,DEGREE,123)
 assert.ok(success(await post(existing,'/profile/get_degree_list',{})).degree_ids.includes(DEGREE))
 assert.equal(history(existing),0);assert.equal((await sale(existing)).stock_quantity,0)
})
test('existing title ownership and exhausted legacy purchase history each prevent a second charge',async()=>{
 const owner=fixture(PRICE*3);degrees.grantPlayerDegreeSync(owner.id,DEGREE,1)
 const ownedBefore=snapshot(owner);assert.equal((await sale(owner)).stock_quantity,0);assert.equal((await buy(owner)).statusCode,400);success(await bulk(owner));assert.deepEqual(snapshot(owner),ownedBefore);assert.equal(history(owner),0)
 const spent=fixture(PRICE*3);purchases.addPlayerShopPurchaseCountSync(spent.id,ITEM,1)
 const spentBefore=snapshot(spent);assert.equal((await sale(spent)).stock_quantity,0);assert.equal((await buy(spent)).statusCode,400);success(await bulk(spent));assert.deepEqual(snapshot(spent),spentBefore)
})
test('the lifetime limit belongs to each save, including another save on one account and a separate account',async()=>{
 const first=fixture(),sameAccount=fixture(PRICE,0,first.accountId),otherAccount=fixture()
 for(const player of [first,sameAccount,otherAccount]){success(await buy(player));assert.equal(history(player),1);assert.equal(owns(player),true);assert.deepEqual(balance(player),{free:0,paid:0})}
 const before=snapshot(first);assert.equal((await buy(first)).statusCode,400);assert.deepEqual(snapshot(first),before)
})
test('parent and product closure each reject stale purchases, and reopening preserves already acquired rights',async()=>{
 const player=fixture(PRICE*2),before=snapshot(player)
 publication(PARENT,false)
 try{assert.equal(await sale(player),undefined);assert.equal((await buy(player)).statusCode,400);success(await bulk(player));assert.deepEqual(snapshot(player),before)}finally{publication(PARENT,true)}
 control(KEY,false)
 try{assert.equal(await sale(player),undefined);assert.equal((await buy(player)).statusCode,400);success(await bulk(player));assert.deepEqual(snapshot(player),before)}finally{control(KEY,true)}
 success(await buy(player));const ownedBefore=snapshot(player)
 publication(PARENT,false);publication(PARENT,true);assert.equal((await buy(player)).statusCode,400);assert.deepEqual(snapshot(player),ownedBefore)
})
test('a parent closed while purchase waits is rechecked before any charge or title write',async()=>{
 const player=fixture(),before=snapshot(player);let release,queued,hold=true
 const wait=new Promise(resolve=>{release=resolve}),entered=new Promise(resolve=>{queued=resolve})
 coordinator.runPersistenceTransaction=async(context,write,options)=>{if(context.operation==='purchase'&&hold){hold=false;queued();await wait}return transaction(context,write,options)}
 try{
  const pending=buy(player).then(value=>value);await entered;publication(PARENT,false);release()
  assert.equal((await pending).statusCode,400);assert.deepEqual(snapshot(player),before)
 }finally{release();coordinator.runPersistenceTransaction=transaction;if(operations.contentOperations().state(PARENT).published===false)publication(PARENT,true)}
})
test('a title received while purchase waits is rechecked, preserving that existing title without charging',async()=>{
 const player=fixture(),grant=degrees.grantPlayerDegreeSync;let release,queued,hold=true
 const wait=new Promise(resolve=>{release=resolve}),entered=new Promise(resolve=>{queued=resolve})
 coordinator.runPersistenceTransaction=async(context,write,options)=>{if(context.operation==='purchase'&&hold){hold=false;queued();await wait}return transaction(context,write,options)}
 try{
  const pending=buy(player).then(value=>value);await entered;grant(player.id,DEGREE,123);const before=snapshot(player);release()
  assert.equal((await pending).statusCode,400);assert.deepEqual(snapshot(player),before);assert.equal(history(player),0)
 }finally{release();coordinator.runPersistenceTransaction=transaction}
})
test('simultaneous single and bulk requests can charge and grant at most once for the same save',async()=>{
 const player=fixture(PRICE*3),responses=await Promise.all([buy(player),bulk(player)])
 assert.ok(responses.some(response=>response.statusCode===200));assert.equal(history(player),1);assert.equal(owns(player),true);assert.deepEqual(balance(player),{free:PRICE*2,paid:0})
 assert.equal(degrees.getPlayerDegreeIdsSync(player.id).filter(id=>id===DEGREE).length,1)
})
test('receipt failures roll back stones, title and stock together for both single and bulk, then permit one retry',async()=>{
 for(const operation of [buy,bulk]){
  const player=fixture(1000000,6000000),before=snapshot(player)
  db.exec(`CREATE TEMP TRIGGER fail_veteran_receipt BEFORE INSERT ON players_shop_purchases WHEN NEW.player_id=${player.id} BEGIN SELECT RAISE(ABORT,'synthetic veteran receipt failure'); END`)
  try{assert.equal((await operation(player)).statusCode,500);assert.deepEqual(snapshot(player),before)}finally{db.exec('DROP TRIGGER fail_veteran_receipt')}
  success(await operation(player));assert.equal(owns(player),true);assert.equal(history(player),1);assert.deepEqual(balance(player),{free:0,paid:2000000})
 }
})
