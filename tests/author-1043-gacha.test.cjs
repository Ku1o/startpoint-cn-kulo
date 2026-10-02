const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const temporaryRoot = path.resolve(os.tmpdir());
const isolated = fs.mkdtempSync(path.join(temporaryRoot, 'starpoint-author1043-'));
process.env.DATA_DIR = isolated;
const Fastify = require('fastify');
const routes = require('../out/routes/api/gacha').default;
const assets = require('../out/lib/assets');
const content = require('../out/lib/content-master');
const {getExchangeableGachaItem} = require('../out/lib/gacha-rules');
const {insertAccountSync} = require('../out/data/domains/account');
const {insertDefaultPlayerSync} = require('../out/data/domains/player');
const {saveAccountDefaultPlayer} = require('../out/data/activeAccount');
const {insertSessionWithToken} = require('../out/data/domains/session');
const {insertPlayerGachaInfoSync,getPlayerGachaInfoSync,updatePlayerGachaInfoSync} = require('../out/data/domains/gacha');
const {getPlayerCharacterSync} = require('../out/data/domains/character');
const {getDb} = require('../out/data/db');
const targets = [119993,119994,119995,129993,129994,129995,129996,129998,139996,149991,149992,149993,149994,159999,169993];
const protectedIds = [119992,119991,119990,139992,139991,139990,149987,149986,159995,159994,169991,169988];

test('old MOD exchanges use the winning pool and actual reward settlement',async t=>{
    const app=Fastify({logger:false});
    app.addHook('onSend',(_request,reply,payload,done)=>done(null,
        String(reply.getHeader('content-type')||'').startsWith('application/x-msgpack')&&typeof payload==='object'
            ? JSON.stringify(payload):payload));
    await app.register(routes,{prefix:'/gacha'});
    t.after(async()=>{
        await app.close();getDb().close();
        const resolved=path.resolve(isolated);
        assert.ok(resolved.startsWith(temporaryRoot+path.sep)&&resolved!==temporaryRoot);
        fs.rmSync(resolved,{recursive:true});
    });
    const pool=assets.getGachaSync(990001);
    assert.deepEqual(pool,require('../assets/gacha.json')['990001']);
    assert.deepEqual(pool,require('../assets/gacha_cnmod.json')['990001']);
    assert.deepEqual(assets.getGachaSync(990002),require('../assets/gacha_rank_p5b.json')['990002']);
    for(const cid of targets) {
        assert.ok(getExchangeableGachaItem(pool,cid));
        assert.equal(pool.pool['1'].find(row=>row.id===cid).odds,1000);
    }
    for(const cid of protectedIds) {
        assert.equal(getExchangeableGachaItem(pool,cid),null);
        assert.equal(pool.pool['1'].find(row=>row.id===cid).odds,0);
    }
    for(const cid of [149987,129992])assert.deepEqual(content.cdnCharacterTexts[cid],require('../assets/cdndata/character_text.json')[cid]);
    const account=insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'leiting',idpId:'',status:'normal'});
    const player=insertDefaultPlayerSync(account.id);saveAccountDefaultPlayer(account.id,player.id);
    const viewer=77392443;
    await insertSessionWithToken({token:String(viewer),accountId:account.id,expires:new Date(Date.now()+86400000),type:2});
    insertPlayerGachaInfoSync(player.id,{gachaId:990001,isAccountFirst:false,isDailyFirst:false,gachaExchangePoint:500});
    const points=amount=>updatePlayerGachaInfoSync(player.id,{gachaId:990001,gachaExchangePoint:amount});
    const exchange=cid=>app.inject({method:'POST',url:'/gacha/exchange_character',payload:{viewer_id:viewer,gacha_id:990001,character_id:cid,api_count:1}});
    await t.test('all 15 previously blocked roles award a character and deduct exactly 250 points',async()=>{
        for(const cid of targets) {
            points(500);const res=await exchange(cid);
            assert.equal(res.statusCode,200,`${cid}: ${res.payload}`);
            assert.equal(getPlayerGachaInfoSync(player.id,990001).gachaExchangePoint,250);
            assert.ok(getPlayerCharacterSync(player.id,cid));
            assert.equal(res.json().data.gacha_info_list[0].gacha_exchange_point,250);
        }
    });
    await t.test('new locked roles, out-of-pool roles and insufficient points leave rewards unchanged',async()=>{
        for(const [cid,amount] of [...protectedIds.map(id=>[id,500]),[10,500],[targets[0],249]]) {
            points(amount);const before=getPlayerCharacterSync(player.id,cid);const res=await exchange(cid);
            assert.equal(res.statusCode,400,`${cid}: ${res.payload}`);
            assert.equal(getPlayerGachaInfoSync(player.id,990001).gachaExchangePoint,amount);
            assert.deepEqual(getPlayerCharacterSync(player.id,cid),before);
        }
    });
});
