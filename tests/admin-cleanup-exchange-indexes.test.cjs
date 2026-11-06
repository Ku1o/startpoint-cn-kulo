'use strict'
require('ts-node/register/transpile-only')
const assert = require('node:assert/strict')
const { test } = require('node:test')
const Database = require('better-sqlite3')
const initialize = require('../src/data/initializers/wdfpData').default
const { ensureCascadeDeleteIndexes, findMissingCascadeDeleteIndexes } = require('../src/lib/admin-account-cleanup')

const tables = ['players_exchange_campaign_receipts', 'players_special_exchange_campaigns']
const indexName = table => `idx_cleanup_fk_${table}_0`

test('exchange tables added to an existing database include player deletion indexes immediately', () => {
    const db = new Database(':memory:')
    try {
        initialize(db, false)
        ensureCascadeDeleteIndexes(db)
        db.exec('CREATE TABLE preserved_fixture(value TEXT); INSERT INTO preserved_fixture VALUES (\'keep\')')
        for (const table of tables) db.exec(`DROP TABLE ${table}`)
        initialize(db, true)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db), [])
        for (const table of tables) {
            assert.deepEqual(db.prepare(`PRAGMA index_info(${indexName(table)})`).all().map(row => row.name), ['player_id'])
        }
        assert.deepEqual(db.prepare('SELECT * FROM preserved_fixture').all(), [{ value: 'keep' }])
    } finally { db.close() }
})

test('existing exchange tables remain unchanged until explicit offline index maintenance', () => {
    const db = new Database(':memory:')
    try {
        initialize(db, false)
        ensureCascadeDeleteIndexes(db)
        for (const table of tables) db.exec(`DROP INDEX ${indexName(table)}`)
        const before = db.prepare('SELECT type,name,sql FROM sqlite_schema ORDER BY type,name').all()
        initialize(db, true)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db).map(index => index.table), tables)
        assert.deepEqual(db.prepare('SELECT type,name,sql FROM sqlite_schema ORDER BY type,name').all(), before,
            'normal initialization must not build indexes on existing potentially populated tables')
        assert.equal(ensureCascadeDeleteIndexes(db), 2)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db), [])
    } finally { db.close() }
})
