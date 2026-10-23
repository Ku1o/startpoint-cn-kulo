'use strict'
// Full application, synthetic-only, loopback benchmark. No production defaults.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict')
const {fork,spawnSync}=require('node:child_process'),{performance,monitorEventLoopDelay}=require('node:perf_hooks')
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,s)=>{if(v.startsWith('--'))a.push([v.slice(2),s[i+1]||true]);return a},[]))
const repo=path.resolve(__dirname,'..'), engine=path.resolve(args.engine||repo), root=path.resolve(args.root||'')
const load=n=>require(path.join(engine,'out',n)), json=(p,v)=>fs.writeFileSync(p,JSON.stringify(v,null,2)+'\n')
const digest=v=>require('node:crypto').createHash('sha256').update(JSON.stringify(v)).digest('hex')
const percentile=(v,p)=>v.length?[...v].sort((a,b)=>a-b)[Math.min(v.length-1,Math.ceil(v.length*p)-1)]:0
const summary=v=>({count:v.length,p50:percentile(v,.5),p95:percentile(v,.95),p99:percentile(v,.99),max:Math.max(0,...v)})
function assertExternalFixtureRoot(directory){
 let ancestor=path.resolve(directory),missing=[]
 while(!fs.existsSync(ancestor)){missing.unshift(path.basename(ancestor));ancestor=path.dirname(ancestor)}
 const physical=path.join(fs.realpathSync(ancestor),...missing)
 const registered=spawnSync('git',['worktree','list','--porcelain'],{cwd:repo,encoding:'utf8',windowsHide:true});assert.equal(registered.status,0)
 for(const match of registered.stdout.matchAll(/^worktree (.+)$/gm)){const rel=path.relative(fs.realpathSync(match[1].trim()),physical);assert.ok(rel==='..'||rel.startsWith('..'+path.sep)||path.isAbsolute(rel),'Fixture must be outside every registered worktree')}
 return physical
}
function assertSealedWalEmpty(file){const wal=file+'-wal';assert.ok(!fs.existsSync(wal)||fs.statSync(wal).size===0,'Immutable extraction requires a sealed snapshot with absent or empty WAL; nonempty WAL would be ignored')}
function readSealedOperations(file){
 file=fs.realpathSync(file);assertSealedWalEmpty(file)
 const script='import sqlite3,json,pathlib,sys\np=pathlib.Path(sys.argv[1]).resolve()\nc=sqlite3.connect(p.as_uri()+"?mode=ro&immutable=1",uri=True)\nc.row_factory=sqlite3.Row\nprint(json.dumps({t:[dict(r) for r in c.execute("SELECT * FROM "+t)] for t in ["content_operations_state","content_operations_meta"]}))\nc.close()'
 const extracted=spawnSync('python',['-c',script,file],{encoding:'utf8',windowsHide:true,maxBuffer:64*1024*1024});assert.equal(extracted.status,0,extracted.stderr);return JSON.parse(extracted.stdout)
}
if(args.server) server().catch(e=>{console.error(e);process.exit(1)})
else if(require.main===module) main().catch(e=>{console.error(e);process.exitCode=1})
async function server(){
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'operations.json')))
 load('data').initializeDatabase();const db=load('data/db').getDb()
 assert.equal(fs.realpathSync(path.dirname(db.name)),fs.realpathSync(path.join(root,'data')))
 db.transaction(()=>{for(const table of ['content_operations_state','content_operations_meta']){
  const rows=fixture[table];db.prepare('DELETE FROM '+table).run()
  if(rows.length){const keys=Object.keys(rows[0]),st=db.prepare('INSERT INTO '+table+' ('+keys.join(',')+') VALUES('+keys.map(()=>'?').join(',')+')');for(const row of rows)st.run(...keys.map(k=>row[k]))}
 }})();assert.equal(db.prepare('SELECT count(*) n FROM content_operations_state').get().n,9599)
 const players=load('data/domains/player'),accounts=load('data/domains/account'),identities=[]
 for(let i=0;i<4;i++){
  const a=accounts.insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'synthetic-mixed-performance',idpId:'benchmark-'+i,status:'normal'})
  const p=players.insertDefaultPlayerSync(a.id),viewer=888000000+p.id
  load('data/activeAccount').saveAccountDefaultPlayer(a.id,p.id)
  db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),a.id,'2099-01-01T00:00:00Z')
  players.updatePlayerSync({id:p.id,freeVmoney:100000,vmoney:5000,stamina:10000,staminaHealTime:new Date()})
  load('data/domains/pass-card').addPlayerPassCardPointSync(p.id,15,10000)
  db.prepare('UPDATE players_pass_cards SET is_buy=1 WHERE player_id=? AND event_id=15').run(p.id)
  identities.push({id:p.id,viewer})
 }
 const guard={kind:'approved-offline-file',databasePath:fs.realpathSync(db.name),allowedRoot:root},clockOptions={cutoverRealMs:Date.now(),legacyOffsetMs:load('utils').getLegacyTimeOffset()||0,offlineGuard:guard}
 const clockPlan=load('lib/time-cutover-rehearsal').planTimeCutoverRehearsalSync(db,clockOptions)
 load('lib/server-clock-state').activateRealServerClockOfflineSync(db,{...clockOptions,expectedPlanDigest:clockPlan.digest,readiness:'scenario-only'})
 const app=load('cn-server').fastify;await app.ready()
 // Full normal lifecycle owns HTTP, realtime owner and configured workers.
 await new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{if(app.server.listening){clearInterval(t);resolve()}else if(++n>600){clearInterval(t);reject(Error('listener timeout'))}},50)})
 const snapshot=()=>({players:db.prepare('SELECT * FROM players ORDER BY id').all(),items:db.prepare('SELECT * FROM players_items ORDER BY player_id,id').all(),characters:db.prepare('SELECT * FROM players_characters ORDER BY player_id,id').all(),equipment:db.prepare('SELECT * FROM players_equipment ORDER BY player_id,id').all(),questProgress:db.prepare('SELECT * FROM players_quest_progress ORDER BY player_id,section,quest_id').all(),activeQuests:db.prepare('SELECT * FROM players_active_quests ORDER BY player_id').all(),pass:db.prepare('SELECT * FROM players_pass_card_rewards ORDER BY player_id,reward_id').all(),gacha:db.prepare('SELECT * FROM players_gacha_info ORDER BY player_id').all(),receipts:db.prepare('SELECT * FROM player_operation_receipts ORDER BY player_id,operation,request_key').all()})
 const delay=monitorEventLoopDelay({resolution:10});delay.enable();let peakRss=0,peakHeap=0,startCpu=process.cpuUsage(),start=performance.now()
 const sample=setInterval(()=>{const m=process.memoryUsage();peakRss=Math.max(peakRss,m.rss);peakHeap=Math.max(peakHeap,m.heapUsed)},25)
 process.on('message',m=>{
  if(m.type==='measure-start'){delay.reset();startCpu=process.cpuUsage();start=performance.now();peakRss=0;peakHeap=0;process.send({type:'measure-started',requestId:m.requestId})}
  if(m.type==='probe')process.send({type:'probe',state:snapshot(),requestId:m.requestId})
  if(m.type==='measure-end'){const cpu=process.cpuUsage(startCpu);process.send({type:'metrics',requestId:m.requestId,metrics:{wallMs:performance.now()-start,cpuUserMs:cpu.user/1000,cpuSystemMs:cpu.system/1000,peakRss,peakHeap,eventLoop:{p50:delay.percentile(50)/1e6,p95:delay.percentile(95)/1e6,p99:delay.percentile(99)/1e6,max:delay.max/1e6}},state:snapshot()})}
 })
 process.send({type:'ready',port:app.server.address().port,identities,controls:9599})
 app.server.once('close',()=>{clearInterval(sample);delay.disable()})
}
async function main(){
 assert.ok([undefined,'baseline','candidate'].includes(args['admin-profile']),'Unknown frontend admin profile');
 assert.ok(args.root&&args.engine&&(args.sealed||args.operations),'--root --engine and --sealed or --operations required');assertExternalFixtureRoot(root);fs.mkdirSync(root,{recursive:true})
 assert.ok(root.toLowerCase().includes('player-priority-performance-20261022'))
 const operations=args.operations?JSON.parse(fs.readFileSync(path.resolve(args.operations),'utf8')):readSealedOperations(args.sealed)
 assert.equal(operations.content_operations_state.length,9599)
 const runs=[]
 for(let repeat=0;repeat<Number(args.repeats||2);repeat++)for(const withAdmin of repeat%2?[true,false]:[false,true])runs.push(await runOne(repeat,withAdmin,operations))
 json(path.join(root,'results.json'),{engine,adminProfile:args['admin-profile']||'content',benchmarkScriptSha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(__filename)).digest('hex'),fixtureDigest:digest(operations),hardware:{cpu:require('node:os').cpus()[0].model,logicalCpuCount:require('node:os').cpus().length,availableParallelism:require('node:os').availableParallelism(),totalMemory:require('node:os').totalmem()},runs,limitations:'Synthetic accounts, localhost HTTP, four logical CPUs on local hardware; receive-history and battle-receipt periodic maintenance disabled only for benchmark isolation. No public network/device, actual realtime battle traffic or simultaneous maintenance-peak acceptance.'})
 console.log(JSON.stringify(runs.map(r=>({name:r.name,player:r.player,admin:r.admin,metrics:r.metrics,correct:r.correct})),null,2))
}
async function runOne(repeat,withAdmin,operations){
 const name=`r${repeat}-${withAdmin?'admin':'player-only'}`,dir=path.join(root,name);fs.mkdirSync(dir,{recursive:true})
 for(const d of ['data','tmp','seeds','logs','config'])fs.mkdirSync(path.join(dir,d),{recursive:true})
 fs.symlinkSync(path.join(repo,'assets'),path.join(dir,'assets'),'junction');json(path.join(dir,'operations.json'),operations)
 json(path.join(dir,'config/client-admission.json'),{enforce:false,builds:[],updateMessage:'Synthetic benchmark only'});json(path.join(dir,'config/client-admission.keys.json'),{})
 json(path.join(dir,'config/news.json'),{version:1,popup:{enabled:false,news_id:null,mode:'once_per_news',start_time:null,end_time:null},news:[]})
 const env=Object.fromEntries(Object.entries(process.env).filter(([k])=>/^(PATH|SYSTEMROOT|WINDIR|COMSPEC|PATHEXT|SYSTEMDRIVE|NUMBER_OF_PROCESSORS|PROCESSOR_ARCHITECTURE)$/i.test(k)))
 Object.assign(env,{STARPOINT_ISOLATED_RUNTIME_ROOT:dir,DATA_DIR:path.join(dir,'data'),TMP:path.join(dir,'tmp'),TEMP:path.join(dir,'tmp'),SQLITE_TMPDIR:path.join(dir,'tmp'),GACHA_SEED_DIR:path.join(dir,'seeds'),CN_LOG_DIR:path.join(dir,'logs'),NEWS_CONFIG_PATH:path.join(dir,'config/news.json'),CLIENT_ADMISSION_CONFIG:path.join(dir,'config/client-admission.json'),CLIENT_ADMISSION_KEYS:path.join(dir,'config/client-admission.keys.json'),CN_RUNTIME_IMPORT_ONLY:'0',CN_LISTEN_HOST:'127.0.0.1',CN_LISTEN_PORT:'0',SESSION_HOST:'127.0.0.1',SESSION_PORT:'0',MULTI_REALTIME_PROCESS:'1',CN_MULTICORE:'0',CN_RESPONSE_WORKERS:'0',CN_WRITER_THREAD:'0',SQLITE_PERSISTENCE_WORKER:'1',SQLITE_CHECKPOINT_WORKER:'1',GAME_ROUTINE_LOGS:'off',GAME_VERBOSE_LOGS:'false',ADMIN_PANEL_PASSWORD:'synthetic-benchmark-only',CDN_DIR:path.join(repo,'.cdn'),GRACEFUL_SHUTDOWN_TIMEOUT_MS:'10000'})
 Object.assign(env,{RECEIVE_HISTORY_RETENTION_ENABLED:'0',BATTLE_RECEIPT_RETENTION_ENABLED:'0'})
 json(path.join(dir,'launch-env.json'),env)
 const child=fork(__filename,['--server','1','--engine',engine,'--root',dir],{cwd:dir,env,windowsHide:true,execArgv:['--require',path.join(repo,'tools/isolated-runtime-fs-guard.cjs')],stdio:['ignore','pipe','pipe','ipc']})
 let logs='';child.stdout.on('data',b=>{logs+=b});child.stderr.on('data',b=>{logs+=b})
 let requestId=0
 const receive=(type,id)=>new Promise((resolve,reject)=>{const t=setTimeout(()=>{cleanup();reject(Error(type+' timeout '+logs.slice(-4000)))},60000);function cleanup(){clearTimeout(t);child.off('message',f);child.off('exit',exited)}function f(m){if(m.type===type&&m.requestId===id){cleanup();resolve(m)}}function exited(){cleanup();reject(Error('child exit awaiting '+type+' '+logs.slice(-6000)))}child.on('message',f);child.once('exit',exited)})
 const command=async(type,result)=>{const id=++requestId,p=receive(result,id);child.send({type,requestId:id});return p}
 try{
 const ready=await receive('ready'),base='http://127.0.0.1:'+ready.port
 const samples=[],adminSamples=[],records=[],perRoute={},timeouts=[],statuses={}
 async function request(route,payload,cookie,measure=true){const t=performance.now();let res,text
 try{res=await fetch(base+route,{method:payload?'POST':'GET',headers:{...(payload?{'content-type':'application/json'}:{}),...(cookie?{cookie}:{})},body:payload?JSON.stringify(payload):undefined,signal:AbortSignal.timeout(15000)});text=await res.text()}catch(e){timeouts.push({route,message:e.message});throw e}
 const elapsed=performance.now()-t;statuses[res.status]=(statuses[res.status]||0)+1;assert.equal(res.status,200,route+' '+text.slice(0,800))
 if(measure){const list=cookie?adminSamples:samples;list.push(elapsed);(perRoute[route]??=[]).push(elapsed)}
 return {res,text,elapsed}}
 const login=await request('/admin-login',{password:env.ADMIN_PANEL_PASSWORD},null,false),cookie=login.res.headers.get('set-cookie').split(';')[0]
 const unpack=require(path.join(repo,'node_modules/msgpackr')).unpack
 const post=async(p,url,body={},measure=true)=>{const r=await request('/api/index.php/'+url,{viewer_id:p.viewer,...body},null,measure);const value=unpack(Buffer.from(r.text,'base64'));assert.equal(value.data_headers.result_code,1,url+' '+JSON.stringify(value.data_headers));return value}
 const stats={clear_phase:1,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],equipments:[null,null,null],ability_soul_ids:[null,null,null]},zones:[]}
 async function sequence(p,round,measure){
 await post(p,'load',{},measure);await post(p,'content_operations',{},measure)
 const before=await command('probe','probe')
 await post(p,'gacha/exec',{gacha_id:1704,payment_type:1,type:1,number_of_exec:1,api_count:round+1},measure)
 const after=await command('probe','probe'),a=before.state.players.find(x=>x.id===p.id),b=after.state.players.find(x=>x.id===p.id)
 assert.equal(a.free_vmoney+a.vmoney-b.free_vmoney-b.vmoney,150,'draw charges exactly 150')
 const claim={pass_card_id:15,all_receive:[841+round]};await post(p,'Pass_card/receive_all',claim,measure)
 const owned=s=>Object.fromEntries(Object.entries(s).map(([k,v])=>[k,v.filter(row=>(k==='players'?row.id:row.player_id)===p.id)]))
 const once=await command('probe','probe');await post(p,'Pass_card/receive_all',claim,measure);const twice=await command('probe','probe');assert.deepEqual(owned(twice.state),owned(once.state),'claim replay does not pay twice')
 const body={category:2,quest_id:1001001,party_id:1,play_id:`synthetic-${p.id}-${round}`,use_boost_point:false,use_boss_boost_point:false,is_auto_start_mode:false,api_count:round+1}
 await post(p,'single_battle_quest/start',body,measure)
 const finish={...body,continue_count:0,elapsed_time_ms:1000,score:12345,add_mana:0,is_accomplished:true,is_restored:false,statistics:stats}
 await post(p,'single_battle_quest/finish',finish,measure);const first=await command('probe','probe');await post(p,'single_battle_quest/finish',finish,measure);const replay=await command('probe','probe');assert.deepEqual(owned(replay.state),owned(first.state),'finish replay does not pay twice')
 }
 for(const p of ready.identities)await sequence(p,0,false)
 // Verify complete unfiltered metadata and 1020 actual parent records.
 const listing=await request('/api/content/?limit=30',null,cookie,false),catalog=JSON.parse(listing.text)
 assert.equal(catalog.total,1020);for(const field of ['rows','typeOptions','statusCounts','groups','searchInfo','permanentReference'])assert.ok(field in catalog,field)
 assert.equal(catalog.searchInfo.verificationNotice,undefined,'Complete discovery source identity must validate; degraded fixtures cannot stand in for the original runtime')
 const detail=JSON.parse((await request('/api/content/'+encodeURIComponent(catalog.rows[0].key)+'/discovery',null,cookie,false)).text)
 assert.ok(detail.characters.length+detail.rewards.length>0,'Actual discovery detail must retain nonempty verified associations')
 const routes=['/api/content/?limit=30','/api/content/?limit=30&offset=30','/api/content/?limit=30&search='+encodeURIComponent('活动'),'/api/content/?limit=30&view=series','/api/content/?limit=30&status=enabled','/api/content/'+encodeURIComponent(catalog.rows[0].key)+'/discovery']
 const businessBefore=await command('probe','probe');json(path.join(dir,'business-before.json'),businessBefore.state)
 await command('measure-start','measure-started');const start=performance.now()
 const frontendProfile=args['admin-profile'],candidate=frontendProfile==='candidate',firstPlayer=ready.identities[0].id
 // Identical nine-page visit actions per cycle, using each UI's actual query contract.
 // Static catalog/lookups are read only on the first visit, matching query-cache behavior.
 const frontendVisits=[
  ['/api/server/status','/api/server/defaultSave',candidate?'/api/server/accounts/summary':'/api/server/accounts'],
  [candidate?'/api/server/accounts/page?page=1&pageSize=20':'/api/server/accounts'],
  [candidate?'/api/server/accounts/targets':'/api/server/accounts','/api/mail/daily'],
  ['/api/news/'],
  candidate?['/api/seeds/group/fes/overview','/api/seeds/group/fes/list?kind=verified&page=1&pageSize=100','/api/seeds/group/fes/list?kind=play&page=1&pageSize=100']
   :['/api/seeds/stats?movieId=fes','/api/seeds/stats?movieId=fes_guarantee','/api/seeds/list?movieId=fes','/api/seeds/list?movieId=fes_guarantee'],
  candidate?['/api/server/clairvoyance/gacha?view=current','/api/server/clairvoyance/gacha?view=catalog']:['/api/server/clairvoyance/gacha'],
  [candidate?'/api/leaderboards/?summary=1':'/api/leaderboards/','/api/leaderboards/'+encodeURIComponent('rush:700099:1')],
  candidate?['/api/player/'+firstPlayer+'/detail?section=player','/api/player/'+firstPlayer+'/detail?section=characters','/api/lookup/characters']
   :['/api/player/'+firstPlayer+'/detail','/api/lookup/characters','/api/lookup/items','/api/lookup/equipment','/api/lookup/quests'],
  [routes[0],routes[5]],
 ]
 const admin=withAdmin?(async()=>{
  if(frontendProfile){
   for(let visit=0;visit<2;visit++)for(let page=0;page<frontendVisits.length;page++)for(const route of frontendVisits[page]){
    if(visit>0&&(route.startsWith('/api/lookup/')||route.endsWith('view=catalog')))continue
    const r=await request(route,null,cookie);records.push({visit,page,route,elapsed:r.elapsed,bytes:Buffer.byteLength(r.text)})
   }
  }else for(let i=0;i<24;i++){const r=await request(routes[i%routes.length],null,cookie);records.push({route:routes[i%routes.length],elapsed:r.elapsed,bytes:r.text.length});if(i<routes.length)fs.writeFileSync(path.join(dir,'admin-response-'+i+'.json'),r.text)}
 })():Promise.resolve()
 const player=(async()=>{for(let r=1;r<=4;r++)await Promise.all(ready.identities.map(p=>sequence(p,r,true)))})()
 await Promise.all([admin,player]);const elapsed=performance.now()-start,metrics=await command('measure-end','metrics')
 for(const p of ready.identities){assert.equal(metrics.state.gacha.find(row=>row.player_id===p.id&&row.gacha_id===1704).gacha_exchange_point,5)
  assert.equal(metrics.state.pass.filter(row=>row.player_id===p.id&&row.event_id===15&&row.is_received_1===1&&row.is_received_2===1).length,5)
  assert.equal(metrics.state.receipts.filter(row=>row.player_id===p.id&&row.operation==='quest_finish.single').length,5)}
 const result={name,withAdmin,adminProfile:frontendProfile||'content',adminPageVisits:withAdmin&&frontendProfile?18:0,repeat,elapsed,player:summary(samples),admin:summary(adminSamples),perRoute:Object.fromEntries(Object.entries(perRoute).map(([k,v])=>[k,summary(v)])),timeouts,httpStatuses:statuses,canceled:0,metrics:metrics.metrics,correct:true,adminRequests:records,finalBusinessDigest:digest(metrics.state),identities:ready.identities,controls:ready.controls,parentCount:catalog.total}
 json(path.join(dir,'business-after.json'),metrics.state);json(path.join(dir,'result.json'),result);return result
 }finally{json(path.join(dir,'server-log.json'),{logs});if(child.connected)child.send({type:'starpoint:shutdown'});await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill();resolve()},20000);child.once('exit',()=>{clearTimeout(timer);resolve()})})}
}
module.exports={summary,assertExternalFixtureRoot,assertSealedWalEmpty,readSealedOperations}
