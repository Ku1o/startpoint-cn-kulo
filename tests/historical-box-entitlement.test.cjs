const {test,before,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'historical-box-'))
process.env.DATA_DIR=directory;process.env.CN_WRITER_THREAD='0';process.env.GAME_VERBOSE_LOGS='false'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
const db=require('../out/data/db').getDb(),players=require('../out/data/domains/player')
const boxes=require('../out/data/domains/boxGacha'),ops=require('../out/lib/content-operations')
const master=require('../out/lib/assets').getBoxGachaSync(28)
const boxId=Number(Object.keys(master.boxes)[0]),rewardId=Number(Object.keys(master.boxes[boxId])[0])
let app,playerId,viewer
const post=(url,extra={})=>app.inject({method:'POST',url,payload:{viewer_id:viewer,...extra}})
const data=r=>{assert.equal(r.statusCode,200,r.body);return unpack(Buffer.from(r.body,'base64')).data}
function snapshot(){return Object.fromEntries(['players_box_gacha','players_box_gacha_drawn_rewards','players_items'].map(table=>[table,db.prepare(`SELECT * FROM ${table} WHERE player_id=? ORDER BY rowid`).all(playerId)]))}
before(async()=>{
    const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'history-box',idpId:'fixture',status:'normal'})
    playerId=players.insertDefaultPlayerSync(account.id).id;viewer=870000000+playerId
    require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,playerId)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00Z')
    app=Fastify({logger:false})
    app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
    await app.register(require('../out/routes/api/boxGacha').default)
})
after(async()=>{await app.close();db.close();fs.rmSync(directory,{recursive:true})})
test('history authenticates, excludes empty and unknown masters without creating boxes',async()=>{
    assert.equal((await post('/get_retained_box_gachas',{viewer_id:0})).statusCode,400)
    assert.equal((await post('/get_retained_box_gachas',{viewer_id:999999999})).statusCode,401)
    const before=snapshot();assert.deepEqual(data(await post('/get_retained_box_gachas')).retained_box_gacha_list,[])
    assert.deepEqual(snapshot(),before)
})
test('history is reachable read-only while draw/reset/close and unverified activation remain denied',async()=>{
    boxes.insertPlayerBoxGachaSync(playerId,28,{boxId,resetTimes:2,remainingNumber:0,isClosed:false})
    boxes.insertPlayerBoxGachaDrawnRewardSync(playerId,28,boxId,{id:rewardId,number:1})
    const before=snapshot()
    const history=data(await post('/get_retained_box_gachas')).retained_box_gacha_list
    assert.equal(history.length,1);assert.equal(history[0].box_gacha_id,28);assert.equal(history[0].participation_enabled,false)
    assert.equal(history[0].all_box_info.find(row=>row.box_id===boxId).reset_times,2)
    data(await post('/get_box_list',{box_gacha_id:28}))
    for(const [url,extra] of [['/exec',{number:1}],['/reset',{}],['/close',{}]]) {
        assert.equal((await post(url,{box_gacha_id:28,box_id:boxId,...extra})).statusCode,400)
    }
    assert.deepEqual(snapshot(),before)
    const store=ops.contentOperations()
    assert.ok(store.capabilities(store.rows.get('box_gacha:28')).includes('enter'), 'reviewed box rules are supported; saved history alone is not authorization')
    const revision=store.revision(),control=store.state('box_gacha:28')
    assert.throws(()=>store.update('box_gacha:28',{expectedRevision:revision,catalogDigest:store.digest,reason:'Unreviewed box actions cannot authorize mutation',
        actionOverrides:{visible:{enabled:true,endsAtMs:null,readiness:'unverified',evidence:'Incomplete box fixture'},enter:{enabled:true,endsAtMs:null,readiness:'unverified',evidence:'Incomplete box fixture'}}},Date.now()),/未验证.*动作禁止开启/)
    assert.equal(store.revision(),revision)
    assert.deepEqual(store.state('box_gacha:28'),control)
    assert.equal(data(await post('/get_retained_box_gachas')).retained_box_gacha_list[0].participation_enabled,false)
    assert.deepEqual(snapshot(),before)
})
