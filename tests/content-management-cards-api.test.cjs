'use strict'
require('ts-node/register/transpile-only')
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
if (!process.env.DATA_DIR || !process.env.STARPOINT_TEST_TMP_ROOT && !/cpu-check-/.test(process.env.DATA_DIR))
    throw Error('Run via tools/run-isolated-check.cjs with disposable DATA_DIR')
Object.assign(process.env, { CN_WRITER_THREAD: '0', MULTI_REALTIME_OWNER_CHILD: '0', ADMIN_PANEL_PASSWORD: 'cards-api-synthetic-only' })
const Sqlite = require('better-sqlite3')
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require('../src/lib/content-operations-store')
const { projectContentManagementCards } = require('../src/lib/content-management-projection')
const { contentManagementSharedReadStatus } = require('../src/lib/content-management-shared')
const db = new Sqlite(':memory:')
initializeContentOperationsSchema(db)
db.exec("CREATE TABLE retained_progress(value TEXT); INSERT INTO retained_progress VALUES('earned-and-paid')")
require('../src/data/db').setDbOverride(db)
const row = (type, id) => ({ key: `${type}:${id}`, type, id, name: `Synthetic ${type} ${id}`,
    originalStartMs: id, originalEndMs: id + 1, originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false,
    source: 'synthetic', definitionDigest: `${type}:${id}`, definitionSources: ['technical source'],
    definitionEvidence: { status: 'matched', serverSources: ['technical source'], clientQuestMappings: 0,
        serverQuestMatches: 0, missingQuestKeys: [], issues: [] } })
const association = { parentKey: 'world_story_event:200100', boxKey: 'box_gacha:108', relationshipMatches: true, description: 'Synthetic association' }
const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' },
    baselineTimeMs: 0, baselineEvidence: 'synthetic', missing: [], resources: {}, questMap: {},
    rows: [...Array.from({ length: 30 }, (_, id) => row('gacha', 900000 + id)), row('world_story_event', 200100), row('box_gacha', 108)] }
const store = new ContentOperationsStore(db, catalog, () => CONTENT_ACTIONS, undefined, undefined, undefined, undefined, undefined,
    { associations: [association], available: true })
const save = (key, changes = {}) => {
    const state = { key, instanceId: `${key}:original`, readiness: 'verified', evidence: 'Synthetic reviewed actions',
        flags: { visible: true, enter: true, claim: true, exchange: true }, endsAtMs: null, published: true,
        revision: store.revision(), catalogDigest: store.digest, contentDigest: store.contentDigests.get(key), ...changes }
    db.prepare('INSERT OR REPLACE INTO content_operations_state(content_key,value_json) VALUES(?,?)').run(key, JSON.stringify(state))
    return state
}
for (const value of catalog.rows) save(value.key)
const operations = require('../src/lib/content-operations'), originalStore = operations.contentOperations
operations.contentOperations = () => store
const history = require('../src/lib/content-history-readiness'), originalHistory = history.contentHistoryReadinessReader
const discovery = require('../src/lib/content-discovery'), originalDiscovery = discovery.contentDiscoveryReader
history.contentHistoryReadinessReader = () => ({ get: () => ({ status: 'passed', reasons: [] }), nativePage: () => undefined,
    boxAssociation: key => [association.parentKey, association.boxKey].includes(key) ? association : undefined })
const meta = value => ({ seriesKey: value.type.padEnd(24, '0').slice(0, 24), seriesTitle: value.type })
let hydrated = 0
discovery.contentDiscoveryReader = () => ({ meta,
    view: value => { hydrated++; return { ...meta(value), highlights: [], notes: [], matchReasons: [] } },
    match: () => ({ matched: true, score: 0, reasons: [] }), details: () => ({ characters: [], rewards: [], aliases: [], notes: [] }) })
let app, cookie, captures = 0
const capture = store.managementSnapshot.bind(store)
store.managementSnapshot = () => { if (!db.inTransaction) captures++; return capture() }
const normalCapture = store.managementSnapshot
const realDateNow = Date.now
const get = url => app.inject({ url, headers: { cookie } })
before(async () => {
    app = require('fastify')({ logger: false })
    require('../src/lib/management-auth').installManagementAuth(app)
    require('../src/lib/persistence-http-errors').installPersistenceHttpErrors(app)
    await app.register(require('../src/routes/web_api/content').default, { prefix: '/api/content' })
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    assert.equal(login.statusCode, 200, login.body)
    cookie = login.headers['set-cookie'].split(';')[0]
})
after(async () => {
    Date.now = realDateNow
    await app.close()
    operations.contentOperations = originalStore
    history.contentHistoryReadinessReader = originalHistory; discovery.contentDiscoveryReader = originalDiscovery
    assert.equal(db.prepare('SELECT value FROM retained_progress').get().value, 'earned-and-paid')
    require('../src/data/db').setDbOverride(null); db.close()
})

test('card projection is opt-in, equivalent to its whitelist, strict and authenticated', async () => {
    for (const query of ['limit=5', 'limit=5&type=gacha&sort=dateDesc', 'view=series&limit=1', 'group=gacha&status=enabled']) {
        const full = await get(`/api/content/?${query}`), cards = await get(`/api/content/?${query}&projection=cards`)
        assert.equal(full.statusCode, 200, full.body); assert.equal(cards.statusCode, 200, cards.body)
        assert.deepEqual(cards.json(), projectContentManagementCards(full.json()))
        assert.equal(Object.hasOwn(full.json(), 'source'), true)
        assert.equal(Object.hasOwn(cards.json(), 'source'), false)
    }
    assert.equal((await app.inject('/api/content/?projection=cards')).statusCode, 401)
    for (const query of ['projection=full', 'projection=cards&projection=cards', 'projection=cards&includeMembers=true'])
        assert.equal((await get(`/api/content/?${query}`)).statusCode, 400)
})

test('eight concurrent cards queries build once; a completed result is not cached and revisions isolate in-flight reads', async () => {
    captures = 0
    const before = contentManagementSharedReadStatus()
    const values = await Promise.all(Array.from({ length: 8 }, () => get('/api/content/?projection=cards&limit=5')))
    for (const response of values) assert.equal(response.statusCode, 200, response.body)
    for (const response of values) assert.deepEqual(response.json(), values[0].json())
    assert.equal(captures, 1)
    assert.equal(contentManagementSharedReadStatus().sharedJoins - before.sharedJoins, 7)
    assert.equal(contentManagementSharedReadStatus().jsonBytes, 0)
    await get('/api/content/?projection=cards&limit=5'); assert.equal(captures, 2)
    const key = 'gacha:900000', revision = store.revision()
    let later
    store.managementSnapshot = () => {
        store.managementSnapshot = normalCapture
        const result = normalCapture()
        setImmediate(() => {
            store.setPublished(key, { published: false, expectedRevision: revision, catalogDigest: store.digest, reason: 'synthetic revision change' }, Date.now())
            later = get('/api/content/?projection=cards&limit=50')
        })
        return result
    }
    const first = await get('/api/content/?projection=cards&limit=50')
    const second = await later
    assert.equal(first.json().revision, revision)
    assert.equal(second.json().revision, revision + 1)
    assert.equal(second.json().rows.find(row => row.key === key).primaryControl.status, 'disabled')
})

test('series cards avoid unused preview hydration while keeping all counts', async () => {
    hydrated = 0
    const response = await get('/api/content/?projection=cards&view=series&limit=2')
    assert.equal(response.statusCode, 200, response.body)
    assert.equal(hydrated, 0)
    assert.equal(response.json().contentTotal, 32)
    assert.equal(response.json().seriesGroups[0].total, 30)
    assert.equal(Object.hasOwn(response.json().seriesGroups[0], 'preview'), false)
})

test('snapshot expiry includes hidden linked peers and action overrides at their exact inclusive boundary', () => {
    let nowMs = 1000; Date.now = () => nowMs
    try {
        save(association.parentKey)
        save(association.boxKey, { endsAtMs: 1100, actionOverrides: { visible: {
            enabled: true, readiness: 'verified', evidence: 'synthetic peer', endsAtMs: 1001,
            catalogDigest: store.digest, contentDigest: store.contentDigests.get(association.boxKey) } } })
        const snapshot = capture()
        assert.equal(snapshot.nextChangeAtMs, Infinity)
        snapshot.row(association.parentKey)
        assert.equal(snapshot.nextChangeAtMs, 1002)
        nowMs = 1002
        const refreshed = capture(); refreshed.row(association.parentKey)
        assert.equal(refreshed.nextChangeAtMs, 1101)
    } finally { Date.now = realDateNow; save(association.boxKey) }
})

test('a deadline crossing during shared construction refreshes both initial and late subscribers', async () => {
    let nowMs = 1000, later
    Date.now = () => nowMs
    save('gacha:900000', { endsAtMs: 1001 })
    captures = 0
    store.managementSnapshot = () => {
        store.managementSnapshot = normalCapture
        const result = normalCapture()
        setImmediate(() => { nowMs = 1002; later = get('/api/content/?projection=cards&limit=50') })
        return result
    }
    try {
        const first = await get('/api/content/?projection=cards&limit=50')
        const second = await later
        for (const response of [first, second]) {
            assert.equal(response.statusCode, 200, response.body)
            const target = response.json().rows.find(row => row.key === 'gacha:900000')
            assert.equal(target.primaryControl.label, '已到期')
            assert.equal(target.primaryControl.enabled, false)
        }
        assert.equal(captures, 2)
    } finally { Date.now = realDateNow; store.managementSnapshot = normalCapture; save('gacha:900000') }
})

test('repeated expiry during a rebuild stops safely with a retryable conflict', async () => {
    let nowMs = 1000
    Date.now = () => nowMs
    store.managementSnapshot = () => {
        if (db.inTransaction) return capture()
        save('gacha:900000', { endsAtMs: nowMs + 1 })
        const result = normalCapture()
        setImmediate(() => { nowMs += 2 })
        return result
    }
    try {
        const response = await get('/api/content/?projection=cards&limit=50')
        assert.equal(response.statusCode, 409, response.body)
        assert.match(response.json().message, /到期更新/)
        assert.equal(contentManagementSharedReadStatus().flights, 0)
    } finally { Date.now = realDateNow; store.managementSnapshot = normalCapture; save('gacha:900000') }
})

test('oversized card JSON uses an independent bounded read and preserves the complete legitimate response', async () => {
    const evidence = 'x'.repeat(2 * 1024 * 1024 + 1)
    const before = contentManagementSharedReadStatus()
    save('gacha:900000', { evidence })
    captures = 0
    try {
        const response = await get('/api/content/?projection=cards&limit=50')
        assert.equal(response.statusCode, 200, response.body.slice(0, 1000))
        assert.equal(response.json().rows.find(row => row.key === 'gacha:900000').state.evidence, evidence)
        assert.equal(captures, 2)
        assert.equal(contentManagementSharedReadStatus().oversized - before.oversized, 1)
        assert.equal(contentManagementSharedReadStatus().jsonBytes, 0)
        assert.equal(response.headers['cache-control'], 'private, no-store')
    } finally { save('gacha:900000') }
})
