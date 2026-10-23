'use strict'
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript')
const filename=path.resolve(__dirname,'../src/lib/content-entitlement-evidence.ts'),compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}})
const instance=new Module(filename,module);instance._compile(compiled.outputText,filename)
const {evaluateContentActionClosure:assess}=instance.exports
const identity={catalogDigest:'a'.repeat(64),manifestSha256:'b'.repeat(64),definitionSha256:'c'.repeat(64),contentDigest:'d'.repeat(64),exactScope:'event_item_shop:9700201',action:'exchange'}
const proof={key:'event_item_shop:9700201',status:'verified',...identity,resourceSha256:['e'.repeat(64)],sourceSha256:['f'.repeat(64)],condition:'safe quantity, costs and lifetime shared stock under final write transaction',issues:[],missingRefs:[]}
test('offline closure always retains enablement/player/memory unknown even with exact CAS and scope',()=>{
 const result=assess(proof,identity);assert.equal(result.status,'verified');assert.equal(result.mayEnable,false);assert.equal(result.currentPlayerEntitlementVerified,false)
})
test('parent or sibling action proof and changed definitions cannot inherit exact scoped closure',()=>{
 for(const delta of [{exactScope:'advent_event:300098'},{action:'enter'},{definitionSha256:'0'.repeat(64)},{contentDigest:'0'.repeat(64)},{missingRefs:['durable:monthly count']}])
  assert.equal(assess({...proof,...delta},identity).status,'unknown')
 assert.equal(assess({...proof,status:'unsupported',missingRefs:['durable:daily rule']},identity).status,'unsupported')
})
test('fresh report binds every product and exact quest scope and preserves phase4 claims',{skip:!process.env.CONTENT_ACTION_TASK_ROOT},()=>{
 const task=process.env.CONTENT_ACTION_TASK_ROOT
 if(!task)return
 const report=JSON.parse(fs.readFileSync(path.join(task,'action-closure.json'),'utf8'))
 assert.equal(report.counts.products,report.products.length);assert.equal(report.products.length,2669);assert.equal(report.candidateParents.length,44)
 assert.equal(report.preservedPhase4Closure.exchangeVerified,20);assert.equal(report.preservedPhase4Closure.passRewards,60)
 assert.equal(report.phase4Pass15.rewards.length*2,120)
 for(const row of report.products){assert.equal(row.mayEnable,false);assert.match(row.definitionCAS.contentDigest,/^[a-f0-9]{64}$/);if(row.status==='verified'){assert.equal(row.ruleVerified,true);assert.deepEqual(row.missingRefs,[]);assert.deepEqual(row.issues,[])}}
 assert.equal(report.runtimeMemoryClockVerified,false);assert.equal(report.currentPlayerEntitlementVerified,false)
 assert.equal(report.candidateActions.filter(x=>x.status==='verified').length,2)
})
test('actual shop route family payments, stock denial, shared stock and policy failures are atomic', {skip:!process.env.CONTENT_ACTION_COMPILED_ROOT},async t=>{
 const task=path.resolve(process.env.CONTENT_ACTION_TASK_ROOT),root=path.resolve(process.env.CONTENT_ACTION_COMPILED_ROOT)
 assert.ok(root.startsWith(task+path.sep) || root===path.resolve(__dirname,'../out'),'runtime must be task-specific or this isolated worktree build')
 const directory=fs.mkdtempSync(path.join(task,'action-fixture-'));process.env.DATA_DIR=directory;process.env.GACHA_SEED_DIR=path.join(directory,'seeds');process.env.TMP=directory;process.env.TEMP=directory;process.env.TMPDIR=directory;process.env.CN_WRITER_THREAD='0';process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false'
 const read=relative=>require(path.join(root,relative)),db=read('data/db').getDb();assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory)+path.sep))
 const Fastify=require('fastify'),{pack}=require('msgpackr'),app=Fastify({logger:false});app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
 t.after(async()=>{await app.close();await read('lib/seed-validator').default.close();if(db.open)db.close()})
 const account=read('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'offline-action-proof',idpId:'fixture',status:'normal'})
 const player=read('data/domains/player').insertDefaultPlayerSync(account.id);read('data/activeAccount').saveAccountDefaultPlayer(account.id,player.id)
 const viewer=879000000+player.id;db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00Z')
 await app.register(read('routes/api/shop').default,{prefix:'/shop'})
 const report=JSON.parse(fs.readFileSync(path.join(task,'action-closure.json'),'utf8')),assets=read('lib/assets'),items=read('data/domains/item'),players=read('data/domains/player'),purchases=read('data/domains/shopPurchase')
 const operations=read('lib/content-operations'),store=operations.contentOperations()
 for(const row of report.products)assert.equal(store.contentDigests.get(row.key),row.definitionCAS.contentDigest,row.key+' definition CAS equals authoritative store formula')
 let requests=0
 const buy=(shopType,id,number=1)=>{requests++;return app.inject({method:'POST',url:'/shop/buy',payload:{viewer_id:viewer,shop_type:shopType,shop_item_id:id,number,api_count:1}})}
 const state=()=>({player:players.getPlayerSync(player.id),items:db.prepare('SELECT * FROM players_items WHERE player_id=? ORDER BY id').all(player.id),equipment:db.prepare('SELECT * FROM players_equipment WHERE player_id=? ORDER BY id').all(player.id),counts:db.prepare('SELECT * FROM players_shop_purchases WHERE player_id=? ORDER BY shop_item_id').all(player.id)})
 const putCurrency=()=>{const value=players.getPlayerSync(player.id);players.updatePlayerSync({...value,freeMana:10000000,paidMana:100,freeVmoney:10000000,vmoney:100,bondToken:100000})}
 const cases=[[8,100001],[9,170000],[7,990099001],[4,9700201]]
 const results=[]
 for(const [shopType,id] of cases){
  const row=report.products.find(x=>x.key.endsWith(':'+id)&&({8:'general_shop',9:'star_grain_shop',7:'boss_coin_shop',4:'event_item_shop'}[shopType])===x.key.split(':')[0]);assert.equal(row.status,'verified')
  const definition=assets.getShopItemSync(shopType,id);assert.deepEqual(definition,row.server);putCurrency()
  for(const cost of definition.costs)items.setPlayerItemSync(player.id,cost.id,cost.amount*definition.stock)
  // Exact balance seeded to total stock; first accepted request consumes the whole lifetime stock.
  const result=await buy(shopType,id,definition.stock);assert.equal(result.statusCode,200,row.key+' '+result.body)
  assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id,row.purchaseLedgerKey),definition.stock)
  const snapshot=state();const retry=await buy(shopType,id,1);assert.equal(retry.statusCode,400);assert.deepEqual(state(),snapshot,'full lifetime stock denies without second payout')
  results.push({key:row.key,paidStock:definition.stock,retryRejectedWithoutWrite:true})
 }
 // Fantasy solo/multi alias has the same durable key. No second equipment payout through the sibling screen.
 const shared=state();assert.equal((await buy(4,9700301)).statusCode,400);assert.deepEqual(state(),shared)
 // A different verified item with insufficient materials must preserve all state.
 const denied=report.products.find(x=>x.status==='verified'&&x.key.startsWith('event_item_shop:')&&x.server.costs.length&&x.key!=='event_item_shop:9700201'&&x.key!=='event_item_shop:9700301')
 for(const cost of denied.server.costs)items.setPlayerItemSync(player.id,cost.id,0)
 const before=state();assert.equal((await buy(4,+denied.key.split(':')[1])).statusCode,400);assert.deepEqual(state(),before)
 assert.equal((await buy(4,+denied.key.split(':')[1],1.5)).statusCode,400);assert.deepEqual(state(),before)
 // Synthetic operations store only: product closure cannot override parent denial.
 const parent='advent_event:300098'
 store.update(parent,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'synthetic parent deny fixture',readiness:'verified',evidence:'offline route policy',flags:{visible:true,enter:false,claim:false,exchange:false},endsAtMs:null},Date.now())
 assert.equal(read('lib/content-economy-operations').shopContentDecision(4,9700202,'exchange',Date.now()),false)
 const policyBefore=state();assert.equal((await buy(4,9700202)).statusCode,400);assert.deepEqual(state(),policyBefore)
 const unsupported=operations.contentCatalog.rows.find(x=>x.key==='treasure_shop:200070');assert.deepEqual(read('lib/content-economy-operations').contentEconomyCapabilities(unsupported),[])
 const box=assets.getBoxGachaSync(28),boxrow=operations.contentCatalog.rows.find(x=>x.key==='box_gacha:28')
 assert.equal(read('lib/box-gacha-policy').getBoxOperationRules(boxrow,box.boxes),null,'actual indefinite sentinel has no valid current takeover rule map')
 assert.deepEqual(read('lib/content-economy-operations').contentEconomyCapabilities(boxrow),[])
 fs.writeFileSync(path.join(task,'content-action-business-case.json'),JSON.stringify({schemaVersion:1,completed:true,requests,syntheticDatabase:db.name,realPlayerDatabaseRead:false,compiledRoot:root,
  cases:results,definitionCASExactProducts:report.products.length,sharedStockAliasDenial:true,insufficientMaterialNoWrite:true,fractionalQuantityNoWrite:true,parentDenyNoWrite:true,unsupportedDailyCapabilitiesRejected:true,boxIndefinitePolicyRejected:true,
  replayBoundary:'shop has no durable request_id replay receipt; repeated purchase while stock remains is permitted. Only exhausted stock/shared alias retries prove no double payout in these cases.'},null,2)+'\n')
})
