'use strict';
const compiled=process.env.STARPOINT_TEST_COMPILED==='1';
if(!compiled)require('ts-node/register/transpile-only');
const load=name=>require('../'+(compiled?'out':'src')+'/'+name);
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'halloween-gacha-'));
process.env.DATA_DIR=path.join(directory,'database');process.env.GACHA_SEED_DIR=path.join(directory,'seeds');
process.env.CN_WRITER_THREAD='0';process.env.GAME_VERBOSE_LOGS='false';process.env.GAME_ROUTINE_LOGS='off';fs.mkdirSync(process.env.GACHA_SEED_DIR);
const {pack,unpack}=require('msgpackr'),db=load('data/db').getDb();
const players=load('data/domains/player'),items=load('data/domains/item'),gachaState=load('data/domains/gacha');
const assets=load('lib/assets'),draws=load('lib/gacha'),snapshots=load('data/snapshots/player-snapshot');
const operations=load('lib/content-operations'),coordinator=load('lib/persistence-coordinator');
const identities=load('lib/gameplay-request-identity');
const {defaultContentDecision}=load('lib/content-operations-defaults'),transaction=coordinator.runPersistenceTransaction;
const TICKET=999023,GID=990005,KEY=`gacha:${GID}`,FEATURED=[169977,169985,159985,139985];
const app=require('fastify')({logger:false});app.addHook('onSend',(_req,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body));
const open={readiness:'verified',evidence:'isolated HTTP economy/save fixture; no game or device acceptance',flags:{visible:true,enter:true,exchange:true},endsAtMs:null};
function control(input){const s=operations.contentOperations();return s.update(KEY,{expectedRevision:s.revision(),catalogDigest:s.digest,reason:'isolated Halloween fixture',...input},Date.now());}
function state(id){return snapshots.createPlayerSaveSnapshotV2Sync(id,db).data.tables;}
function points(id,value,gid=GID){if(gachaState.getPlayerGachaInfoSync(id,gid))gachaState.updatePlayerGachaInfoSync(id,{gachaId:gid,gachaExchangePoint:value});else gachaState.insertPlayerGachaInfoSync(id,{gachaId:gid,isDailyFirst:true,isAccountFirst:true,gachaExchangePoint:value});}
let serial=0;
async function player(free=100000,paid=100000){const a=load('data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'halloween-fixture',idpId:`halloween-${++serial}`,status:'normal'});const p=players.insertDefaultPlayerSync(a.id);players.updatePlayerSync({id:p.id,freeVmoney:free,vmoney:paid});load('data/activeAccount').saveAccountDefaultPlayer(a.id,p.id);const viewer=870000000+p.id;await load('data/domains/session').insertSessionWithToken({token:String(viewer),accountId:a.id,expires:new Date('2099-01-01'),type:2});const token=db.transaction(()=>identities.issueGameplayLoginTokenSync(db,{accountId:a.id,viewerId:viewer,udid:`halloween-${viewer}`,expiresAt:Date.now()+86400000}))();return{id:p.id,viewer,account:a.id,token,apiCount:0};}
const exec=(p,payment=3,type=4,count=1)=>app.inject({method:'POST',url:'/gacha/exec',headers:{login_token:p.token},payload:{viewer_id:p.viewer,api_count:++p.apiCount,gacha_id:GID,payment_type:payment,type,number_of_exec:count}});
const exchange=(p,id,requestId)=>app.inject({method:'POST',url:'/gacha/exchange_character',headers:{login_token:p.token},payload:{viewer_id:p.viewer,api_count:++p.apiCount,gacha_id:GID,character_id:id,...(requestId?{request_id:requestId}:{})}});
function data(r){assert.equal(r.statusCode,200,r.body);return unpack(Buffer.from(r.body,'base64')).data;}
before(async()=>{identities.initializeGameplayRequestIdentitySchemaSync(db);assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(process.env.DATA_DIR));await app.register(require('@fastify/multipart'));await app.register(load('routes/api/gacha').default,{prefix:'/gacha'});await app.register(load('routes/web_api/player').default,{prefix:'/player'});await app.ready();});
after(async()=>{coordinator.runPersistenceTransaction=transaction;await app.close();await load('lib/seed-validator').default.close();if(db.open)db.close();assert.equal(path.dirname(fs.realpathSync(directory)),fs.realpathSync(os.tmpdir()));fs.rmSync(directory,{recursive:true});});

test('ticket-only pool preserves reference odds and excludes unrelated limited/exchange entries',()=>{
    const g=assets.getGachaSync(GID),reference=assets.getGachaSync(1552),merged=load('lib/content-master').serverGachas;
    assert.strictEqual(g,merged[GID]);assert.deepEqual(g,require('../assets/gacha_halloween_2026.json')[GID]);
    for(const field of ['type','paymentType','singleCost','multiCost','discountCost'])assert.deepEqual(g[field],reference[field],field);
    assert.equal(g.pageKind,4);assert.equal(g.tenTicketItemId,TICKET);assert.equal(Object.hasOwn(g,'onceTicketItemId'),false);assert.equal(g.wildcardTicketAvailable,false);
    assert.ok(load('lib/content-master').serverItemIds.includes(TICKET));assert.equal(require('../assets/item_lookup_cnmod.json')[TICKET],'万圣惊奇扭蛋券');
    assert.deepEqual(g.rankRates,{normal:[50,250,700],multiGuarantee:[50,950]});assert.equal(g.canBeStartDashExchange,false);
    assert.deepEqual(Object.values(g.pool).flat().filter(x=>x.isExchangeable).map(x=>x.id),FEATURED);
    assert.equal(g.pool['1'].reduce((n,x)=>n+x.odds,0),100);
    for(const id of FEATURED){const row=g.pool['1'].find(x=>x.id===id);assert.equal(row.odds,10);assert.equal(row.isLimited,true);assert.equal(row.isRateUp,true);}
    for(const rank of ['1','2','3']){
        const weighted=x=>({id:x.id,rank:x.rank,odds:x.odds});
        assert.deepEqual(g.pool[rank].filter(x=>!FEATURED.includes(x.id)).map(weighted),reference.pool[rank].filter(x=>!x.isLimited&&!x.isRateUp).map(weighted));
        const total=g.pool[rank].reduce((n,x)=>n+x.odds,0);
        for(const item of g.pool[rank])assert.ok(Math.abs(item.rarity-item.odds/total*1000)<1e-9,'display weights are renormalized after donor UP removal');
    }
    assert.equal(Object.values(g.pool).flat().some(x=>x.id===149985),false);
});
test('all one-thousand rarity rolls and all five-star weight rolls match exact probabilities',()=>{
    const g=assets.getGachaSync(GID),original=crypto.randomInt,normal={3:0,4:0,5:0},guaranteed={3:0,4:0,5:0},counts=new Map();
    try{for(let roll=1;roll<=1000;roll++){let call=0;crypto.randomInt=()=>call++%2===0?roll:1;const values=draws.drawGachaWithMetadataSync(g,10);normal[values[0].rank]++;guaranteed[values[9].rank]++;}
        for(let roll=1;roll<=100;roll++){let call=0;crypto.randomInt=()=>call++%2===0?1:roll;const [x]=draws.drawGachaWithMetadataSync(g,1);counts.set(x.id,(counts.get(x.id)||0)+1);}
    }finally{crypto.randomInt=original;}
    assert.deepEqual(normal,{3:700,4:250,5:50});assert.deepEqual(guaranteed,{3:0,4:950,5:50});
    for(const id of FEATURED)assert.equal(counts.get(id),10);assert.equal([...counts].filter(([id])=>!FEATURED.includes(id)).reduce((n,[,v])=>n+v,0),60);
});
test('uncontrolled new pool rejects both draw and preloaded-point exchange without touching progress',async()=>{
    const store=operations.contentOperations(),row=store.rows.get(KEY);assert.ok(row);assert.equal(row.uncontrolledExchangeAllowed,false);
    assert.equal(defaultContentDecision(row,'visible'),false);assert.equal(defaultContentDecision(row,'enter'),false);assert.equal(defaultContentDecision(row,'exchange'),false);
    assert.equal(defaultContentDecision({...row,uncontrolledExchangeAllowed:undefined},'exchange'),true,'legacy rows retain accrued exchange rights');
    assert.equal(store.state(KEY),null);const p=await player();items.setPlayerItemSync(p.id,TICKET,1);points(p.id,250);const before=state(p.id);
    assert.equal((await exec(p)).statusCode,400);assert.equal((await exchange(p,FEATURED[0])).statusCode,400);assert.deepEqual(state(p.id),before);
    control(open);assert.equal(store.allowed(KEY,'enter',Date.now()),true);assert.equal(store.allowed(KEY,'exchange',Date.now()),true);
});
test('one Halloween ticket grants ten draws, a four-star guarantee and ten points without spending beads',async()=>{
    control(open);const p=await player(4000,200),oldPoints=777;points(p.id,oldPoints,990003);
    for(const[id,count]of[[TICKET,1],[999001,2],[999003,2],[999019,7]])items.setPlayerItemSync(p.id,id,count);
    const original=crypto.randomInt;let g;
    // Force the bottom normal rarity; only the tenth-slot guarantee can lift it.
    try{crypto.randomInt=(_min,max)=>max===1001?1000:1;g=data(await exec(p));}finally{crypto.randomInt=original;}
    assert.equal(g.draw.length,10);assert.equal(items.getPlayerItemSync(p.id,TICKET),0);
    const pool=Object.values(assets.getGachaSync(GID).pool).flat(),ranks=g.draw.map(x=>pool.find(row=>row.id===x.character_id)?.rank);assert.deepEqual(ranks,[3,3,3,3,3,3,3,3,3,4]);
    assert.equal(players.getPlayerSync(p.id).freeVmoney,4000);assert.equal(players.getPlayerSync(p.id).vmoney,200);
    assert.equal(gachaState.getPlayerGachaInfoSync(p.id,GID).gachaExchangePoint,10);assert.equal(gachaState.getPlayerGachaInfoSync(p.id,990003).gachaExchangePoint,oldPoints);
    assert.equal(items.getPlayerItemSync(p.id,999001),2);assert.equal(items.getPlayerItemSync(p.id,999003),2);assert.equal(items.getPlayerItemSync(p.id,999019),7);
});

test('native retry replays one Halloween debit/result after closure and rejects counter payload reuse',async()=>{
    control(open);const p=await player();items.setPlayerItemSync(p.id,TICKET,2);
    const payload={viewer_id:p.viewer,api_count:++p.apiCount,gacha_id:GID,payment_type:3,type:4,number_of_exec:1};
    const request=()=>app.inject({method:'POST',url:'/gacha/exec',headers:{login_token:p.token},payload});
    const first=data(await request());assert.equal(first.draw.length,10);assert.equal(items.getPlayerItemSync(p.id,TICKET),1);
    assert.equal(gachaState.getPlayerGachaInfoSync(p.id,GID).gachaExchangePoint,10);const settled=state(p.id);
    control({flags:{enter:false}});assert.deepEqual(data(await request()),first,'retry retains the original successful result');
    assert.deepEqual(state(p.id),settled,'retry creates no second debit, reward or points');
    const conflicting=await app.inject({method:'POST',url:'/gacha/exec',headers:{login_token:p.token},payload:{...payload,number_of_exec:2}});
    assert.equal(conflicting.statusCode,400);assert.deepEqual(state(p.id),settled);
    control(open);
});

test('missing or insufficient Halloween tickets reject without changing any player table',async()=>{
    control(open);const p=await player();let before=state(p.id);
    assert.equal((await exec(p)).statusCode,400);assert.deepEqual(state(p.id),before);
    items.setPlayerItemSync(p.id,TICKET,1);before=state(p.id);
    assert.equal((await exec(p,3,4,2)).statusCode,400);assert.deepEqual(state(p.id),before);
    items.setPlayerItemSync(p.id,TICKET,0);before=state(p.id);
    assert.equal((await exec(p)).statusCode,400);assert.deepEqual(state(p.id),before);
});

test('other tickets cannot substitute for the Halloween ten-draw ticket',async()=>{
    control(open);const p=await player();for(const id of[999001,999003,999004,999005,999013,999014,999015,999016,999019])items.setPlayerItemSync(p.id,id,10);
    const before=state(p.id);assert.equal((await exec(p)).statusCode,400);assert.deepEqual(state(p.id),before);
});

test('beads, paid daily, single, wildcard and campaign requests reject even with sufficient balances and tickets',async()=>{
    control(open);const p=await player();for(const id of[TICKET,999001,999003,999004,999005])items.setPlayerItemSync(p.id,id,10);const before=state(p.id);
    for(const[payment,type]of[[1,1],[1,2],[2,5],[3,3],[3,9],[3,10],[3,12],[3,13],[4,7],[4,8]]){const r=await exec(p,payment,type);assert.equal(r.statusCode,400,`${payment}/${type}: ${r.body}`);assert.deepEqual(state(p.id),before);}
});

test('250 earned points exchange exactly one of four; 249 points, companions and removed king remain rejected',async()=>{
    control(open);const p=await player();items.setPlayerItemSync(p.id,TICKET,25);for(let i=0;i<25;i++)assert.equal(data(await exec(p)).draw.length,10);assert.equal(gachaState.getPlayerGachaInfoSync(p.id,GID).gachaExchangePoint,250);assert.equal(items.getPlayerItemSync(p.id,TICKET),0);assert.equal(players.getPlayerSync(p.id).freeVmoney,100000);assert.equal(players.getPlayerSync(p.id).vmoney,100000);
    data(await exchange(p,FEATURED[0],'halloween-earned-250'));assert.equal(gachaState.getPlayerGachaInfoSync(p.id,GID).gachaExchangePoint,0);const settled=state(p.id);data(await exchange(p,FEATURED[0],'halloween-earned-250'));assert.deepEqual(state(p.id),settled,'same exchange request is idempotent');
    for(const id of FEATURED.slice(1)){points(p.id,250);data(await exchange(p,id));assert.equal(gachaState.getPlayerGachaInfoSync(p.id,GID).gachaExchangePoint,0);assert.ok(load('data/domains/character').getPlayerCharacterSync(p.id,id));}
    for(const[id,value]of[[FEATURED[0],249],[149985,250],[assets.getGachaSync(GID).pool['1'].find(x=>!x.isRateUp).id,250]]){points(p.id,value);const before=state(p.id);assert.equal((await exchange(p,id)).statusCode,400);assert.deepEqual(state(p.id),before);}
});
test('closure at final write rejects a queued draw and exchange; failure rolls back every player table',async()=>{
    const p=await player();items.setPlayerItemSync(p.id,TICKET,1);control(open);let before=state(p.id),queued=false;
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{if(context.domain==='gacha'&&context.operation==='draw'){queued=true;control({flags:{enter:false}});}return transaction(context,fn,options);};
    try{assert.equal((await exec(p)).statusCode,400);assert(queued);assert.deepEqual(state(p.id),before);}finally{coordinator.runPersistenceTransaction=transaction;}
    control(open);points(p.id,250);before=state(p.id);queued=false;
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{if(context.operation==='gacha_exchange_character'){queued=true;control({flags:{exchange:false}});}return transaction(context,fn,options);};
    try{assert.equal((await exchange(p,FEATURED[0])).statusCode,400);assert(queued);assert.deepEqual(state(p.id),before);}finally{coordinator.runPersistenceTransaction=transaction;}
    control(open);const mail=load('data/domains/mail'),insert=mail.insertReceiveHistorySync;before=state(p.id);try{mail.insertReceiveHistorySync=()=>{throw Error('isolated Halloween settlement rollback');};assert.equal((await exec(p)).statusCode,500);}finally{mail.insertReceiveHistorySync=insert;}assert.deepEqual(state(p.id),before);
});
test('V2 HTTP export/import and automatic backup preserve new/old pool points, tickets and destination identity',async()=>{
    control(open);const source=await player(),target=await player();points(source.id,170);points(source.id,777,990003);items.setPlayerItemSync(source.id,TICKET,5);items.setPlayerItemSync(source.id,999001,4);items.setPlayerItemSync(source.id,999019,9);data(await exec(source));
    const exported=await app.inject({url:`/player/save?id=${source.id}`});assert.equal(exported.statusCode,200);const archive=exported.json();snapshots.validatePlayerSaveSnapshotV2Sync(archive);
    points(target.id,80);points(target.id,111,990003);items.setPlayerItemSync(target.id,TICKET,2);items.setPlayerItemSync(target.id,999019,2);const before=state(target.id),s=operations.contentOperations(),ops=s.snapshot(Date.now()),boundary='halloween-save-boundary';
    const body=`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="save.json"\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(archive)}\r\n--${boundary}--\r\n`;
    const r=await app.inject({method:'POST',url:`/player/save?id=${target.id}`,headers:{accept:'application/json','content-type':`multipart/form-data; boundary=${boundary}`},payload:body});assert.equal(r.statusCode,200,r.body);
    const folder=path.basename(r.json().backup.replaceAll('\\','/')),backup=JSON.parse(fs.readFileSync(path.join(process.env.DATA_DIR,'admin-backups',folder,'player-save.json'),'utf8'));assert.deepEqual(backup.data.tables,before);
    assert.equal(gachaState.getPlayerGachaInfoSync(target.id,GID).gachaExchangePoint,180);assert.equal(gachaState.getPlayerGachaInfoSync(target.id,990003).gachaExchangePoint,777);assert.equal(items.getPlayerItemSync(target.id,TICKET),4);assert.equal(items.getPlayerItemSync(target.id,999001),4);assert.equal(items.getPlayerItemSync(target.id,999019),9);assert.equal(db.prepare('SELECT account_id FROM players WHERE id=?').get(target.id).account_id,target.account);assert.deepEqual(s.snapshot(ops.server_time_ms),ops);
    assert.equal((await app.inject({url:`/player/save?id=${target.id}`})).statusCode,200);assert.equal(db.pragma('integrity_check',{simple:true}),'ok');assert.deepEqual(db.pragma('foreign_key_check'),[]);
    // The current HTTP contract explicitly supports V2 only; the new pool
    // must not turn a rejected legacy upload into a partial import or backup.
    const beforeLegacy=state(target.id),backupRoot=path.join(process.env.DATA_DIR,'admin-backups'),backupNames=fs.readdirSync(backupRoot).sort();
    const legacy={schema:'starpoint-cn-save',version:1,playerId:source.id,data:{}};
    const legacyBody=`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="v1.json"\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(legacy)}\r\n--${boundary}--\r\n`;
    const rejected=await app.inject({method:'POST',url:`/player/save?id=${target.id}`,headers:{accept:'application/json','content-type':`multipart/form-data; boundary=${boundary}`},payload:legacyBody});
    assert.equal(rejected.statusCode,400);assert.match(rejected.json().error,/仅支持 V2 完整存档/);assert.deepEqual(state(target.id),beforeLegacy);assert.deepEqual(fs.readdirSync(backupRoot).sort(),backupNames);
});
