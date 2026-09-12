const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'abyss-records-'))
process.env.DATA_DIR = temp
const version = require('../out/lib/version')
const revA = 'a'.repeat(64), revB = 'b'.repeat(64)
let revision = revA
version.getPatchManifest = () => ({ patches: [
    { type: 'patch', enabled: true, version: '1.4.104', quest_time_revisions: {'rush:700099': revA} },
    { type: 'patch', enabled: true, version: '1.4.106', quest_time_revisions: {'rush:700099': revision} },
] })
const {getDb} = require('../out/data/db'), db = getDb()
const { recordAbyssFloorFinishSync: record, getAbyssFloorRecordSync: read } = require('../out/data/domains/abyss-records')
const finish = require('../out/routes/api/singleBattleQuest')
const { getPlayerSingleQuestProgressSync } = require('../out/data/domains/quest')
const { pack, unpack } = require('msgpackr')
const Fastify = require('fastify')
const account = require('../out/data/domains/account'), player = require('../out/data/domains/player')
const valid = overrides => ({category:24,questId:700099001,revision:revA,viewerId:123456,
    elapsedTimeMs:60000,startedAtMs:1000,nowMs:120000,accomplished:true,registered:true,matchingPlay:true,isMulti:false,...overrides})
test.after(() => { db.close(); assert.ok(path.resolve(temp).startsWith(path.resolve(os.tmpdir())+path.sep)); fs.rmSync(temp,{recursive:true,force:true}) })

test('atomic minimum, equal ties, version isolation and invalid finishes', () => {
    assert.equal(record(valid()), true)
    for (const elapsedTimeMs of [70000,60000]) assert.equal(record(valid({elapsedTimeMs,viewerId:654321})),false)
    assert.equal(record(valid({elapsedTimeMs:45000,viewerId:654321})),true)
    assert.equal(read(revA,700099001),45000)
    const before = db.prepare('SELECT * FROM abyss_floor_records').all()
    for (const changes of [{elapsedTimeMs:0},{elapsedTimeMs:-1},{elapsedTimeMs:NaN},{elapsedTimeMs:1.5},
        {elapsedTimeMs:Infinity},{elapsedTimeMs:130000},{registered:false},{matchingPlay:false},
        {accomplished:false},{isMulti:true},{revision:revB},{revision:null},{startedAtMs:undefined},
        {startedAtMs:130000},{category:2},{questId:700099099},{viewerId:0}])
        assert.equal(record(valid(changes)),false,JSON.stringify(changes))
    assert.deepEqual(db.prepare('SELECT * FROM abyss_floor_records').all(),before)
    revision=revB
    assert.equal(read(revB,700099001),null)
    assert.equal(record(valid({revision:revB,elapsedTimeMs:90000})),true)
    assert.equal(read(revA,700099001),45000)
    assert.equal(read(revB,700099001),90000)
    revision=revA
})

test('read endpoint excludes stale clients, endless, absent floors and private identifiers', async () => {
    const app=Fastify(); await app.register(require('../out/routes/cn/abyssRecords').default)
    try {
        const response=await app.inject('/abyss-records/700099001?res_ver=1.4.106')
        assert.equal(response.statusCode,200); assert.equal(response.json().best_time_ms,45000)
        assert.deepEqual(Object.keys(response.json()).sort(),['status','quest_id','revision','best_time_ms','holder_name'].sort())
        assert.equal(response.json().holder_name,null)
        assert.equal((await app.inject('/abyss-records/700099002?res_ver=1.4.106')).json().best_time_ms,null)
        for (const id of [700099099,700099098,700098001,'700099001junk'])
            assert.equal((await app.inject(`/abyss-records/${id}?res_ver=1.4.106`)).statusCode,404)
        revision=revB
        assert.equal((await app.inject('/abyss-records/700099001?res_ver=1.4.104')).json().status,'update_required')
        assert.equal((await app.inject('/abyss-records/700099001')).json().status,'update_required')
        assert.equal((await app.inject('/abyss-records/700099001?res_ver=1.4.106')).json().best_time_ms,90000)
    } finally { revision=revA; await app.close() }
})

test('holder nickname follows the winning public profile; ties, renames and missing accounts', async () => {
    const a=account.insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'record-name',idpId:'',status:'normal'})
    const p=player.insertDefaultPlayerSync(a.id), viewer=830000000+p.id
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),a.id,'2000-01-01T00:00:00.000Z')
    db.prepare('UPDATE players SET name=? WHERE id=?').run('星海<勇者>&',p.id)
    assert.equal(record(valid({questId:700099002,viewerId:viewer,elapsedTimeMs:40000})),true)
    const app=Fastify(); await app.register(require('../out/routes/cn/abyssRecords').default)
    const get=async()=> (await app.inject('/abyss-records/700099002?res_ver=1.4.106')).json()
    try {
        let result=await get()
        assert.equal(result.holder_name,'星海<勇者>&');assert.equal(result.best_time_ms,40000)
        assert.equal(record(valid({questId:700099002,viewerId:654321,elapsedTimeMs:40000})),false)
        assert.equal((await get()).holder_name,'星海<勇者>&','equal time retains original holder')
        db.prepare('UPDATE players SET name=? WHERE id=?').run('改名后的勇者',p.id)
        assert.equal((await get()).holder_name,'改名后的勇者')
        db.prepare('DELETE FROM sessions WHERE token=?').run(String(viewer))
        result=await get();assert.equal(result.holder_name,null);assert.equal(result.best_time_ms,40000)
        assert.deepEqual(Object.keys(result).sort(),['status','quest_id','revision','best_time_ms','holder_name'].sort())
        assert.equal(record(valid({questId:700099002,viewerId:654321,elapsedTimeMs:30000})),true)
        assert.equal((await get()).best_time_ms,30000)
    } finally { await app.close() }
})

test('real finish updates global only for registered success; personal records stay separate', async () => {
    db.prepare('DELETE FROM abyss_floor_records').run()
    const app=Fastify()
    app.addHook('onSend',(_req,reply,payload,done)=>done(null,reply.getHeader('content-type')==='application/x-msgpack'?pack(payload).toString('base64'):payload))
    await app.register(finish.default,{prefix:'/single_battle_quest'})
    const create = () => {
        const a=account.insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'test',idpId:'',status:'normal'})
        const p=player.insertDefaultPlayerSync(a.id),viewer=820000000+p.id
        db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),a.id,'2099-01-01T00:00:00.000Z')
        return {id:p.id,viewer}
    }
    const p=create(),q=create();let n=0
    async function settle(p,time,{start=true,success=true,persisted=false}={}) {
        const id='abyss-record-'+(++n)
        if(start) finish.insertActiveQuest(p.id,{category:24,questId:700099001,playId:id,isMulti:false,
            useBoostPoint:false,useBossBoostPoint:false,isAutoStartMode:false,continueCount:0,startedAtMs:Date.now()-180000})
        if(persisted)delete finish.activeQuests[p.id]
        const response=await app.inject({method:'POST',url:'/single_battle_quest/finish',headers:{res_ver:'1.4.106'},payload:{
            viewer_id:p.viewer,category:24,quest_id:700099001,play_id:id,continue_count:0,
            elapsed_time_ms:time,score:12345,add_mana:0,is_accomplished:success,is_restored:false,api_count:n,
            statistics:{clear_phase:1,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],
                equipments:[null,null,null],ability_soul_ids:[null,null,null]},zones:[]}}})
        assert.equal(response.statusCode,200,response.body)
        assert.equal(unpack(Buffer.from(response.body,'base64')).data_headers.result_code,1)
    }
    try {
        await settle(p,60000)
        await settle(q,45000,{persisted:true})
        assert.equal(read(revA,700099001),45000)
        assert.equal(getPlayerSingleQuestProgressSync(p.id,24,700099001).bestElapsedTimeMs,60000)
        await settle(p,70000)
        assert.equal(read(revA,700099001),45000)
        await settle(p,1000,{success:false})
        await settle(p,500,{start:false})
        assert.equal(read(revA,700099001),45000,'recovered no-start finish cannot seed global record')
        revision=revB
        assert.equal(getPlayerSingleQuestProgressSync(p.id,24,700099001).bestElapsedTimeMs,null)
        assert.equal(read(revB,700099001),null)
        await settle(p,90000)
        assert.equal(read(revB,700099001),90000)
    } finally { revision=revA; await app.close() }
})

test('record lookup uses its primary key; 10000 reads do not scan players', () => {
    const plan=db.prepare('EXPLAIN QUERY PLAN SELECT elapsed_time_ms FROM abyss_floor_records WHERE revision=? AND quest_id=?').all(revA,700099001)
    assert.ok(plan.some(row=>/SEARCH.*PRIMARY KEY/i.test(row.detail)),JSON.stringify(plan))
    const start=performance.now();for(let i=0;i<10000;i++)read(revA,700099001)
    console.log(`10000 indexed record reads: ${(performance.now()-start).toFixed(1)} ms`)
})
