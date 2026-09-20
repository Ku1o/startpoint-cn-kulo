const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-endurance-'))
process.env.DATA_DIR = temporary
process.env.GACHA_SEED_DIR = path.join(temporary, 'seeds')
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const { getDb } = require('../out/data/db')
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const { getPlayerDegreeIdsSync } = require('../out/data/domains/degree')
const tracker = require('../out/lib/abyss-endurance-degree-rewards')
const service = require('../out/lib/leaderboard/service')
const availability = require('../out/lib/leaderboard/availability')
const ranks = require('../out/data/domains/leaderboard')
const versions = require('../out/lib/version')
const { QuestCategory } = require('../out/lib/types')
const db = getDb()
const party = Object.fromEntries(['characterIds', 'unisonCharacterIds', 'equipmentIds', 'abilitySoulIds', 'evolutionImgLevels', 'unisonEvolutionImgLevels'].map(key => [key, [null,null,null]]))
function player() {
    const account = insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'test',idpId:'',status:'normal'})
    return insertDefaultPlayerSync(account.id).id
}
function quest(round, eventId = 700099, folderId = 1) {
    return {category:QuestCategory.RUSH_EVENT,eventId,folderId,round,questId:eventId*1000+round,totalRounds:30}
}
function complete(id, total, options = {}) {
    let awarded = [], sum = 0
    const each = Math.floor(total / 30)
    for(let round=1;round<=30;round++) {
        const q=quest(round, options.eventId ?? 700099)
        const startedAtMs=1_800_000_000_000+round*20_000_000
        const ms=round===30 ? total-sum : each; sum+=ms
        tracker.startAbyssEnduranceQuestSync(id,q,startedAtMs,options)
        awarded.push(...tracker.finishAbyssEnduranceQuestSync({playerId:id,quest:q,accomplished:true,clientBattleMs:ms,party,finishedAtMs:startedAtMs+ms},options))
    }
    return awarded
}
test.after(() => {
    if(db.open)db.close()
    const resolved=fs.realpathSync(temporary)
    assert.equal(path.dirname(resolved),fs.realpathSync(os.tmpdir()))
    assert.ok(path.basename(resolved).startsWith('starpoint-endurance-'))
    fs.rmSync(resolved,{recursive:true})
})
test('strict minute boundaries and cumulative awards use only summed battle time', () => {
    for(const [total,expected] of [
        [3_600_000,[]],[3_600_001,[9911101]],
        [7_200_000,[9911101]],[7_200_001,[9911101,9911102]],
        [10_800_000,[9911101,9911102]],[10_800_001,[9911101,9911102,9911103]],
    ]) {
        const id=player(); assert.deepEqual(complete(id,total),expected)
        assert.deepEqual(getPlayerDegreeIdsSync(id).filter(x=>x>=9911101&&x<=9911103),expected)
        const run=db.prepare("SELECT * FROM leaderboard_runs WHERE player_id=? AND competition_key LIKE 'achievement:%'").get(id)
        assert.equal(run.client_battle_ms,total)
        assert.ok(run.server_duration_ms>10_800_000)
    }
})
test('disabled ranking still tracks all 30 rounds without entering the public competition', () => {
    const id=player();availability.setLeaderboardAvailabilitySync('rush:700099:1',false)
    let granted=[]
    for(let round=1;round<=30;round++) {
        const q=quest(round);assert.equal(service.startLeaderboardQuestSync(id,q),null)
        granted.push(...service.finishLeaderboardQuestSync({playerId:id,quest:q,accomplished:true,clientBattleMs:360001,party}))
    }
    assert.deepEqual(granted,[9911101,9911102,9911103])
    assert.equal(db.prepare("SELECT COUNT(*) AS n FROM leaderboard_runs WHERE player_id=? AND competition_key='rush:700099:1'").get(id).n,0)
})
test('duplicate finishes and repeat complete runs never duplicate ownership or timing', () => {
    const id=player();assert.deepEqual(complete(id,10_800_001),[9911101,9911102,9911103])
    const time=db.prepare('SELECT acquired_at FROM players_degrees WHERE player_id=? AND degree_id=9911103').get(id).acquired_at
    assert.deepEqual(tracker.finishAbyssEnduranceQuestSync({playerId:id,quest:quest(30),accomplished:true,clientBattleMs:900000,party}),[])
    assert.deepEqual(complete(id,10_800_001),[])
    assert.equal(db.prepare('SELECT acquired_at FROM players_degrees WHERE player_id=? AND degree_id=9911103').get(id).acquired_at,time)
})
test('missing first round, failed finish, wrong quest and invalid durations cannot award', () => {
    const id=player()
    for(let round=2;round<=30;round++) {
        const q=quest(round);tracker.startAbyssEnduranceQuestSync(id,q)
        assert.deepEqual(tracker.finishAbyssEnduranceQuestSync({playerId:id,quest:q,accomplished:true,clientBattleMs:900000,party}),[])
    }
    const q=quest(1);tracker.startAbyssEnduranceQuestSync(id,q)
    for(const patch of [{accomplished:false},{clientBattleMs:NaN},{clientBattleMs:0},{clientBattleMs:1.5},{quest:{...q,questId:q.questId+1}}]) {
        assert.deepEqual(tracker.finishAbyssEnduranceQuestSync({playerId:id,quest:q,accomplished:true,clientBattleMs:900000,party,...patch}),[])
    }
    assert.equal(ranks.getActiveLeaderboardRunSync(id,'achievement:abyss-endurance:700099:1').roundsCleared,0)
    tracker.finishAbyssEnduranceQuestSync({playerId:id,quest:q,accomplished:true,clientBattleMs:900000,party})
    assert.equal(ranks.getActiveLeaderboardRunSync(id,'achievement:abyss-endurance:700099:1').roundsCleared,1)
})
test('reset and tower revision changes abandon the old partial run', () => {
    const id=player(),q=quest(1)
    tracker.startAbyssEnduranceQuestSync(id,q)
    service.resetLeaderboardCompetitionSync(id,q)
    assert.equal(ranks.getActiveLeaderboardRunSync(id,'achievement:abyss-endurance:700099:1'),null)
    tracker.startAbyssEnduranceQuestSync(id,q)
    const original=versions.getPatchManifest
    const manifest=JSON.parse(JSON.stringify(original()))
    manifest.patches.push({id:'test-revision',type:'patch',enabled:true,version:'999.0.0',quest_time_revisions:{'rush:700099':'b'.repeat(64)}})
    versions.getPatchManifest=()=>manifest
    try {
        assert.deepEqual(tracker.finishAbyssEnduranceQuestSync({playerId:id,quest:q,accomplished:true,clientBattleMs:900000,party}),[])
        assert.equal(ranks.getActiveLeaderboardRunSync(id,'achievement:abyss-endurance:700099:1'),null)
    } finally { versions.getPatchManifest=original }
})
test('future EX configuration supports the same achievement with separate run identity', () => {
    const configPath=path.join(temporary,'ex-config.json')
    fs.writeFileSync(configPath,JSON.stringify({schema_version:2,enabled:true,modes:[{mode:'normal',event_id:700099,folder_id:1},{mode:'ex',event_id:700199,folder_id:1}]}))
    const original=versions.getPatchManifest,manifest=JSON.parse(JSON.stringify(original()))
    manifest.patches.push({id:'test-ex',type:'patch',enabled:true,version:'999.0.0',quest_time_revisions:{'rush:700199':'a'.repeat(64)}})
    versions.getPatchManifest=()=>manifest
    try {
        const id=player(),normal=quest(1)
        tracker.startAbyssEnduranceQuestSync(id,normal,Date.now(),{configPath})
        tracker.finishAbyssEnduranceQuestSync({playerId:id,quest:normal,accomplished:true,clientBattleMs:900000,party},{configPath})
        assert.deepEqual(complete(id,10_800_001,{configPath,eventId:700199}),[9911101,9911102,9911103])
        assert.equal(ranks.getActiveLeaderboardRunSync(id,'achievement:abyss-endurance:700099:1').roundsCleared,1)
        tracker.resetAbyssEnduranceQuestSync(id,quest(1,700199),Date.now(),{configPath})
        assert.equal(ranks.getActiveLeaderboardRunSync(id,'achievement:abyss-endurance:700099:1').roundsCleared,1)
    } finally { versions.getPatchManifest=original }
})
