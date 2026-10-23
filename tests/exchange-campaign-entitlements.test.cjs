const {test,before,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'campaign-entitlement-'))
process.env.DATA_DIR=directory;process.env.CN_WRITER_THREAD='0';process.env.GAME_VERBOSE_LOGS='false';process.env.GAME_ROUTINE_LOGS='off'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
const db=require('../out/data/db').getDb(),players=require('../out/data/domains/player')
const items=require('../out/data/domains/item'),campaigns=require('../out/data/domains/campaign')
const defs=require('../out/lib/exchange-campaign-definitions'),entitlements=require('../out/lib/exchange-campaign-entitlements')
const ops=require('../out/lib/content-operations'),coordinator=require('../out/lib/persistence-coordinator'),transaction=coordinator.runPersistenceTransaction
const saves=require('../out/data/snapshots/player-snapshot')
let app,player,viewer,second
function create(name){const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:name,idpId:name,status:'normal'});const p=players.insertDefaultPlayerSync(account.id);require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,p.id);return p}
const post=(url,extra={})=>app.inject({method:'POST',url,payload:{viewer_id:viewer,...extra}})
function data(response){assert.equal(response.statusCode,200,response.body);return unpack(Buffer.from(response.body,'base64')).data}
function snapshot(){return saves.createPlayerSaveSnapshotV2Sync(player.id,db).data.tables}
function special(id,status=2){db.prepare('INSERT OR REPLACE INTO players_special_exchange_campaigns(campaign_id,status,player_id) VALUES(?,?,?)').run(id,status,player.id)}
function control(type,id,flags){const store=ops.contentOperations();return store.update(`${type}:${id}`,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'Nonempty isolated entitlement fixture',readiness:'verified',evidence:'Actual master plus saved campaign and ticket',actionOverrides:Object.fromEntries(Object.entries(flags).map(([action,enabled])=>[action,{enabled,endsAtMs:null,readiness:'verified',evidence:'Independent retained-rights action fixture'}]))},Date.now())}
before(async()=>{
 assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory)+path.sep))
 player=create('entitlement-source');second=create('entitlement-target');viewer=890000000+player.id
 db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),db.prepare('SELECT account_id FROM players WHERE id=?').get(player.id).account_id,'2099-01-01T00:00:00Z')
 // Account property is not part of the returned default player; resolve the persisted owner.
 db.prepare('UPDATE sessions SET account_id=(SELECT account_id FROM players WHERE id=?) WHERE token=?').run(player.id,String(viewer))
 app=Fastify({logger:false});app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
 await app.register(require('../out/routes/api/specialExchange').default,{prefix:'/special'})
 await app.register(require('../out/routes/api/startDashExchange').default,{prefix:'/start'})
 await app.ready()
})
after(async()=>{coordinator.runPersistenceTransaction=transaction;if(app)await app.close();await require('../out/lib/seed-validator').default.close();db.close();fs.rmSync(directory,{recursive:true})})
test('actual special master shares tickets but history and balances create no campaign qualification',async()=>{
 assert.equal(defs.SPECIAL_EXCHANGE_DEFINITIONS['1'].ticketItemId,999002);assert.equal(defs.SPECIAL_EXCHANGE_DEFINITIONS['3'].ticketItemId,999002)
 items.setPlayerItemSync(player.id,999002,3)
 const before=snapshot();assert.equal(data(await post('/special/get_retained_campaigns')).special_exchange_campaign_list.length,0)
 assert.equal((await post('/special/exchange_character',{campaign_id:1,character_id:111001})).statusCode,400)
 assert.equal((await post('/special/enter_campaign',{campaign_id:1})).statusCode,400)
 assert.equal((await post('/special/buy_ticket',{campaign_id:1})).statusCode,400)
 assert.deepEqual(snapshot(),before)
})
test('purchased special character right remains reachable after entry closure and exchanges once',async()=>{
 special(1);control('special_exchange_campaign',1,{visible:false,enter:false})
 const before=snapshot();assert.equal(data(await post('/special/enter_campaign',{campaign_id:1})).special_exchange_campaign_list[0].status,2);assert.deepEqual(snapshot(),before)
 assert.equal((await post('/special/exchange_character',{campaign_id:3,character_id:111001})).statusCode,400,'ticket for campaign1 cannot qualify campaign3')
 assert.equal((await post('/special/exchange_character',{campaign_id:1,character_id:169995})).statusCode,400,'non-native choice denied')
 const granted=data(await post('/special/exchange_character',{campaign_id:1,character_id:111001}))
 assert.equal(granted.special_exchange_campaign_list[0].status,3);assert.equal(granted.item_list['999002'],2);assert.ok(granted.character_list.length)
 const saved=snapshot();data(await post('/special/exchange_character',{campaign_id:1,character_id:111001}));assert.deepEqual(snapshot(),saved)
 assert.equal((await post('/special/exchange_character',{campaign_id:1,character_id:111002})).statusCode,400,'another selection cannot replay the receipt')
 assert.deepEqual(snapshot(),saved)
})
test('equipment exchange and rollback use the real equipment whitelist and preserve qualification on failure',async()=>{
 special(2);items.setPlayerItemSync(player.id,999006,1)
 const before=snapshot();coordinator.runPersistenceTransaction=async(context,fn,options)=>transaction(context,()=>{const result=fn();if(context.operation==='exchange_special_exchange_campaign'&&result)throw Error('injected after-grant failure');return result},options)
 try{assert.equal((await post('/special/exchange_equipment',{campaign_id:2,equipment_id:5010028})).statusCode,500);assert.deepEqual(snapshot(),before)}finally{coordinator.runPersistenceTransaction=transaction}
 const result=data(await post('/special/exchange_equipment',{campaign_id:2,equipment_id:5010028}));assert.equal(result.equipment_list.length,1);assert.equal(result.item_list['999006'],0)
})
test('operator exchange close is checked after queue admission and does not remove history or tickets',async()=>{
 special(3);items.setPlayerItemSync(player.id,999002,2)
 let queued=false;const before=snapshot()
 coordinator.runPersistenceTransaction=async(context,fn,options)=>{if(context.operation==='exchange_special_exchange_campaign'){queued=true;control('special_exchange_campaign',3,{exchange:false})}return transaction(context,fn,options)}
 try{assert.equal((await post('/special/exchange_character',{campaign_id:3,character_id:111001})).statusCode,400);assert.ok(queued);assert.deepEqual(snapshot(),before)}finally{coordinator.runPersistenceTransaction=transaction}
 assert.ok(data(await post('/special/get_retained_campaigns')).special_exchange_campaign_list.some(row=>row.campaign_id===3&&row.status===2))
})
test('StartDash keeps its saved pool, term, personal dates and paid right while entry is closed',async()=>{
 const gachas=require('../out/lib/content-master').serverGachas
 const [gid,gacha]=Object.entries(gachas).find(([id,g])=>g.type===0&&Object.values(g.pool).flat().some(row=>[4,5].includes(row.rank)&&!row.isLimited))
 const choice=Object.values(gacha.pool).flat().find(row=>[4,5].includes(row.rank)&&!row.isLimited)
 campaigns.insertPlayerStartDashExchangeCampaignsSync(player.id,[{campaignId:1,gachaId:Number(gid),termIndex:0,status:2,periodStartTime:new Date('2024-01-01T00:00:00Z'),periodEndTime:new Date('2024-01-08T00:00:00Z')}])
 items.setPlayerItemSync(player.id,990007,1);control('start_dash_exchange_campaign',1,{visible:false,enter:false})
 const before=campaigns.getPlayerStartDashExchangeCampaignsSync(player.id)[0]
 const result=data(await post('/start/exchange_character',{campaign_id:1,character_id:choice.id}))
 assert.equal(result.start_dash_exchange_campaign_list[0].status,3);assert.equal(result.item_list['990007'],0)
 assert.deepEqual({...campaigns.getPlayerStartDashExchangeCampaignsSync(player.id)[0],status:2},before)
 const saved=snapshot();data(await post('/start/exchange_character',{campaign_id:1,character_id:choice.id}));assert.deepEqual(snapshot(),saved)
})
test('legacy completed status without an exact selection receipt never returns a false successful choice',async()=>{
 special(11,3);const saved=snapshot()
 const choice=defs.SPECIAL_EXCHANGE_DEFINITIONS['11'].rewardIds[0]
 assert.equal((await post('/special/exchange_character',{campaign_id:11,character_id:choice})).statusCode,400)
 assert.deepEqual(snapshot(),saved)
})
test('fresh process reads committed campaign qualifications and exact choice receipts',()=>{
 const sql='SELECT campaign_type,campaign_id,reward_type,reward_id FROM players_exchange_campaign_receipts WHERE player_id=? ORDER BY campaign_type,campaign_id'
 const expected=db.prepare(sql).all(player.id);assert.ok(expected.length>=3)
 const child=require('node:child_process').execFileSync(process.execPath,['-e',"const D=require('better-sqlite3');const d=new D(process.argv[1],{readonly:true});console.log(JSON.stringify(d.prepare(process.argv[2]).all(Number(process.argv[3]))));d.close()",db.name,sql,String(player.id)],{cwd:path.resolve(__dirname,'..'),encoding:'utf8'})
 assert.deepEqual(JSON.parse(child),expected)
})
test('V1 preserves target special rights, V2 restores exact imported rights and failed replacement rolls back',()=>{
 special(11,2);const original=entitlements.getSpecialExchangeEntitlementsSync(player.id)
 const merged=require('../out/data/utils/player-data').getMergedPlayerDataSync(player.id);players.replacePlayerDataSync(merged)
 assert.deepEqual(entitlements.getSpecialExchangeEntitlementsSync(player.id),original)
 const archive=saves.createPlayerSaveSnapshotV2Sync(player.id,db);assert.ok(archive.data.tables.players_special_exchange_campaigns.rows.length)
 saves.restorePlayerSaveSnapshotV2Sync(archive,second.id,{},db)
 assert.deepEqual(entitlements.getSpecialExchangeEntitlementsSync(second.id),original)
 const before=snapshot();db.exec(`CREATE TRIGGER fail_special_restore BEFORE INSERT ON players_special_exchange_campaigns WHEN NEW.player_id=${player.id} BEGIN SELECT RAISE(ABORT,'special restore failure'); END`)
 try{assert.throws(()=>saves.restorePlayerSaveSnapshotV2Sync(archive,player.id,{},db),/special restore failure/);assert.deepEqual(snapshot(),before)}finally{db.exec('DROP TRIGGER fail_special_restore')}
})
test('precisely recognized pre-special V2 imports preserve target rights and player deletion cascades',()=>{
 const archive=saves.createPlayerSaveSnapshotV2Sync(player.id,db),before=entitlements.getSpecialExchangeEntitlementsSync(player.id)
 delete archive.data.tables.players_special_exchange_campaigns;delete archive.data.tables.players_exchange_campaign_receipts;delete archive.data.tables.players_shop_quotas
 const tables=saves.PLAYER_SNAPSHOT_V2_TABLES.filter(table=>!['players_special_exchange_campaigns','players_exchange_campaign_receipts','players_shop_quotas'].includes(table))
 const schema=tables.map(table=>({table,columns:(require('../out/lib/storage-layout').getStorageSnapshotTableInfo(db,table)||db.prepare(`PRAGMA table_info("${table}")`).all()).map(c=>({name:c.name,type:c.type,notnull:c.notnull,defaultValue:c.dflt_value,pk:c.pk}))}))
 archive.schemaFingerprint=crypto.createHash('sha256').update(JSON.stringify(schema)).digest('hex');archive.summary.includedTableCount=tables.length;archive.summary.rowCount=Object.values(archive.data.tables).reduce((n,t)=>n+t.rows.length,0)
 saves.restorePlayerSaveSnapshotV2Sync(archive,player.id,{},db);assert.deepEqual(entitlements.getSpecialExchangeEntitlementsSync(player.id),before)
 players.deletePlayerSync(second.id);assert.deepEqual(entitlements.getSpecialExchangeEntitlementsSync(second.id),[]);assert.deepEqual(db.pragma('foreign_key_check'),[])
})
