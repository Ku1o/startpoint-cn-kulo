const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
process.env.DATA_DIR=fs.mkdtempSync(path.join(os.tmpdir(),'abyss-repair-login-'))
process.env.GACHA_SEED_DIR=path.join(process.env.DATA_DIR,'seeds')
const version=require('../out/lib/version'),readManifest=version.getPatchManifest
const published=readManifest();let manifest=published
version.getPatchManifest=()=>manifest
const progress=require('../out/data/domains/abyss-tower-progress'),timing=require('../out/lib/abyss-time-revision')
const rush=require('../out/data/domains/rushEvent'),{getDb}=require('../out/data/db')
const db=getDb(),key='rush:700100'
const latest=published.patches.filter(p=>p.enabled&&p.quest_time_revisions?.[key]).at(-1)
const prior=published.patches.filter(p=>p.enabled&&p.rush_tower_resets?.[key]).at(-1).rush_tower_resets[key]
test.after(()=>{version.getPatchManifest=readManifest;db.close()})
test('effective repair advances timing but resolves the existing EX run revision',()=>{
    manifest=published
    assert.notEqual(timing.getAbyssTimeRevision(700100),prior)
    assert.equal(progress.getAbyssTowerResetRevision(700100),prior)
    assert.equal(latest.rush_tower_preserves[key],prior)
})
test('missing, wrong, conflicting, disabled and superseded repair declarations fail closed',()=>{
    for(const mutate of [p=>delete p.rush_tower_preserves,p=>p.rush_tower_preserves[key]='a'.repeat(64),
        p=>p.rush_tower_preserves[key]='bad',p=>p.rush_tower_resets={[key]:p.quest_time_revisions[key]}]){
        manifest=structuredClone(published);mutate(manifest.patches.find(p=>p.id===latest.id))
        assert.throws(()=>progress.getAbyssTowerResetRevision(700100),/marker/)
    }
    manifest=structuredClone(published)
    manifest.patches.push({...latest,id:'conflict',rush_tower_preserves:undefined})
    assert.throws(()=>progress.getAbyssTowerResetRevision(700100),/marker/)
    manifest=structuredClone(published)
    manifest.patches.push({...latest,id:'next',version:'1.4.116',rush_tower_preserves:undefined,quest_time_revisions:{[key]:'a'.repeat(64)}})
    assert.throws(()=>progress.getAbyssTowerResetRevision(700100),/marker/)
    manifest=structuredClone(published);manifest.patches.find(p=>p.id===latest.id).enabled=false
    assert.equal(progress.getAbyssTowerResetRevision(700100),prior)
    manifest=published
})
test('real login load succeeds repeatedly and retains a run through floor 19',async()=>{
    manifest=published
    const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'test',idpId:'',status:'normal'})
    const player=require('../out/data/domains/player').insertDefaultPlayerSync(account.id)
    require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,player.id)
    const viewer='88001151'
    await require('../out/data/domains/session').insertSessionWithToken({token:viewer,accountId:account.id,expires:new Date(Date.now()+86400000),type:2})
    for(const event of [700099,700100]){
        rush.insertPlayerRushEventSync(player.id,rush.getDefaultPlayerRushEventSync(event))
        rush.updatePlayerRushEventSync(player.id,{eventId:event,towerRevision:progress.getAbyssTowerResetRevision(event)})
        for(let round=1;round<=19;round++)db.prepare('INSERT INTO players_rush_events_played_parties(player_id,event_id,round,battle_type) VALUES(?,?,?,0)').run(player.id,event,event*1000+round)
    }
    rush.insertPlayerRushEventClearedFolderSync(player.id,700099,1)
    const read=()=>db.prepare('SELECT * FROM players_rush_events_played_parties WHERE player_id=? ORDER BY event_id,round').all(player.id)
    const before=read(),normalRevision=progress.getAbyssTowerResetRevision(700099)
    const app=require('fastify')({logger:false})
    app.addHook('onSend',(_req,reply,payload,done)=>done(null,String(reply.getHeader('content-type')||'').startsWith('application/x-msgpack')&&typeof payload==='object'?JSON.stringify(payload):payload))
    // /load imports the room manager's process-lifetime maintenance interval.
    // Own and close those timers in this isolated route fixture.
    const intervals=[],originalInterval=global.setInterval
    let routes
    try {
        global.setInterval=(...args)=>{const timer=originalInterval(...args);intervals.push(timer);return timer}
        routes=require('../out/routes/cn/load').default
    } finally {global.setInterval=originalInterval}
    await app.register(routes)
    try{
        for(let i=0;i<2;i++){
            const r=await app.inject({method:'POST',url:'/load',payload:{viewer_id:viewer},headers:{device:'android',res_ver:'1.4.115'}})
            assert.equal(r.statusCode,200,r.payload);assert.equal(JSON.parse(r.payload).data_headers.result_code,1)
            assert.deepEqual(read(),before)
        }
        assert.equal(progress.getAbyssTowerResetRevision(700099),normalRevision)
        assert.equal(progress.canStartAbyssQuestSync(player.id,24,700100020),true)
        assert.equal(progress.canStartAbyssQuestSync(player.id,24,700100001),false)
        assert.equal(progress.hasAbyssExUnlockSync(player.id),true)
        assert.equal(timing.isStaleAbyssClient(24,700100020,'1.4.114'),true)
        assert.equal(timing.isStaleAbyssClient(24,700100020,'1.4.115'),false)
    }finally{await app.close();for(const timer of intervals)clearInterval(timer)}
})
