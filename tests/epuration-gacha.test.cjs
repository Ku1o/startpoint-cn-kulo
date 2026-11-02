const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
if (process.env.STARPOINT_TEST_COMPILED !== '1') require('ts-node/register/transpile-only');
const code = process.env.STARPOINT_TEST_COMPILED === '1' ? '../out/' : '../src/';
const isolated = fs.mkdtempSync(path.join(os.tmpdir(), 'epuration-gacha-'));
process.env.DATA_DIR = isolated;
process.env.GACHA_SEED_DIR = path.join(isolated, 'seeds');
fs.mkdirSync(process.env.GACHA_SEED_DIR);
const assets = require(code + 'lib/assets');
const rules = require(code + 'lib/gacha-rules');
const {selectWeightedIndexByRoll} = require(code + 'lib/gacha');

test('歼灭者两池按准确权重参与普通及保底抽取，镜像一致且其他Boss保持禁兑', () => {
    const base = require('../assets/gacha.json');
    for (const [gid, weight, percent, extension] of [
        [990001, 1000, 0.1, require('../assets/gacha_cnmod.json')],
        [990002, 10000, 1, require('../assets/gacha_rank_p5b.json')],
    ]) {
        const g = assets.getGachaSync(gid);
        const rows = g.pool['1'], index = rows.findIndex(x => x.id === 179981);
        const row = rows[index], weights = rows.map(x => x.odds);
        assert.ok(row, 'Epuration missing from effective pool ' + gid);
        assert.deepEqual(g, base[gid]); assert.deepEqual(g, extension[gid]);
        assert.equal(row.odds, weight); assert.equal(row.isRateUp, true);
        assert.ok(rules.getExchangeableGachaItem(g, 179981));
        const total = weights.reduce((a,b)=>a+b,0);
        for (const rates of [g.rankRates.normal, g.rankRates.multiGuarantee]) {
            assert.equal(weight / total * rates[0] / rates.reduce((a,b)=>a+b,0) * 100, percent);
        }
        // Exercise both inclusive boundaries in the real weighted selector.
        const start = weights.slice(0,index).reduce((a,b)=>a+b,0)+1;
        assert.equal(selectWeightedIndexByRoll(weights,start),index);
        assert.equal(selectWeightedIndexByRoll(weights,start+weight-1),index);
        assert.notEqual(selectWeightedIndexByRoll(weights,start+weight),index);
    }
    for (const id of [179982,179983,179984,179985,179986]) {
        const g = assets.getGachaSync(990002);
        assert.equal(rules.getGachaPoolItem(g,id),null);
        assert.equal(rules.getExchangeableGachaItem(g,id),null);
    }
});

test('两池实际兑换接口各扣250点，积分不足和女帝歼灭者仍拒绝', async t => {
    const app = require('fastify')({logger:false});
    const {getDb} = require(code + 'data/db');
    const {insertAccountSync} = require(code + 'data/domains/account');
    const {insertDefaultPlayerSync} = require(code + 'data/domains/player');
    const {saveAccountDefaultPlayer} = require(code + 'data/activeAccount');
    const {insertSessionWithToken} = require(code + 'data/domains/session');
    const {insertPlayerGachaInfoSync,getPlayerGachaInfoSync,updatePlayerGachaInfoSync} = require(code + 'data/domains/gacha');
    const {getPlayerCharacterSync} = require(code + 'data/domains/character');
    const identities = require(code + 'lib/gameplay-request-identity');
    app.addHook('onSend',(_req,reply,payload,done)=>done(null,
        String(reply.getHeader('content-type')||'').startsWith('application/x-msgpack') && typeof payload==='object'
            ? JSON.stringify(payload):payload));
    await app.register(require(code + 'routes/api/gacha').default,{prefix:'/gacha'});
    t.after(async()=>{await app.close();getDb().close();});
    for (const gid of [990001,990002]) {
        const account = insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'leiting',idpId:'',status:'normal'});
        const player = insertDefaultPlayerSync(account.id);
        saveAccountDefaultPlayer(account.id,player.id);
        const viewer = 77390000+gid;
        await insertSessionWithToken({token:String(viewer),accountId:account.id,expires:new Date(Date.now()+86400000),type:2});
        insertPlayerGachaInfoSync(player.id,{gachaId:gid,isAccountFirst:false,isDailyFirst:false,gachaExchangePoint:249});
        identities.initializeGameplayRequestIdentitySchemaSync(getDb());
        const token = getDb().transaction(()=>identities.issueGameplayLoginTokenSync(getDb(),{
            accountId:account.id,viewerId:viewer,udid:'epuration-restore',expiresAt:Date.now()+86400000,
        }))();
        let apiCount = 0;
        const exchange = id=>app.inject({method:'POST',url:'/gacha/exchange_character',headers:{login_token:token},
            payload:{viewer_id:viewer,gacha_id:gid,character_id:id,api_count:++apiCount}});
        const before = getPlayerCharacterSync(player.id,179981);
        assert.equal((await exchange(179981)).statusCode,400);
        assert.equal(getPlayerGachaInfoSync(player.id,gid).gachaExchangePoint,249);
        assert.deepEqual(getPlayerCharacterSync(player.id,179981),before);
        updatePlayerGachaInfoSync(player.id,{gachaId:gid,gachaExchangePoint:507});
        assert.equal((await exchange(179985)).statusCode,400);
        assert.equal(getPlayerGachaInfoSync(player.id,gid).gachaExchangePoint,507);
        const response = await exchange(179981);
        assert.equal(response.statusCode,200,response.payload);
        assert.equal(getPlayerGachaInfoSync(player.id,gid).gachaExchangePoint,257);
        assert.ok(getPlayerCharacterSync(player.id,179981));
        assert.equal(response.json().data.gacha_info_list[0].gacha_exchange_point,257);
    }
    // Keep this small isolated database for audit; never read or alter real saves.
    console.log('Isolated database:',isolated);
});

test('Android和iOS取得新增.356分包，终态概率表与实际服务端逐行一致', async () => {
    const report = require('../assets/asset-patch/audit/epuration-gacha-1.4.356/report.json');
    const manifest = require('../assets/asset-patch/manifest.json');
    const patch = manifest.patches.find(x=>x.enabled && x.version==='1.4.356');
    const handlers = new Map();
    await require(code + 'routes/cn/asset').default({post:(name,handler)=>handlers.set(name,handler)});
    for (const device of ['android','ios']) {
        let body;
        const reply = {type(){return this},status(code){assert.equal(code,200);return this},send(x){body=x;return this}};
        await handlers.get('/get_path')({headers:{host:'127.0.0.1:8001',device,res_ver:'1.4.355'}},reply);
        assert.equal(body.data.info.target_asset_version,'1.4.356');
        assert.deepEqual(body.data.diff[0].archive.map(x=>path.posix.basename(x.location)),patch.chain);
        assert.ok(patch.chain.includes(report.archive.name));
    }
    const app = require('fastify')({logger:false});
    require(code + 'lib/custom-cdn-resource-routes').installCustomCdnResourceRoutes(app,{
        patchRoot:path.resolve(__dirname,'../assets/asset-patch'),cdnRoot:path.resolve(__dirname,'../.cdn')});
    try {
        const zlib = require('node:zlib');
        function map(raw) {
            const length=raw.readUInt32LE(0),index=zlib.inflateSync(raw.subarray(4,4+length));
            const count=index.readUInt32LE(0),keys=index.subarray(4+count*8),values=raw.subarray(4+length);
            const result=new Map();let k=0,v=0;
            for(let i=0;i<count;i++){const ke=index.readUInt32LE(4+i*8),ve=index.readUInt32LE(8+i*8);
                result.set(keys.subarray(k,ke).toString(),values.subarray(v,ve));k=ke;v=ve;}
            return result;
        }
        for (const row of report.pools) {
            const hash=require('node:crypto').createHash('sha1').update(row.logical+'K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy').digest('hex');
            const result = await app.inject({method:'GET',url:'/patch/cn/dummy/download/production/upload/'+hash.slice(0,2)+'/'+hash.slice(2)});
            assert.equal(result.statusCode,200);
            assert.equal(require('node:crypto').createHash('sha256').update(result.rawPayload).digest('hex'),row.afterSha256);
            const native=[...map([...map(result.rawPayload).values()][0]).values()].map(raw=>zlib.inflateSync(raw).toString().trimEnd());
            const expected=assets.getGachaSync(row.gachaId).pool['1'].map(x=>[x.id,x.rank,x.odds,x.isRateUp,x.isLimited,x.isExchangeable,x.trialReadingForced].join(','));
            assert.deepEqual(native,expected);
        }
    } finally {await app.close();}
});
