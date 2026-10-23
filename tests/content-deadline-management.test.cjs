'use strict'
const compiledMode = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiledMode) require('ts-node/register/transpile-only')
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const path = require('node:path'), fs = require('node:fs'), os = require('node:os')
const temporary = fs.mkdtempSync(path.join(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir(), 'deadline-management-'))
Object.assign(process.env, { DATA_DIR: temporary, TEMP: temporary, TMP: temporary, SQLITE_TMPDIR: temporary,
  CN_WRITER_THREAD: '0', ADMIN_PANEL_PASSWORD: 'synthetic-deadline-password' })
const load = name => require(path.join(__dirname, '..', compiledMode ? 'out' : 'src', name))
const db = new (require('better-sqlite3'))(':memory:')
const { ContentOperationsStore, ContentOperationError, initializeContentOperationsSchema } = load('lib/content-operations-store')
initializeContentOperationsSchema(db); load('data/db').setDbOverride(db)
const rows = ['world_story_event:200100', 'box_gacha:108', 'box_gacha:109', 'gacha:1', 'special_exchange_campaign:1'].map(key => ({
  key, type: key.split(':')[0], id: Number(key.split(':')[1]), name: key, source: 'Synthetic fixture',
  originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: 3, windowCandidate: false, browseCandidate: false,
}))
const store = new ContentOperationsStore(db, { schemaVersion: 1, source: {}, resources: {}, rows,
  baselineTimeMs: 1, baselineEvidence: 'Synthetic only', missing: [], questMap: { '9:1': 'world_story_event:200100' } },
  row => row.type === 'special_exchange_campaign' ? ['exchange'] : ['visible', 'enter', 'claim', 'exchange'])
const operations = load('lib/content-operations'), originalStore = operations.contentOperations
operations.contentOperations = () => store
const history = load('lib/content-history-readiness'), originalReader = history.contentHistoryReadinessReader
let relationshipMatches = true
history.contentHistoryReadinessReader = () => ({ ...originalReader(),
  boxAssociation: key => ['world_story_event:200100', 'box_gacha:108'].includes(key)
    ? { parentKey: 'world_story_event:200100', boxKey: 'box_gacha:108', relationshipMatches, description: 'Synthetic association' } : undefined })
const body = extra => ({ expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic deadline request', ...extra })
function configure(key, endsAtMs = null) {
  const action = name => ({ enabled: true, readiness: 'verified', evidence: 'Synthetic exact review',
    endsAtMs: ['visible', 'enter'].includes(name) || key.startsWith('special_') ? endsAtMs : null,
    ...(['enter', 'claim'].includes(name) && key.startsWith('world_') ? { questKeys: ['9:1'] } : {}) })
  store.update(key, body({ actionOverrides: Object.fromEntries((key.startsWith('special_') ? ['exchange'] : ['visible', 'enter', 'claim', 'exchange'])
    .map(name => [name, action(name)])) }), Date.now() - 10000)
}
let app, cookie
const patch = (key, endsAtMs, extra = {}, auth = true) => app.inject({ method: 'PATCH', url: `/api/content/${encodeURIComponent(key)}/deadline`,
  headers: auth ? { cookie } : {}, payload: body({ endsAtMs, ...extra }) })
const snapshot = () => ['content_operations_state', 'content_operations_meta', 'content_operations_audit'].map(table => db.prepare(`SELECT * FROM ${table}`).all())
const listing = async key => (await app.inject({ url: '/api/content/?limit=200', headers: { cookie } })).json().rows.find(row => row.key === key)
before(async () => {
  configure('world_story_event:200100'); configure('box_gacha:108'); configure('gacha:1'); configure('special_exchange_campaign:1')
  app = require('fastify')({ logger: false }); load('lib/management-auth').installManagementAuth(app)
  await app.register(load('routes/web_api/content').default, { prefix: '/api/content' }); await app.ready()
  const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
  assert.equal(login.statusCode, 200, login.body); cookie = login.headers['set-cookie'].split(';')[0]
})
after(async () => {
  await app?.close(); operations.contentOperations = originalStore; history.contentHistoryReadinessReader = originalReader
  load('data/db').setDbOverride(null); db.close(); fs.rmSync(temporary, { recursive: true })
})

test('deadline endpoint authenticates and rejects stale CAS/invalid input without writes', async () => {
  const saved = snapshot()
  assert.equal((await patch('gacha:1', null, {}, false)).statusCode, 401)
  assert.equal((await patch('gacha:1', Date.now() - 1)).statusCode, 400)
  assert.equal((await patch('gacha:1', null, { enabled: true })).statusCode, 400)
  assert.equal((await patch('gacha:1', null, { expectedRevision: store.revision() - 1 })).statusCode, 409)
  assert.deepEqual(snapshot(), saved)
  assert.equal((await patch('box_gacha:109', null)).statusCode, 409)
  assert.equal((await listing('box_gacha:109')).deadlineControl.canEdit, false)
})

test('World/Box save atomically shares only participation deadlines and preserves rights/scopes', async () => {
  const keys = ['world_story_event:200100', 'box_gacha:108'], before = keys.map(key => store.state(key)), end = Date.now() + 60000
  const revision = store.revision(), response = await patch(keys[0], end)
  assert.equal(response.statusCode, 200, response.body); assert.equal(response.json().revision, revision + 2)
  assert.equal(response.json().linkedStates.length, 1)
  keys.forEach((key, index) => {
    const state = store.state(key)
    assert.equal(state.published, before[index].published); assert.equal(state.instanceId, before[index].instanceId)
    for (const name of ['visible', 'enter']) assert.deepEqual(state.actionOverrides[name], { ...before[index].actionOverrides[name], endsAtMs: end })
    for (const name of ['claim', 'exchange']) assert.deepEqual(state.actionOverrides[name], before[index].actionOverrides[name])
  })
  const row = await listing(keys[0]); assert.equal(row.deadlineControl.canEdit, true)
  assert.equal(row.deadlineControl.endsAtMs, end); assert.match(row.deadlineControl.reason, /同时保存/)
})

test('second linked write failure rolls back both state, revision and audit', async () => {
  const original = store.setDeadline, saved = snapshot(); let calls = 0
  store.setDeadline = function (...args) { if (++calls === 2) throw new ContentOperationError('Synthetic second write failure', 409); return original.apply(this, args) }
  try { assert.equal((await patch('box_gacha:108', null)).statusCode, 409) }
  finally { store.setDeadline = original }
  assert.equal(calls, 2); assert.deepEqual(snapshot(), saved)
  relationshipMatches = false
  assert.equal((await patch('box_gacha:108', null)).statusCode, 409)
  assert.equal((await listing('box_gacha:108')).deadlineControl.canEdit, false)
  assert.deepEqual(snapshot(), saved); relationshipMatches = true
})

test('missing linked peer refuses a deadline edit without partial writes or qualification creation', async () => {
  const peer = db.prepare('SELECT value_json FROM content_operations_state WHERE content_key=?').get('box_gacha:108').value_json
  db.prepare('DELETE FROM content_operations_state WHERE content_key=?').run('box_gacha:108')
  const saved = snapshot()
  assert.equal((await listing('world_story_event:200100')).deadlineControl.canEdit, false)
  assert.equal((await patch('world_story_event:200100', null)).statusCode, 409)
  assert.deepEqual(snapshot(), saved)
  db.prepare('INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?)').run('box_gacha:108', peer)
})

test('manually closed linked entries retain their closed marker when saving new deadlines', async () => {
  const down = await app.inject({ method: 'PATCH', url: '/api/content/world_story_event%3A200100/publication',
    headers: { cookie }, payload: body({ published: false }) })
  assert.equal(down.statusCode, 200, down.body)
  const saved = await patch('box_gacha:108', null)
  assert.equal(saved.statusCode, 200, saved.body)
  for (const key of ['world_story_event:200100', 'box_gacha:108']) {
    assert.equal(store.state(key).published, false)
    assert.equal(store.allowed(key, 'enter', Date.now()), false)
    assert.equal(store.allowed(key, 'claim', Date.now()), true)
  }
})

test('expired linked entries save together and remain closed until explicit grouped reopen', async () => {
  for (const key of ['world_story_event:200100', 'box_gacha:108']) {
    configure(key, Date.now() - 1000)
    const state = store.state(key); delete state.published
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(state), key)
    const row = await listing(key)
    assert.equal(row.primaryControl.status, 'disabled'); assert.equal(row.primaryControl.label, '已到期')
    assert.equal(row.deadlineControl.canEdit, true)
  }
  const saved = await patch('world_story_event:200100', null)
  assert.equal(saved.statusCode, 200, saved.body)
  for (const key of ['world_story_event:200100', 'box_gacha:108']) assert.equal(store.state(key).published, false)
  const up = await app.inject({ method: 'PATCH', url: '/api/content/box_gacha%3A108/publication',
    headers: { cookie }, payload: body({ published: true }) })
  assert.equal(up.statusCode, 200, up.body)
  for (const key of ['world_story_event:200100', 'box_gacha:108']) assert.equal(store.allowed(key, 'enter', Date.now()), true)
})

test('expired listing is closed but editable; deadline save stays closed then manual publication succeeds', async () => {
  configure('gacha:1', Date.now() - 1000)
  const row = await listing('gacha:1')
  assert.equal(row.primaryControl.status, 'disabled'); assert.equal(row.primaryControl.enabled, false)
  assert.equal(row.primaryControl.canToggle, false); assert.equal(row.deadlineControl.canEdit, true)
  const before = store.state('gacha:1'), response = await patch('gacha:1', null)
  assert.equal(response.statusCode, 200, response.body)
  assert.equal(response.json().state.published, false); assert.equal(store.allowed('gacha:1', 'enter', Date.now()), false)
  assert.deepEqual(response.json().state.actionOverrides.claim, before.actionOverrides.claim)
  assert.deepEqual(response.json().state.actionOverrides.exchange, before.actionOverrides.exchange)
  const reopened = await app.inject({ method: 'PATCH', url: '/api/content/gacha%3A1/publication', headers: { cookie }, payload: body({ published: true }) })
  assert.equal(reopened.statusCode, 200, reopened.body); assert.equal(store.allowed('gacha:1', 'enter', Date.now()), true)
})

test('expired exchange-only endpoint stays closed after save and does not grant entitlement', async () => {
  configure('special_exchange_campaign:1', Date.now() - 1000)
  const row = await listing('special_exchange_campaign:1')
  assert.equal(row.primaryControl.status, 'disabled'); assert.equal(row.deadlineControl.canEdit, true)
  assert.deepEqual(row.deadlineControl.actionLabels, ['已有资格兑换'])
  const response = await patch('special_exchange_campaign:1', null)
  assert.equal(response.statusCode, 200, response.body)
  assert.equal(response.json().state.actionOverrides.exchange.enabled, false)
  assert.equal(store.allowed('special_exchange_campaign:1', 'exchange', Date.now()), false)
  assert.equal((await listing('special_exchange_campaign:1')).primaryControl.canToggle, true)
  const review = store.state('special_exchange_campaign:1').actionOverrides.exchange
  const reopened = await app.inject({ method: 'PATCH', url: '/api/content/special_exchange_campaign%3A1', headers: { cookie },
    payload: body({ actionOverrides: { exchange: { enabled: true, endsAtMs: review.endsAtMs, readiness: review.readiness, evidence: review.evidence } } }) })
  assert.equal(reopened.statusCode, 200, reopened.body)
  assert.equal(store.allowed('special_exchange_campaign:1', 'exchange', Date.now()), true)
})
