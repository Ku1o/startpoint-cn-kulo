const { test, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'slow-persistence-'))
process.env.DATA_DIR = directory
process.env.CN_WRITER_THREAD = '0'
process.env.SLOW_OPERATION_DIAGNOSTICS = 'true'
process.env.SLOW_OPERATION_MS = '1'
process.env.ROUTE_PERF_SUMMARY = 'true'
process.env.SQLITE_COMMIT_DIAGNOSTICS = 'false'

const coordinator = require('../out/lib/persistence-coordinator')
const { persistenceWriteGate } = require('../out/lib/persistence-write-gate')
const { drainSlowOperationDiagnostics } = require('../out/lib/slow-operation-diagnostics')
const db = require('../out/data/db').getDb()
db.exec('CREATE TABLE slow_fixture(value TEXT)')
const insert = db.prepare('INSERT INTO slow_fixture VALUES (?)')
const timer = new Int32Array(new SharedArrayBuffer(4))
function shortBlockingWork() {
    Atomics.wait(timer, 0, 0, 5)
}

after(async () => {
    await coordinator.drainPersistence()
    db.close()
    const resolvedDirectory = fs.realpathSync(directory)
    assert.equal(path.dirname(resolvedDirectory), fs.realpathSync(os.tmpdir()))
    assert.match(path.basename(resolvedDirectory), /^slow-persistence-[a-zA-Z0-9]+$/)
    fs.rmSync(resolvedDirectory, { recursive: true })
})

test('real persistence phases follow interleaved commands through the gate, queue, yield and transaction', async () => {
    drainSlowOperationDiagnostics()
    const release = await persistenceWriteGate.acquire(true)
    const firstResult = { committed: true }
    const legacyResult = { legacy: true }
    const secondError = new Error('private rollback detail')
    const legacyError = new Error('legacy private rollback detail')
    const first = coordinator.runPersistenceTransaction({ domain: 'maintenance', operation: 'first' }, () => {
        shortBlockingWork()
        insert.run('first commit')
        return firstResult
    })
    const second = coordinator.runPersistenceTransaction({ domain: 'mail', operation: 'second' }, () => {
        shortBlockingWork()
        insert.run('second rollback')
        throw secondError
    })
    const outcomes = Promise.allSettled([first, second])

    try {
        await new Promise(resolve => setImmediate(resolve))
        assert.equal(persistenceWriteGate.stats().waiting, 1)
        shortBlockingWork()
        // This blocks the next check-phase turn before the admitted transaction resumes.
        setImmediate(shortBlockingWork)
        release()

        assert.equal(coordinator.runPersistenceTransactionSync({ domain: 'admin', operation: 'legacy:private-suffix' }, () => {
            shortBlockingWork()
            insert.run('legacy commit')
            return legacyResult
        }), legacyResult)
        assert.throws(() => coordinator.runPersistenceTransactionSync({ domain: 'admin', operation: 'legacy_failed' }, () => {
            shortBlockingWork()
            insert.run('legacy rollback')
            throw legacyError
        }), error => error === legacyError)

        assert.deepEqual(await outcomes, [
            { status: 'fulfilled', value: firstResult },
            { status: 'rejected', reason: secondError },
        ])
        assert.equal(await first, firstResult)
        assert.deepEqual(db.prepare('SELECT value FROM slow_fixture ORDER BY rowid').pluck().all(), [
            'legacy commit', 'first commit',
        ])

        const { samples } = drainSlowOperationDiagnostics()
        function requirePhase(domain, operation, phase, kind, failed = false) {
            const sample = samples.find(entry => entry.operation === operation && entry.phase === phase)
            assert.ok(sample, 'missing phase ' + operation + '/' + phase + ' in ' + JSON.stringify(samples))
            assert.equal(sample.domain, domain)
            assert.equal(sample.kind, kind)
            assert.equal(sample.failed, failed)
            assert.ok(sample.wallMs >= 1)
            if (kind === 'wait') assert.equal(sample.threadCpuMs, null)
        }
        requirePhase('maintenance', 'first', 'persistence.gate', 'wait')
        requirePhase('maintenance', 'first', 'persistence.yield', 'wait')
        requirePhase('maintenance', 'first', 'db.body', 'sync')
        requirePhase('mail', 'second', 'persistence.order', 'wait')
        requirePhase('mail', 'second', 'db.body', 'sync', true)
        requirePhase('admin', 'legacy', 'db.sync.body', 'sync')
        requirePhase('admin', 'legacy_failed', 'db.sync.body', 'sync', true)
        assert.doesNotMatch(JSON.stringify(samples), /private-suffix|rollback detail/)
    } finally {
        release()
        await outcomes
    }
})
