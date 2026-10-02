const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { setTimeout: delay } = require('node:timers/promises')
const Database = require('better-sqlite3')

process.env.SQLITE_DIAGNOSTICS = 'true'
const checkpoint = require('../out/lib/sqlite-checkpoint-worker')
const { collectMemoryDiagnostics } = require('../out/lib/memory-diagnostics')
const environment = {
    SQLITE_CHECKPOINT_WORKER: '1',
    SQLITE_CHECKPOINT_INTERVAL_MS: '3600000',
    SQLITE_CHECKPOINT_TRUNCATE_FRAMES: '1000',
    SQLITE_CHECKPOINT_TRUNCATE_BYTES: String(4 * 1024 * 1024),
    SQLITE_CHECKPOINT_TRUNCATE_COOLDOWN_MS: '5000',
}
const state = () => collectMemoryDiagnostics().counters.sqliteCheckpoint
async function until(predicate, label, timeout = 10000) {
    const deadline = Date.now() + timeout
    while (Date.now() < deadline) {
        if (predicate()) return
        await delay(20)
    }
    assert.fail(`${label}: ${JSON.stringify(state())}`)
}
function open(file) {
    const db = new Database(file)
    db.pragma('journal_mode=WAL')
    db.pragma('wal_autocheckpoint=0')
    db.exec('CREATE TABLE payloads(id INTEGER PRIMARY KEY, data BLOB)')
    db.prepare('INSERT INTO payloads VALUES(0,?)').run(Buffer.alloc(3800, 1))
    return db
}
function append(db) {
    const put = db.prepare('INSERT INTO payloads VALUES(?,?)')
    const data = Buffer.alloc(3800, 7)
    db.transaction(() => { for (let i = 1; i <= 1300; i++) put.run(i, data) })()
    assert.ok(fs.statSync(db.name + '-wal').size >= 4 * 1024 * 1024)
}

test('checkpoint worker handles backlog, pinned readers, cooldown and lifecycle on isolated databases', async t => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-checkpoint-worker-'))
    try {
        await t.test('disabled switch does not start a worker', async () => {
            const before = state().completed
            checkpoint.startSqliteCheckpointWorker(path.join(directory, 'disabled.db'), { SQLITE_CHECKPOINT_WORKER: '0' })
            assert.equal(state().started, false)
            assert.equal(state().completed, before)
            assert.equal(fs.existsSync(path.join(directory, 'disabled.db')), false)
            await checkpoint.stopSqliteCheckpointWorker()
        })
        await t.test('startup reclaims existing WAL without losing committed rows', async () => {
            const db = open(path.join(directory, 'backlog.db'))
            try {
                append(db)
                const before = state().truncateCompleted
                checkpoint.startSqliteCheckpointWorker(db.name, environment)
                await until(() => state().truncateCompleted > before, 'startup truncate')
                await until(() => {
                    const worker = collectMemoryDiagnostics().workers.find(row => row.name === 'sqlite-checkpoint')
                    return worker && !worker.stale && worker.pendingMs === 0
                }, 'checkpoint memory probe')
                assert.equal(fs.statSync(db.name + '-wal').size, 0)
                assert.equal(db.prepare('SELECT count(*) FROM payloads').pluck().get(), 1301)
                assert.equal(db.pragma('integrity_check', { simple: true }), 'ok')
            } finally {
                await checkpoint.stopSqliteCheckpointWorker()
                assert.equal(state().started, false)
                assert.ok(!collectMemoryDiagnostics().workers.some(worker => worker.name === 'sqlite-checkpoint'))
                db.close()
            }
        })
        await t.test('pinned reader reports busy, respects cooldown and retries after release', async () => {
            const db = open(path.join(directory, 'reader.db'))
            const reader = new Database(db.name, { readonly: true })
            try {
                reader.exec('BEGIN')
                assert.equal(reader.prepare('SELECT count(*) FROM payloads').pluck().get(), 1)
                append(db)
                const before = state()
                checkpoint.startSqliteCheckpointWorker(db.name, environment)
                await until(() => state().truncateBusy > before.truncateBusy, 'pinned-reader busy')
                assert.equal(state().errors, before.errors)
                assert.ok(state().lastPassiveCheckpointedFrames < state().lastPassiveLogFrames)
                assert.equal(reader.prepare('SELECT count(*) FROM payloads').pluck().get(), 1)
                const first = state()
                checkpoint.requestSqliteCheckpoint()
                await until(() => state().completed > first.completed, 'cooldown passive checkpoint')
                assert.equal(state().truncateAttempts, first.truncateAttempts)
                reader.exec('COMMIT')
                await delay(5100)
                checkpoint.requestSqliteCheckpoint()
                await until(() => state().truncateCompleted > before.truncateCompleted, 'retry after reader release')
                assert.equal(state().lastWalBytes, 0)
                assert.equal(db.prepare('SELECT count(*) FROM payloads').pluck().get(), 1301)
                assert.equal(reader.prepare('SELECT count(*) FROM payloads').pluck().get(), 1301)
                assert.equal(db.pragma('integrity_check', { simple: true }), 'ok')
            } finally {
                if (reader.inTransaction) reader.exec('ROLLBACK')
                reader.close()
                await checkpoint.stopSqliteCheckpointWorker()
                db.close()
            }
        })
        await t.test('failed startup is observable and a later start can recover', async () => {
            const before = state().errors
            checkpoint.startSqliteCheckpointWorker(path.join(directory, 'missing', 'db.sqlite'), environment)
            await until(() => state().errors > before && !state().started, 'startup failure')
            const db = open(path.join(directory, 'recovered.db'))
            try {
                const completed = state().completed
                checkpoint.startSqliteCheckpointWorker(db.name, environment)
                await until(() => state().completed > completed, 'restart after failure')
                assert.equal(state().lastError, false)
            } finally {
                await checkpoint.stopSqliteCheckpointWorker()
                await checkpoint.stopSqliteCheckpointWorker()
                db.close()
            }
        })
    } finally {
        await checkpoint.stopSqliteCheckpointWorker()
        const resolved = path.resolve(directory)
        assert.ok(resolved.startsWith(path.resolve(os.tmpdir()) + path.sep))
        fs.rmSync(resolved, { recursive: true })
    }
})
