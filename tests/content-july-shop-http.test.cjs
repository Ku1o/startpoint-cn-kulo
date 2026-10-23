'use strict'
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process')
const task=path.resolve(process.env.CONTENT_EXACT_TASK_ROOT),root=path.resolve(__dirname,'..')
assert.ok(!task.startsWith(root+path.sep),'fixture must be outside registered source worktrees')
fs.mkdirSync(task,{recursive:true});const directory=fs.mkdtempSync(path.join(task,'shop-fixture-'))
process.env.DATA_DIR=directory;process.env.GACHA_SEED_DIR=path.join(directory,'seeds');process.env.TMP=process.env.TEMP=process.env.TMPDIR=directory
process.env.CN_WRITER_THREAD='0';process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr'),originalNow=Date.now
const now=Date.parse('2051-01-01T00:00:00Z');Date.now=()=>now
const {initializeDatabase}=require('../out/data');initializeDatabase()
const {getDb}=require('../out/data/db'),db=getDb(),ops=require('../out/lib/content-operations'),bootstrap=require('../out/lib/content-operations-bootstrap')
const items=require('../out/data/domains/item'),purchases=require('../out/data/domains/shopPurchase')
test('fixed July shop survives old calendar, spends existing coins atomically, preserves stock on closure and restart',async t=>{
 const store=ops.contentOperations();assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(task)+path.sep))
 const databasePath=fs.realpathSync(db.name)
 const applied=bootstrap.applyJulyContentPlanOfflineSync(store,{expectedRevision:0,expectedCatalogDigest:store.digest,nowMs:now,
  offlineGuard:{kind:'approved-offline-file',databasePath,allowedRoot:task}})
 assert.equal(applied.controls,bootstrap.julyContentPlan.controls.length)
 const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'exact-shop',idpId:'fixture',status:'normal'})
 const player=require('../out/data/domains/player').insertDefaultPlayerSync(account.id),viewer=883000000+player.id
 require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,player.id)
 db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00Z')
 items.setPlayerItemSync(player.id,40501,10000);items.setPlayerItemSync(player.id,49100,8);purchases.addPlayerShopPurchaseCountSync(player.id,5000,13)
 const app=Fastify({logger:false});app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
 await app.register(require('../out/routes/api/shop').default,{prefix:'/shop'})
 let closed=false;t.after(async()=>{Date.now=originalNow;if(!closed){await app.close();await require('../out/lib/seed-validator').default.close();if(db.open)db.close()}})
 const post=(url,payload)=>app.inject({method:'POST',url,payload:{viewer_id:viewer,...payload}})
 const buy=amount=>post('/shop/buy',{shop_type:4,shop_item_id:5000,number:amount,api_count:1})
 const state=()=>({coin:items.getPlayerItemSync(player.id,40501),reward:items.getPlayerItemSync(player.id,49100),purchased:purchases.getPlayerShopPurchaseCountSync(player.id,5000)})
 const control=(key,enabled)=>store.update(key,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'isolated exact shop close/reopen',actionOverrides:{exchange:{enabled,endsAtMs:null,readiness:'verified',evidence:'same exact scoped shop evidence'}}},now)
 assert.equal(store.allowed('score_attack_event:1','visible',now),true);assert.equal(store.allowed('score_attack_event:1','exchange',now),true)
 const scoreQuestScope=store.state('score_attack_event:1').actionOverrides.enter
 assert.equal(store.allowed('score_attack_event:1','enter',now),true,'July quest participation has its own reviewed control')
 assert.deepEqual(scoreQuestScope,{...bootstrap.julyContentPlan.controls.find(control=>control.key==='score_attack_event:1').actionOverrides.enter,
  catalogDigest:store.digest,contentDigest:store.contentDigests.get('score_attack_event:1')})
 for(const key of scoreQuestScope.questKeys)assert.equal(store.catalog.questMap[key],'score_attack_event:1')
 const listing=await post('/shop/get_sales_list',{shop_types:[],event_list:[{event_type:12,event_ids:[1]}],equipment_enhancement_shop_category_ids:[],boss_coin_shop_category_ids:[],browse_treasure_flag:false})
 assert.equal(listing.statusCode,200,listing.body)
 const list=unpack(Buffer.from(listing.body,'base64')).data
 assert.ok(JSON.stringify(list).includes('5000'),'actual listing retains reviewed product')
 const success=await buy(2);assert.equal(success.statusCode,200,success.body)
 assert.deepEqual(state(),{coin:9916,reward:88,purchased:15})
 const before=state();control('score_attack_event:1',false)
 assert.equal((await buy(1)).statusCode,400);assert.deepEqual(state(),before)
 assert.deepEqual(store.state('score_attack_event:1').actionOverrides.enter,scoreQuestScope,'exchange closure cannot change separately reviewed quest scope')
 control('score_attack_event:1',true);control('event_item_shop:5000',false)
 assert.equal((await buy(1)).statusCode,400);assert.deepEqual(state(),before)
 control('event_item_shop:5000',true)
 assert.equal((await buy(1)).statusCode,200);assert.deepEqual(state(),{coin:9874,reward:128,purchased:16})
 assert.equal((await buy(1.5)).statusCode,400);assert.deepEqual(state(),{coin:9874,reward:128,purchased:16})
 control('event_item_shop:5000',false)
 items.setPlayerItemSync(player.id,2370099,100)
 const buyRush=id=>post('/shop/buy',{shop_type:4,shop_item_id:id,number:1,api_count:1})
 assert.equal(store.allowed('rush_event:700099','exchange',now),true)
 const rushQuestScope=store.state('rush_event:700099').actionOverrides.enter
 assert.equal(store.allowed('rush_event:700099','enter',now),true,'custom July quest scope is separately reviewed')
 assert.deepEqual(rushQuestScope,{...bootstrap.julyContentPlan.controls.find(control=>control.key==='rush_event:700099').actionOverrides.enter,
  catalogDigest:store.digest,contentDigest:store.contentDigests.get('rush_event:700099')})
 const reviewed=await buyRush(9700117);assert.equal(reviewed.statusCode,200,reviewed.body)
 assert.equal(items.getPlayerItemSync(player.id,2370099),50)
 assert.equal(items.getPlayerItemSync(player.id,999014),1)
 const unreviewed=await buyRush(9700121);assert.equal(unreviewed.statusCode,400,unreviewed.body)
 assert.equal(items.getPlayerItemSync(player.id,2370099),50)
 assert.equal(items.getPlayerItemSync(player.id,999014),1)
 await app.close();await require('../out/lib/seed-validator').default.close();db.close();closed=true
 const script=`const path=require('node:path'),assert=require('node:assert/strict'),root=process.argv[1],id=Number(process.argv[2]);const r=p=>require(path.join(root,'out',p));r('data').initializeDatabase();const db=r('data/db').getDb(),store=r('lib/content-operations').contentOperations();assert.equal(store.allowed('event_item_shop:5000','exchange',Date.parse('2051-01-01T00:00:00Z')),false);const items=r('data/domains/item'),purchases=r('data/domains/shopPurchase');const result={coin:items.getPlayerItemSync(id,40501),reward:items.getPlayerItemSync(id,49100),purchased:purchases.getPlayerShopPurchaseCountSync(id,5000),revision:store.revision(),closed:true};assert.deepEqual({coin:result.coin,reward:result.reward,purchased:result.purchased},{coin:9874,reward:128,purchased:16});db.close();console.log('EXACT_RESULT '+JSON.stringify(result));`
 const restarted=spawnSync(process.execPath,['-e',script,root,String(player.id)],{env:process.env,encoding:'utf8'})
 assert.equal(restarted.status,0,restarted.stdout+'\n'+restarted.stderr)
 const line=restarted.stdout.split(/\r?\n/).find(x=>x.startsWith('EXACT_RESULT ')),restart=JSON.parse(line.slice(13))
 const result={schemaVersion:1,completed:true,syntheticDatabase:databasePath,sourceDatabaseRead:false,controls:applied.controls,
  testedParent:'score_attack_event:1',testedProduct:'event_item_shop:5000',businessAt:'2051-01-01T00:00:00Z',starting:{coin:10000,reward:8,purchased:13},
  after:{coin:9874,reward:128,purchased:16},oldCoinsPaidAndRewardGranted:true,parentAndProductClosureAtomic:true,fractionalQuantityRejected:true,
  questParticipationIndependentlyReviewed:true,questScopesPreserved:true,reviewedRushProductPurchased:true,uncataloguedSiblingRejected:true,
  actualProcessRestart:restart,deviceAcceptance:false}
 fs.writeFileSync(path.join(task,'shop-http-result.json'),JSON.stringify(result,null,2)+'\n')
})
