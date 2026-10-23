'use strict'
require('ts-node/register/transpile-only')
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
if (!process.env.DATA_DIR || !process.env.STARPOINT_TEST_TMP_ROOT && !/cpu-check-/.test(process.env.DATA_DIR))
    throw Error('Run via tools/run-isolated-check.cjs with disposable DATA_DIR')
Object.assign(process.env, { CN_WRITER_THREAD: '0', MULTI_REALTIME_OWNER_CHILD: '0', ADMIN_PANEL_PASSWORD: 'snapshot-api-synthetic-only' })
const Sqlite = require('better-sqlite3')
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require('../src/lib/content-operations-store')
const sql = [], db = new Sqlite(':memory:', { verbose: statement => sql.push(statement) })
initializeContentOperationsSchema(db)
db.exec("CREATE TABLE retained_progress(value TEXT); INSERT INTO retained_progress VALUES('earned-and-paid')")
require('../src/data/db').setDbOverride(db)
const row = (type, id) => ({ key: `${type}:${id}`, type, id, name: `Synthetic ${type} ${id}`,
    originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: null,
    windowCandidate: false, browseCandidate: false, source: 'synthetic', definitionDigest: `${type}:${id}` })
const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' },
    baselineTimeMs: 0, baselineEvidence: 'synthetic', missing: [], resources: {}, questMap: {},
    rows: [...Array.from({ length: 1020 }, (_, id) => row('gacha', 900000 + id)),
        ...Array.from({ length: 500 }, (_, id) => row('event_item_shop', 500000 + id)),
        row('world_story_event', 200100), row('box_gacha', 108)] }
const store = new ContentOperationsStore(db, catalog, () => CONTENT_ACTIONS)
const insert = db.prepare('INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?)')
db.transaction(() => {
    for (const value of catalog.rows) insert.run(value.key, JSON.stringify({ key: value.key, instanceId: `${value.key}:original`,
        readiness: 'verified', evidence: 'Synthetic reviewed actions', flags: { visible: true, enter: true, claim: true, exchange: true },
        endsAtMs: null, published: false, revision: 0, catalogDigest: store.digest, contentDigest: store.contentDigests.get(value.key) }))
})()
const operations = require('../src/lib/content-operations'), originalStore = operations.contentOperations
operations.contentOperations = () => store
const history = require('../src/lib/content-history-readiness'), originalHistory = history.contentHistoryReadinessReader
const discovery = require('../src/lib/content-discovery'), originalDiscovery = discovery.contentDiscoveryReader
let viewReads = 0, historyCaptures = 0, decoded = 0
const decode = store.decodeState.bind(store)
store.decodeState = (...args) => { decoded++; return decode(...args) }
const association = { parentKey: 'world_story_event:200100', boxKey: 'box_gacha:108', relationshipMatches: true, description: 'Synthetic association' }
history.contentHistoryReadinessReader = () => {
    historyCaptures++
    return { get: () => ({ status: 'passed', reasons: [] }), nativePage: () => undefined,
        boxAssociation: key => [association.parentKey, association.boxKey].includes(key) ? association : undefined }
}
const meta = value => ({ seriesKey: value.type.padEnd(24, '0').slice(0, 24), seriesTitle: value.type })
discovery.contentDiscoveryReader = () => ({ meta,
    view: value => { viewReads++; return { ...meta(value), highlights: [], notes: [], matchReasons: [] } },
    match: () => ({ matched: true, score: 0, reasons: [] }),
    details: () => ({ characters: [], rewards: [], aliases: [], notes: [] }) })
let app, cookie
before(async () => {
    app = require('fastify')({ logger: false })
    require('../src/lib/management-auth').installManagementAuth(app)
    await app.register(require('../src/routes/web_api/content').default, { prefix: '/api/content' })
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    assert.equal(login.statusCode, 200, login.body)
    cookie = login.headers['set-cookie'].split(';')[0]
})
after(async () => {
    await app.close()
    operations.contentOperations = originalStore
    history.contentHistoryReadinessReader = originalHistory
    discovery.contentDiscoveryReader = originalDiscovery
    assert.equal(db.prepare('SELECT value FROM retained_progress').get().value, 'earned-and-paid')
    require('../src/data/db').setDbOverride(null)
    db.close()
})
const get = url => app.inject({ url, headers: { cookie } })

test('default management GET captures controls once, decodes only parents, and hydrates only its page', async () => {
    sql.length = 0; decoded = 0; viewReads = 0; historyCaptures = 0
    const response = await get('/api/content/?limit=5')
    assert.equal(response.statusCode, 200, response.body)
    const data = response.json()
    assert.equal(data.total, 1022)
    assert.equal(data.rows.length, 5)
    assert.equal(decoded, 1022, '500 member controls never enter the parent read/decode path')
    assert.equal(viewReads, 5, 'full discovery is not prepared for all 1022 parents before pagination')
    assert.equal(historyCaptures, 1)
    assert.equal(sql.filter(statement => /SELECT content_key,value_json FROM content_operations_state/.test(statement)).length, 1)
    assert.equal(sql.filter(statement => /SELECT revision FROM content_operations_meta/.test(statement)).length, 1)
    assert.equal(sql.filter(statement => /SELECT value_json FROM content_operations_state WHERE/.test(statement)).length, 0,
        'linked deadline controls reuse the captured snapshot')
})

test('series summary hydrates only returned previews and preserves all edition counts', async () => {
    viewReads = 0
    const response = await get('/api/content/?view=series&limit=1')
    assert.equal(response.statusCode, 200, response.body)
    assert.equal(response.json().contentTotal, 1022)
    assert.equal(response.json().seriesGroups[0].total, 1020)
    assert.equal(viewReads, 1)
})

test('a write between cooperative read slices cannot mix revisions and stale page CAS remains rejected', async () => {
    const revision = store.revision(), key = 'gacha:900000'
    const capture = store.managementSnapshot.bind(store)
    let changed = false
    store.managementSnapshot = () => {
        store.managementSnapshot = capture
        const snapshot = capture()
        setImmediate(() => {
            store.setPublished(key, { expectedRevision: revision, catalogDigest: store.digest,
                reason: 'Synthetic concurrent publication', published: true }, Date.now())
            changed = true
        })
        return snapshot
    }
    const response = await get('/api/content/?limit=5')
    assert.equal(response.statusCode, 200, response.body)
    assert.equal(changed, true, 'the read yielded while a new control revision was written')
    assert.equal(response.json().revision, revision)
    assert.equal(response.json().rows.find(value => value.key === key).state.published, false)
    const fresh = await get('/api/content/?limit=5')
    assert.equal(fresh.json().revision, revision + 1)
    assert.equal(fresh.json().rows.find(value => value.key === key).state.published, true)
    const rejected = await app.inject({ method: 'PATCH', url: `/api/content/${encodeURIComponent(key)}/publication`, headers: { cookie },
        payload: { expectedRevision: revision, catalogDigest: store.digest, reason: 'Synthetic stale page', published: false } })
    assert.equal(rejected.statusCode, 409, rejected.body)
    assert.equal(store.state(key).published, true)
})

test('actual WorldBox publication route rolls back first side and audit if the linked second write fails', async () => {
    const revision = store.revision(), original = store.state(association.parentKey)
    const auditCount = db.prepare('SELECT count(*) AS n FROM content_operations_audit').get().n
    const setPublished = store.setPublished.bind(store)
    store.setPublished = (key, body, nowMs) => {
        if (key === association.boxKey) throw new Error('Synthetic second-side failure')
        return setPublished(key, body, nowMs)
    }
    try {
        const response = await app.inject({ method: 'PATCH', url: `/api/content/${encodeURIComponent(association.parentKey)}/publication`,
            headers: { cookie }, payload: { expectedRevision: revision, catalogDigest: store.digest, reason: 'Synthetic linked rollback', published: true } })
        assert.equal(response.statusCode, 500, response.body)
        assert.equal(store.revision(), revision)
        assert.deepEqual(store.state(association.parentKey), original)
        assert.equal(store.state(association.boxKey).published, false)
        assert.equal(db.prepare('SELECT count(*) AS n FROM content_operations_audit').get().n, auditCount)
    } finally { store.setPublished = setPublished }
})
