'use strict'
require('ts-node/register/transpile-only')
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const path = require('node:path'), fs = require('node:fs'), os = require('node:os')
const temporary = fs.mkdtempSync(path.join(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir(), 'box-lifecycle-api-'))
Object.assign(process.env, { DATA_DIR: temporary, TEMP: temporary, TMP: temporary, SQLITE_TMPDIR: temporary,
  CN_WRITER_THREAD: '0', ADMIN_PANEL_PASSWORD: 'synthetic-box-lifecycle-password' })
const load = name => require(path.join(__dirname, '..', 'src', name))
const associationsModule = load('lib/content-box-associations')
const originalAvailability = associationsModule.isContentBoxAssociationIndexAvailable
assert.equal(originalAvailability(), true)
const pairs = associationsModule.getContentBoxAssociations().map(pair => ({ ...pair }))
assert.equal(pairs.length, 48)
assert.equal(pairs.filter(pair => pair.parentKey.startsWith('raid_event:')).length, 7)
let indexAvailable = true
associationsModule.isContentBoxAssociationIndexAvailable = () => indexAvailable
const lifecycle = { associations: pairs, available: true, requiredKeys: pairs.flatMap(pair => [pair.parentKey, pair.boxKey]) }
const byKey = new Map(pairs.flatMap(pair => [[pair.parentKey, pair], [pair.boxKey, pair]]))
const db = new (require('better-sqlite3'))(':memory:')
const { ContentOperationsStore, ContentOperationError, initializeContentOperationsSchema } = load('lib/content-operations-store')
initializeContentOperationsSchema(db); load('data/db').setDbOverride(db)
const keys = [...byKey.keys(), 'box_gacha:999999', 'gacha:999999']
const rows = keys.map(key => ({ key, type: key.split(':')[0], id: Number(key.split(':')[1]), name: `合成 ${key}`,
  source: 'Synthetic fixture', definitionDigest: `synthetic-${key}`, originalStartMs: 1, originalEndMs: 2,
  originalExchangeEndMs: 3, windowCandidate: false, browseCandidate: false }))
const questKey = key => `${key.startsWith('raid_') ? 8 : 9}:${key.split(':')[1]}`
const questMap = Object.fromEntries(pairs.map(pair => [questKey(pair.parentKey), pair.parentKey]))
const store = new ContentOperationsStore(db, { schemaVersion: 1, source: {}, resources: {}, rows,
  baselineTimeMs: 1, baselineEvidence: 'Synthetic only', missing: [], questMap },
  row => row.type === 'box_gacha' ? ['visible', 'enter', 'claim'] : ['visible', 'enter', 'claim', 'exchange'],
  undefined, undefined, undefined, undefined, undefined, lifecycle)
const operations = load('lib/content-operations'), originalStore = operations.contentOperations
operations.contentOperations = () => store
const history = load('lib/content-history-readiness'), originalReader = history.contentHistoryReadinessReader
history.contentHistoryReadinessReader = () => ({ ...originalReader(), boxAssociation: key => indexAvailable ? byKey.get(key) : undefined })
const body = extra => ({ expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic lifecycle request', ...extra })
const raw = key => db.prepare('SELECT value_json FROM content_operations_state WHERE content_key=?').get(key)?.value_json
const restore = (key, value) => db.prepare('INSERT OR REPLACE INTO content_operations_state(content_key,value_json) VALUES(?,?)').run(key, value)
const snapshot = () => ['content_operations_state', 'content_operations_meta', 'content_operations_audit']
  .map(table => db.prepare(`SELECT * FROM ${table} ORDER BY ${table === 'content_operations_state' ? 'content_key' : table === 'content_operations_audit' ? 'revision' : 'id'}`).all())
const actions = key => key.startsWith('box_') ? ['visible', 'enter', 'claim'] : ['visible', 'enter', 'claim', 'exchange']
function configure(key, end = null) {
  const parent = byKey.get(key)?.parentKey === key
  store.update(key, body({ actionOverrides: Object.fromEntries(actions(key).map(action => [action, {
    enabled: true, readiness: 'verified', evidence: 'Synthetic exact member/action review',
    endsAtMs: ['visible', 'enter'].includes(action) || parent && action === 'exchange' ? end : null,
    ...(parent && ['enter', 'claim'].includes(action) ? { questKeys: [questKey(key)] } : {}),
  }])) }), Date.now() - 10000)
  if (store.state(key).published !== false) store.setPublished(key, body({ published: false }), Date.now())
}
let app, cookie
const patch = (key, action, payload, auth = true) => app.inject({ method: 'PATCH',
  url: `/api/content/${encodeURIComponent(key)}/${action}`, headers: auth ? { cookie } : {}, payload: body(payload) })
const publish = (key, published, extra = {}) => patch(key, 'publication', { published, ...extra })
const deadline = (key, endsAtMs, extra = {}) => patch(key, 'deadline', { endsAtMs, ...extra })
const listing = async key => {
  const response = await app.inject({ url: `/api/content/?limit=200&type=${key.split(':')[0]}`, headers: { cookie } })
  assert.equal(response.statusCode, 200, response.body)
  return response.json().rows.find(row => row.key === key)
}
before(async () => {
  for (const key of keys) configure(key)
  app = require('fastify')({ logger: false }); load('lib/management-auth').installManagementAuth(app)
  await app.register(load('routes/web_api/content').default, { prefix: '/api/content' }); await app.ready()
  const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
  assert.equal(login.statusCode, 200, login.body); cookie = login.headers['set-cookie'].split(';')[0]
})
after(async () => {
  await app?.close(); history.contentHistoryReadinessReader = originalReader
  associationsModule.isContentBoxAssociationIndexAvailable = originalAvailability; operations.contentOperations = originalStore
  load('data/db').setDbOverride(null); db.close(); fs.rmSync(temporary, { recursive: true })
})

test('all 48 real pairs open and close from either side without altering reviews, scopes or other states', async () => {
  for (const pair of pairs) {
    const controls = [pair.parentKey, pair.boxKey], before = controls.map(key => store.state(key))
    const unrelated = new Map(keys.filter(key => !controls.includes(key)).map(key => [key, raw(key)]))
    const revision = store.revision(), opened = await publish(pair.parentKey, true)
    assert.equal(opened.statusCode, 200, `${pair.parentKey}: ${opened.body}`)
    assert.equal(opened.json().revision, revision + 2)
    assert.equal(store.allowed(pair.parentKey, 'exchange', Date.now()), true)
    assert.equal(store.allowed(pair.boxKey, 'enter', Date.now()), true)
    const closed = await publish(pair.boxKey, false)
    assert.equal(closed.statusCode, 200, `${pair.boxKey}: ${closed.body}`)
    controls.forEach((key, index) => {
      const after = store.state(key)
      assert.equal(after.published, false); assert.equal(after.instanceId, before[index].instanceId)
      assert.deepEqual(after.actionOverrides, before[index].actionOverrides)
      assert.equal(store.allowed(key, 'enter', Date.now()), false)
    })
    assert.equal(store.allowed(pair.parentKey, 'exchange', Date.now()), false)
    assert.equal(store.allowed(pair.parentKey, 'claim', Date.now()), true)
    assert.equal(store.allowed(pair.boxKey, 'claim', Date.now()), false)
    for (const [key, value] of unrelated) assert.equal(raw(key), value, key)
    assert.equal((await publish(pair.boxKey, true)).statusCode, 200)
    assert.equal((await publish(pair.parentKey, false)).statusCode, 200)
  }
})

test('all 48 pairs share deadlines in both directions while preserving closed markers and independent claims', async () => {
  const end = Date.now() + 120000
  for (const pair of pairs) {
    const before = [pair.parentKey, pair.boxKey].map(key => store.state(key)), revision = store.revision()
    const response = await deadline(pair.boxKey, end)
    assert.equal(response.statusCode, 200, `${pair.boxKey}: ${response.body}`)
    assert.equal(response.json().revision, revision + 2)
    for (const [index, key] of [pair.parentKey, pair.boxKey].entries()) {
      const state = store.state(key)
      assert.equal(state.published, false); assert.equal(state.instanceId, before[index].instanceId)
      for (const action of key === pair.parentKey ? ['visible', 'enter', 'exchange'] : ['visible', 'enter'])
        assert.deepEqual(state.actionOverrides[action], { ...before[index].actionOverrides[action], endsAtMs: end })
      assert.deepEqual(state.actionOverrides.claim, before[index].actionOverrides.claim)
    }
    assert.equal((await deadline(pair.parentKey, null)).statusCode, 200)
  }
})

test('mixed publication markers reconcile atomically and no-op requests still validate CAS and input', async () => {
  const pair = pairs[0]
  store.setPublished(pair.boxKey, body({ published: true }), Date.now())
  let revision = store.revision()
  assert.equal((await publish(pair.boxKey, true)).statusCode, 200)
  assert.equal(store.revision(), revision + 1)
  assert.equal(store.state(pair.parentKey).published, true)
  const saved = snapshot()
  assert.equal((await publish(pair.boxKey, true, { expectedRevision: store.revision() - 1 })).statusCode, 409)
  assert.equal((await publish(pair.boxKey, true, { reason: ' ' })).statusCode, 400)
  assert.equal((await publish(pair.boxKey, true, { unsupported: true })).statusCode, 400)
  assert.deepEqual(snapshot(), saved)
  assert.equal((await publish(pair.parentKey, false)).statusCode, 200)
})

test('publication and deadline second-write failures roll back state, revision and audit', async () => {
  const pair = pairs[1]
  for (const [method, run] of [['setPublished', () => publish(pair.parentKey, true)], ['setDeadline', () => deadline(pair.boxKey, Date.now() + 60000)]]) {
    const original = store[method], saved = snapshot(); let calls = 0
    store[method] = function (...args) { if (++calls === 2) throw new ContentOperationError('Synthetic second-write failure', 409); return original.apply(this, args) }
    try { const response = await run(); assert.equal(response.statusCode, 409, response.body) }
    finally { store[method] = original }
    assert.equal(calls, 2); assert.deepEqual(snapshot(), saved)
  }
})

test('missing/corrupt/uncontrolled peer blocks publication and deadlines but never prevents safe shutdown', async () => {
  const pair = pairs[2]
  for (const [ownKey, peerKey] of [[pair.parentKey, pair.boxKey], [pair.boxKey, pair.parentKey]]) {
    for (const fault of ['missing', 'corrupt', 'uncontrolled']) {
      assert.equal((await publish(ownKey, true)).statusCode, 200)
      const peer = raw(peerKey)
      if (fault === 'missing') db.prepare('DELETE FROM content_operations_state WHERE content_key=?').run(peerKey)
      if (fault === 'corrupt') restore(peerKey, '{')
      if (fault === 'uncontrolled') restore(peerKey, JSON.stringify({ ...store.state(peerKey), controlled: false }))
      const saved = snapshot()
      assert.equal((await publish(ownKey, true)).statusCode, 409, `${ownKey}:${fault}`)
      assert.equal((await deadline(ownKey, null)).statusCode, 409, `${ownKey}:${fault}`)
      assert.deepEqual(snapshot(), saved)
      const card = await listing(ownKey)
      assert.equal(card.primaryControl.enabled, true)
      assert.equal(card.primaryControl.canToggle, true)
      assert.match(card.primaryControl.reason, /关闭/)
      const response = await publish(ownKey, false)
      assert.equal(response.statusCode, 200, `${ownKey}:${fault}:${response.body}`)
      assert.equal(store.state(ownKey).published, false)
      restore(peerKey, peer)
      assert.equal((await publish(ownKey, false)).statusCode, 200)
    }
  }
})

test('unmatched association and unavailable index fail closed while known healthy entries can be taken offline', async () => {
  const pair = pairs[3]
  assert.equal((await publish(pair.parentKey, true)).statusCode, 200)
  pair.relationshipMatches = false
  let saved = snapshot()
  assert.equal((await publish(pair.boxKey, true)).statusCode, 409)
  assert.equal((await deadline(pair.parentKey, null)).statusCode, 409)
  assert.deepEqual(snapshot(), saved)
  assert.equal((await publish(pair.parentKey, false)).statusCode, 200)
  pair.relationshipMatches = true
  assert.equal((await publish(pair.parentKey, true)).statusCode, 200)
  indexAvailable = false; lifecycle.available = false
  saved = snapshot()
  assert.equal((await publish(pair.boxKey, true)).statusCode, 409)
  assert.equal((await deadline(pair.boxKey, null)).statusCode, 409)
  assert.deepEqual(snapshot(), saved)
  assert.equal((await publish(pair.parentKey, false)).statusCode, 200)
  assert.equal((await publish('gacha:999999', true)).statusCode, 200)
  indexAvailable = true; lifecycle.available = true
  assert.equal((await publish(pair.parentKey, false)).statusCode, 200)
  assert.equal((await publish('gacha:999999', false)).statusCode, 200)
})

test('orphan peer state without a catalog row never causes a 404 rollback of the healthy shutdown', async () => {
  const pair = pairs[7]
  for (const [ownKey, peerKey] of [[pair.parentKey, pair.boxKey], [pair.boxKey, pair.parentKey]]) {
    assert.equal((await publish(ownKey, true)).statusCode, 200)
    const catalogRow = store.rows.get(peerKey), peerState = raw(peerKey)
    store.rows.delete(peerKey)
    const saved = snapshot()
    assert.equal((await publish(ownKey, true)).statusCode, 409)
    assert.deepEqual(snapshot(), saved)
    const response = await publish(ownKey, false)
    assert.equal(response.statusCode, 200, response.body)
    assert.equal(store.state(ownKey).published, false)
    assert.equal(raw(peerKey), peerState)
    store.rows.set(peerKey, catalogRow)
    assert.equal((await publish(ownKey, false)).statusCode, 200)
  }
})

test('expired group remains closed after deadline extension until explicit grouped reopen', async () => {
  const pair = pairs[4]
  for (const key of [pair.parentKey, pair.boxKey]) {
    configure(key, Date.now() - 1000)
    const state = store.state(key); delete state.published; restore(key, JSON.stringify(state))
  }
  assert.equal((await deadline(pair.boxKey, null)).statusCode, 200)
  for (const key of [pair.parentKey, pair.boxKey]) {
    assert.equal(store.state(key).published, false)
    assert.equal(store.allowed(key, 'enter', Date.now()), false)
  }
  assert.equal((await publish(pair.parentKey, true)).statusCode, 200)
  assert.equal(store.allowed(pair.parentKey, 'exchange', Date.now()), true)
  assert.equal(store.allowed(pair.boxKey, 'enter', Date.now()), true)
  assert.equal((await publish(pair.parentKey, false)).statusCode, 200)
})

test('missing or expired parent exchange review cannot be bypassed by the Box switch', async () => {
  const pair = pairs[5], saved = raw(pair.parentKey)
  for (const change of ['disabled', 'missing', 'expired']) {
    const state = JSON.parse(saved)
    if (change === 'disabled') state.actionOverrides.exchange.enabled = false
    if (change === 'missing') delete state.actionOverrides.exchange
    if (change === 'expired') state.actionOverrides.exchange.endsAtMs = Date.now() - 1
    restore(pair.parentKey, JSON.stringify(state))
    const before = snapshot()
    assert.equal((await publish(pair.boxKey, true)).statusCode, 409, change)
    assert.deepEqual(snapshot(), before)
  }
  restore(pair.parentKey, saved)
})

test('filtered Raid cards retain peer context and use activity wording instead of WorldStory identity', async () => {
  const pair = pairs.find(row => row.parentKey.startsWith('raid_event:'))
  const row = await listing(pair.parentKey)
  assert.equal(row.linkedActivity.parentKey, pair.parentKey)
  assert.equal(row.linkedActivity.boxKey, pair.boxKey)
  assert.equal(row.linkedActivity.grouped, true)
  assert.equal(row.primaryControl.canToggle, true)
  assert.equal(row.presentation.typeLabel, '奖励箱关联活动')
  assert.match(row.linkedActivity.operationNotice, /新开箱/)
  assert.equal(row.deadlineControl.canEdit, true)
  const unlinked = await publish('box_gacha:999999', true)
  assert.equal(unlinked.statusCode, 200, unlinked.body)
  assert.equal((await publish('box_gacha:999999', false)).statusCode, 200)
})

test('publication and grouped deadline reject unauthenticated and stale-CAS requests without writes', async () => {
  const pair = pairs[6], saved = snapshot()
  assert.equal((await patch(pair.parentKey, 'publication', { published: true }, false)).statusCode, 401)
  assert.equal((await patch(pair.boxKey, 'deadline', { endsAtMs: null }, false)).statusCode, 401)
  assert.equal((await deadline(pair.boxKey, null, { expectedRevision: store.revision() - 1 })).statusCode, 409)
  assert.equal((await deadline(pair.parentKey, null, { catalogDigest: 'changed' })).statusCode, 409)
  assert.deepEqual(snapshot(), saved)
})
