const { test, after, beforeEach } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const Database = require('better-sqlite3')
const output = process.env.STARPOINT_TEST_OUT_DIR || path.resolve(__dirname, '../out')
const load = name => require(path.join(output, name))

const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'sync-phase-'))
process.env.DATA_DIR = directory
process.env.CN_WRITER_THREAD = '0'
process.env.SLOW_OPERATION_DIAGNOSTICS = 'true'
process.env.SLOW_OPERATION_MS = '1'
process.env.ROUTE_PERF_SUMMARY = 'true'
process.env.SQLITE_COMMIT_DIAGNOSTICS = 'false'

const db = new Database(path.join(directory, 'fixture.db'))
load('data/db').setDbOverride(db)
const coordinator = load('lib/persistence-coordinator')
const clock = load('lib/server-clock-state')
const diagnostics = load('lib/slow-operation-diagnostics')
db.exec(`CREATE TABLE saved(value TEXT);
    CREATE TABLE parent(id INTEGER PRIMARY KEY);
    CREATE TABLE child(parent_id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED);`)
db.pragma('foreign_keys = ON')
const insert = db.prepare('INSERT INTO saved VALUES (?)')
const rows = () => db.prepare('SELECT value FROM saved ORDER BY rowid').pluck().all()
const timer = new Int32Array(new SharedArrayBuffer(4))
const delay = () => Atomics.wait(timer, 0, 0, 8)
const run = operation => coordinator.runPersistenceTransactionSync({ domain: 'maintenance', operation: 'sync_fixture' }, operation)

beforeEach(() => {
    db.exec('DELETE FROM saved; DELETE FROM child')
    diagnostics.drainSlowOperationDiagnostics()
})
after(async () => {
    await coordinator.drainPersistence()
    db.close()
    load('data/db').setDbOverride(null)
    const resolved = fs.realpathSync(directory)
    assert.equal(path.dirname(resolved), fs.realpathSync(os.tmpdir()))
    assert.match(path.basename(resolved), /^sync-phase-[a-zA-Z0-9]+$/)
    fs.rmSync(resolved, { recursive: true })
})

// Observe even sub-threshold native failures without changing the diagnostics
// threshold or inventing timing samples. Business SQL still uses real SQLite.
function observeBoundaries(t) {
    const completed = []
    const end = diagnostics.endSlowOperationPhase
    t.mock.method(diagnostics, 'endSlowOperationPhase', (token, failed) => {
        if (token) completed.push({ phase: token.phase, failed: !!failed })
        return end(token, failed)
    })
    return completed
}

test('sync samples separate driver entry, clock checks, business body and driver completion', t => {
    const transaction = db.transaction
    t.mock.method(db, 'transaction', function (operation) {
        const wrapped = transaction.call(this, function (...args) {
            delay() // Native BEGIN has returned, before the coordinator callback.
            return operation.apply(this, args)
        })
        const immediate = wrapped.immediate
        // better-sqlite3 defines this property as non-writable. Keep its callable
        // intact and decorate only the value returned to the coordinator.
        return { immediate(...args) {
            try { return immediate.apply(this, args) }
            finally { delay() } // Native COMMIT/rollback has returned.
        } }
    })
    const check = clock.assertServerClockMatchesDatabaseSync
    t.mock.method(clock, 'assertServerClockMatchesDatabaseSync', connection => {
        assert.equal(connection.inTransaction, true)
        const result = check(connection)
        delay()
        return result
    })
    const result = { committed: true }
    assert.equal(run(() => { delay(); insert.run('complete'); return result }), result)
    assert.deepEqual(rows(), ['complete'])
    const { samples, observerErrors } = diagnostics.drainSlowOperationDiagnostics()
    assert.equal(observerErrors, 0)
    for (const phase of ['db.sync.begin', 'persistence.clock', 'db.sync.body', 'db.sync.commit', 'persistence.sync']) {
        const sample = samples.find(entry => entry.phase === phase)
        assert.ok(sample, `missing ${phase}: ${JSON.stringify(samples)}`)
        assert.ok(sample.wallMs >= 7, `${phase}: ${sample.wallMs}`)
        assert.equal(sample.domain, 'maintenance')
        assert.equal(sample.operation, 'sync_fixture')
        assert.equal(sample.failed, false)
    }
})

test('a real busy BEGIN is attributed to entry and never runs the callback', t => {
    const completed = observeBoundaries(t)
    const other = new Database(db.name)
    const timeout = db.pragma('busy_timeout', { simple: true })
    let called = false
    try {
        db.pragma('busy_timeout = 10')
        other.exec('BEGIN IMMEDIATE')
        assert.throws(() => run(() => { called = true }), error => error.code === 'SQLITE_BUSY')
        assert.equal(called, false)
        assert.equal(db.inTransaction, false)
        assert.deepEqual(completed, [{ phase: 'db.sync.begin', failed: true }])
        const samples = diagnostics.drainSlowOperationDiagnostics().samples
        assert.ok(samples.some(sample => sample.phase === 'db.sync.begin' && sample.failed))
        assert.ok(!samples.some(sample => sample.phase === 'db.sync.body' || sample.phase === 'db.sync.commit'))
    } finally {
        if (other.inTransaction) other.exec('ROLLBACK')
        other.close()
        db.pragma(`busy_timeout = ${timeout}`)
    }
    assert.equal(run(() => 42), 42)
})

test('clock rejection preserves the original error and rolls back before business writes', t => {
    const completed = observeBoundaries(t)
    const error = new Error('clock fixture rejection')
    let called = false
    const check = t.mock.method(clock, 'assertServerClockMatchesDatabaseSync', () => {
        insert.run('clock partial')
        delay()
        throw error
    })
    assert.throws(() => run(() => { called = true }), actual => actual === error)
    assert.equal(called, false)
    assert.deepEqual(rows(), [])
    assert.equal(db.inTransaction, false)
    assert.deepEqual(completed, [
        { phase: 'db.sync.begin', failed: false }, { phase: 'db.sync.rollback', failed: true },
    ])
    assert.ok(diagnostics.drainSlowOperationDiagnostics().samples.some(sample => sample.phase === 'persistence.clock' && sample.failed))
    check.mock.restore()
    assert.equal(run(() => 42), 42)
})

test('a caught inner failure retains savepoint rollback and successful outer writes', t => {
    const completed = observeBoundaries(t)
    const error = new Error('inner rejection')
    const result = { saved: true }
    assert.equal(run(() => {
        insert.run('outer before')
        assert.throws(() => run(() => { insert.run('inner partial'); throw error }), actual => actual === error)
        assert.equal(db.inTransaction, true)
        insert.run('outer after')
        return result
    }), result)
    assert.deepEqual(rows(), ['outer before', 'outer after'])
    assert.deepEqual(completed, [
        { phase: 'db.sync.begin', failed: false }, { phase: 'db.sync.commit', failed: false },
    ])
})

test('business failure rolls back all writes and preserves the exact thrown value', t => {
    const completed = observeBoundaries(t)
    const error = new Error('business rejection')
    assert.throws(() => run(() => {
        insert.run('outer partial')
        run(() => insert.run('inner complete'))
        throw error
    }), actual => actual === error)
    assert.deepEqual(rows(), [])
    assert.equal(db.inTransaction, false)
    assert.deepEqual(completed, [
        { phase: 'db.sync.begin', failed: false }, { phase: 'db.sync.rollback', failed: true },
    ])
    assert.equal(run(() => 42), 42)
})

test('native deferred constraint failure is a failed commit boundary with automatic rollback', t => {
    const completed = observeBoundaries(t)
    let bodyReturned = false
    assert.throws(() => run(() => {
        insert.run('partial before commit')
        db.prepare('INSERT INTO child VALUES (?)').run(999)
        bodyReturned = true
        return 'must not return'
    }), error => error.code === 'SQLITE_CONSTRAINT_FOREIGNKEY')
    assert.equal(bodyReturned, true)
    assert.deepEqual(rows(), [])
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM child').get().n, 0)
    assert.equal(db.inTransaction, false)
    assert.deepEqual(completed, [
        { phase: 'db.sync.begin', failed: false }, { phase: 'db.sync.commit', failed: true },
    ])
    assert.equal(run(() => 42), 42)
})

test('a thenable result still triggers the native rejection and rollback', t => {
    const completed = observeBoundaries(t)
    assert.throws(() => run(() => {
        insert.run('invalid async partial')
        return Promise.resolve('invalid')
    }), /Transaction function cannot return a promise/)
    assert.deepEqual(rows(), [])
    assert.equal(db.inTransaction, false)
    assert.deepEqual(completed, [
        { phase: 'db.sync.begin', failed: false }, { phase: 'db.sync.commit', failed: true },
    ])
})
