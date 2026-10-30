'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawn } = require('node:child_process')
const { Worker } = require('node:worker_threads')
const { test } = require('node:test')
const { setTimeout: delay } = require('node:timers/promises')
const Database = require('better-sqlite3')

const out = process.env.STARPOINT_TEST_OUT_DIR
if (!out) throw Error('Use the current isolated build via STARPOINT_TEST_OUT_DIR')
const modulePath = path.join(out, 'lib/admin-database-backup-worker')
const backup = process.argv[2] === '--controlled' ? null : require(modulePath)

async function until(predicate, label) {
    const deadline = Date.now() + 10000
    while (!predicate()) {
        assert.ok(Date.now() < deadline, `timeout: ${label}`)
        await delay(5)
    }
}

function fixture() {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-admin-backup-'))
    const source = path.join(directory, 'source.db')
    const db = new Database(source)
    db.pragma('journal_mode=WAL')
    db.pragma('wal_autocheckpoint=0')
    db.exec('CREATE TABLE payloads(id INTEGER PRIMARY KEY, data BLOB); CREATE TABLE state(id INTEGER PRIMARY KEY, revision INTEGER); CREATE TABLE journal(id INTEGER PRIMARY KEY, data BLOB)')
    const insert = db.prepare('INSERT INTO payloads VALUES(?, ?)')
    const payload = Buffer.alloc(3800, 7)
    db.transaction(() => {
        for (let index = 0; index < 8192; index++) insert.run(index, payload)
        for (let index = 0; index < 32; index++) db.prepare('INSERT INTO state VALUES(?, 0)').run(index)
    })()
    db.pragma('wal_checkpoint(TRUNCATE)')
    // Real change anchors a WAL generation before the backup pins its reader.
    db.prepare('UPDATE state SET revision=1').run()
    return {
        directory, source, db,
        destination: name => path.join(directory, `${name}.db`),
        async close() {
            backup.cancelActiveDatabaseBackups('test cleanup')
            await backup.drainDatabaseBackups()
            db.close()
            assert.ok(path.resolve(directory).startsWith(path.resolve(os.tmpdir()) + path.sep))
            assert.ok(path.basename(directory).startsWith('sp-admin-backup-'))
            fs.rmSync(directory, { recursive: true, force: true })
        },
    }
}

async function writer(source) {
    const shared = new SharedArrayBuffer(8)
    const counters = new Int32Array(shared)
    const worker = new Worker(`
        const { parentPort, workerData } = require('node:worker_threads')
        const Database = require(workerData.databaseModule)
        const db = new Database(workerData.source)
        db.pragma('wal_autocheckpoint=0')
        const state = new Int32Array(workerData.shared)
        const change = db.transaction(() => {
            db.prepare('UPDATE state SET revision=revision+1').run()
            db.prepare('INSERT INTO journal(data) VALUES(?)').run(Buffer.alloc(3800, 9))
        })
        parentPort.postMessage('ready')
        const tick = () => {
            if (Atomics.load(state, 0)) { db.close(); parentPort.close(); return }
            change(); Atomics.add(state, 1, 1); setTimeout(tick, 1)
        }
        tick()
    `, { eval: true, workerData: { source, shared, databaseModule: require.resolve('better-sqlite3') } })
    const exit = new Promise((resolve, reject) => { worker.once('exit', resolve); worker.once('error', reject) })
    await new Promise((resolve, reject) => { worker.once('message', resolve); worker.once('error', reject) })
    return { counters, async stop() { Atomics.store(counters, 0, 1); assert.equal(await exit, 0) } }
}

async function controlled(name) {
    const { EventEmitter } = require('node:events')
    const threads = require('node:worker_threads')
    let worker
    class ControlledWorker extends EventEmitter {
        constructor() { super(); worker = this; this.messages = []; this.terminates = 0 }
        postMessage(value) { this.messages.push(value) }
        unref() {}
        terminate() { this.terminates++; return Promise.resolve(1) }
    }
    threads.Worker = ControlledWorker
    const api = require(modulePath)
    const controller = new AbortController()
    let settled = false, drained = false
    const pending = api.backupDatabaseInWorker('unused-source.db', 'unused-destination.db', {
        signal: controller.signal,
        timeoutMs: name === 'timeout' ? 10 : 10000,
        stallTimeoutMs: name === 'stalled' ? 10 : 10000,
    })
    const observed = pending.then(value => { settled = true; return { value } }, error => { settled = true; return { error } })
    const drain = api.drainDatabaseBackups().then(() => { drained = true })
    let stop
    if (name === 'completed' || name === 'crash-after-completed' || name === 'terminal-completed-stuck') {
        worker.emit('message', { type: 'completed', result: { totalPages: 31, elapsedMs: 8, quickCheck: 'ok', snapshot: true } })
        if (name === 'completed') controller.abort() // A late caller abort must not undo completion.
        if (name === 'terminal-completed-stuck') await until(() => worker.terminates > 0, 'completed worker exit watchdog')
    } else if (name === 'cancelled') controller.abort()
    else if (name === 'terminate-resolved') {
        controller.abort()
        await until(() => worker.terminates > 0, 'cooperative cancel escalates to terminate')
    }
    else if (name === 'timeout' || name === 'stalled') {
        await until(() => worker.messages.length > 0 || worker.terminates > 0, 'deadline requests cancellation')
    } else if (name === 'worker-error') worker.emit('error', Error('native worker fixture failure'))
    else if (name === 'failed-message' || name === 'terminal-failed-stuck') {
        worker.emit('message', { type: 'failed', code: 'wal-growth', error: 'WAL growth fixture' })
        if (name === 'terminal-failed-stuck') await until(() => worker.terminates > 0, 'failed worker exit watchdog')
    }
    else stop = api.stopDatabaseBackups('stop fixture')
    await delay(10)
    assert.equal(settled, false, 'message, error and cancellation request must wait for actual native exit')
    assert.equal(drained, false, 'drain must wait for actual native exit')
    await assert.rejects(api.backupDatabaseInWorker('unused-source.db', 'unused-second.db'), error => error.code === (name === 'stop' ? 'SERVER_CLOSING' : 'busy'))
    worker.emit('exit', name === 'completed' ? 0 : 1)
    const result = await observed
    await drain
    if (stop) await stop
    assert.equal(drained, true)
    if (name === 'completed') assert.equal(result.value.totalPages, 31)
    else assert.equal(result.error.code, ({ 'worker-error': 'failed', 'failed-message': 'wal-growth', 'terminal-failed-stuck': 'wal-growth', 'terminal-completed-stuck': 'failed', 'crash-after-completed': 'failed', 'terminate-resolved': 'cancelled', stop: 'cancelled' })[name] || name)
    if (name === 'stop') {
        await assert.rejects(api.backupDatabaseInWorker('unused-source.db', 'unused-next.db'), error => error.code === 'SERVER_CLOSING')
        return
    }
    // A new generation can only own the slot after the old connection exits.
    const next = api.backupDatabaseInWorker('unused-source.db', 'unused-next.db')
    worker.emit('message', { type: 'completed', result: { totalPages: 2, elapsedMs: 1, quickCheck: 'ok', snapshot: true } })
    worker.emit('exit', 0)
    assert.equal((await next).totalPages, 2)
}

if (process.argv[2] === '--controlled') {
    controlled(process.argv[3]).catch(error => { console.error(error); process.exitCode = 1 })
} else {
test('online WAL backup stays on one snapshot while two other connections keep writing', { timeout: 30000 }, async () => {
    const f = fixture()
    let writes
    try {
        writes = await writer(f.source)
        await until(() => Atomics.load(writes.counters, 1) >= 3, 'concurrent writer starts')
        const progress = []
        let revisionAtCopy, writesAtCopy
        const result = await backup.backupDatabaseInWorker(f.source, f.destination('snapshot'), {
            onProgress(value) {
                progress.push(value)
                if (value.phase === 'copying' && revisionAtCopy === undefined) {
                    revisionAtCopy = f.db.prepare('SELECT revision FROM state LIMIT 1').pluck().get()
                    writesAtCopy = Atomics.load(writes.counters, 1)
                    f.db.prepare('UPDATE state SET revision=revision+1000').run()
                }
            },
        })
        assert.equal(result.quickCheck, 'ok')
        assert.equal(result.snapshot, true)
        assert.ok(result.totalPages > 1000)
        assert.ok(progress.some(value => value.phase === 'opening'))
        assert.ok(progress.some(value => value.phase === 'copying' && value.remainingPages > 0))
        assert.ok(progress.some(value => value.phase === 'verifying'))
        for (const value of progress) {
            assert.ok(Number.isFinite(value.elapsedMs) && value.elapsedMs >= 0)
            assert.ok(value.walBytes >= 0 && value.walGrowthBytes >= 0)
            if (value.phase === 'copying') {
                assert.equal(value.totalPages, result.totalPages)
                assert.equal(value.copiedPages + value.remainingPages, value.totalPages)
            }
        }
        const copy = new Database(f.destination('snapshot'), { readonly: true })
        try {
            assert.equal(copy.pragma('quick_check', { simple: true }), 'ok')
            assert.equal(copy.prepare('SELECT count(*) FROM payloads').pluck().get(), 8192)
            assert.equal(copy.prepare('SELECT sum(length(data)) FROM payloads').pluck().get(), 8192 * 3800)
            assert.equal(copy.prepare('SELECT count(DISTINCT revision) FROM state').pluck().get(), 1, 'no mixed transaction state')
            const snapshotRevision = copy.prepare('SELECT revision FROM state LIMIT 1').pluck().get()
            assert.equal(copy.prepare('SELECT count(*) FROM journal').pluck().get(), snapshotRevision - 1, 'related tables reflect the same committed snapshot')
            assert.ok(snapshotRevision <= revisionAtCopy, 'writes after the pinned snapshot cannot restart the backup')
            assert.ok(f.db.prepare('SELECT revision FROM state LIMIT 1').pluck().get() >= revisionAtCopy + 1000)
        } finally { copy.close() }
        assert.ok(Atomics.load(writes.counters, 1) > writesAtCopy, 'another connection commits while backup is in progress')
    } finally { if (writes) await writes.stop(); await f.close() }
})

test('real worker rejects bad inputs and keeps existing destinations untouched', { timeout: 30000 }, async () => {
    const f = fixture()
    try {
        const existing = f.destination('existing')
        fs.writeFileSync(existing, 'keep-existing-backup')
        await assert.rejects(backup.backupDatabaseInWorker(f.source, existing), error => error.code === 'destination-exists')
        assert.equal(fs.readFileSync(existing, 'utf8'), 'keep-existing-backup')
        const plain = new Database(f.destination('plain'))
        plain.exec('CREATE TABLE value(id INTEGER)')
        plain.close()
        await assert.rejects(backup.backupDatabaseInWorker(f.destination('plain'), f.destination('not-wal')), error => error.code === 'not-wal')
        const unchanged = new Database(f.destination('plain'), { readonly: true })
        try { assert.equal(unchanged.pragma('journal_mode', { simple: true }), 'delete') } finally { unchanged.close() }
        await assert.rejects(backup.backupDatabaseInWorker(f.destination('missing'), f.destination('error')), error => error.code === 'failed')
        assert.equal(fs.existsSync(f.destination('error')), false)
        assert.equal(fs.existsSync(f.destination('not-wal')), false)
        assert.equal((await backup.backupDatabaseInWorker(f.source, f.destination('recovery'))).quickCheck, 'ok')
    } finally { await f.close() }
})

test('real cancellation, deadline and WAL growth fail without publishing partial backups', { timeout: 30000 }, async () => {
    const f = fixture()
    try {
        const controller = new AbortController()
        await assert.rejects(backup.backupDatabaseInWorker(f.source, f.destination('cancelled'), {
            signal: controller.signal,
            onProgress(value) { if (value.phase === 'copying') controller.abort() },
        }), error => error.code === 'cancelled')
        assert.equal(fs.existsSync(f.destination('cancelled')), false)
        await assert.rejects(backup.backupDatabaseInWorker(f.source, f.destination('timeout'), { timeoutMs: 1 }), error => error.code === 'timeout')
        assert.equal(fs.existsSync(f.destination('timeout')), false)
        let grew = false
        await assert.rejects(backup.backupDatabaseInWorker(f.source, f.destination('wal-growth'), {
            maxWalGrowthBytes: 1,
            onProgress(value) {
                if (value.phase === 'copying' && !grew) {
                    grew = true
                    f.db.prepare('INSERT INTO journal(data) VALUES(?)').run(Buffer.alloc(64 * 1024, 3))
                }
            },
        }), error => error.code === 'wal-growth')
        assert.equal(grew, true)
        assert.equal(fs.existsSync(f.destination('wal-growth')), false)
        assert.equal((await backup.backupDatabaseInWorker(f.source, f.destination('after-failures'))).quickCheck, 'ok')
    } finally { await f.close() }
})

for (const name of ['completed', 'crash-after-completed', 'terminal-completed-stuck', 'terminal-failed-stuck', 'cancelled', 'terminate-resolved', 'timeout', 'stalled', 'worker-error', 'failed-message', 'stop']) {
    test(`backup lifecycle waits for actual worker exit: ${name}`, { timeout: 15000 }, async () => {
        const child = spawn(process.execPath, [__filename, '--controlled', name], { env: process.env, stdio: ['ignore', 'pipe', 'pipe'] })
        let output = ''
        child.stdout.on('data', value => { output += value })
        child.stderr.on('data', value => { output += value })
        const code = await new Promise((resolve, reject) => { child.once('exit', resolve); child.once('error', reject) })
        assert.equal(code, 0, output)
    })
}
}
