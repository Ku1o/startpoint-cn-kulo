const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const isolated = fs.mkdtempSync(path.join(os.tmpdir(), 'epuration-gacha-'));
process.env.DATA_DIR = isolated;
process.env.GACHA_SEED_DIR = path.join(isolated, 'seeds');
fs.mkdirSync(process.env.GACHA_SEED_DIR);
const assets = require('../out/lib/assets');
const rules = require('../out/lib/gacha-rules');
const {selectWeightedIndexByRoll} = require('../out/lib/gacha');

test('歼灭者两池按准确权重参与普通及保底抽取，镜像一致且其他Boss保持禁兑', () => {
    const base = require('../assets/gacha.json');
    for (const [gid, weight, percent, extension] of [
        [990001, 1000, 0.1, require('../assets/gacha_cnmod.json')],
        [990002, 10000, 1, require('../assets/gacha_rank_p5b.json')],
    ]) {
        const g = assets.getGachaSync(gid);
        assert.deepEqual(g, base[gid]); assert.deepEqual(g, extension[gid]);
        const rows = g.pool['1'], index = rows.findIndex(x => x.id === 179981);
        const row = rows[index], weights = rows.map(x => x.odds);
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
        assert.equal(rules.getGachaPoolItem(g,id).odds,0);
        assert.equal(rules.getExchangeableGachaItem(g,id),null);
    }
});

test('两池实际兑换接口各扣250点，积分不足和女帝歼灭者仍拒绝', async t => {
    const app = require('fastify')({logger:false});
    const {getDb} = require('../out/data/db');
    const {insertAccountSync} = require('../out/data/domains/account');
    const {insertDefaultPlayerSync} = require('../out/data/domains/player');
    const {saveAccountDefaultPlayer} = require('../out/data/activeAccount');
    const {insertSessionWithToken} = require('../out/data/domains/session');
    const {insertPlayerGachaInfoSync,getPlayerGachaInfoSync,updatePlayerGachaInfoSync} = require('../out/data/domains/gacha');
    const {getPlayerCharacterSync} = require('../out/data/domains/character');
    app.addHook('onSend',(_req,reply,payload,done)=>done(null,
        String(reply.getHeader('content-type')||'').startsWith('application/x-msgpack') && typeof payload==='object'
            ? JSON.stringify(payload):payload));
    await app.register(require('../out/routes/api/gacha').default,{prefix:'/gacha'});
    t.after(async()=>{await app.close();getDb().close();});
    for (const gid of [990001,990002]) {
        const account = insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'leiting',idpId:'',status:'normal'});
        const player = insertDefaultPlayerSync(account.id);
        saveAccountDefaultPlayer(account.id,player.id);
        const viewer = 77390000+gid;
        await insertSessionWithToken({token:String(viewer),accountId:account.id,expires:new Date(Date.now()+86400000),type:2});
        insertPlayerGachaInfoSync(player.id,{gachaId:gid,isAccountFirst:false,isDailyFirst:false,gachaExchangePoint:249});
        const exchange = id=>app.inject({method:'POST',url:'/gacha/exchange_character',
            payload:{viewer_id:viewer,gacha_id:gid,character_id:id,api_count:1}});
        const before = getPlayerCharacterSync(player.id,179981);
        assert.equal((await exchange(179981)).statusCode,400);
        assert.equal(getPlayerGachaInfoSync(player.id,gid).gachaExchangePoint,249);
        assert.deepEqual(getPlayerCharacterSync(player.id,179981),before);
        updatePlayerGachaInfoSync(player.id,{gachaId:gid,gachaExchangePoint:250});
        assert.equal((await exchange(179985)).statusCode,400);
        assert.equal(getPlayerGachaInfoSync(player.id,gid).gachaExchangePoint,250);
        const response = await exchange(179981);
        assert.equal(response.statusCode,200,response.payload);
        assert.equal(getPlayerGachaInfoSync(player.id,gid).gachaExchangePoint,0);
        assert.ok(getPlayerCharacterSync(player.id,179981));
        assert.equal(response.json().data.gacha_info_list[0].gacha_exchange_point,0);
    }
    // Keep this small isolated database for audit; never read or alter real saves.
    console.log('Isolated database:',isolated);
});

test('Android和iOS从.107获取.108两个分包，四条直读资源与分包摘要一致', async () => {
    const report = require('../assets/asset-patch/audit/epuration-gacha-1.4.108/report.json');
    const manifest = require('../assets/asset-patch/manifest.json');
    const patch = manifest.patches.find(x=>x.enabled && x.version==='1.4.108');
    const handlers = new Map();
    await require('../out/routes/cn/asset').default({post:(name,handler)=>handlers.set(name,handler)});
    for (const device of ['android','ios']) {
        let body;
        const reply = {type(){return this},status(code){assert.equal(code,200);return this},send(x){body=x;return this}};
        await handlers.get('/get_path')({headers:{host:'127.0.0.1:8001',device,res_ver:'1.4.107'}},reply);
        assert.equal(body.data.info.target_asset_version,'1.4.108');
        assert.deepEqual(body.data.diff[0].archive.map(x=>path.posix.basename(x.location)),patch.chain);
        assert.ok(patch.chain.includes(report.archive.name));
    }
    const app = require('fastify')({logger:false});
    require('../out/lib/custom-cdn-resource-routes').installCustomCdnResourceRoutes(app,{
        patchRoot:path.resolve(__dirname,'../assets/asset-patch'),cdnRoot:path.resolve(__dirname,'../.cdn')});
    try {
        for (const row of Object.values(report.resources)) {
            const result = await app.inject({method:'GET',url:'/patch/cn/dummy/download/'+row.member});
            assert.equal(result.statusCode,200);
            assert.equal(require('node:crypto').createHash('sha256').update(result.rawPayload).digest('hex'),row.sha256);
        }
    } finally {await app.close();}
});
