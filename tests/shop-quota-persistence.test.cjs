const {test,before,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'shop-quota-'))
process.env.DATA_DIR=directory;process.env.CN_WRITER_THREAD='0';process.env.GAME_VERBOSE_LOGS='false';process.env.GAME_ROUTINE_LOGS='off'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
const db=require('../out/data/db').getDb(),players=require('../out/data/domains/player'),assets=require('../out/lib/assets')
const purchases=require('../out/data/domains/shopPurchase'),quota=require('../out/lib/shop-quota'),utils=require('../out/utils'),saves=require('../out/data/snapshots/player-snapshot')
const coordinator=require('../out/lib/persistence-coordinator'),transaction=coordinator.runPersistenceTransaction
const getDate=utils.getServerDate;let at=new Date('2026-10-20T20:59:59Z'),app,player,viewer,other
const itemId=200070,shopType=2,item=assets.getShopItemSync(shopType,itemId)
function create(name){const a=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:name,idpId:name,status:'normal'});const p=players.insertDefaultPlayerSync(a.id);require('../out/data/activeAccount').saveAccountDefaultPlayer(a.id,p.id);return {...p,accountId:a.id}}
const post=(url,body={})=>app.inject({method:'POST',url,payload:{viewer_id:viewer,...body}})
const buy=number=>post('/buy',{shop_type:shopType,shop_item_id:itemId,number,api_count:1})
function data(r){assert.equal(r.statusCode,200,r.body);return unpack(Buffer.from(r.body,'base64')).data}
function snapshot(){return saves.createPlayerSaveSnapshotV2Sync(player.id,db).data.tables}
const state=()=>quota.getShopQuotaStateSync(player.id,shopType,itemId,item,at)
before(async()=>{
 assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory)+path.sep));assert.equal(item.dailyStock,30);assert.equal(item.stock,30)
 player=create('quota-new');other=create('quota-legacy');viewer=910000000+player.id
 players.updatePlayerSync({id:player.id,freeMana:10000000,paidMana:10000000});players.updatePlayerSync({id:other.id,freeMana:10000000,paidMana:10000000})
 db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),player.accountId,'2099-01-01T00:00:00Z')
 utils.getServerDate=()=>new Date(at)
 app=Fastify({logger:false});app.addHook('onSend',(_r,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
 await app.register(require('../out/routes/api/shop').default);await app.register(require('../out/routes/api/howToGet').default,{prefix:'/how'});await app.ready()
})
after(async()=>{utils.getServerDate=getDate;coordinator.runPersistenceTransaction=transaction;await app.close();await require('../out/lib/seed-validator').default.close();db.close();fs.rmSync(directory,{recursive:true})})
test('real July daily product charges exact costs, persists quota, caps single/bulk and updates sales',async()=>{
 assert.equal(state().migrationState,'known');assert.equal(state().remaining,30)
 data(await buy(2));assert.equal(state().today,2);assert.equal(state().remaining,28)
 assert.equal((await buy(29)).statusCode,400)
 data(await post('/bulk_buy',{shop_type:2,buy_item_list:{[itemId]:50},api_count:2}));assert.equal(state().today,30);assert.equal(state().total,30)
 const saved=snapshot();assert.equal((await buy(1)).statusCode,400);assert.deepEqual(snapshot(),saved)
 const sales=data(await post('/get_sales_list',{shop_types:[2],event_list:[],boss_coin_shop_category_ids:[],equipment_enhancement_category_ids:[]})).sales_list.find(row=>row.shop_item_id===itemId)
 assert.equal(sales.stock_quantity,0);assert.equal(sales.today_purchase_num,30);assert.equal(sales.total_purchase_num,30)
 const acquisition=data(await post('/how/get_list',{item_id:2})).shop_sales_list.find(row=>row.shop_type===2&&row.shop_item_id===itemId);assert.deepEqual(acquisition,sales)
})
test('business boundary opens only the next day, keeps lifetime history and does not reuse stock as lifetime cap',async()=>{
 assert.equal(state().remaining,0)
 at=new Date('2026-10-20T21:00:00Z') // 05:00 UTC+8
 assert.equal(state().today,0);assert.equal(state().remaining,30);assert.equal(state().total,30)
 data(await buy(3));assert.equal(state().today,3);assert.equal(state().total,33)
 const sales=data(await post('/get_sales_list',{shop_types:[2],event_list:[],boss_coin_shop_category_ids:[],equipment_enhancement_category_ids:[]})).sales_list.find(row=>row.shop_item_id===itemId)
 const acquisition=data(await post('/how/get_list',{item_id:2})).shop_sales_list.find(row=>row.shop_type===2&&row.shop_item_id===itemId);assert.equal(sales.stock_quantity,27);assert.equal(sales.today_purchase_num,3);assert.deepEqual(acquisition,sales)
 assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_shop_quotas WHERE player_id=? AND purchase_key=?').get(player.id,itemId).n,2)
})
test('grant failure rolls quota, inventory and cost back together',async()=>{
 const saved=snapshot();coordinator.runPersistenceTransaction=async(context,fn,options)=>transaction(context,()=>{const result=fn();if(context.operation==='purchase'&&result.ok)throw Error('after quota failure');return result},options)
 try{assert.equal((await buy(1)).statusCode,500);assert.deepEqual(snapshot(),saved)}finally{coordinator.runPersistenceTransaction=transaction}
 data(await buy(1));assert.equal(state().today,4)
})
test('legacy lifetime history without dates is unresolved and cannot silently become today usage or zero',async()=>{
 purchases.addPlayerShopPurchaseCountSync(other.id,itemId,7)
 const s=quota.getShopQuotaStateSync(other.id,2,itemId,item,at);assert.equal(s.migrationState,'unresolved');assert.equal(s.remaining,0);assert.equal(s.total,7)
 db.prepare('UPDATE sessions SET account_id=? WHERE token=?').run(other.accountId,String(viewer));const before=saves.createPlayerSaveSnapshotV2Sync(other.id,db).data.tables
 try{const source=data(await post('/how/get_list',{item_id:2})).shop_sales_list.find(row=>row.shop_type===2&&row.shop_item_id===itemId);assert.equal(source.stock_quantity,0);assert.equal(source.quota_migration_state,'unresolved');assert.equal((await buy(1)).statusCode,400);data(await post('/bulk_buy',{shop_type:2,buy_item_list:{[itemId]:2},api_count:2}));assert.deepEqual(saves.createPlayerSaveSnapshotV2Sync(other.id,db).data.tables,before)}finally{db.prepare('UPDATE sessions SET account_id=? WHERE token=?').run(player.accountId,String(viewer))}
})
test('native monthly and lifetime rules use separate persistent counters and reset-aware month',()=>{
 // Current server masters contain daily rows only. Exercise the supported monthly/max-frequency contract explicitly.
 const example={...item,stock:100,dailyStock:undefined,monthlyStock:5,maxFrequency:7},id=999900001
 const read=()=>quota.getShopQuotaStateSync(player.id,2,id,example,at)
 at=new Date('2026-10-31T20:59:59Z');assert.equal(read().remaining,5)
 db.transaction(()=>{quota.recordShopQuotaPurchaseSync(player.id,2,id,example,5,at);purchases.addPlayerShopPurchaseCountSync(player.id,id,5)})()
 assert.equal(read().remaining,0);at=new Date('2026-10-31T21:00:00Z');assert.equal(read().thisMonth,0);assert.equal(read().remaining,2)
 db.transaction(()=>{quota.recordShopQuotaPurchaseSync(player.id,2,id,example,2,at);purchases.addPlayerShopPurchaseCountSync(player.id,id,2)})()
 assert.equal(read().remaining,0)
})
test('legacy reservation belongs to the persistent cutover day, expires at 05:00 even for late return, and is save-portable',()=>{
 const carried=create('quota-carry'),late=create('quota-late'),anchor=Date.parse('2026-10-20T12:00:00Z'),cutoverDay=new Date(anchor),nextDay=new Date('2026-10-20T21:00:00Z')
 purchases.addPlayerShopPurchaseCountSync(carried.id,itemId,12);purchases.addPlayerShopPurchaseCountSync(late.id,itemId,12)
 const read=(id,when,explicit=anchor)=>quota.getShopQuotaStateSync(id,2,itemId,item,when,explicit)
 assert.equal(read(carried.id,cutoverDay).migrationState,'legacy-carry');assert.equal(read(carried.id,cutoverDay).today,12);assert.equal(read(carried.id,cutoverDay).remaining,18)
 assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_shop_quotas WHERE player_id=?').get(carried.id).n,0,'read paths never persist the reservation')
 db.transaction(()=>{quota.recordShopQuotaPurchaseSync(carried.id,2,itemId,item,2,cutoverDay,anchor);purchases.addPlayerShopPurchaseCountSync(carried.id,itemId,2)})()
 assert.equal(read(carried.id,cutoverDay).today,14);assert.equal(read(carried.id,cutoverDay).remaining,16);assert.equal(read(carried.id,cutoverDay).total,14,'reservation is never re-added to lifetime')
 assert.equal(read(carried.id,nextDay).remaining,30);assert.equal(read(carried.id,nextDay).today,0);assert.equal(read(carried.id,nextDay).total,14)
 assert.equal(read(late.id,nextDay).remaining,30,'late first return reserves the old cutover day, not today')
 db.transaction(()=>{quota.recordShopQuotaPurchaseSync(late.id,2,itemId,item,1,nextDay,anchor);purchases.addPlayerShopPurchaseCountSync(late.id,itemId,1)})()
 assert.equal(quota.getShopQuotaStateSync(late.id,2,itemId,item,nextDay).remaining,29)
 const archived=saves.createPlayerSaveSnapshotV2Sync(carried.id,db),before=archived.data.tables.players_shop_quotas
 assert.ok(before.rows.some(row=>row[before.columns.indexOf('period_kind')]==='legacy'&&row[before.columns.indexOf('count')]===12))
 players.replacePlayerDataSync(require('../out/data/utils/player-data').getMergedPlayerDataSync(carried.id));assert.deepEqual(saves.createPlayerSaveSnapshotV2Sync(carried.id,db).data.tables.players_shop_quotas,before)
 saves.restorePlayerSaveSnapshotV2Sync(archived,late.id,{},db);assert.equal(read(late.id,cutoverDay,undefined).remaining,16);assert.equal(read(late.id,nextDay,undefined).remaining,30)
 const sql='SELECT period_kind,period_key,count FROM players_shop_quotas WHERE player_id=? ORDER BY period_kind,period_key'
 const child=require('node:child_process').execFileSync(process.execPath,['-e',"const D=require('better-sqlite3');const d=new D(process.argv[1],{readonly:true});console.log(JSON.stringify(d.prepare(process.argv[2]).all(Number(process.argv[3]))));d.close()",db.name,sql,String(carried.id)],{cwd:path.resolve(__dirname,'..'),encoding:'utf8'})
 assert.deepEqual(JSON.parse(child),db.prepare(sql).all(carried.id))
})
test('production reservation reads the actual persisted real-clock cutover anchor',()=>{
 const D=require('better-sqlite3'),fixture=new D(':memory:'),connection=require('../out/data/db'),clock=require('../out/lib/server-clock-state'),rehearsal=require('../out/lib/time-cutover-rehearsal')
 const anchor=Date.parse('2026-10-20T12:00:00Z')
 fixture.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY,exp_pool INTEGER,exp_pooled_time,time_offset,vmoney INTEGER,last_login_time TEXT,total_login_days INTEGER);
 CREATE TABLE players_active_quests(player_id INTEGER PRIMARY KEY,play_id TEXT,started_at_ms INTEGER,clock_version INTEGER);`)
 fixture.prepare('INSERT INTO players VALUES(?,?,?,?,?,?,?)').run(1,123,new Date(anchor-1000).toISOString(),0,900,'2026-10-20T00:00:00Z',12)
 for(const table of ['players_shop_purchases','players_shop_quotas'])fixture.exec(db.prepare('SELECT sql FROM sqlite_master WHERE name=?').get(table).sql)
 fixture.prepare('INSERT INTO players_shop_purchases(player_id,shop_item_id,count) VALUES(1,?,12)').run(itemId)
 const options={cutoverRealMs:anchor,legacyOffsetMs:0,readiness:'scenario-only'},plan=rehearsal.planTimeCutoverRehearsalSync(fixture,options)
 clock.activateRealServerClockOfflineSync(fixture,{...options,expectedPlanDigest:plan.digest})
 connection.setDbOverride(fixture)
 try{
  const first=quota.getShopQuotaStateSync(1,2,itemId,item,new Date(anchor));assert.equal(first.remaining,18);assert.equal(first.legacyAnchorMs,anchor)
  const late=quota.getShopQuotaStateSync(1,2,itemId,item,new Date('2026-10-20T21:00:00Z'));assert.equal(late.remaining,30)
 }finally{connection.setDbOverride(null);fixture.close()}
})
test('fresh process reads every previous day/month quota without resetting counters',()=>{
 const sql='SELECT purchase_key,period_kind,period_key,count FROM players_shop_quotas WHERE player_id=? ORDER BY purchase_key,period_kind,period_key'
 const expected=db.prepare(sql).all(player.id);assert.ok(expected.length>=4)
 const child=require('node:child_process').execFileSync(process.execPath,['-e',"const D=require('better-sqlite3');const d=new D(process.argv[1],{readonly:true});console.log(JSON.stringify(d.prepare(process.argv[2]).all(Number(process.argv[3]))));d.close()",db.name,sql,String(player.id)],{cwd:path.resolve(__dirname,'..'),encoding:'utf8'})
 assert.deepEqual(JSON.parse(child),expected)
})
test('V1 preserve-target, V2 replacement and failure rollback retain exact quotas; delete cascades',()=>{
 const archive=saves.createPlayerSaveSnapshotV2Sync(player.id,db),before=archive.data.tables.players_shop_quotas
 players.replacePlayerDataSync(require('../out/data/utils/player-data').getMergedPlayerDataSync(player.id))
 assert.deepEqual(snapshot().players_shop_quotas,before)
 saves.restorePlayerSaveSnapshotV2Sync(archive,other.id,{},db)
 assert.deepEqual(saves.createPlayerSaveSnapshotV2Sync(other.id,db).data.tables.players_shop_quotas.rows.map(row=>row.slice(1)),before.rows.map(row=>row.slice(1)))
 const saved=snapshot();db.exec(`CREATE TRIGGER fail_quota_restore BEFORE INSERT ON players_shop_quotas WHEN NEW.player_id=${player.id} BEGIN SELECT RAISE(ABORT,'quota restore failure'); END`)
 try{assert.throws(()=>saves.restorePlayerSaveSnapshotV2Sync(archive,player.id,{},db),/quota restore failure/);assert.deepEqual(snapshot(),saved)}finally{db.exec('DROP TRIGGER fail_quota_restore')}
 players.deletePlayerSync(other.id);assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_shop_quotas WHERE player_id=?').get(other.id).n,0);assert.deepEqual(db.pragma('foreign_key_check'),[])
})
