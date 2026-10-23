'use strict'
require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const Sqlite = require('better-sqlite3')
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require('../src/lib/content-operations-store')

function fixture(t, count = 245) {
    const queries = []
    const db = new Sqlite(':memory:', { verbose: sql => queries.push(sql) })
    t.after(() => db.close())
    initializeContentOperationsSchema(db)
    db.exec("CREATE TABLE retained_progress(value TEXT); INSERT INTO retained_progress VALUES('paid-qualified-claimed')")
    const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' },
        baselineTimeMs: 0, baselineEvidence: 'synthetic', missing: [], resources: {}, questMap: {},
        rows: Array.from({ length: count }, (_, id) => ({ key: `gacha:${id}`, type: 'gacha', id, name: `Synthetic ${id}`,
            originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: null, windowCandidate: false,
            browseCandidate: false, source: 'synthetic', definitionDigest: `synthetic-${id}` })) }
    const store = new ContentOperationsStore(db, catalog, () => CONTENT_ACTIONS)
    const controls = db.prepare('INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?)')
    db.transaction(() => {
        for (const row of catalog.rows) controls.run(row.key, JSON.stringify({ key: row.key, instanceId: `${row.key}:original`,
            readiness: 'verified', evidence: 'Synthetic reviewed evidence', flags: { visible: true, enter: true, claim: true, exchange: true },
            endsAtMs: null, revision: 0, catalogDigest: store.digest, contentDigest: store.contentDigests.get(row.key) }))
    })()
    let decoded = 0
    const decode = store.decodeState.bind(store)
    store.decodeState = (...args) => { decoded++; return decode(...args) }
    queries.length = 0
    return { store, db, queries, decoded: () => decoded }
}

test('one request snapshot decodes each stored state once, including repeated pages and linked lookups', t => {
    const { store, queries, decoded } = fixture(t)
    const snapshot = store.managementSnapshot()
    assert.equal(snapshot.all().rows.length, 245)
    assert.equal(snapshot.list({ offset: 200, limit: 200 }).rows.length, 45)
    assert.equal(snapshot.list({ readiness: 'verified', search: 'Synthetic 244' }).rows[0].key, 'gacha:244')
    assert.equal(snapshot.row('gacha:1').effectiveFlags.enter, true)
    assert.equal(snapshot.state('gacha:1').instanceId, 'gacha:1:original')
    assert.equal(decoded(), 245, 'all controls are decoded exactly once, not once per type or page')
    assert.equal(queries.filter(sql => /SELECT content_key,value_json FROM content_operations_state/.test(sql)).length, 1)
    assert.equal(queries.filter(sql => /SELECT revision FROM content_operations_meta/.test(sql)).length, 1)
})

test('member pages do not decode controls outside the returned page and repeated keys reuse their decode', t => {
    const { store, decoded } = fixture(t)
    const snapshot = store.managementSnapshot()
    assert.equal(decoded(), 0)
    assert.equal(snapshot.list({ limit: 5, offset: 200 }).total, 245)
    assert.equal(decoded(), 5)
    snapshot.row('gacha:200'); snapshot.state('gacha:200')
    assert.equal(decoded(), 5)
})

test('deadline passes without a revision change; old request stays internally consistent and next request expires', t => {
    const { store, db } = fixture(t, 1), key = 'gacha:0'
    const originalNow = Date.now
    t.after(() => { Date.now = originalNow })
    const saved = store.state(key)
    saved.endsAtMs = 1000
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(saved), key)
    Date.now = () => 1000
    const before = store.managementSnapshot()
    Date.now = () => 1001
    assert.equal(before.nowMs, 1000)
    assert.equal(before.row(key).effectiveFlags.enter, true)
    assert.equal(before.list().rows[0].effectiveFlags.enter, true)
    const after = store.managementSnapshot()
    assert.equal(after.revision, before.revision)
    assert.equal(after.row(key).effectiveFlags.enter, false)
    assert.equal(store.allowed(key, 'enter', 1001), false, 'business guard uses its current time independently')
})

test('read snapshot does not authorize stale CAS writes or change retained player data', t => {
    const { store, db } = fixture(t, 1), key = 'gacha:0'
    const snapshot = store.managementSnapshot()
    const body = { expectedRevision: snapshot.revision, catalogDigest: store.digest, reason: 'Synthetic CAS request', published: false }
    store.setPublished(key, body, Date.now())
    assert.equal(snapshot.revision, 0)
    assert.equal(snapshot.row(key).effectiveFlags.enter, true)
    assert.equal(store.managementSnapshot().row(key).effectiveFlags.enter, false)
    assert.throws(() => store.setPublished(key, { ...body, published: true }, Date.now()), error => error.statusCode === 409)
    assert.equal(store.state(key).published, false)
    assert.equal(db.prepare('SELECT value FROM retained_progress').get().value, 'paid-qualified-claimed')
})

test('an outer linked-update transaction still rolls back both controls and audit after its second failure', t => {
    const { store, db } = fixture(t, 2)
    const snapshot = store.managementSnapshot(), original = store.state('gacha:0')
    assert.throws(() => db.transaction(() => {
        store.setPublished('gacha:0', { expectedRevision: snapshot.revision, catalogDigest: store.digest,
            reason: 'Synthetic linked first side', published: false }, Date.now())
        store.setPublished('gacha:1', { expectedRevision: snapshot.revision, catalogDigest: store.digest,
            reason: 'Synthetic linked stale second side', published: false }, Date.now())
    })(), error => error.statusCode === 409)
    assert.equal(store.revision(), snapshot.revision)
    assert.deepEqual(store.state('gacha:0'), original)
    assert.equal(store.state('gacha:1').published, undefined)
    assert.equal(db.prepare('SELECT count(*) AS n FROM content_operations_audit').get().n, 0)
})
