'use strict'
const {test,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'july-pass-facts-'))
process.env.DATA_DIR=directory;process.env.GACHA_SEED_DIR=path.join(directory,'seeds')
process.env.CN_WRITER_THREAD='0';process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false'
const db=require('../out/data/db').getDb()
const players=require('../out/data/domains/player'),missions=require('../out/data/domains/mission')
const operations=require('../out/lib/content-operations'),facts=require('../out/lib/mission/pass-battle-facts')
const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'pass-july',idpId:'fixture',status:'normal'})
const playerId=players.insertDefaultPlayerSync(account.id).id
function gate(enabled) {
    const store=operations.contentOperations()
    store.update('pass_card_event:14',{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'isolated pass regression',
        actionOverrides:{enter:{enabled,readiness:'verified',evidence:'actual July mission definitions and accepted finish facts',endsAtMs:null,
            missionKeys:['7:55','8:81','8:85']}}},Date.now())
}
const value=(category,id)=>missions.getPlayerCategoryMissionsSync(playerId,category)[String(id)]?.progress??0
const context={playerId,questAccomplished:true,isMulti:true,questCategory:8,questId:200080001,
    statistics:{zones:[{send_emotion_count:3}],party:{characters:[],unison_characters:[]}}}
after(async()=>{await require('../out/lib/seed-validator').default.close();if(db.open)db.close();fs.rmSync(directory,{recursive:true})})

test('July pass selected co-op ranges count actual advent and boss categories only while enabled',()=>{
    gate(true)
    assert.ok(facts.recordPassMissionBattleFacts(context,new Date()).includes(81))
    assert.equal(value(8,81),1)
    const boss={...context,questCategory:2,questId:1001001}
    assert.ok(facts.recordPassMissionBattleFacts(boss,new Date()).includes(85))
    assert.equal(value(8,85),1)
    facts.recordPassMissionBattleFacts({...context,isMulti:false},new Date())
    facts.recordPassMissionBattleFacts({...context,questId:200081001},new Date())
    assert.equal(value(8,81),1,'single-player and another event do not qualify')
    gate(false)
    facts.recordPassMissionBattleFacts(context,new Date())
    facts.recordPassMissionBattleFacts(boss,new Date())
    assert.equal(value(8,81),1);assert.equal(value(8,85),1)
})

test('weekly emotion facts preserve old progress and include accepted failure statistics without opening closed tasks',()=>{
    gate(true)
    missions.incrementPlayerCategoryMissionSync(playerId,7,55,17)
    facts.recordPassWeeklyEmotionFacts({...context,questAccomplished:false},new Date())
    assert.equal(value(7,55),20)
    gate(false)
    facts.recordPassWeeklyEmotionFacts(context,new Date())
    assert.equal(value(7,55),20,'closed participation does not accumulate new facts')
    gate(true)
    facts.recordPassWeeklyEmotionFacts({...context,statistics:{send_emotion_count:-3}},new Date())
    assert.equal(value(7,55),20,'invalid negative client statistics cannot reduce progress')
    assert.throws(()=>db.transaction(()=>{
        facts.recordPassWeeklyEmotionFacts(context,new Date())
        throw Error('rollback')
    })(),/rollback/)
    assert.equal(value(7,55),20,'finish transaction rollback includes periodic pass facts')
})
