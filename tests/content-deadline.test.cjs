'use strict'
const compiledMode = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiledMode) require('ts-node/register/transpile-only')
const { test } = require('node:test'), assert = require('node:assert/strict')
const { ContentOperationsStore, initializeContentOperationsSchema } = require(compiledMode ? '../out/lib/content-operations-store' : '../src/lib/content-operations-store')
const now = Date.parse('2026-10-22T00:00:00Z')
const action = (extra = {}) => ({ enabled: true, endsAtMs: null, readiness: 'verified', evidence: 'Synthetic exact action review', ...extra })
function fixture(t) {
  const db = new (require('better-sqlite3'))(':memory:'); t.after(() => db.close()); initializeContentOperationsSchema(db)
  db.exec('CREATE TABLE player_progress(id INTEGER PRIMARY KEY, value TEXT); INSERT INTO player_progress VALUES(1,\'untouched\')')
  const rows = ['gacha:1', 'pass_card_event:11', 'pass_card_event:12', 'special_exchange_campaign:1'].map(key => ({
    key, type: key.split(':')[0], id: Number(key.split(':')[1]), name: key, source: 'Synthetic fixture',
    originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: 3, windowCandidate: true, browseCandidate: true,
  }))
  const store = new ContentOperationsStore(db, { schemaVersion: 1, source: {}, resources: {}, rows,
    baselineTimeMs: 1, baselineEvidence: 'Synthetic fixture', missing: [], questMap: {}, missionMap: { '8:11': 'pass_card_event:11' } },
    row => row.type === 'special_exchange_campaign' ? ['exchange'] : ['visible', 'enter', 'claim', 'exchange'])
  const body = extra => ({ expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic deadline edit', ...extra })
  const review = (key = 'gacha:1', overrides = {}) => store.update(key, body({ actionOverrides: {
    visible: action(), enter: action(key === 'pass_card_event:11' ? { missionKeys: ['8:11'] } : {}),
    claim: action(key === 'pass_card_event:11' ? { missionKeys: ['8:11'] } : {}), exchange: action(), ...overrides,
  } }), now)
  const deadline = (key, endsAtMs, at = now) => store.setDeadline(key, body({ endsAtMs }), at)
  const publish = (key, published, at = now) => store.setPublished(key, body({ published }), at)
  return { db, store, body, review, deadline, publish }
}
const stateTables = db => ['content_operations_state', 'content_operations_meta', 'content_operations_audit', 'player_progress']
  .map(table => db.prepare(`SELECT * FROM ${table}`).all())

test('active and manually closed deadlines preserve exact reviews, scope, rights and player progress', t => {
  const { db, store, review, deadline, publish } = fixture(t)
  review('pass_card_event:11'); const before = store.state('pass_card_event:11')
  const after = deadline('pass_card_event:11', now + 1000)
  assert.equal(after.published, before.published); assert.equal(after.instanceId, before.instanceId)
  for (const name of ['visible', 'enter']) assert.deepEqual(after.actionOverrides[name], { ...before.actionOverrides[name], endsAtMs: now + 1000 })
  for (const name of ['claim', 'exchange']) assert.deepEqual(after.actionOverrides[name], before.actionOverrides[name])
  assert.equal(store.allowed('pass_card_event:11', 'enter', now + 1000), true)
  assert.equal(store.allowed('pass_card_event:11', 'enter', now + 1001), false)
  assert.equal(store.allowed('pass_card_event:11', 'claim', now + 1001), true)
  assert.equal(store.snapshot(now + 1001).states[0].actions.enter.ends_at_ms, now + 1000)
  publish('pass_card_event:11', false)
  assert.equal(deadline('pass_card_event:11', null).published, false)
  assert.equal(store.allowed('pass_card_event:11', 'enter', now), false)
  assert.equal(db.prepare('SELECT value FROM player_progress').get().value, 'untouched')
})

test('extending naturally expired entry atomically marks it closed until an explicit publication', t => {
  const { store, review, deadline, publish } = fixture(t)
  review(); deadline('gacha:1', now + 1000)
  const before = store.state('gacha:1'); assert.equal(store.allowed('gacha:1', 'enter', now + 1001), false)
  assert.equal(store.deadlineControl('gacha:1').canEdit, true)
  const saved = deadline('gacha:1', null, now + 1001)
  assert.equal(saved.published, false); assert.equal(saved.actionOverrides.enter.enabled, true)
  assert.equal(store.allowed('gacha:1', 'enter', now + 1001), false)
  assert.deepEqual(saved.actionOverrides.exchange, before.actionOverrides.exchange)
  const audit = store.audit().rows[0]
  assert.equal(audit.before.published, before.published); assert.equal(audit.after.published, false)
  assert.equal(audit.after.actionOverrides.enter.endsAtMs, null)
  publish('gacha:1', true, now + 1001)
  assert.equal(store.allowed('gacha:1', 'enter', now + 1001), true)
})

test('legacy shared deadline splits without changing independent claim/exchange expiry or scope', t => {
  const { store, body, deadline, publish } = fixture(t)
  const before = store.update('pass_card_event:11', body({ readiness: 'verified', evidence: 'Synthetic legacy review',
    flags: { visible: true, enter: true, claim: true, exchange: true }, endsAtMs: now + 1000, missionKeys: ['8:11'] }), now)
  const after = deadline('pass_card_event:11', null, now + 1001)
  assert.equal(after.published, false)
  assert.equal(after.endsAtMs, before.endsAtMs); assert.equal(after.instanceId, before.instanceId)
  assert.equal(after.actionOverrides.enter.endsAtMs, null)
  for (const name of ['claim', 'exchange']) {
    assert.equal(after.actionOverrides[name].endsAtMs, now + 1000)
    assert.deepEqual(after.actionOverrides[name].missionKeys, ['8:11'])
    assert.equal(store.allowed('pass_card_event:11', name, now + 1001), false)
  }
  publish('pass_card_event:11', true, now + 1001)
  assert.equal(store.allowed('pass_card_event:11', 'enter', now + 1001), true)
  for (const name of ['claim', 'exchange']) assert.equal(store.allowed('pass_card_event:11', name, now + 1001), false)
})

test('expired rights only bypass the deadline check; stale or unreviewed rights still block publication', t => {
  const { db, store, body, review, deadline, publish } = fixture(t)
  review('gacha:1', { claim: action({ endsAtMs: now + 1 }), exchange: action({ endsAtMs: now + 1 }) })
  publish('gacha:1', false)
  deadline('gacha:1', null, now + 2)
  const before = store.state('gacha:1'), revision = store.revision()
  for (const bad of [{ contentDigest: 'stale' }, { readiness: 'unverified' }, { missionKeys: ['8:999999'] }]) {
    const invalid = structuredClone(before); Object.assign(invalid.actionOverrides.claim, bad)
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(invalid), 'gacha:1')
    assert.throws(() => publish('gacha:1', true, now + 2), /动作失效|有效的已核查/)
    assert.equal(store.revision(), revision)
  }
  db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(before), 'gacha:1')
  publish('gacha:1', true, now + 2)
  assert.equal(store.allowed('gacha:1', 'enter', now + 2), true)
  assert.equal(store.allowed('gacha:1', 'claim', now + 2), false)
})

test('deadline-only changes never enable disabled reviews and exchange-only expiry needs manual reopen', t => {
  const { store, body, review, deadline } = fixture(t)
  review('gacha:1', { enter: action({ enabled: false }) })
  deadline('gacha:1', now + 1000); assert.equal(store.state('gacha:1').actionOverrides.enter.enabled, false)
  store.update('special_exchange_campaign:1', body({ actionOverrides: { exchange: action({ endsAtMs: now + 1000 }) } }), now)
  const before = store.state('special_exchange_campaign:1')
  assert.deepEqual(store.deadlineControl('special_exchange_campaign:1').actionLabels, ['已有资格兑换'])
  const after = deadline('special_exchange_campaign:1', null, now + 1001)
  assert.equal(after.actionOverrides.exchange.enabled, false)
  assert.equal(after.instanceId, before.instanceId); assert.equal(after.actionOverrides.exchange.evidence, before.actionOverrides.exchange.evidence)
  assert.equal(store.allowed('special_exchange_campaign:1', 'exchange', now + 1001), false)
})

test('missing review, unreviewed, stale definition and forged fields fail without writes', t => {
  const { db, store, body, review } = fixture(t)
  const assertRejected = (input, message) => {
    const before = stateTables(db)
    assert.throws(() => store.setDeadline('gacha:1', input, now), message)
    assert.deepEqual(stateTables(db), before)
  }
  assert.equal(store.deadlineControl('gacha:1').canEdit, false)
  assertRejected(body({ endsAtMs: null }), /核查/)
  review()
  for (const bad of [undefined, now, -1, Number.NaN, 1.5, 'future']) assertRejected(body({ endsAtMs: bad }), /截止/)
  assertRejected(body({ endsAtMs: null, startsAtMs: now }), /参数/)
  assertRejected(body({ endsAtMs: null, expectedRevision: store.revision() - 1 }), /其他操作/)
  assertRejected(body({ endsAtMs: null, catalogDigest: 'stale' }), /目录/)
  const original = store.state('gacha:1')
  original.actionOverrides.enter.readiness = 'unverified'
  db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(original), 'gacha:1')
  assertRejected(body({ endsAtMs: null }), /尚未核查/)
  review(); store.runtimeDefinitions.set('gacha:1', { digest: 'changed', matchesCatalog: false })
  assert.equal(store.deadlineControl('gacha:1').canEdit, false)
  assertRejected(body({ endsAtMs: null }), /定义/)
})
