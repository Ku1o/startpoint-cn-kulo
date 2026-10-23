'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const Sqlite = require('better-sqlite3')
const { ContentOperationsStore, initializeContentOperationsSchema } = require('../out/lib/content-operations-store')

test('fixed July admin filter uses complete reference day rather than the old captured August candidate flag', t => {
    const db = new Sqlite(':memory:'); t.after(() => db.close()); initializeContentOperationsSchema(db)
    const start = Date.parse('2025-07-20T00:00:00+08:00'), end = start + 86400000
    const row = (id, originalStartMs, originalEndMs, windowCandidate, personalWindow = false) => ({
        key: `gacha:${id}`, type: 'gacha', id, name: String(id), source: 'fixture',
        originalStartMs, originalEndMs, originalExchangeEndMs: null, windowCandidate, browseCandidate: false, personalWindow,
    })
    const catalog = { schemaVersion: 1, source: { assetVersion: 'fixture', manifestSha256: 'fixture' },
        baselineTimeMs: Date.parse('2025-08-17T16:40:39Z'), baselineEvidence: 'different historical capture',
        missing: [], resources: {}, questMap: {}, rows: [
            row(1, start, end - 1000, false), row(2, null, null, false),
            row(3, end, end + 86400000, true), row(4, start + 1000, end, false),
            row(5, start - 86400000, start, false), row(6, null, null, true, true),
        ] }
    const store = new ContentOperationsStore(db, catalog, () => ['visible', 'enter'])
    const july = store.list({ referenceWindow: [start, end], offset: 1, limit: 1 })
    assert.equal(july.total, 2)
    assert.deepEqual(july.rows.map(value => value.key), ['gacha:2'])
    assert.deepEqual(store.list({ candidatesOnly: true }).rows.map(value => value.key), ['gacha:3', 'gacha:6'])
    assert.equal(store.state('gacha:1'), null, 'browsing reference candidates cannot create an operator decision')
})
