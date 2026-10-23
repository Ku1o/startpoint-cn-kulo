'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict'), path = require('node:path')
const { createHash } = require('node:crypto'), Sqlite = require('better-sqlite3')
if (!process.env.STARPOINT_TEST_OUT_DIR) require('ts-node/register/transpile-only')
const base = process.env.STARPOINT_TEST_OUT_DIR || path.join(__dirname, '../src')
const { ContentOperationsStore, initializeContentOperationsSchema } = require(path.join(base, 'lib/content-operations-store'))
const { completeExistingHistoryReviewsOfflineSync, prepareReviewedHistoryOfflineSync, runReviewedHistoryBatchOfflineSync } = require(path.join(base, 'lib/content-history-bootstrap'))
const now = 1792540800000, sha = value => createHash('sha256').update(value).digest('hex')
const action = (enabled = true, extra = {}) => ({ enabled, endsAtMs: null, readiness: 'verified', evidence: 'Synthetic exact native rule review', ...extra })
function fixture(t) {
    const db = new Sqlite(':memory:'); t.after(() => db.close()); initializeContentOperationsSchema(db)
    db.exec("CREATE TABLE earned_progress(value TEXT); INSERT INTO earned_progress VALUES('claims and inventory retained')")
    const rows = ['story_event:1', 'pass_card_event:15', 'event_item_shop:1', 'gacha:700000', 'active_mission_event:150'].map(key => ({
        key, type: key.split(':')[0], id: Number(key.split(':')[1]), name: key, source: 'synthetic',
        originalStartMs: null, originalEndMs: null, originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false,
        ...(key === 'event_item_shop:1' ? { parentKey: 'story_event:1' } : {}),
    }))
    const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' },
        baselineTimeMs: 0, baselineEvidence: 'synthetic only', missing: [], resources: {},
        questMap: { '2:1': 'story_event:1', '2:2': 'story_event:1' },
        missionMap: { '7:1': 'pass_card_event:15', '0:15000': 'active_mission_event:150' }, rows }
    const caps = row => row.type === 'event_item_shop' ? ['visible', 'exchange'] : row.type === 'gacha' ? ['exchange']
        : row.type === 'story_event' ? ['visible', 'enter', 'claim', 'exchange'] : ['visible', 'enter', 'claim']
    const store = new ContentOperationsStore(db, catalog, caps, row => ({ digest: sha(row.key), matchesCatalog: true }))
    const update = (key, actionOverrides) => store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Synthetic original reviewed state', actionOverrides }, now)
    const raw = key => db.prepare('SELECT value_json FROM content_operations_state WHERE content_key=?').get(key).value_json
    const upgrade = (key, actionOverrides, extra = {}) => ({ key, previousRawSha256: sha(raw(key)), actionOverrides, ...extra })
    const complete = upgrades => completeExistingHistoryReviewsOfflineSync(store,
        { schemaVersion: 1, catalogDigest: store.digest, evidenceDigest: 'b'.repeat(64), upgrades }, { expectedRevision: store.revision(), nowMs: now })
    const prepare = (candidates, approvedExistingOwners) => prepareReviewedHistoryOfflineSync(store,
        { schemaVersion: 1, catalogDigest: store.digest, evidenceDigest: 'c'.repeat(64), candidates, approvedExistingOwners },
        { expectedRevision: store.revision(), nowMs: now })
    return { db, store, update, raw, upgrade, complete, prepare }
}

test('explicit native review completes members and missing exchange while keeping the current instance and publication', t => {
    const f = fixture(t), before = f.update('story_event:1', { visible: action(), enter: action(true, { questKeys: ['2:1'] }) })
    f.complete([f.upgrade(before.key, { enter: action(true, { questKeys: ['2:1', '2:2'] }), exchange: action() })])
    const after = f.store.state(before.key)
    assert.equal(after.instanceId, before.instanceId); assert.equal(after.published, before.published)
    assert.equal(f.store.scopedAllowed(before.key, 'quest', '2:2', 'enter', now), true)
    assert.equal(f.store.allowed(before.key, 'exchange', now), true)
    assert.equal(f.db.prepare('SELECT value FROM earned_progress').get().value, 'claims and inventory retained')
})

test('a claim-only historical pass gains reviewed participation while staying closed until an explicit publication', t => {
    const f = fixture(t), key = 'pass_card_event:15'
    f.update(key, { visible: action(false, { readiness: 'unverified' }), enter: action(false, { readiness: 'unverified' }),
        claim: action(true, { missionKeys: ['7:1'] }) })
    const delta = { visible: action(), enter: action(true, { missionKeys: ['7:1'] }) }
    assert.throws(() => f.complete([f.upgrade(key, delta)]), /默认关闭/)
    f.complete([f.upgrade(key, delta, { defaultClosed: true })])
    assert.equal(f.store.allowed(key, 'visible', now), false); assert.equal(f.store.allowed(key, 'enter', now), false)
    assert.equal(f.store.allowed(key, 'claim', now), true)
    f.store.setPublished(key, { expectedRevision: f.store.revision(), catalogDigest: f.store.digest, published: true, reason: 'Explicit synthetic activation' }, now)
    assert.equal(f.store.allowed(key, 'enter', now), true)
})

test('scope removal and stale later entries roll all metadata and audit writes back', t => {
    const f = fixture(t), key = 'story_event:1'
    f.update(key, { visible: action(), enter: action(true, { questKeys: ['2:1', '2:2'] }) })
    const before = f.raw(key), revision = f.store.revision(), audit = f.store.audit({}).rows
    assert.throws(() => f.complete([f.upgrade(key, { enter: action(true, { questKeys: ['2:1'] }) })]), /删除既有成员/)
    const first = f.upgrade(key, { exchange: action() }), stale = { ...first, key: 'pass_card_event:15', previousRawSha256: '0'.repeat(64) }
    assert.throws(() => f.complete([first, stale]), /配置已变化/)
    assert.equal(f.raw(key), before); assert.equal(f.store.revision(), revision); assert.deepEqual(f.store.audit({}).rows, audit)
})

test('a new product under an open owner needs an exact owner review and explicit exchange permission', t => {
    const f = fixture(t), parent = 'story_event:1', product = { key: 'event_item_shop:1', actionOverrides: { visible: action(), exchange: action() } }
    f.update(parent, { visible: action(), enter: action(true, { questKeys: ['2:1'] }) })
    const owner = () => [{ key: parent, rawSha256: sha(f.raw(parent)) }]
    assert.throws(() => f.prepare([product], owner()), /隶属已经关闭/)
    assert.equal(f.store.state(product.key), null)
    f.complete([f.upgrade(parent, { exchange: action() })])
    assert.throws(() => f.prepare([product], [{ key: parent, rawSha256: '0'.repeat(64) }]), /隶属已经关闭/)
    const before = f.raw(parent)
    f.prepare([product], owner())
    assert.equal(f.raw(parent), before); assert.equal(f.store.allowed(product.key, 'exchange', now), true)
})

test('review completion preserves finite deadlines and explicit verified action closures', t => {
    const f = fixture(t), key = 'story_event:1', deadline = now + 10000
    f.update(key, { visible: action(), enter: action(true, { questKeys: ['2:1'], endsAtMs: deadline }), exchange: action(false) })
    const before = f.raw(key), revision = f.store.revision()
    assert.throws(() => f.complete([f.upgrade(key, { enter: action(true, { questKeys: ['2:1', '2:2'] }) })]), /原生规则依据/)
    assert.throws(() => f.complete([f.upgrade(key, { exchange: action() })]), /明确关闭/)
    assert.equal(f.raw(key), before); assert.equal(f.store.revision(), revision)
    f.complete([f.upgrade(key, { enter: action(true, { questKeys: ['2:1', '2:2'], endsAtMs: deadline }) })])
    assert.equal(f.store.state(key).actionOverrides.enter.endsAtMs, deadline)
    assert.equal(f.store.allowed(key, 'exchange', now), false)
})

test('retained rights prepare only the explicitly deferred personal pools and return event without new participation', t => {
    const f = fixture(t)
    f.prepare([{ key: 'gacha:700000', mode: 'retained_rights', actionOverrides: { exchange: action() } },
        { key: 'active_mission_event:150', mode: 'retained_rights', actionOverrides: { claim: action(true, { missionKeys: ['0:15000'] }) } }])
    assert.equal(f.store.allowed('gacha:700000', 'exchange', now), true)
    assert.equal(f.store.allowed('gacha:700000', 'enter', now), false)
    assert.equal(f.store.allowed('active_mission_event:150', 'enter', now), false)
    assert.equal(f.store.allowed('active_mission_event:150', 'claim', now), true)
})

test('an implicit whole-member scope and an exchange-only open owner cannot be narrowed by preparation', t => {
    const f = fixture(t), key = 'story_event:1'
    f.update(key, { visible: action(), enter: action(true, { questKeys: null }) })
    const legacy = JSON.parse(f.raw(key)); delete legacy.actionOverrides.enter.questKeys
    f.db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(legacy), key)
    const before = f.raw(key)
    assert.equal(f.store.scopedAllowed(key, 'quest', '2:2', 'enter', now), true)
    assert.throws(() => f.complete([f.upgrade(key, { enter: action(true, { questKeys: ['2:1'] }) })]), /不得缩小/)
    assert.equal(f.raw(key), before)
    f.update(key, { visible: action(false, { readiness: 'unverified' }), enter: action(false, { readiness: 'unverified' }), exchange: action() })
    const retained = f.raw(key), revision = f.store.revision()
    assert.throws(() => f.complete([f.upgrade(key, { visible: action(), enter: action(true, { questKeys: ['2:1', '2:2'] }) }, { defaultClosed: true })]), /既有兑换权限/)
    assert.equal(f.raw(key), retained); assert.equal(f.store.revision(), revision); assert.equal(f.store.allowed(key, 'exchange', now), true)
})

test('the guarded offline batch permits staged savepoints and rolls earlier stages back on a later failure', t => {
    const f = fixture(t), key = 'story_event:1'
    f.update(key, { visible: action(), enter: action(true, { questKeys: ['2:1'] }) })
    const before = f.raw(key), revision = f.store.revision(), delta = () => f.upgrade(key, { exchange: action() })
    assert.throws(() => f.db.transaction(() => f.complete([delta()]))(), /outside a transaction/)
    assert.throws(() => runReviewedHistoryBatchOfflineSync(f.store, { expectedRevision: revision }, () => {
        f.complete([delta()])
        f.prepare([{ key: 'event_item_shop:999999', actionOverrides: { exchange: action() } }])
    }), /不存在/)
    assert.equal(f.raw(key), before); assert.equal(f.store.revision(), revision)
    runReviewedHistoryBatchOfflineSync(f.store, { expectedRevision: revision }, () => {
        f.complete([delta()])
        f.prepare([{ key: 'event_item_shop:1', actionOverrides: { visible: action(), exchange: action() } }],
            [{ key, rawSha256: sha(f.raw(key)) }])
    })
    assert.equal(f.store.allowed('event_item_shop:1', 'exchange', now), true)
    // Callback completion removes the private permission to bypass the outer guard.
    assert.throws(() => f.db.transaction(() => f.complete([delta()]))(), /outside a transaction/)
})
