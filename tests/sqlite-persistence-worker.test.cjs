const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const Database = require('better-sqlite3')

const {
    executeSqlitePersistenceCommand,
    startSqlitePersistenceWorker,
    stopSqlitePersistenceWorker,
} = require('../out/lib/sqlite-persistence-worker.js')
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
    }), true)

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
