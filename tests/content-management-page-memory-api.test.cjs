'use strict'
require('ts-node/register/transpile-only')
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), Module = require('node:module'), ts = require('typescript')
if (!process.env.DATA_DIR || !process.env.STARPOINT_TEST_TMP_ROOT) throw Error('Task-local isolated environment is required')
Object.assign(process.env, { CN_WRITER_THREAD: '0', MULTI_REALTIME_OWNER_CHILD: '0', ADMIN_PANEL_PASSWORD: 'page-memory-api-synthetic-only' })
const repo = path.resolve(__dirname, '..')
const oracleRoot = path.join(__dirname, 'fixtures/content-original-oracles')
const phase = process.env.STARPOINT_PAGE_MEMORY_BASELINE
function previous(relative) {
    const file = phase ? path.join(phase, 'preimage', relative) : path.join(oracleRoot, 'management-page', relative)
    if (!phase) {
        const identity = JSON.parse(fs.readFileSync(path.join(oracleRoot, 'manifest.json'))).files['management-page/' + relative]
        assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'), identity.sha256)
        assert.equal(fs.statSync(file).size, identity.bytes)
    }
    const virtual = path.join(repo, relative.replace(/\.ts$/, '.page-memory-baseline.cjs'))
    const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { fileName: file,
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2016, esModuleInterop: true } }).outputText
    const module = new Module(virtual, require.module)
    module.filename = virtual; module.paths = Module._nodeModulePaths(path.dirname(virtual)); module._compile(compiled, virtual)
    return module.exports
}
const priorStore = previous('src/lib/content-operations-store.ts')
const priorRoute = previous('src/routes/web_api/content.ts').default
const currentStore = require('../src/lib/content-operations-store')
const Sqlite = require('better-sqlite3'), databases = []
const row = (type, id, extra = {}) => ({ key: `${type}:${id}`, type, id, name: `Synthetic ${type} ${id}`,
    originalStartMs: id % 5 === 0 ? null : Date.UTC(2025, 6, 10 + id % 4), originalEndMs: id % 7 === 0 ? Date.UTC(2025, 5, 1) : Date.UTC(2025, 7, 1),
    originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false, source: 'synthetic', definitionDigest: `${type}:${id}`, ...extra })
const native = { parentKey: 'world_story_event:200100', boxKey: 'box_gacha:108', relationshipMatches: true, description: 'Synthetic native pair' }
const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' }, baselineTimeMs: 0,
    baselineEvidence: 'synthetic', missing: [], resources: {}, questMap: {}, rows: [
        ...Array.from({ length: 40 }, (_, id) => row('gacha', 900000 + id)), row('gacha', 2), row('pass_card_event', 1), row('pass_card_event', 2),
        row('collect_item_event', 70), row('active_mission_event', 69), row('world_story_event', 200100, { parentKey: 'event_item_shop:500000' }),
        row('box_gacha', 108), row('unsupported', 1),
        ...Array.from({ length: 1200 }, (_, id) => row('event_item_shop', 500000 + id)),
        ...Array.from({ length: 100 }, (_, id) => row('mission_daily', 700000 + id)),
    ] }
const frozenNow = Date.UTC(2026, 9, 23, 2), realNow = Date.now
Date.now = () => frozenNow
function fixture(implementation) {
    const db = new Sqlite(':memory:'); databases.push(db); implementation.initializeContentOperationsSchema(db)
    db.exec("CREATE TABLE retained_progress(value TEXT); INSERT INTO retained_progress VALUES('paid-earned-claimed')")
    const store = new implementation.ContentOperationsStore(db, catalog, value => value.type === 'unsupported' ? [] : implementation.CONTENT_ACTIONS,
        undefined, undefined, undefined, undefined, undefined, { available: true, associations: [native] })
    const insert = db.prepare('INSERT INTO content_operations_state VALUES(?,?)')
    for (const value of catalog.rows) insert.run(value.key, JSON.stringify({ key: value.key, instanceId: `${value.key}:original`,
        readiness: value.id % 13 === 0 ? 'blocked' : 'verified', evidence: 'Synthetic exact scope ' + 'x'.repeat(1500),
        flags: { visible: true, enter: value.id % 8 !== 0, claim: true, exchange: true },
        endsAtMs: value.id % 6 === 0 ? frozenNow - 1 : value.id % 6 === 1 ? frozenNow + 5000 : null,
        published: value.id % 3 !== 0, revision: 0, catalogDigest: store.digest, contentDigest: store.contentDigests.get(value.key),
        questKeys: [], missionKeys: null,
    }))
    const reads = [], prepare = db.prepare.bind(db)
    db.prepare = sql => {
        const statement = prepare(sql)
        if (/^SELECT content_key,value_json FROM content_operations_state/.test(sql)) {
            const all = statement.all.bind(statement)
            statement.all = (...args) => {
                const values = all(...args)
                reads.push({ controls: values.length, bytes: values.reduce((sum, value) => sum + Buffer.byteLength(value.value_json), 0), scoped: /WHERE/.test(sql) })
                return values
            }
        }
        return statement
    }
    return { store, db, reads }
}
const old = fixture(priorStore), current = fixture(currentStore)
let active = current, oldApp, app, cookie
require('../src/data/db').setDbOverride(current.db)
const operations = require('../src/lib/content-operations'), originalOperations = operations.contentOperations
operations.contentOperations = () => active.store
const history = require('../src/lib/content-history-readiness'), originalHistory = history.contentHistoryReadinessReader
history.contentHistoryReadinessReader = () => ({
    get: key => key === 'unsupported:1' ? { status: 'blocked', reasons: ['Synthetic blocked review'] } : { status: 'passed', reasons: [] },
    nativePage: key => key === 'collect_item_event:70' ? { kind: 'collect_item_exchange_shop', label: 'Synthetic native exchange', description: 'Exact native group' } : undefined,
    boxAssociation: key => [native.parentKey, native.boxKey].includes(key) ? native : undefined,
})
const discovery = require('../src/lib/content-discovery'), originalDiscovery = discovery.contentDiscoveryReader
const seriesKey = type => crypto.createHash('sha256').update(type).digest('hex').slice(0, 24)
const meta = row => ({ seriesKey: seriesKey(row.type), seriesTitle: row.type + ' series' })
discovery.contentDiscoveryReader = () => ({ verificationNotice: 'Synthetic association fixture', meta,
    view: row => ({ ...meta(row), highlights: [], notes: ['Synthetic retained note'], matchReasons: [] }),
    match: (row, terms) => { const text = discovery.normalizeDiscoveryText(`${row.name} ${row.presentation.title} ${row.key}`)
        const matched = terms.every(term => text.includes(term))
        return { matched, score: terms.length && matched ? 100 + row.id % 3 : 0, reasons: terms.length && matched ? ['Synthetic exact match'] : [] } },
    details: () => ({ characters: [], rewards: [], aliases: [], notes: [] }),
})
const get = async (target, owner, query) => {
    active = owner
    const response = await target.inject({ url: '/api/content/?' + query, headers: { cookie } })
    return { status: response.statusCode, data: response.json() }
}
before(async () => {
    const create = async route => {
        const server = require('fastify')({ logger: false })
        require('../src/lib/management-auth').installManagementAuth(server)
        require('../src/lib/persistence-http-errors').installPersistenceHttpErrors(server)
        await server.register(route, { prefix: '/api/content' }); await server.ready(); return server
    }
    oldApp = await create(priorRoute); app = await create(require('../src/routes/web_api/content').default)
    const response = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    assert.equal(response.statusCode, 200, response.body); cookie = response.headers['set-cookie'].split(';')[0]
})
after(async () => {
    await app.close(); await oldApp.close(); operations.contentOperations = originalOperations
    history.contentHistoryReadinessReader = originalHistory; discovery.contentDiscoveryReader = originalDiscovery
    for (const db of databases) { assert.equal(db.prepare('SELECT value FROM retained_progress').get().value, 'paid-earned-claimed'); db.close() }
    require('../src/data/db').setDbOverride(null); Date.now = realNow
})

test('frozen original and scoped implementation produce identical complete full/cards responses across filters and navigation', async () => {
    const queries = ['', 'limit=5&offset=5', 'group=gacha', 'group=events', 'group=missions', 'group=exchange',
        'status=enabled', 'status=disabled', 'status=pending', 'status=blocked', 'status=unsupported', 'type=gacha',
        'readiness=blocked', 'readiness=verified', 'julyOnly=true', 'candidatesOnly=true', 'sort=dateAsc', 'sort=dateDesc',
        'view=series', 'view=series&offset=1&limit=1', `series=${seriesKey('gacha')}`, 'keys=',
        'keys=gacha%3A900005,gacha%3A900006&keyOrder=true', 'search=Synthetic', 'search=900005',
        'search=Synthetic&group=gacha&status=disabled&sort=dateAsc', 'search=absent-text', 'includeMembers=true&limit=3',
        'type=event_item_shop&limit=3']
    let pairs = 0
    for (const query of queries) for (const projection of ['', '&projection=cards']) {
        const request = query + projection
        const expected = await get(oldApp, old, request), actual = await get(app, current, request)
        assert.deepEqual(actual, expected, request); pairs++
    }
    assert.equal(pairs, 58)
})

test('actual parent route captures only parent/dependency controls while member/full legacy routes remain available', async () => {
    old.reads.length = 0; current.reads.length = 0
    const expected = await get(oldApp, old, 'limit=5'), actual = await get(app, current, 'limit=5')
    assert.deepEqual(actual, expected)
    assert.equal(old.reads.length, 1); assert.equal(current.reads.length, 1)
    assert.equal(old.reads[0].controls, catalog.rows.length)
    const parentCount = catalog.rows.filter(row => !row.type.startsWith('mission_') && row.type !== 'event_item_shop').length
    assert.equal(current.reads[0].controls, parentCount + 1)
    assert.equal(current.reads[0].scoped, true)
    assert.ok(current.reads[0].bytes < old.reads[0].bytes / 10)
    const member = await get(app, current, 'type=event_item_shop&limit=3')
    assert.equal(member.status, 200); assert.equal(member.data.rows.length, 3)
    assert.equal(current.reads.at(-1).scoped, false)
})
