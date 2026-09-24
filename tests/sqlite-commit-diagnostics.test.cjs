const test=require('node:test'),assert=require('node:assert/strict')
const fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const {Worker}=require('node:worker_threads')
const {performance}=require('node:perf_hooks')
const Database=require('better-sqlite3')
const diagnostics=require('../out/lib/sqlite-commit-diagnostics')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'sqlite-commit-probe-'))
let db
const dbModule=require.resolve('../out/data/db')
require.cache[dbModule]={id:dbModule,filename:dbModule,loaded:true,exports:{getDb:()=>db}}
const {runMeasuredSingleTransaction,runImmediateTransactionWithRetry}=require('../out/lib/sqlite-write-coordinator')
const {drainServerWorkPerformance}=require('../out/lib/server-work-performance')
process.env.SQLITE_SLOW_COMMIT_MS='0'
let next=0
function open(){
    const value=new Database(path.join(directory,`${next++}.db`))
    value.pragma('journal_mode=WAL');value.pragma('synchronous=NORMAL');value.pragma('busy_timeout=1000')
    value.exec('CREATE TABLE items(id INTEGER PRIMARY KEY, data BLOB)')
    diagnostics.drainSqliteCommitDiagnostics();drainServerWorkPerformance()
    return value
}

test('WAL metadata proves automatic checkpoint progress without executing a checkpoint query',()=>{
    db=open()
    try {
        const before=diagnostics.readWalCommitState(db);assert.ok(before)
        const put=db.prepare('INSERT INTO items VALUES (?,?)'),blob=Buffer.alloc(3000,7)
        const result=runMeasuredSingleTransaction(db,()=>{for(let i=0;i<1100;i++)put.run(i,blob);return 'kept'})
        assert.equal(result,'kept')
        const value=diagnostics.drainSqliteCommitDiagnostics(),sample=value.samples[0]
        assert.equal(value.n,1);assert.equal(value.errors,0)
        assert.equal(sample.settings.autoCheckpoint,1000);assert.equal(sample.settings.synchronous,1)
        assert.equal(sample.checkpointProgress,true)
        assert.ok(sample.after.frames>=1000);assert.equal(sample.after.backfilled,sample.after.frames)
        assert.equal(db.prepare('SELECT count(*) AS n FROM items').get().n,1100)
        const state=diagnostics.readWalCommitState(db)
        assert.deepEqual(diagnostics.readWalCommitState(db),state)
    } finally {db.close()}
})

test('both transaction paths preserve rollback and deferred constraint errors',async()=>{
    db=open()
    try {
        assert.throws(()=>runMeasuredSingleTransaction(db,()=>{db.prepare('INSERT INTO items VALUES(1,?)').run('rollback');throw Error('body failure')}),/body failure/)
        await assert.rejects(runImmediateTransactionWithRetry(()=>{db.prepare('INSERT INTO items VALUES(2,?)').run('rollback');throw Error('body failure')}),/body failure/)
        assert.equal(db.prepare('SELECT count(*) AS n FROM items').get().n,0)
        db.pragma('foreign_keys=ON')
        db.exec('CREATE TABLE parent(id PRIMARY KEY); CREATE TABLE child(id REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)')
        assert.throws(()=>runMeasuredSingleTransaction(db,()=>db.exec('INSERT INTO child VALUES(9)')),/FOREIGN KEY/)
        assert.equal(db.prepare('SELECT count(*) AS n FROM child').get().n,0)
        const error=diagnostics.drainSqliteCommitDiagnostics()
        assert.equal(error.errors,1);assert.equal(error.samples[0].errorCode,'SQLITE_CONSTRAINT_FOREIGNKEY')
        assert.equal(await runImmediateTransactionWithRetry(()=>{db.exec("INSERT INTO items VALUES(3,'ok')");return 42}),42)
        const completed=diagnostics.drainSqliteCommitDiagnostics()
        assert.equal(completed.n,1);assert.equal(completed.samples[0].kind,'immediate');assert.equal(completed.errors,0)
    }finally{db.close()}
})

test('writer contention appears in BEGIN rather than mislabeling COMMIT',async()=>{
    db=open()
    const worker=new Worker(`const {parentPort,workerData}=require('node:worker_threads');
        const db=new (require(workerData.module))(workerData.file);db.exec('BEGIN IMMEDIATE');
        parentPort.postMessage('locked');setTimeout(()=>{db.exec('ROLLBACK');db.close();parentPort.postMessage('released')},200)`,
        {eval:true,workerData:{file:db.name,module:require.resolve('better-sqlite3')}})
    try{
        await new Promise((resolve,reject)=>{worker.once('message',resolve);worker.once('error',reject)})
        await runImmediateTransactionWithRetry(()=>db.exec("INSERT INTO items VALUES(1,'lock fixture')"))
        const work=drainServerWorkPerformance(),commit=diagnostics.drainSqliteCommitDiagnostics()
        assert.ok(work['db.begin'].maxMs>=100)
        assert.ok(commit.maxMs<work['db.begin'].maxMs)
        assert.equal(commit.samples[0].checkpointProgress,false)
    }finally{await worker.terminate();db.close()}
})

test('bounded samples, unavailable metadata and disable switches do not change writes',()=>{
    db=open()
    try{
        for(let i=0;i<12;i++)runMeasuredSingleTransaction(db,()=>db.prepare('INSERT INTO items VALUES(?,?)').run(i,'sample'))
        const summary=diagnostics.drainSqliteCommitDiagnostics()
        assert.equal(summary.samples.length,8);assert.equal(summary.omitted,4)
        assert.equal(summary.n,12)
        assert.equal(diagnostics.readWalCommitState({open:true,memory:true}),null)
        assert.equal(diagnostics.readWalCommitState({open:true,memory:false,name:path.join(directory,'missing')}),null)
        process.env.SQLITE_COMMIT_DIAGNOSTICS='false'
        runMeasuredSingleTransaction(db,()=>db.prepare('INSERT INTO items VALUES(100,?)').run('disabled'))
        assert.equal(diagnostics.drainSqliteCommitDiagnostics().n,0)
        delete process.env.SQLITE_COMMIT_DIAGNOSTICS
        process.env.SQLITE_DIAGNOSTICS='false'
        runMeasuredSingleTransaction(db,()=>db.prepare('INSERT INTO items VALUES(101,?)').run('disabled'))
        assert.equal(diagnostics.drainSqliteCommitDiagnostics().n,0)
        delete process.env.SQLITE_DIAGNOSTICS
        assert.equal(db.prepare('SELECT count(*) AS n FROM items').get().n,14)
    }finally{delete process.env.SQLITE_COMMIT_DIAGNOSTICS;delete process.env.SQLITE_DIAGNOSTICS;db.close()}
})

test('nested savepoint releases are not reported as durable commits',()=>{
    db=open()
    try{
        runMeasuredSingleTransaction(db,()=>runMeasuredSingleTransaction(db,()=>db.exec("INSERT INTO items VALUES(1,'nested')")))
        assert.equal(diagnostics.drainSqliteCommitDiagnostics().n,1)
        process.env.ROUTE_PERF_SUMMARY='false'
        runMeasuredSingleTransaction(db,()=>db.exec("INSERT INTO items VALUES(2,'monitor disabled')"))
        assert.equal(diagnostics.drainSqliteCommitDiagnostics().n,0)
    }finally{delete process.env.ROUTE_PERF_SUMMARY;db.close()}
})
