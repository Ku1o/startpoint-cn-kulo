// Controlled SQLite experiments; only owns generated databases under os.tmpdir().
const fs=require('node:fs'),path=require('node:path'),os=require('node:os')
const {performance}=require('node:perf_hooks')
const Database=require('better-sqlite3')
const {beginCommitProbe,endCommitProbe,drainSqliteCommitDiagnostics,readWalCommitState}=require('../out/lib/sqlite-commit-diagnostics')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'sqlite-commit-evidence-'))
process.env.SQLITE_SLOW_COMMIT_MS='0'
const describe=a=>{
    const b=[...a].sort((x,y)=>x-y)
    return {n:b.length,avgMs:b.reduce((x,y)=>x+y,0)/(b.length||1),p95Ms:b[Math.ceil(b.length*.95)-1]||0,maxMs:b.at(-1)||0}
}
function run(mode){
    const db=new Database(path.join(directory,mode+'.db'))
    db.pragma('journal_mode=WAL');db.pragma('synchronous=NORMAL');db.pragma('wal_autocheckpoint=1000')
    db.exec('CREATE TABLE rows(id INTEGER PRIMARY KEY,data BLOB)')
    const insert=db.prepare('INSERT INTO rows VALUES(?,?)'),blob=Buffer.alloc(3000,1)
    db.transaction(()=>{for(let i=0;i<3200;i++)insert.run(i,blob)})()
    db.pragma('wal_checkpoint(TRUNCATE)')
    if(mode==='separate-fixture-checkpoints')db.pragma('wal_autocheckpoint=0')
    const update=db.prepare('UPDATE rows SET data=? WHERE id=?')
    const ordinary=[],automatic=[],explicit=[],samples=[]
    try{
        for(let i=0;i<180;i++){
            db.exec('BEGIN IMMEDIATE');blob.writeUInt32LE(i,0)
            for(let j=0;j<32;j++)update.run(blob,(i*79+j*97)%3200)
            const probe=beginCommitProbe(db,'immediate')
            db.exec('COMMIT');endCommitProbe(db,probe,true)
            const sample=drainSqliteCommitDiagnostics().samples[0]
            ;(sample.checkpointProgress?automatic:ordinary).push(sample.wallMs)
            if(sample.checkpointProgress)samples.push(sample)
            if(mode==='separate-fixture-checkpoints' && readWalCommitState(db).frames>=1000){
                const start=performance.now();db.pragma('wal_checkpoint(PASSIVE)');explicit.push(performance.now()-start)
            }
        }
        return {mode,sqliteVersion:db.prepare('select sqlite_version() AS v').get().v,
            ordinaryCommit:describe(ordinary),commitWithCheckpoint:describe(automatic),explicitFixtureCheckpoint:describe(explicit),
            slowestCheckpoint:samples.sort((a,b)=>b.wallMs-a.wallMs)[0]||null,integrity:db.pragma('quick_check',{simple:true})}
    }finally{db.close()}
}
function overhead(){
    const db=new Database(path.join(directory,'overhead.db'))
    db.pragma('journal_mode=WAL');db.pragma('synchronous=NORMAL');db.pragma('wal_autocheckpoint=0')
    db.exec('CREATE TABLE t(x); INSERT INTO t VALUES(1)')
    process.env.SQLITE_SLOW_COMMIT_MS='100'
    const results=[]
    try{
        for(const enabled of [false,true,true,false]){
            process.env.SQLITE_COMMIT_DIAGNOSTICS=String(enabled)
            const start=performance.now()
            for(let i=0;i<1000;i++){
                db.exec('BEGIN; UPDATE t SET x=x+1')
                const probe=beginCommitProbe(db,'immediate');db.exec('COMMIT');endCommitProbe(db,probe,true)
            }
            results.push({enabled,msPerTransaction:(performance.now()-start)/1000})
            drainSqliteCommitDiagnostics()
        }
        return results
    }finally{delete process.env.SQLITE_COMMIT_DIAGNOSTICS;db.close()}
}
const result={experiments:[run('automatic'),run('separate-fixture-checkpoints')],diagnosticOverhead:overhead()}
fs.writeFileSync(process.argv[2],JSON.stringify(result,null,2));console.log(JSON.stringify(result))
