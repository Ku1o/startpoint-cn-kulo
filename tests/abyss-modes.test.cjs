const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'abyss-modes-'))
process.env.DATA_DIR = temp
const version = require('../out/lib/version')
const originalManifest = version.getPatchManifest
const A = 'a'.repeat(64), B = 'b'.repeat(64), C = 'c'.repeat(64)
let patches = []
version.getPatchManifest = () => ({ patches })
const revisions = require('../out/lib/abyss-time-revision')
const progress = require('../out/data/domains/abyss-tower-progress')
const rush = require('../out/data/domains/rushEvent')
const { getDb } = require('../out/data/db')
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const { refreshPlayerAbyssBestTimesSync } = require('../out/data/domains/abyss-time-revision')
const availability = require('../out/lib/leaderboard/availability')
const db = getDb()
test.after(() => { version.getPatchManifest = originalManifest; db.close(); fs.rmSync(temp, { recursive: true, force: true }) })
const edge = (v, normal, ex, reset = true) => ({ id: v, version: v, enabled: true, type: 'patch',
    quest_time_revisions: { 'rush:700099': normal, 'rush:700100': ex },
    ...(reset ? { rush_tower_resets: { 'rush:700099': normal, 'rush:700100': ex } } : {}) })
function player() {
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'test', idpId: '', status: 'normal' })
    const p = insertDefaultPlayerSync(account.id)
    for (const event of [700099, 700100, 700098]) {
        rush.insertPlayerRushEventSync(p.id, rush.getDefaultPlayerRushEventSync(event))
    }
    return p.id
}
function party(playerId, event, round, type = 0) {
    db.prepare('INSERT INTO players_rush_events_played_parties (player_id,event_id,round,battle_type) VALUES (?,?,?,?)')
        .run(playerId, event, type === 0 ? event * 1000 + round : round, type)
}
test('winning reward accessors preserve the original EX economy and normal 0.7 ticket rate', () => {
    const assets=require('../out/lib/assets')
    const baseline=JSON.parse(fs.readFileSync(path.join(__dirname,'../assets/asset-patch/audit/abyss-normal-ex/reward-baseline.json'),'utf8'))
    const normal=assets.getRogueEventConfig(700099), ex=assets.getRogueEventConfig(700100)
    const allowed=new Set([2370099,999013,999014,10002,12001,99,52,55,58,61,64,67])
    for (const row of normal.per_round_drops) assert.ok(allowed.has(row.id),`unexpected normal reward ${row.id}`)
    for (const row of normal.folder_clear_random) for (const id of row.pool) assert.ok(allowed.has(id))
    for (const id of [999013,999014]) {
        const before=baseline.config.per_round_drops.filter(row=>row.id===id)
        const after=normal.per_round_drops.filter(row=>row.id===id)
        assert.equal(after.length,before.length)
        before.forEach((row,index)=> {
            assert.equal(after[index].count,row.count)
            if (typeof row.chance==='number') assert.ok(Math.abs(after[index].chance-row.chance*.7)<1e-12)
            else for (const key of ['start','per_round']) assert.ok(Math.abs((after[index].chance[key]||0)-(row.chance[key]||0)*.7)<1e-12)
        })
    }
    assert.equal(ex.per_round_drops.length,baseline.config.per_round_drops.length)
    baseline.config.per_round_drops.forEach((row,index)=> {
        assert.equal(ex.per_round_drops[index].count,row.count*([2370099,999013,999014].includes(row.id)?2:1))
        assert.deepEqual(ex.per_round_drops[index].chance,row.chance)
    })
    assert.equal(normal.folder_clear_chance.find(row=>row.id===999014).chance,.07)
    assert.equal(ex.folder_clear_chance.find(row=>row.id===999014).count,2)
    assert.deepEqual(assets.getRushEventFolderClearRewards(700100,2),[])
})
const parties = (playerId, event) => db.prepare('SELECT round,battle_type FROM players_rush_events_played_parties WHERE player_id=? AND event_id=? ORDER BY round').all(playerId,event)

test('normal and EX fingerprints, stale battles, and finite ranges are independent', () => {
    patches = [edge('1.4.111', A, B)]
    assert.equal(revisions.getAbyssTimeRevision(), A)
    assert.equal(revisions.getAbyssTimeRevision(700100), B)
    assert.equal(revisions.isAbyssFiniteQuest(24, 700100030), true)
    for (const id of [700100031,700100099,700098030]) assert.equal(revisions.isAbyssFiniteQuest(24,id), false)
    assert.equal(revisions.isStaleAbyssBattle({category:24,questId:700100001,questTimeRevision:A}),true)
    assert.equal(revisions.isStaleAbyssBattle({category:24,questId:700100001,questTimeRevision:B}),false)
    patches.push(edge('1.4.112', C, B))
    assert.equal(revisions.isStaleAbyssClient(24,700100001,'1.4.111'),false)
    assert.equal(revisions.isStaleAbyssClient(24,700099001,'1.4.111'),true)
})

test('legacy towers and art-only updates cannot reset a run', () => {
    patches = [edge('1.4.110',A,B,false)]
    const id=player(); party(id,700099,1)
    assert.equal(progress.refreshPlayerAbyssTowerSync(id,700099),false)
    patches.push({ id:'art',version:'1.4.111',type:'patch',enabled:true })
    assert.equal(progress.refreshPlayerAbyssTowerSync(id,700099),false)
    assert.equal(parties(id,700099).length,1)
})

test('rotation resets once and preserves clear, reward, endless and other-mode state', () => {
    patches=[edge('1.4.111',A,B)]
    const id=player()
    for (const event of [700099,700100,700098]) party(id,event,1)
    party(id,700099,8,1)
    rush.insertPlayerRushEventClearedFolderSync(id,700099,1)
    db.prepare(`INSERT INTO players_quest_progress (player_id,section,quest_id,finished,unlocked,s_plus_reward_received)
        VALUES (?,24,700099030,1,1,1)`).run(id)
    assert.equal(progress.refreshPlayerAbyssTowerSync(id,700099),true)
    assert.deepEqual(parties(id,700099),[{round:8,battle_type:1}])
    assert.equal(parties(id,700100).length,1)
    assert.equal(parties(id,700098).length,1)
    assert.deepEqual(db.prepare('SELECT finished,s_plus_reward_received FROM players_quest_progress WHERE player_id=? AND quest_id=700099030').get(id),{finished:1,s_plus_reward_received:1})
    assert.equal(progress.hasAbyssExUnlockSync(id),true)
    party(id,700099,1)
    assert.equal(progress.refreshPlayerAbyssTowerSync(id,700099),false)
    assert.equal(parties(id,700099).length,2)
    patches.push(edge('1.4.112',C,B))
    assert.equal(progress.refreshPlayerAbyssTowerSync(id,700099),true)
    assert.equal(progress.hasAbyssExUnlockSync(id),true)
})

test('EX gate requires real historical normal clear and enforces the current finite order', () => {
    patches=[edge('1.4.111',A,B)]
    const id=player()
    assert.equal(progress.canStartAbyssQuestSync(id,24,700100001),false)
    assert.equal(progress.canStartAbyssQuestSync(id,24,700100099),false)
    rush.insertPlayerRushEventClearedFolderSync(id,700099,1)
    assert.equal(progress.canStartAbyssQuestSync(id,24,700100001),true)
    assert.equal(progress.canStartAbyssQuestSync(id,24,700100002),false)
    party(id,700100,1)
    assert.equal(progress.canStartAbyssQuestSync(id,24,700100002),true)
    assert.equal(progress.canStartAbyssQuestSync(id,24,700100030),false)
    assert.equal(progress.canStartAbyssQuestSync(id,24,700100099),true)
    assert.equal(progress.canStartAbyssQuestSync(id,24,700098009),true)
})

test('rotation marker must match the actual current tower and rejects conflicting publication', () => {
    patches=[edge('1.4.111',A,B)]
    patches.push(edge('1.4.112',C,B,false))
    assert.throws(()=>progress.getAbyssTowerResetRevision(700099),/without a matching/)
    patches=[edge('1.4.111',A,B),edge('1.4.111',C,B)]
    assert.throws(()=>progress.getAbyssTowerResetRevision(700099),/Conflicting/)
})

test('old V1 rush rows accept the new nullable marker and new rows round-trip it', () => {
    patches=[]
    const id=player()
    assert.equal(rush.getPlayerRushEventSync(id,700099).towerRevision,null)
    rush.updatePlayerRushEventSync(id,{eventId:700099,towerRevision:A})
    const row=rush.getPlayerRushEventSync(id,700099)
    const other=player()
    db.prepare('DELETE FROM players_rush_events WHERE player_id=? AND event_id=700099').run(other)
    rush.insertPlayerRushEventSync(other,JSON.parse(JSON.stringify(row)))
    assert.equal(rush.getPlayerRushEventSync(other,700099).towerRevision,A)
})

test('EX leaderboard starts disabled and can be enabled through existing administration', () => {
    assert.equal(availability.isLeaderboardEnabledSync('rush:700100:1'),false)
    availability.setLeaderboardAvailabilitySync('rush:700100:1',true)
    assert.equal(availability.isLeaderboardEnabledSync('rush:700100:1'),true)
    assert.equal(availability.isLeaderboardEnabledSync('rush:700099:1'),true)
})

test('a genuine previous-schema V2 archive restores without rewriting its fingerprint', () => {
    patches=[]
    const id=player(), target=player()
    rush.insertPlayerRushEventClearedFolderSync(id,700099,1)
    const saves=require('../out/data/snapshots/player-snapshot')
    db.exec('ALTER TABLE players_rush_events DROP COLUMN tower_revision')
    const old=saves.createPlayerSaveSnapshotV2Sync(id,db)
    const oldFingerprint=old.schemaFingerprint
    require('../out/data/initializers/abyss-tower-progress').initializeAbyssTowerProgress(db)
    assert.notEqual(saves.createPlayerSaveSnapshotV2Sync(id,db).schemaFingerprint,oldFingerprint)
    assert.equal(saves.validatePlayerSaveSnapshotV2Sync(old,db),old)
    saves.restorePlayerSaveSnapshotV2Sync(old,target,{},db)
    assert.equal(old.schemaFingerprint,oldFingerprint)
    assert.equal(rush.getPlayerRushEventSync(target,700099).towerRevision,null)
    assert.equal(progress.hasAbyssExUnlockSync(target),true)
    const invalid=structuredClone(old)
    invalid.schemaFingerprint='0'.repeat(64)
    assert.throws(()=>saves.restorePlayerSaveSnapshotV2Sync(invalid,target,{},db),/不一致/)
    assert.equal(progress.hasAbyssExUnlockSync(target),true)
})

test('real EX endless entry and finish preserve balances even with client-supplied mana', async () => {
    patches=[]
    const Fastify=require('fastify'), {pack,unpack}=require('msgpackr')
    const finish=require('../out/routes/api/singleBattleQuest')
    const getPlayer=require('../out/data/domains/player').getPlayerSync
    const assets=require('../out/lib/assets')
    const id=player(), viewerId=890000000+id
    const accountId=db.prepare('SELECT account_id FROM players WHERE id=?').get(id).account_id
    db.prepare("INSERT INTO sessions (token,account_id,expires,type) VALUES (?,?,?,2)").run(String(viewerId),accountId,'2099-01-01T00:00:00.000Z')
    const app=Fastify()
    app.addHook('onSend',(_request,reply,payload,done)=>done(null,
        reply.getHeader('content-type')==='application/x-msgpack' ? pack(payload).toString('base64') : payload))
    await app.register(require('../out/routes/api/rushEvent').default,{prefix:'/event/rush'})
    await app.register(finish.default,{prefix:'/single_battle_quest'})
    const decode=res=>{assert.equal(res.statusCode,200,res.body);return unpack(Buffer.from(res.body,'base64'))}
    try {
        const locked=decode(await app.inject({method:'POST',url:'/event/rush/endless_battle',payload:{viewer_id:viewerId,event_id:700100}}))
        assert.equal(locked.data_headers.result_code,4050)
        rush.insertPlayerRushEventClearedFolderSync(id,700099,1)
        const open=decode(await app.inject({method:'POST',url:'/event/rush/endless_battle',payload:{viewer_id:viewerId,event_id:700100}}))
        assert.equal(open.data.endless_battle_next_round,1)
        assert.deepEqual(assets.getRushEventFolderClearRewards(700100,2),[])
        const before=getPlayer(id)
        finish.insertActiveQuest(id,{category:24,questId:700100099,useBossBoostPoint:false,useBoostPoint:false,
            isAutoStartMode:false,isMulti:false,playId:'ex-endless-test',continueCount:0})
        const result=decode(await app.inject({method:'POST',url:'/single_battle_quest/finish',payload:{
            viewer_id:viewerId,category:24,quest_id:700100099,play_id:'ex-endless-test',continue_count:0,
            elapsed_time_ms:60000,score:12345,add_mana:999999,is_accomplished:true,is_restored:false,api_count:1,
            statistics:{clear_phase:1,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],
                equipments:[null,null,null],ability_soul_ids:[null,null,null]},zones:[]}
        }}))
        assert.equal(result.data_headers.result_code,1)
        const after=getPlayer(id)
        for(const key of ['rankPoint','freeMana','paidMana','expPool']) assert.equal(after[key],before[key],key)
        assert.equal(rush.getPlayerRushEventSync(id,700100).endlessBattleNextRound,2)
        assert.equal(db.prepare('SELECT count(*) n FROM players_rush_events_cleared_folders WHERE player_id=? AND event_id=700100').get(id).n,0)
        assert.equal(db.prepare('SELECT count(*) n FROM leaderboard_runs WHERE player_id=? AND competition_key=?').get(id,'rush:700100:1').n,0)
    } finally { delete finish.activeQuests[id]; await app.close() }
})
