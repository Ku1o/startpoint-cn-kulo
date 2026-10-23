const {test,before,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path')
const root=process.env.MISSION_PASS_SAVE_TEST_ROOT||path.resolve(__dirname,'../.test-data')
fs.mkdirSync(root,{recursive:true})
const directory=fs.mkdtempSync(path.join(root,'mission-pass-save-'))
process.env.DATA_DIR=directory;process.env.CN_WRITER_THREAD='0'
const db=require('../out/data/db').getDb()
const players=require('../out/data/domains/player'),missions=require('../out/data/domains/mission')
const passes=require('../out/data/domains/pass-card'),saves=require('../out/data/snapshots/player-snapshot')
const {getMergedPlayerDataSync}=require('../out/data/utils/player-data')
let app
function subject() {
    return players.insertDefaultPlayerSync(require('../out/data/domains/account').insertAccountSync(
        {appId:'wf_cn',idpAlias:'',idpCode:'mission-pass-save',idpId:'',status:'normal'}).id)
}
function seed(p,progress=11,point=1000,bought=false,rewardId=841) {
    missions.updatePlayerCategoryMissionSync(p.id,6,53,progress)
    missions.updatePlayerCategoryMissionStageSync(p.id,6,1,53,true)
    missions.updatePlayerCategoryMissionStageSync(p.id,6,2,53,false)
    passes.addPlayerPassCardPointSync(p.id,15,point)
    db.prepare('UPDATE players_pass_cards SET is_buy=? WHERE player_id=? AND event_id=15').run(bought?1:0,p.id)
    passes.setPlayerPassCardRewardReceivedSync(p.id,15,rewardId,true,bought)
}
function state(p) {return saves.createPlayerSaveSnapshotV2Sync(p.id,db).data.tables}
function category(p) {return missions.getPlayerCategoryMissionsSync(p.id,6)}
function rights(p) {return {state:passes.getPlayerPassCardStateSync(p.id,15),records:passes.getPlayerPassCardRewardRecordsSync(p.id,15)}}
function replacement(source,target) {const merged=getMergedPlayerDataSync(source.id);merged.player.id=target.id;return merged}
function backupFiles() {
    const folder=path.join(directory,'admin-backups')
    return fs.existsSync(folder)?fs.readdirSync(folder).filter(name=>fs.existsSync(path.join(folder,name,'player-save.json'))):[]
}
function backup(name) {return JSON.parse(fs.readFileSync(path.join(directory,'admin-backups',name,'player-save.json'),'utf8'))}
async function upload(p,archive) {
    const boundary='mission-pass-save-fixture-boundary'
    return app.inject({method:'POST',url:`/save?id=${p.id}`,headers:{accept:'application/json','content-type':`multipart/form-data; boundary=${boundary}`},
        payload:Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="save.json"\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(archive)}\r\n--${boundary}--\r\n`)})
}
before(async()=>{
    app=require('fastify')({logger:false})
    await app.register(require('@fastify/multipart'))
    await app.register(require('../out/routes/web_api/player').default)
    await app.ready()
})
after(async()=>{if(app)await app.close();db.close();fs.rmSync(directory,{recursive:true})})

test('V1 supplied category missions are portable; absent pass fields preserve exact destination rights',()=>{
    const source=subject(),target=subject();seed(source);seed(target,2,777,true,842)
    const originalSource=state(source),targetRights=rights(target),accountId=players.getAccountFromPlayerIdSync(target.id).id
    players.replacePlayerDataSync(replacement(source,target))
    assert.deepEqual(category(target),category(source))
    assert.equal(category(target)['53'].progress,11)
    assert.deepEqual(category(target)['53'].stages,{'1':true,'2':false})
    assert.deepEqual(rights(target),targetRights,'no lost destination purchase, receipt or imported source premium state')
    assert.deepEqual(state(source),originalSource)
    assert.equal(players.getAccountFromPlayerIdSync(target.id).id,accountId)
})

test('old V1 lacking category progress retains it; explicit empty category map remains an explicit reset',()=>{
    const target=subject();seed(target,17,777,true)
    const before=category(target),passBefore=rights(target)
    const legacy=getMergedPlayerDataSync(target.id);delete legacy.categoryMissionList
    players.replacePlayerDataSync(legacy)
    assert.deepEqual(category(target),before);assert.deepEqual(rights(target),passBefore)
    const empty=getMergedPlayerDataSync(target.id);empty.categoryMissionList={}
    players.replacePlayerDataSync(empty)
    assert.deepEqual(category(target),{});assert.deepEqual(rights(target),passBefore)
})

test('malformed V1 progress/stages reject without mutation, and preserved-receipt failure rolls back cascades',()=>{
    const target=subject();seed(target,17,777,true)
    for(const categories of [null,{'0':{}},{'6':{'53':{progress:NaN,stages:{}}}},
        {'6':{'53':{progress:11,stages:{'1':'true'}}}}, {'06':{'53':{progress:11,stages:[]}}}]) {
        const saved=state(target),invalid=getMergedPlayerDataSync(target.id);invalid.categoryMissionList=categories
        assert.throws(()=>players.replacePlayerDataSync(invalid),/categoryMissionList/)
        assert.deepEqual(state(target),saved)
    }
    const saved=state(target)
    db.exec(`CREATE TRIGGER fail_retained_pass_receipt BEFORE INSERT ON players_pass_card_rewards
        WHEN NEW.player_id=${target.id} BEGIN SELECT RAISE(ABORT,'retained pass receipt failure'); END`)
    try {assert.throws(()=>players.replacePlayerDataSync(getMergedPlayerDataSync(target.id)),/retained pass receipt failure/)}
    finally {db.exec('DROP TRIGGER fail_retained_pass_receipt')}
    assert.deepEqual(state(target),saved)
    assert.deepEqual(db.pragma('foreign_key_check'),[])
})

test('V2 HTTP import makes an exact destination backup and imports nonempty mission/pass progress',async()=>{
    const source=subject(),target=subject();seed(source);seed(target,17,777,true,842)
    const archive=saves.createPlayerSaveSnapshotV2Sync(source.id,db),before=state(target)
    const response=await upload(target,archive)
    assert.equal(response.statusCode,200,response.body)
    const result=response.json(),name=path.basename(result.backup.replaceAll('\\','/'))
    assert.deepEqual(backup(name).data.tables,before,'automatic rollback backup captures the actual destination')
    assert.deepEqual(category(target),category(source))
    assert.deepEqual(rights(target),rights(source),'V2 has explicit portable pass state, unlike V1')
})

test('HTTP rejects V1 and invalid V2 before backup; V2 insertion failure keeps exact original data and backup',async()=>{
    const source=subject(),target=subject();seed(source);seed(target,17,777,true,842)
    const before=state(target),existing=backupFiles()
    const v1=await upload(target,{schema:'starpoint-cn-save',version:1,data:getMergedPlayerDataSync(source.id)})
    assert.equal(v1.statusCode,400);assert.match(v1.body,/仅支持 V2/)
    const invalid=saves.createPlayerSaveSnapshotV2Sync(source.id,db);invalid.schemaFingerprint='invalid'
    assert.ok((await upload(target,invalid)).statusCode>=400)
    assert.deepEqual(state(target),before);assert.deepEqual(backupFiles(),existing)
    db.exec(`CREATE TRIGGER fail_imported_pass BEFORE INSERT ON players_pass_cards
        WHEN NEW.player_id=${target.id} BEGIN SELECT RAISE(ABORT,'imported pass failure'); END`)
    let response
    try {response=await upload(target,saves.createPlayerSaveSnapshotV2Sync(source.id,db))}
    finally {db.exec('DROP TRIGGER fail_imported_pass')}
    assert.equal(response.statusCode,500,response.body)
    assert.deepEqual(state(target),before,'failed restore rolls back inventory, progress, purchase and receipts')
    const added=backupFiles().filter(name=>!existing.includes(name));assert.equal(added.length,1)
    assert.deepEqual(backup(added[0]).data.tables,before)
    assert.deepEqual(db.pragma('foreign_key_check'),[])
})
