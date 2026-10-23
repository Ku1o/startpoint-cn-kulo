'use strict'
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const out = process.env.STARPOINT_TEST_OUT_DIR
if (!out) throw Error('Use the current isolated build via STARPOINT_TEST_OUT_DIR')
const load = name => require(path.join(out, name))
const Fastify = require('fastify')
const Sqlite = require('better-sqlite3')
process.env.MULTI_REALTIME_OWNER_CHILD = '0'
process.env.CN_WRITER_THREAD = '0'
const previousPassword = process.env.ADMIN_PANEL_PASSWORD
process.env.ADMIN_PANEL_PASSWORD = 'isolated-content-management-fixture'
const { ContentOperationsStore, initializeContentOperationsSchema } = load('lib/content-operations-store')
const db = new Sqlite(':memory:')
initializeContentOperationsSchema(db)
db.exec("CREATE TABLE retained_progress(id INTEGER PRIMARY KEY, value TEXT); INSERT INTO retained_progress VALUES(1,'existing clears and claims')")
load('data/db').setDbOverride(db)
const catalog = {
    schemaVersion: 1, source: { assetVersion: 'isolated-fixture', manifestSha256: 'fixture' },
    baselineTimeMs: 0, baselineEvidence: 'isolated test, not playable evidence', missing: [], resources: {}, questMap: {},
    rows: [
        { key: 'gacha:1', type: 'gacha', id: 1, name: 'search fixture', originalStartMs: null, originalEndMs: null, originalExchangeEndMs: null, windowCandidate: true, browseCandidate: false, source: 'fixture', definitionDigest: 'gacha1' },
        { key: 'unsupported:2', type: 'unsupported', id: 2, name: 'review only', originalStartMs: null, originalEndMs: null, originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false, source: 'fixture', definitionDigest: 'unsupported2' },
    ],
}
const store = new ContentOperationsStore(db, catalog, row => row.type === 'gacha' ? ['visible', 'enter', 'exchange'] : [])
const operations = load('lib/content-operations'), originalStore = operations.contentOperations
operations.contentOperations = () => store
let app, cookie
const body = (overrides = {}) => ({ expectedRevision: store.revision(), catalogDigest: store.digest,
    readiness: 'verified', evidence: 'isolated resource and gameplay fixture', reason: 'isolated manual control',
    flags: { visible: true, enter: true, claim: false, exchange: true }, endsAtMs: null, ...overrides })
const patch = (key, payload) => app.inject({ method: 'PATCH', url: `/api/content/${encodeURIComponent(key)}`, headers: { cookie }, payload })
const get = url => app.inject({ url, headers: { cookie } })
before(async () => {
    app = Fastify({ logger: false })
    load('lib/management-auth').installManagementAuth(app)
    load('lib/persistence-http-errors').installPersistenceHttpErrors(app)
    await app.register(load('routes/web_api/content').default, { prefix: '/api/content' })
    await app.ready()
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    assert.equal(login.statusCode, 200, login.body)
    cookie = login.headers['set-cookie'].split(';', 1)[0]
})
after(async () => {
    operations.contentOperations = originalStore
    if (app) await app.close()
    assert.equal(db.prepare('SELECT value FROM retained_progress WHERE id=1').get().value, 'existing clears and claims')
    load('data/db').setDbOverride(null)
    db.close()
    if (previousPassword === undefined) delete process.env.ADMIN_PANEL_PASSWORD
    else process.env.ADMIN_PANEL_PASSWORD = previousPassword
})
test('content catalog, writes and audit all retain the management authentication boundary', async () => {
    for (const url of ['/api/content/', '/api/content/audit', '/api/%63ontent/', '/api/content//audit']) {
        const response = await app.inject({ url })
        assert.equal(response.statusCode, 401, `${url}: ${response.body}`)
    }
    assert.equal((await app.inject({ method: 'PATCH', url: '/api/content/gacha%3A1', payload: body() })).statusCode, 401)
    assert.equal((await app.inject('/api/content-unrelated')).statusCode, 404)
    assert.equal(store.revision(), 0)
    const unguarded = Fastify({ logger: false })
    await unguarded.register(load('routes/web_api/content').default, { prefix: '/api/content' })
    try {
        assert.equal((await unguarded.inject('/api/content/')).statusCode, 401)
        assert.equal((await unguarded.inject('/api/content/audit')).statusCode, 401)
        assert.equal((await unguarded.inject({ method: 'PATCH', url: '/api/content/gacha%3A1', payload: body() })).statusCode, 401)
        assert.equal(store.revision(), 0)
    } finally { await unguarded.close() }
})
test('catalog searches, filters and paginates with explicit capabilities and strict query validation', async () => {
    const listing = (await get('/api/content/?search=fixture&offset=0&limit=1&candidatesOnly=true')).json()
    assert.equal(listing.total, 1)
    assert.equal(listing.rows[0].key, 'gacha:1')
    assert.deepEqual(listing.rows[0].capabilities, ['visible', 'enter', 'exchange'])
    const reviewOnly = (await get('/api/content/?type=unsupported')).json().rows[0]
    assert.deepEqual(reviewOnly.capabilities, [])
    assert.equal(reviewOnly.state, null)
    assert.equal((await get('/api/content/?offset=1&limit=1')).json().rows.length, 1)
    for (const query of ['limit=NaN', 'limit=0', 'limit=201', 'offset=-1', 'offset=', 'offset=1e2', 'limit=1&limit=2',
        'readiness=unknown', 'candidatesOnly=yes', 'unsupported=value', `search=${'a'.repeat(201)}`]) {
        assert.equal((await get(`/api/content/?${query}`)).statusCode, 400, query)
    }
})
test('management changes require evidence, catalog identity and revision; rejected writes have no audit', async () => {
    for (const payload of [body({ evidence: '' }), body({ reason: '' }), body({ expectedRevision: undefined }), body({ instanceId: 'reset' })]) {
        assert.equal((await patch('gacha:1', payload)).statusCode, 400)
    }
    assert.equal((await patch('gacha:1', body({ catalogDigest: 'stale' }))).statusCode, 409)
    assert.equal((await patch('missing:1', body())).statusCode, 404)
    assert.equal((await patch('unsupported:2', body())).statusCode, 409)
    assert.equal(store.revision(), 0)
    assert.equal(db.prepare('SELECT count(*) AS n FROM content_operations_audit').get().n, 0)
    const revision = store.revision()
    const saved = await patch('gacha:1', body())
    assert.equal(saved.statusCode, 200, saved.body)
    assert.equal(saved.json().state.instanceId, 'gacha:1:original')
    assert.equal(saved.json().revision, revision + 1)
    assert.equal((await patch('gacha:1', body({ expectedRevision: revision }))).statusCode, 409)
    assert.equal(store.revision(), revision + 1)
})
test('review-only blocked content stays distinguishable from wired controls and has explicit evidence', async () => {
    const saved = await patch('unsupported:2', body({ readiness: 'blocked', evidence: 'fixture: resource missing; business guard not connected', flags: { visible: false, enter: false, claim: false, exchange: false } }))
    assert.equal(saved.statusCode, 200, saved.body)
    const row = (await get('/api/content/?readiness=blocked')).json().rows[0]
    assert.equal(row.key, 'unsupported:2')
    assert.deepEqual(row.capabilities, [])
    assert.equal(row.readiness, 'blocked')
    assert.match(row.state.evidence, /not connected/)
})
test('audit is authenticated, descending and cursor-paginated; close and reopen preserve instance and progress', async () => {
    const original = store.state('gacha:1')
    assert.equal((await patch('gacha:1', body({ flags: { visible: false, enter: false, claim: false, exchange: false }, reason: 'close fixture' }))).statusCode, 200)
    const closed = (await get('/api/content/?type=gacha')).json().rows[0]
    assert.equal(closed.effectiveFlags.enter, false)
    assert.equal((await patch('gacha:1', body({ reason: 'reopen fixture' }))).statusCode, 200)
    assert.equal(store.state('gacha:1').instanceId, original.instanceId)
    const first = (await get('/api/content/audit?limit=2')).json()
    assert.equal(first.rows.length, 2)
    assert.ok(first.rows[0].revision > first.rows[1].revision)
    assert.equal(first.rows[0].reason, 'reopen fixture')
    assert.equal(first.rows[0].before.flags.enter, false)
    assert.equal(first.rows[0].after.flags.enter, true)
    const earlier = (await get(`/api/content/audit?beforeRevision=${first.rows[1].revision}&limit=2`)).json()
    assert.ok(earlier.rows.every(row => row.revision < first.rows[1].revision))
    const onlyReview = (await get('/api/content/audit?key=unsupported%3A2')).json()
    assert.equal(onlyReview.rows.length, 1)
    assert.equal(onlyReview.rows[0].key, 'unsupported:2')
    for (const query of ['limit=201', 'beforeRevision=0', 'beforeRevision=-1', 'key=', 'limit=2&limit=3', 'unknown=value']) {
        assert.equal((await get(`/api/content/audit?${query}`)).statusCode, 400, query)
    }
})
test('shutdown rejects a new management write without changing state or audit', async () => {
    const revision = store.revision(), before = store.state('gacha:1')
    load('lib/shutdown-state').beginServerShutdown()
    const response = await patch('gacha:1', body({ reason: 'rejected while closing' }))
    assert.equal(response.statusCode, 503, response.body)
    assert.equal(response.json().code, 'SERVER_CLOSING')
    assert.equal(store.revision(), revision)
    assert.deepEqual(store.state('gacha:1'), before)
})
