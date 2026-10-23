'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const { createHash } = require('node:crypto')
const Sqlite = require('better-sqlite3')
if (!process.env.STARPOINT_TEST_OUT_DIR) require('ts-node/register/transpile-only')
const base = process.env.STARPOINT_TEST_OUT_DIR || path.join(__dirname, '../src')
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require(path.join(base, 'lib/content-operations-store'))
const { prepareReviewedHistoryOfflineSync, rebindReviewedContentIdentitiesOfflineSync } = require(path.join(base, 'lib/content-history-bootstrap'))
const now = 1792540800000
const plain = value => JSON.parse(JSON.stringify(value))
function fixture(t) {
    const db = new Sqlite(':memory:'); t.after(() => db.close())
    initializeContentOperationsSchema(db)
    db.exec("CREATE TABLE earned_progress(value TEXT); INSERT INTO earned_progress VALUES('retained paid claims and completed battles')")
    const rows = ['pass_card_event:1', 'pass_card_event:2', 'gacha:216', 'special_exchange_campaign:1', 'story_event:1', 'event_item_shop:1'].map(key => ({
        key, type: key.split(':')[0], id: Number(key.split(':')[1]), name: key,
        source: 'synthetic-only', originalStartMs: null, originalEndMs: null, originalExchangeEndMs: null,
        windowCandidate: false, browseCandidate: false,
        ...(key === 'event_item_shop:1' ? { parentKey: 'story_event:1' } : {}),
    }))
    const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' },
        baselineTimeMs: 0, baselineEvidence: 'synthetic, not gameplay acceptance', missing: [], resources: {},
        questMap: { '2:1001': 'story_event:1' }, missionMap: {}, rows }
    const capabilities = row => row.type === 'special_exchange_campaign' ? ['exchange'] : row.type === 'event_item_shop' ? ['visible', 'exchange'] : CONTENT_ACTIONS
    const reopen = epoch => new ContentOperationsStore(db, catalog, capabilities,
        row => ({ digest: createHash('sha256').update(epoch + row.key).digest('hex'), matchesCatalog: true }))
    const store = reopen('previous reviewed loader')
    const action = () => ({ enabled: true, readiness: 'verified', evidence: 'Synthetic exact-action proof', endsAtMs: null })
    const candidate = key => ({ key, actionOverrides: Object.fromEntries(capabilities(rows.find(row => row.key === key)).map(name => [name,
        key.startsWith('story') && ['enter', 'claim'].includes(name) ? { ...action(), questKeys: ['2:1001'] } : action()])) })
    const plan = (...keys) => ({ schemaVersion: 1, catalogDigest: store.digest, evidenceDigest: 'a'.repeat(64), candidates: keys.map(candidate) })
    const apply = value => prepareReviewedHistoryOfflineSync(store, value, { expectedRevision: store.revision(), nowMs: now })
    return { db, store, plan, apply, reopen }
}

function rebindPlan(db, store, keys) {
    return { schemaVersion: 1, catalogDigest: store.digest, evidenceDigest: 'e'.repeat(64), bindings: keys.map(key => ({ key,
        previousRawSha256: createHash('sha256').update(db.prepare('SELECT value_json FROM content_operations_state WHERE content_key=?').get(key).value_json).digest('hex'),
        nextContentDigest: store.contentDigests.get(key),
    })) }
}

test('reviewed native loader rebind preserves publication, action scopes, instances and earned data', t => {
    const { db, store, plan, apply, reopen } = fixture(t)
    apply(plan('gacha:216', 'story_event:1'))
    store.setPublished('gacha:216', { published: true, expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'existing operator selection' }, now)
    const keys = ['gacha:216', 'story_event:1']
    const before = keys.map(key => plain(store.state(key)))
    const fresh = reopen('reviewed native normalizer')
    const revision = fresh.revision()
    const result = rebindReviewedContentIdentitiesOfflineSync(fresh, rebindPlan(db, fresh, keys), { expectedRevision: revision, nowMs: now })
    assert.deepEqual(result.reboundKeys, keys)
    assert.equal(result.revision, revision + 2)
    for (let index = 0; index < keys.length; index++) {
        const after = plain(fresh.state(keys[index])), prior = before[index]
        for (const field of ['readiness', 'flags', 'questKeys', 'missionKeys', 'endsAtMs', 'instanceId', 'published'])
            assert.deepEqual(after[field], prior[field], field)
        assert.notEqual(after.contentDigest, prior.contentDigest)
        for (const action of Object.keys(prior.actionOverrides)) {
            const oldAction = { ...prior.actionOverrides[action] }, newAction = { ...after.actionOverrides[action] }
            delete oldAction.contentDigest; delete oldAction.catalogDigest
            delete newAction.contentDigest; delete newAction.catalogDigest
            assert.deepEqual(newAction, oldAction)
        }
    }
    assert.equal(fresh.allowed('gacha:216', 'enter', now), true)
    assert.equal(fresh.allowed('story_event:1', 'enter', now), false)
    assert.equal(db.prepare('SELECT value FROM earned_progress').get().value, 'retained paid claims and completed battles')
})

test('identity rebind rejects stale CAS and changed raw states, atomically rolling back earlier bindings', t => {
    const { db, plan, apply, reopen } = fixture(t)
    apply(plan('gacha:216', 'story_event:1'))
    const fresh = reopen('reviewed native normalizer')
    const input = rebindPlan(db, fresh, ['gacha:216', 'story_event:1'])
    const revision = fresh.revision(), before = db.serialize()
    assert.throws(() => rebindReviewedContentIdentitiesOfflineSync(fresh, input, { expectedRevision: revision + 1, nowMs: now }), /版本不匹配/)
    assert.deepEqual(db.serialize(), before)
    input.bindings[1].previousRawSha256 = '0'.repeat(64)
    assert.throws(() => rebindReviewedContentIdentitiesOfflineSync(fresh, input, { expectedRevision: revision, nowMs: now }), /发生变化/)
    assert.equal(fresh.revision(), revision)
    assert.deepEqual(db.serialize(), before)
})
test('historical preparation stays closed, preserves earned claims and supports multiple closed passes', t => {
    const { db, store, plan, apply } = fixture(t)
    const result = apply(plan('pass_card_event:1', 'pass_card_event:2', 'gacha:216', 'special_exchange_campaign:1'))
    assert.equal(result.preparedKeys.length, 4)
    for (const key of result.preparedKeys) {
        assert.equal(store.allowed(key, 'visible', now), false)
        assert.equal(store.allowed(key, 'enter', now), false)
    }
    assert.equal(store.allowed('gacha:216', 'claim', now), true)
    assert.equal(store.allowed('special_exchange_campaign:1', 'exchange', now), false)
    const publish = key => store.setPublished(key, { published: true, expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'synthetic admin open' }, now)
    publish('pass_card_event:1')
    assert.equal(store.activeManagedPass(now), 'pass_card_event:1')
    assert.throws(() => publish('pass_card_event:2'), /通行证/)
    assert.equal(db.prepare('SELECT value FROM earned_progress').get().value, 'retained paid claims and completed battles')
})
test('preparation preserves every existing operator state and same-instance reopening data', t => {
    const { store, plan, apply } = fixture(t)
    const initial = plan('gacha:216')
    apply(initial)
    store.setPublished('gacha:216', { published: true, expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'existing operator choice' }, now)
    const before = plain(store.state('gacha:216')), revision = store.revision()
    const result = apply(initial)
    assert.deepEqual(result.preparedKeys, [])
    assert.deepEqual(result.preservedKeys, ['gacha:216'])
    assert.equal(store.revision(), revision)
    assert.deepEqual(plain(store.state('gacha:216')), before)
})
test('a later invalid candidate rolls back the entire preparation and its audit', t => {
    const { db, store, plan, apply } = fixture(t)
    const input = plan('gacha:216', 'pass_card_event:1')
    input.candidates[1].actionOverrides.enter.questKeys = ['7:999999']
    const revision = store.revision(), tablesBefore = db.serialize()
    assert.throws(() => apply(input), /范围/)
    assert.equal(store.revision(), revision)
    assert.equal(store.state('gacha:216'), null)
    assert.equal(store.state('pass_card_event:1'), null)
    assert.deepEqual(db.serialize(), tablesBefore)
})
test('review identity, duplicate candidates and entry-only preparation fail closed', t => {
    const { store, plan, apply } = fixture(t)
    const wrong = plan('gacha:216'); wrong.catalogDigest = 'wrong'
    assert.throws(() => apply(wrong), /目录不匹配/)
    assert.throws(() => apply(plan('gacha:216', 'gacha:216')), /重复项目/)
    const entryOnly = plan('gacha:216'); entryOnly.candidates[0].actionOverrides.enter.enabled = false
    assert.throws(() => apply(entryOnly), /实际参与/)
    assert.equal(store.state('gacha:216'), null)
})
test('dependent products can be reviewed only behind their closed event owner', t => {
    const { store, plan, apply } = fixture(t)
    assert.throws(() => apply(plan('event_item_shop:1')), /已经关闭的活动/)
    assert.equal(store.state('event_item_shop:1'), null)
    apply(plan('story_event:1'))
    store.setPublished('story_event:1', { published: true, expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'synthetic operator choice' }, now)
    assert.throws(() => apply(plan('event_item_shop:1')), /已经关闭的活动/)
    store.setPublished('story_event:1', { published: false, expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'synthetic close' }, now)
    apply(plan('event_item_shop:1'))
    assert.equal(store.allowed('event_item_shop:1', 'exchange', now), true)
    assert.equal(store.allowed('story_event:1', 'exchange', now), false)
})
