'use strict'
require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const Sqlite = require('better-sqlite3')
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require('../src/lib/content-operations-store')
const { defaultContentDecision } = require('../src/lib/content-operations-defaults')
const { projectReleaseClosedSnapshot } = require('../src/lib/content-release-restrictions')
const now = 1800000000000
function fixture(t, policy = defaultContentDecision) {
    const db = new Sqlite(':memory:'); t.after(() => db.close()); initializeContentOperationsSchema(db)
    const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' },
        baselineTimeMs: 0, baselineEvidence: 'synthetic', resources: {}, missing: [], questMap: {},
        rows: [1, 2].map(id => ({ key: `gacha:${id}`, type: 'gacha', id, name: `synthetic-${id}`,
            originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: null, source: 'synthetic', windowCandidate: false, browseCandidate: false })) }
    const store = new ContentOperationsStore(db, catalog, () => CONTENT_ACTIONS, () => ({ digest: 'synthetic', matchesCatalog: true }),
        undefined, undefined, undefined, policy, undefined, projectReleaseClosedSnapshot)
    const update = body => store.update('gacha:1', { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'synthetic hotpath verification', ...body }, now)
    update({ readiness: 'verified', evidence: 'synthetic evidence', flags: { visible: true, enter: true, claim: true, exchange: true }, endsAtMs: now + 1000 })
    return { db, store, catalog, update }
}
test('login snapshots read fresh time/revision/raw state, including rollback and damaged JSON', t => {
    const { db, store, update } = fixture(t)
    const first = store.snapshot(now)
    assert.equal(first.states.find(s => s.key === 'gacha:1').enter, true)
    assert.equal(store.snapshot(now + 1001).states.find(s => s.key === 'gacha:1').enter, false)
    assert.equal(store.snapshot(now + 1001).revision, first.revision)
    update({ flags: { enter: false } })
    assert.equal(store.snapshot(now).states.find(s => s.key === 'gacha:1').enter, false)
    assert.equal(store.snapshot(now).revision, first.revision + 1)
    assert.throws(() => db.transaction(() => {
        update({ flags: { enter: true } })
        assert.equal(store.snapshot(now).states.find(s => s.key === 'gacha:1').enter, true)
        throw Error('rollback')
    })(), /rollback/)
    assert.equal(store.snapshot(now).states.find(s => s.key === 'gacha:1').enter, false)
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run('{broken', 'gacha:1')
    assert.equal(store.snapshot(now).states.find(s => s.key === 'gacha:1').exchange, false)
})
test('cached default templates cannot be polluted by a prior response and revoke changed runtime rights', t => {
    const { store, catalog } = fixture(t)
    const original = store.snapshot(now), expected = structuredClone(original)
    original.default_policy.actions.visible.closed_keys.length = 0
    original.default_policy.actions.exchange.qualified_rights_keys.push('gacha:fake')
    original.default_policy.actions.claim.legacy_keys.push('fake:claim')
    original.catalog[0].quest_keys.push('1:fake')
    original.states[0].actions.exchange.enabled = false
    assert.deepEqual(store.snapshot(now), expected)
    const runtime = store.runtimeDefinitions.get('gacha:1')
    store.runtimeDefinitions.set('gacha:1', { ...runtime, matchesCatalog: false })
    const changed = store.snapshot(now)
    assert.equal(changed.default_policy.actions.exchange.qualified_rights_keys.includes('gacha:1'), false)
    assert.equal(changed.default_policy.actions.exchange.closed_keys.includes('gacha:1'), true)
    store.runtimeDefinitions.set('gacha:1', runtime)
    assert.deepEqual(store.snapshot(now), expected)
    const other = new ContentOperationsStore(store.db, { ...catalog, resources: { changed: { sha256: 'new' } } }, () => CONTENT_ACTIONS,
        undefined, undefined, undefined, undefined, defaultContentDecision)
    assert.notEqual(other.digest, store.digest)
    assert.equal(other.snapshot(now).states[0].enter, false)
})
test('custom default policies are evaluated each time instead of treated as immutable production policy', t => {
    let decision = true
    const { store } = fixture(t, () => decision)
    assert.ok(store.snapshot(now).default_policy.actions.visible.qualified_rights_keys.includes('gacha:2'))
    decision = false
    assert.ok(store.snapshot(now).default_policy.actions.visible.closed_keys.includes('gacha:2'))
})
test('unknown policy shapes retain deep-clone isolation in restriction projection', () => {
    const original = { schema_version: 2, full_snapshot: true, revision: 1, catalog_digest: 'synthetic', server_time_ms: now,
        states: [], catalog: [], default_policy: { extra: { nested: ['retained'] }, actions: {} } }
    const projected = projectReleaseClosedSnapshot(original)
    projected.default_policy.extra.nested.push('changed')
    assert.deepEqual(original.default_policy.extra.nested, ['retained'])
})
