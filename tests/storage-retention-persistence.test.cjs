require('ts-node/register/transpile-only')
const test=require('node:test')
const assert=require('node:assert/strict')
const D=require('better-sqlite3')
const fs=require('node:fs')
const path=require('node:path')
const os=require('node:os')
const maintenance=require('../src/lib/maintenance-state')
const {runReceiveHistoryRetentionPass}=require('../src/lib/receive-history-retention')

test('age retention covers inactive players, preserves cutoff and recent rows, and limits each transaction',async()=>{
    const db=new D(':memory:')
    try {
        db.exec('CREATE TABLE players_receive_history(id INTEGER PRIMARY KEY,player_id INTEGER NOT NULL,create_time TEXT NOT NULL)')
        const insert=db.prepare('INSERT INTO players_receive_history VALUES(?,?,?)')
        db.transaction(()=>{
            for(let i=1;i<=2200;i++)insert.run(i,1,'2026-08-01 00:00:00')
            insert.run(2201,2,'2026-08-31T00:00:00.000Z')
            insert.run(2202,2,'2026-09-07 00:00:00')
            insert.run(2203,3,'2026-08-30T23:59:59.000Z')
        })()
        let maxBatch=0,lastCount=2203
        const result=await runReceiveHistoryRetentionPass(db,{nowMs:Date.parse('2026-09-07T00:00:00Z'),maxDays:7,maxRows:500,pauseMs:0},()=>{
            const n=db.prepare('SELECT COUNT(*) n FROM players_receive_history').get().n
            maxBatch=Math.max(maxBatch,lastCount-n); lastCount=n
            return false
        })
        assert.equal(result.deletedRows,2201)
        assert.ok(maxBatch<=1000)
        assert.deepEqual(db.prepare('SELECT id FROM players_receive_history ORDER BY id').all(),[{id:2201},{id:2202}])
        assert.equal((await runReceiveHistoryRetentionPass(db,{nowMs:Date.parse('2026-09-07T00:00:00Z'),pauseMs:0})).deletedRows,0)
    } finally {db.close()}
})

test('policy, completion and lease persist across reopen; crashed lease can be reclaimed',()=>{
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sp-maintenance-state-'))
    const file=path.join(dir,'db')
    let db=new D(file)
    try {
        maintenance.initializeMaintenanceState(db)
        maintenance.writeHistoryPolicy(db,{maxRows:400,maxDays:30,dailyHour:3,dailyMinute:5})
        const now=Date.now()
        const lease=maintenance.acquireHistoryLease(db,now)
        assert.ok(lease)
        assert.equal(maintenance.acquireHistoryLease(db,now),null)
        db.close(); db=new D(file)
        assert.equal(maintenance.readHistoryPolicy(db).maxDays,30)
        assert.equal(maintenance.acquireHistoryLease(db,now+1000),null)
        const recovered=maintenance.acquireHistoryLease(db,now+120001)
        assert.ok(recovered)
        maintenance.finishHistoryLease(db,lease,{old:true},true)
        assert.equal(db.prepare('SELECT owner_token FROM server_maintenance_jobs').get().owner_token,recovered.token)
        maintenance.finishHistoryLease(db,recovered,{deletedRows:1},true)
        assert.equal(maintenance.isHistoryCatchupNeeded(db,3,5,new Date()),false)
        db.close(); db=new D(file)
        assert.equal(maintenance.isHistoryCatchupNeeded(db,3,5,new Date()),false)
        assert.equal(maintenance.isHistoryCatchupNeeded(db,3,5,new Date(Date.now()+2*86400000)),true)
        assert.equal(JSON.parse(db.prepare('SELECT last_result_json FROM server_maintenance_jobs').get().last_result_json).deletedRows,1)
    } finally { db.close(); fs.rmSync(dir,{recursive:true,force:true}) }
})
