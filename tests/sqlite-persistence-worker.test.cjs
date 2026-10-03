const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const Database = require('better-sqlite3')
process.env.SQLITE_DIAGNOSTICS = 'true'

const {
    executeSqlitePersistenceCommand,
    startSqlitePersistenceWorker,
    stopSqlitePersistenceWorker,
    setSqlitePersistenceCheckpointOwner,
} = require('../out/lib/sqlite-persistence-worker.js')
const { collectMemoryDiagnostics } = require('../out/lib/memory-diagnostics')
const {
    configurePersistenceSqlExecutor,
    runPersistenceSqlCommand,
} = require('../out/lib/persistence-coordinator.js')

test('persistence worker serializes commands and rolls back a failed command', async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'startpoint-persistence-worker-'))
    const databasePath = path.join(directory, 'data.db')
    const setup = new Database(databasePath)
    setup.pragma('journal_mode = WAL')
    setup.exec('CREATE TABLE ledger (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
    setup.close()

    assert.equal(startSqlitePersistenceWorker(databasePath, {
        SQLITE_PERSISTENCE_WORKER: '1',
        SQLITE_PERSISTENCE_BUSY_TIMEOUT_MS: '0',
        SQLITE_PERSISTENCE_MAX_ATTEMPTS: '2',
        SQLITE_SYNCHRONOUS: 'FULL',
        SQLITE_CACHE_KIB: '32768',
        SQLITE_MMAP_MIB: '64',
    }), true)
    const settings = () => collectMemoryDiagnostics().counters.sqlitePersistence
    const until = async predicate => {
        const deadline = Date.now() + 5000
        while (Date.now() < deadline) {
            if (predicate()) return
            await new Promise(resolve => setTimeout(resolve, 20))
        }
        assert.fail(`worker settings unavailable: ${JSON.stringify(settings())}`)
    }
    await until(() => settings()?.walAutocheckpoint === 1000)
    collectMemoryDiagnostics()
    await new Promise(resolve => setTimeout(resolve, 50))
    const firstWorkerSample = collectMemoryDiagnostics().workers
        .find(worker => worker.name === 'sqlite-persistence')
    await new Promise(resolve => setTimeout(resolve, 50))
    const secondWorkerSample = collectMemoryDiagnostics().workers
        .find(worker => worker.name === 'sqlite-persistence')
    assert.equal(firstWorkerSample?.counters.failed, 0)
    assert.equal(secondWorkerSample?.counters.failed, 0)
    assert.equal(settings().synchronous, 2)
    assert.equal(settings().cacheSize, -32768)
    assert.equal(settings().mmapSize, 64 * 1024 * 1024)
    setSqlitePersistenceCheckpointOwner(true)
    await until(() => settings()?.walAutocheckpoint === 0)
    setSqlitePersistenceCheckpointOwner(false)
    await until(() => settings()?.walAutocheckpoint === 1000)

    const first = executeSqlitePersistenceCommand({
        operation: 'test_first',
        statements: [{ sql: 'INSERT INTO ledger (value) VALUES (?)', params: ['first'] }],
    })
    const second = executeSqlitePersistenceCommand({
        operation: 'test_second',
        statements: [{ sql: 'INSERT INTO ledger (value) VALUES (?)', params: ['second'] }],
    })
    assert.equal((await first).changes, 1)
    assert.equal((await second).changes, 1)

    configurePersistenceSqlExecutor(async (context, statements) => {
        await executeSqlitePersistenceCommand({ operation: context.operation, statements })
    })
    let fallbackCalled = false
    await runPersistenceSqlCommand({ domain: 'account', operation: 'test_coordinator_command' }, [{
        sql: 'INSERT INTO ledger (value) VALUES (?)', params: ['coordinator'],
    }], () => { fallbackCalled = true })
    assert.equal(fallbackCalled, false)

    await assert.rejects(
        executeSqlitePersistenceCommand({
            operation: 'test_rollback',
            statements: [
                { sql: 'INSERT INTO ledger (value) VALUES (?)', params: ['rolled-back'] },
                { sql: 'INSERT INTO missing_table (value) VALUES (?)', params: ['failure'] },
            ],
        }),
        /missing_table/,
    )

    const verify = new Database(databasePath)
    assert.deepEqual(
        verify.prepare('SELECT value FROM ledger ORDER BY id').all().map(row => row.value),
        ['first', 'second', 'coordinator'],
    )
    verify.close()
    configurePersistenceSqlExecutor(null)
    await stopSqlitePersistenceWorker()
    fs.rmSync(directory, { recursive: true, force: true })
    console.log('sqlite persistence worker tests passed')
})
