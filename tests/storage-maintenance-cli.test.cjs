require('ts-node/register/transpile-only')
const test=require('node:test')
const assert=require('node:assert/strict')
const fs=require('node:fs')
const path=require('node:path')
const os=require('node:os')
const {spawnSync}=require('node:child_process')
const D=require('better-sqlite3')
const api=require('../src/storage-maintenance')
const root=path.resolve(__dirname,'..')

function fixture(){
    const project=fs.mkdtempSync(path.join(os.tmpdir(),'sp-storage-cli-'))
    const data=path.join(project,'.database');fs.mkdirSync(data)
    const result=spawnSync(process.execPath,['-r','ts-node/register/transpile-only','-e',`
        const db=require('./src/data/db').getDb();
        const a=require('./src/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'test',idpId:'cli',status:'normal'});
        const p=require('./src/data/domains/player').insertDefaultPlayerSync(a.id);
        require('./src/lib/mission/counters').addMissionCounterSync(p.id,{dimension:'clear',scopeType:'lifetime',scopeKey:'all'},123);
        db.prepare("INSERT INTO players_receive_history(player_id,type,type_id,number,reason_id,create_time)VALUES(?,5,1,1,0,'2020-01-01')").run(p.id);
        db.close();
    `],{cwd:root,env:{...process.env,DATA_DIR:data},encoding:'utf8',timeout:30000})
    assert.equal(result.status,0,result.stdout+result.stderr)
    return {project,database:path.join(data,'wdfp_data.db'),lock:path.join(data,'storage-maintenance.lock'),state:path.join(data,'storage-maintenance-state.json'),backups:path.join(data,'maintenance-backups')}
}
function cleanup(p){fs.rmSync(p.project,{recursive:true,force:true})}

test('offline tool backs up, compacts, persists policy and safely repeats without reverting new progress',async()=>{
    const p=fixture()
    try {
        const before=fs.readFileSync(p.database)
        const versionFile=p.database+'.version'
        const version=fs.readFileSync(versionFile)
        fs.writeFileSync(versionFile,'999')
        try {assert.throws(()=>api.previewMaintenance(p),/基础数据库版本/)}finally{fs.writeFileSync(versionFile,version)}
        const preview=api.previewMaintenance(p)
        assert.equal(preview.stats.layoutVersion,0)
        assert.deepEqual(fs.readFileSync(p.database),before)
        const previousSwitch=process.env.RECEIVE_HISTORY_RETENTION_ENABLED
        process.env.RECEIVE_HISTORY_RETENTION_ENABLED='false'
        try {
            assert.equal(api.previewMaintenance(p).automaticRetentionEnabled,false)
            await assert.rejects(api.applyMaintenance(p),/已关闭/)
            assert.equal(fs.existsSync(p.lock),false)
        } finally {
            if(previousSwitch===undefined)delete process.env.RECEIVE_HISTORY_RETENTION_ENABLED
            else process.env.RECEIVE_HISTORY_RETENTION_ENABLED=previousSwitch
        }
        const result=await api.applyMaintenance(p)
        assert.equal(result.phase,'ready')
        assert.equal(result.retention.deletedRows,1)
        assert.ok(result.backupSha256)
        assert.ok(fs.existsSync(p.lock))
        const original=new D(result.backup,{readonly:true,fileMustExist:true})
        assert.equal(original.prepare('SELECT value FROM players_mission_counters').get().value,123)
        assert.equal(original.prepare('SELECT COUNT(*) n FROM players_receive_history').get().n,1)
        original.close()
        api.releaseMaintenance(p)
        assert.equal(fs.existsSync(p.lock),false)
        const db=new D(p.database)
        db.prepare('UPDATE players SET total_stamina_used=total_stamina_used+77').run()
        const mana=db.prepare('SELECT total_stamina_used FROM players').get().total_stamina_used
        db.close()
        await assert.rejects(api.rollbackMaintenance(p),/维护锁|开放写入/)
        api.completeMaintenance(p)
        const again=await api.applyMaintenance(p)
        assert.equal(again.migration.alreadyApplied,true)
        assert.equal(again.retention.deletedRows,0)
        api.releaseMaintenance(p);api.completeMaintenance(p)
        for(let i=0;i<3;i++) {await api.applyMaintenance(p);api.releaseMaintenance(p);api.completeMaintenance(p)}
        assert.equal(fs.readdirSync(p.backups).length,3)
        assert.ok(fs.existsSync(result.backup),'pre-migration rollback baseline must stay pinned')
        const reopened=new D(p.database,{readonly:true})
        assert.equal(reopened.prepare('SELECT total_stamina_used FROM players').get().total_stamina_used,mana)
        assert.equal(JSON.parse(reopened.prepare('SELECT value_json FROM server_maintenance_settings').get().value_json).maxDays,7)
        assert.equal(reopened.pragma('integrity_check',{simple:true}),'ok')
        reopened.close()
    } finally {cleanup(p)}
})

test('a failed migration has a verified rollback, including history cleared after migration commit',async()=>{
    const p=fixture()
    try {
        await assert.rejects(api.applyMaintenance(p,stage=>{if(stage==='before-vacuum')throw Error('injected failure')}),/injected/)
        const state=JSON.parse(fs.readFileSync(p.state,'utf8'))
        assert.equal(state.phase,'failed')
        await api.rollbackMaintenance(p)
        await api.rollbackMaintenance(p)
        api.releaseMaintenance(p);api.completeMaintenance(p)
        const db=new D(p.database,{readonly:true})
        assert.equal(db.prepare("SELECT type FROM sqlite_master WHERE name='players_mission_counters'").get().type,'table')
        assert.equal(db.prepare('SELECT COUNT(*) n FROM players_receive_history').get().n,1)
        assert.equal(db.prepare('SELECT value FROM players_mission_counters').get().value,123)
        db.close()
    } finally {cleanup(p)}
})

test('abrupt process termination leaves a recoverable WAL database and persistent lock',async()=>{
    const p=fixture()
    try {
        const result=spawnSync(process.execPath,['-r','ts-node/register/transpile-only','-e',`
            const api=require('./src/storage-maintenance');
            api.applyMaintenance(${JSON.stringify(p)},stage=>{if(stage==='before-vacuum')process.exit(88)}).catch(e=>{console.error(e);process.exit(1)});
        `],{cwd:root,encoding:'utf8',timeout:30000})
        assert.equal(result.status,88,result.stdout+result.stderr)
        assert.equal(fs.existsSync(p.lock),true)
        await api.rollbackMaintenance(p)
        api.releaseMaintenance(p);api.completeMaintenance(p)
        const db=new D(p.database,{readonly:true})
        assert.equal(db.pragma('integrity_check',{simple:true}),'ok')
        assert.equal(db.prepare('SELECT COUNT(*) n FROM players_receive_history').get().n,1)
        db.close()
    } finally {cleanup(p)}
})
