'use strict'
if (process.env.STARPOINT_TEST_COMPILED !== '1') require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const Sqlite = require('better-sqlite3')
const { pack, unpack } = require('msgpackr')
const root = '../' + (process.env.STARPOINT_TEST_COMPILED === '1' ? 'out' : 'src') + '/lib/'
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require(root + 'content-operations-store')
const { defaultContentDecision } = require(root + 'content-operations-defaults')
const { projectReleaseClosedSnapshot } = require(root + 'content-release-restrictions')
const { cachedContentOperationsSnapshot, clearContentOperationsSnapshotCache } = require(root + 'content-operations-snapshot-cache')
const { encodeCnResponse } = require(root + 'cn-response-encoding')
const restriction = require('../assets/quest_shop_availability_cnmod.json')
const now = Date.parse('2026-10-31T00:00:00Z')
const open = { readiness: 'verified', evidence: 'isolated cache fixture', flags: { visible: true, enter: true, claim: true, exchange: true }, endsAtMs: null }
const normalizeTime = snapshot => ({ ...snapshot, server_time_ms: 0 })

function fixture(t) {
    clearContentOperationsSnapshotCache()
    const db = new Sqlite(':memory:')
    t.after(() => { clearContentOperationsSnapshotCache(); db.close() })
    initializeContentOperationsSchema(db)
    const row = (type, id, extra = {}) => ({ key: `${type}:${id}`, type, id, name: 'cache fixture',
        originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: 3,
        windowCandidate: false, browseCandidate: false, source: 'synthetic', ...extra })
    const [shopType, shopId] = restriction.closedShopKeys[0].split(':')
    const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' },
        baselineTimeMs: 0, baselineEvidence: 'synthetic', resources: {}, missing: [],
        rows: [row('gacha', 1), row('gacha', 2), row('pass_card_event', 15), row('mission_daily', 14),
            row('hard_multi_event', 2088), row(shopType, Number(shopId))],
        questMap: { [restriction.managedQuestKeys[0]]: 'hard_multi_event:2088', '26:9000001': 'hard_multi_event:2088' },
        missionMap: { '6:60': 'pass_card_event:15', '2:14': 'mission_daily:14' } }
    const serverActions = [...CONTENT_ACTIONS]
    const store = new ContentOperationsStore(db, catalog, () => serverActions,
        () => ({ digest: 'synthetic', matchesCatalog: true }), row => ({ kind: 'fixture', id: row.id }),
        () => ['visible', 'enter', 'claim', 'exchange'], undefined, defaultContentDecision, undefined, projectReleaseClosedSnapshot)
    const update = (key, body) => store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'isolated cache verification', ...body }, now)
    let fullReads = 0
    const prepare = db.prepare.bind(db)
    db.prepare = sql => {
        if (sql === 'SELECT content_key,value_json FROM content_operations_state ORDER BY content_key') fullReads++
        return prepare(sql)
    }
    return { db, store, update, serverActions, fullReads: () => fullReads }
}

test('cache preserves the complete default policy and restriction projection while hits skip the full read', t => {
    const { store, update, fullReads } = fixture(t)
    update('gacha:1', open)
    update('hard_multi_event:2088', { ...open, questKeys: [restriction.managedQuestKeys[0], '26:9000001'] })
    update(restriction.closedShopKeys[0], open)
    const fresh = store.snapshot(now)
    const first = cachedContentOperationsSnapshot(store, now)
    const count = fullReads()
    const hit = cachedContentOperationsSnapshot(store, now + 5000)
    assert.equal(fullReads(), count)
    assert.equal(hit.server_time_ms, now + 5000)
    assert.equal(JSON.stringify(normalizeTime(hit)), JSON.stringify(normalizeTime(fresh)))
    assert.deepEqual(pack(normalizeTime(hit)), pack(normalizeTime(fresh)))
    assert.notEqual(first, hit)
    assert.ok(hit.default_policy.actions.exchange.qualified_rights_keys.includes('gacha:2'))
    const closed = hit.states.find(state => state.key === 'closed_boss_quests:1')
    assert.deepEqual(closed.quest_keys, restriction.managedQuestKeys)
    assert.equal(closed.actions.enter.enabled, false)
    assert.equal(hit.states.find(state => state.key === restriction.closedShopKeys[0]).actions.exchange.enabled, false)
    assert.deepEqual(hit.catalog.find(row => row.key === 'hard_multi_event:2088').quest_keys, ['26:9000001'])
})

test('committed revision changes are visible to the next request', t => {
    const { store, update, fullReads } = fixture(t)
    update('gacha:1', open)
    const first = cachedContentOperationsSnapshot(store, now)
    const count = fullReads()
    update('gacha:1', { flags: { visible: false, enter: false } })
    const next = cachedContentOperationsSnapshot(store, now + 1)
    assert.equal(next.revision, first.revision + 1)
    assert.equal(fullReads(), count + 1)
    assert.equal(next.states.find(state => state.key === 'gacha:1').enter, false)
    assert.deepEqual(next, store.snapshot(now + 1))
})

test('cache crosses independent action deadlines at the same inclusive boundary as the store and handles backwards time', t => {
    const { store, update, fullReads } = fixture(t)
    update('gacha:1', { actionOverrides: Object.fromEntries(['visible', 'enter', 'exchange'].map(action => [action,
        { enabled: true, endsAtMs: now + (action === 'exchange' ? 2000 : 1000), readiness: 'verified', evidence: 'action deadline fixture' }])) })
    const first = cachedContentOperationsSnapshot(store, now)
    const count = fullReads()
    for (const time of [now + 999, now + 1000]) {
        assert.equal(cachedContentOperationsSnapshot(store, time).states[0].enter, true)
        assert.equal(fullReads(), count)
    }
    const expired = cachedContentOperationsSnapshot(store, now + 1001)
    assert.equal(expired.revision, first.revision)
    assert.equal(expired.states[0].enter, false)
    assert.equal(expired.states[0].exchange, true)
    assert.equal(cachedContentOperationsSnapshot(store, now + 2000).states[0].exchange, true)
    assert.equal(cachedContentOperationsSnapshot(store, now + 2001).states[0].exchange, false)
    const backwards = cachedContentOperationsSnapshot(store, now)
    assert.equal(backwards.states[0].enter, true)
    assert.equal(backwards.states[0].exchange, true)
    assert.deepEqual(backwards, store.snapshot(now))
})

test('caller transaction reads see uncommitted state and a rollback cannot replace the committed cache', t => {
    const { db, store, update } = fixture(t)
    update('gacha:1', open)
    const committed = cachedContentOperationsSnapshot(store, now)
    assert.throws(() => db.transaction(() => {
        update('gacha:1', { flags: { visible: false, enter: false } })
        const pending = cachedContentOperationsSnapshot(store, now + 1)
        assert.equal(pending.revision, committed.revision + 1)
        assert.equal(pending.states.find(state => state.key === 'gacha:1').enter, false)
        throw new Error('isolated rollback')
    })(), /isolated rollback/)
    const after = cachedContentOperationsSnapshot(store, now + 2)
    assert.equal(after.revision, committed.revision)
    assert.equal(after.states.find(state => state.key === 'gacha:1').enter, true)
    assert.deepEqual(normalizeTime(after), normalizeTime(committed))
    assert.deepEqual(after, store.snapshot(now + 2))
})

test('first and hit responses have independent top levels and immutable nested values without freezing store inputs', t => {
    const { store, update, serverActions } = fixture(t)
    update('gacha:1', open)
    const first = cachedContentOperationsSnapshot(store, now)
    const saved = JSON.stringify(normalizeTime(first))
    first.server_time_ms = -1
    first.extra = 'caller top-level value'
    assert.throws(() => first.states.push({ key: 'fake' }), TypeError)
    assert.throws(() => { first.states[0].actions.enter.enabled = false }, TypeError)
    assert.throws(() => first.catalog[0].server_actions.push('fake'), TypeError)
    assert.throws(() => first.default_policy.actions.visible.closed_keys.push('fake'), TypeError)
    const hit = cachedContentOperationsSnapshot(store, now + 1)
    assert.notEqual(first, hit)
    assert.equal(hit.states, first.states)
    assert.equal(hit.extra, undefined)
    assert.equal(hit.server_time_ms, now + 1)
    assert.equal(JSON.stringify(normalizeTime(hit)), saved)
    assert.equal(Object.isFrozen(serverActions), false, 'cache freezing must not reach capability callback arrays')
    const legacy = store.snapshot(now)
    legacy.default_policy.actions.visible.closed_keys.push('legacy-only')
    legacy.states[0].actions.enter.enabled = false
    assert.equal(JSON.stringify(normalizeTime(cachedContentOperationsSnapshot(store, now + 2))), saved)
    assert.equal(store.snapshot(now).states[0].actions.enter.enabled, true)
})

test('different store identities never reuse one another even with equal revision and catalog', t => {
    const a = fixture(t), b = fixture(t)
    a.update('gacha:1', open)
    b.update('gacha:2', open)
    const first = cachedContentOperationsSnapshot(a.store, now)
    const second = cachedContentOperationsSnapshot(b.store, now)
    assert.equal(first.revision, second.revision)
    assert.equal(first.catalog_digest, second.catalog_digest)
    assert.equal(second.states.some(state => state.key === 'gacha:1'), false)
    assert.equal(second.states.some(state => state.key === 'gacha:2'), true)
    assert.deepEqual(cachedContentOperationsSnapshot(a.store, now), a.store.snapshot(now))
})

test('closing participation retains scoped old claim and exchange rights without changing progress', t => {
    const { db, store, update } = fixture(t)
    db.exec('CREATE TABLE retained_progress(id INTEGER PRIMARY KEY, cleared INTEGER, claimed INTEGER); INSERT INTO retained_progress VALUES(15, 8, 1)')
    const progress = db.prepare('SELECT * FROM retained_progress').all()
    update('pass_card_event:15', { ...open, missionKeys: ['6:60'] })
    update('gacha:1', open)
    cachedContentOperationsSnapshot(store, now)
    update('pass_card_event:15', { flags: { visible: false, enter: false } })
    update('gacha:1', { flags: { visible: false, enter: false } })
    const snapshot = cachedContentOperationsSnapshot(store, now + 1)
    const pass = snapshot.states.find(state => state.key === 'pass_card_event:15')
    const gacha = snapshot.states.find(state => state.key === 'gacha:1')
    assert.equal(pass.enter, false)
    assert.equal(pass.claim, true)
    assert.deepEqual(pass.actions.claim.mission_keys, ['6:60'])
    assert.equal(gacha.enter, false)
    assert.equal(gacha.exchange, true)
    assert.equal(snapshot.full_snapshot, true)
    assert.deepEqual(db.prepare('SELECT * FROM retained_progress').all(), progress)
    assert.deepEqual(snapshot, store.snapshot(now + 1))
})

test('actual MessagePack and CN response encoding accept frozen snapshots without changing their values', async t => {
    const { store, update } = fixture(t)
    update('gacha:1', open)
    const fresh = store.snapshot(now)
    const cached = cachedContentOperationsSnapshot(store, now)
    const before = JSON.stringify(cached)
    const freshPayload = { data_headers: { server_time: 4294967295 }, data: { content_operations: fresh } }
    const cachedPayload = { data_headers: { server_time: 4294967295 }, data: { content_operations: cached } }
    assert.deepEqual(pack(cachedPayload), pack(freshPayload))
    assert.deepEqual(unpack(pack(cachedPayload)), cachedPayload)
    const config = { mode: 'gzip', minimumBytes: 0, gzipLevel: 1, brotliQuality: 4, log: false }
    const [expected, actual] = await Promise.all([freshPayload, cachedPayload].map(payload =>
        encodeCnResponse({ payload, compression: { config, acceptEncoding: 'gzip' } })))
    assert.deepEqual(actual.body, expected.body)
    assert.equal(actual.compression.encoding, 'gzip')
    assert.equal(JSON.stringify(cached), before)
})
