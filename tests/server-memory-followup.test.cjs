const test = require('node:test')
const assert = require('node:assert/strict')
const { setImmediate: nextTick } = require('node:timers/promises')
const net = require('node:net')
const Database = require('better-sqlite3')
const { ProcessMemoryProbe, readWindowsProcessMemory } = require('../out/lib/process-memory-probe')
const { observeSqliteDatabase } = require('../out/lib/sqlite-diagnostics')
const { collectMemoryDiagnostics, observeServerConnections } = require('../out/lib/memory-diagnostics')
const { cachedStatement } = require('../out/lib/cached-statement')
const path = require('node:path')

test('OS probe bounds outstanding work, invalidates failed/stale values, recovers and cancels', async () => {
    let now = 100, calls = 0, resolve, reject, signal
    const values = {privateBytes:200,workingSetBytes:100,virtualBytes:1000,handleCount:7,threadCount:3}
    const probe = new ProcessMemoryProbe(true, abort => {
        calls++; signal=abort
        return new Promise((yes,no)=>{resolve=yes;reject=no})
    },()=>now)
    probe.request();probe.request();await nextTick()
    assert.equal(calls,1);assert.equal(probe.snapshot().memory,null)
    resolve(values);await nextTick()
    assert.deepEqual(probe.snapshot().memory,values);assert.equal(probe.snapshot().stale,false)
    now += 120001;assert.equal(probe.snapshot().stale,true)
    probe.request();await nextTick();reject(new Error('fixture timeout'));await nextTick()
    assert.equal(probe.snapshot().failed,true)
    probe.request();await nextTick();resolve(values);await nextTick()
    assert.equal(probe.snapshot().failed,false);assert.equal(probe.snapshot().stale,false)
    probe.request();await nextTick();probe.close()
    assert.equal(signal.aborted,true)
    resolve({...values,privateBytes:999});await nextTick()
    assert.equal(probe.snapshot().memory.privateBytes,200)
    probe.request();await nextTick();assert.equal(calls,4)
    const disabled = new ProcessMemoryProbe(false,()=>{throw Error('must not run')})
    disabled.request();assert.equal(disabled.snapshot().available,false)
})

test('Windows probe reads only numeric parent-process measurements', {skip:process.platform!=='win32'}, async () => {
    const sample = await readWindowsProcessMemory(new AbortController().signal)
    assert.deepEqual(Object.keys(sample).sort(),['handleCount','privateBytes','regions','threadCount','virtualBytes','workingSetBytes'])
    for (const [key,value] of Object.entries(sample)) {
        if(key!=='regions')assert.ok(Number.isSafeInteger(value) && value>0)
    }
    for(const value of Object.values(sample.regions))assert.ok(Number.isSafeInteger(value) && value>=0)
    assert.ok(sample.regions.privateCommittedBytes>0)
})

test('native region capture classifies committed mappings without touching target memory', {skip:process.platform!=='win32'}, async () => {
    const execFile=require('node:util').promisify(require('node:child_process').execFile)
    const {stdout}=await execFile(path.join(process.env.SystemRoot,'System32/WindowsPowerShell/v1.0/powershell.exe'),
        ['-NoLogo','-NoProfile','-NonInteractive','-File',path.join(__dirname,'../tools/capture-native-memory.ps1'),
            '-ProcessId',String(process.pid)],{windowsHide:true,timeout:15000,maxBuffer:4096})
    const sample=JSON.parse(stdout.trim().replace(/^\uFEFF/,''))
    assert.equal(sample.pid,process.pid)
    assert.ok(sample.regions.privateCommittedBytes>0)
    assert.ok(sample.regions.imageCommittedBytes>0)
    assert.ok(sample.regions.regionCount>0)
    assert.ok(sample.processStartedAt)
})

test('SQL diagnostics count uncached compilation without retaining results or changing rollback', () => {
    const db = new Database(':memory:')
    observeSqliteDatabase(db,'fixture')
    const prepare = db.prepare
    observeSqliteDatabase(db,'fixture')
    assert.equal(db.prepare,prepare)
    db.exec('CREATE TABLE t(id INTEGER PRIMARY KEY,value TEXT)')
    const sql='INSERT INTO t VALUES (?,?)'
    cachedStatement(db,sql).run(1,'first')
    cachedStatement(db,sql).run(2,'second')
    assert.throws(()=>db.transaction(()=>{cachedStatement(db,sql).run(3,'rolled back');throw Error('rollback')})())
    assert.deepEqual(db.prepare('SELECT value FROM t ORDER BY id').all(),[{value:'first'},{value:'second'}])
    assert.throws(()=>db.prepare('SELECT * FROM missing_table'))
    const sample = collectMemoryDiagnostics().counters['sqlite.fixture']
    assert.equal(sample.prepareCalls,3)
    assert.equal(sample.prepareErrors,1)
    assert.equal(sample.sampledPrepareCalls,1)
    assert.equal(sample.nativeBytesAvailable,false)
    assert.ok(sample.page_size>0)
    assert.equal(sample.inTransaction,false)
    db.close();collectMemoryDiagnostics()
    assert.equal(collectMemoryDiagnostics().counters['sqlite.fixture'],undefined)
})

test('connection diagnostics count real sockets and unregister after close', async () => {
    const server=net.createServer(socket=>socket.on('error',()=>{}))
    observeServerConnections('fixture',server)
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
    const client=net.connect(server.address().port,'127.0.0.1')
    try {
        await new Promise((resolve,reject)=>{client.once('connect',resolve);client.once('error',reject)})
        collectMemoryDiagnostics();await nextTick()
        assert.equal(collectMemoryDiagnostics().counters['connections.fixture'].connections,1)
    } finally {
        client.destroy()
        await new Promise(resolve=>server.close(resolve))
    }
    assert.equal(collectMemoryDiagnostics().counters['connections.fixture'],undefined)
})

test('routine logging caps examples, delays message construction and preserves aggregate counts', () => {
    const {routineGameLog,flushRoutineGameLogs}=require('../out/lib/routine-game-logging')
    const log=console.log, lines=[];let built=0
    console.log=value=>lines.push(value)
    try {
        for(let i=0;i<1000;i++)routineGameLog('multiBarrier',()=>{built++;return 'barrier'})
        assert.equal(built,3);assert.equal(lines.length,3)
        flushRoutineGameLogs()
        assert.match(lines[3],/multiBarrier=1000\(suppressed=997\)/)
        routineGameLog('multiBarrier',()=>{built++;return 'next interval'})
        assert.equal(built,4)
        flushRoutineGameLogs()
    } finally {console.log=log}
})
