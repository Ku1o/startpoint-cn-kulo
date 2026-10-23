'use strict'
require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path'), fs = require('node:fs'), crypto = require('node:crypto')
const Module = require('node:module'), ts = require('typescript')
if (!process.env.DATA_DIR || !/cpu-check-/.test(process.env.DATA_DIR)) throw Error('Use tools/run-isolated-check.cjs')
Object.assign(process.env, { CN_WRITER_THREAD: '0', MULTI_REALTIME_OWNER_CHILD: '0', ADMIN_PANEL_PASSWORD: 'baseline-comparison-synthetic' })
const baseline = process.env.STARPOINT_SNAPSHOT_BASELINE
const current = path.resolve(__dirname, '..')
const oracleRoot = path.join(__dirname, 'fixtures/content-original-oracles')
function originalModule(relative, overrides = {}) {
    const file = path.join(oracleRoot, 'management-full', relative), bytes = fs.readFileSync(file)
    const identity = JSON.parse(fs.readFileSync(path.join(oracleRoot, 'manifest.json'))).files['management-full/' + relative]
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), identity.sha256)
    assert.equal(bytes.length, identity.bytes)
    const virtual = path.join(current, relative.replace(/\.ts$/, '.full-snapshot-oracle.cjs'))
    const instance = new Module(virtual, module)
    instance.filename = virtual; instance.paths = Module._nodeModulePaths(path.dirname(virtual))
    const requireOriginal = instance.require.bind(instance)
    instance.require = name => Object.hasOwn(overrides, name) ? overrides[name] : requireOriginal(name)
    instance._compile(ts.transpileModule(bytes.toString('utf8'), { fileName: file,
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2016, esModuleInterop: true } }).outputText, virtual)
    return instance.exports
}
const Sqlite = require('better-sqlite3')
const hash = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex')
const memberTypes = new Set(['general_shop', 'treasure_shop', 'star_grain_shop', 'boss_coin_shop', 'event_item_shop', 'mission_regular', 'mission_daily', 'mission_event', 'shop_product'])
const isParent = row => !memberTypes.has(row.type) && !row.type.startsWith('mission_')
const frozenTime = Date.parse('2026-10-22T02:00:00Z')

async function fixture(root, directory, catalog) {
    const original = root === null, isolated = {}
    const load = name => {
        if (!original) return require(path.join(root, directory, name))
        if (name === 'lib/content-operations-store') return isolated[name] ??= originalModule('src/' + name + '.ts')
        if (['lib/content-operations', 'lib/content-history-readiness', 'lib/content-discovery'].includes(name)) {
            return isolated[name] ??= { ...require(path.join(current, 'src', name)) }
        }
        if (name === 'routes/web_api/content') return isolated[name] ??= originalModule('src/' + name + '.ts', {
            '../../lib/content-operations': load('lib/content-operations'),
            '../../lib/content-operations-store': load('lib/content-operations-store'),
            '../../lib/content-history-readiness': load('lib/content-history-readiness'),
            '../../lib/content-discovery': load('lib/content-discovery'),
        })
        return require(path.join(current, 'src', name))
    }
    const db = new Sqlite(':memory:')
    const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = load('lib/content-operations-store')
    initializeContentOperationsSchema(db)
    load('data/db').setDbOverride(db)
    const store = new ContentOperationsStore(db, catalog,
        row => row.id % 7 === 0 ? [] : row.type.endsWith('_exchange_campaign') ? ['exchange'] : CONTENT_ACTIONS,
        () => ({ digest: 'controlled-runtime-definition', matchesCatalog: true }))
    const insert = db.prepare('INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?)')
    db.transaction(() => {
        for (let index = 0; index < catalog.rows.length; index++) {
            const row = catalog.rows[index]
            if (index % 6 === 0) continue
            insert.run(row.key, JSON.stringify({ key: row.key, instanceId: `${row.key}:original`,
                readiness: index % 5 === 0 ? 'blocked' : 'verified', evidence: 'Controlled baseline equivalence review',
                flags: { visible: true, enter: true, claim: true, exchange: true },
                endsAtMs: index % 4 === 0 ? frozenTime - 1 : index % 4 === 1 ? frozenTime + 1 : null,
                published: index % 3 !== 0, revision: 17, catalogDigest: store.digest, contentDigest: store.contentDigests.get(row.key) }))
        }
    })()
    db.prepare('UPDATE content_operations_meta SET revision=17').run()
    const operations = load('lib/content-operations'), savedOperations = operations.contentOperations
    operations.contentOperations = () => store
    const history = load('lib/content-history-readiness')
    const old = { get: history.getContentHistoryReadiness, nativePage: history.getContentHistoryNativePage,
        boxAssociation: history.getContentHistoryBoxAssociation, reader: history.contentHistoryReadinessReader }
    const historyReader = { get: key => ({ status: Number(key.split(':')[1]) % 11 === 0 ? 'blocked' : 'passed',
        reasons: Number(key.split(':')[1]) % 11 === 0 ? ['Controlled unavailable child'] : [] }),
        nativePage: () => undefined, boxAssociation: () => undefined }
    history.getContentHistoryReadiness = historyReader.get
    history.getContentHistoryNativePage = historyReader.nativePage
    history.getContentHistoryBoxAssociation = historyReader.boxAssociation
    if (history.contentHistoryReadinessReader) history.contentHistoryReadinessReader = () => historyReader
    const discovery = load('lib/content-discovery'), oldDiscovery = discovery.contentDiscoveryReader
    const meta = row => ({ seriesKey: hash([row.type, row.presentation.originalTitle || row.presentation.title]).slice(0, 24),
        seriesTitle: row.presentation.title, editionLabel: `Edition ${row.id}` })
    discovery.contentDiscoveryReader = () => ({ meta,
        view: row => ({ ...meta(row), highlights: [{ label: 'Controlled reward', names: [`Reward ${row.id}`], total: 1 }], notes: [], matchReasons: [] }),
        match: (row, terms) => ({ matched: terms.every(term => [row.name, row.key, row.presentation.title, '共同检索'].join(' ').toLocaleLowerCase().includes(term)),
            score: terms.length ? row.id % 13 : 0, reasons: terms.length ? ['Controlled match'] : [] }),
        details: key => ({ characters: [{ id: Number(key.split(':')[1]), name: `Controlled ${key}`, relation: 'up' }], rewards: [], aliases: [], notes: [] }) })
    const app = require('fastify')({ logger: false })
    load('lib/management-auth').installManagementAuth(app)
    await app.register(load('routes/web_api/content').default, { prefix: '/api/content' })
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    assert.equal(login.statusCode, 200, login.body)
    const cookie = login.headers['set-cookie'].split(';')[0]
    return { get: url => app.inject({ url, headers: { cookie } }), close: async () => {
        await app.close(); operations.contentOperations = savedOperations; discovery.contentDiscoveryReader = oldDiscovery
        history.getContentHistoryReadiness = old.get; history.getContentHistoryNativePage = old.nativePage
        history.getContentHistoryBoxAssociation = old.boxAssociation
        if (old.reader) history.contentHistoryReadinessReader = old.reader
        load('data/db').setDbOverride(null); db.close()
    } }
}

test('frozen baseline and current backend produce exact JSON across all real parent pages and query contracts', async () => {
    const originalNow = Date.now
    Date.now = () => frozenTime
    const catalog = JSON.parse(fs.readFileSync(path.join(baseline || current, 'assets/content_catalog.json'), 'utf8'))
    assert.equal(catalog.rows.filter(isParent).length, 1020)
    let old, next
    const comparisons = []
    try {
        old = await fixture(baseline || null, 'out', catalog)
        next = await fixture(current, 'src', catalog)
        const compare = async url => {
            const a = await old.get(url), b = await next.get(url)
            assert.equal(b.statusCode, a.statusCode, url)
            const left = a.json(), right = b.json()
            const query = new URL(url, 'http://fixture.invalid').searchParams
            if (a.statusCode === 200 && ['dateAsc', 'dateDesc'].includes(query.get('sort'))) {
                // Explicit date ordering intentionally changed after this frozen
                // implementation: ties now keep catalog order, independent of
                // search score or enabled state. Derive the new expectation
                // from the complete original API rows, not the new response.
                const selected = [], all = new URLSearchParams(query)
                all.delete('sort'); all.set('limit', '200')
                for (let offset = 0; ; offset += 200) {
                    all.set('offset', String(offset))
                    const original = await old.get('/api/content/?' + all)
                    assert.equal(original.statusCode, 200)
                    const page = original.json(); selected.push(...page.rows)
                    if (selected.length >= page.total) break
                }
                const positions = new Map(catalog.rows.map((row, index) => [row.key, index]))
                const direction = query.get('sort') === 'dateDesc' ? -1 : 1
                selected.sort((one, two) => {
                    if (one.originalStartMs === null && two.originalStartMs !== null) return 1
                    if (two.originalStartMs === null && one.originalStartMs !== null) return -1
                    return (one.originalStartMs !== null && two.originalStartMs !== null
                        ? (one.originalStartMs - two.originalStartMs) * direction : 0)
                        || positions.get(one.key) - positions.get(two.key)
                })
                const offset = Number(query.get('offset') || 0), limit = Number(query.get('limit') || 200)
                left.rows = selected.slice(offset, offset + limit)
            }
            assert.deepEqual(right, left, url)
            comparisons.push({ url, statusCode: b.statusCode, sha256: hash(right), rows: right.rows?.length,
                total: right.total, series: right.seriesGroups?.length })
            return right
        }
        for (let offset = 0; offset < 1020; offset += 200) await compare(`/api/content/?offset=${offset}&limit=200`)
        const firstSeries = await compare('/api/content/?view=series&limit=200')
        for (let offset = 200; offset < firstSeries.total; offset += 200) await compare(`/api/content/?view=series&offset=${offset}&limit=200`)
        const firstKey = catalog.rows.find(isParent).key, finalKey = catalog.rows.filter(isParent).at(-1).key
        for (const query of ['search=共同检索&group=gacha&status=disabled&sort=dateDesc&limit=17',
            'group=events&status=unsupported&limit=17', 'group=exchange&readiness=verified&sort=dateAsc&limit=17',
            'type=gacha&status=all&offset=200&limit=17', 'julyOnly=true&limit=17', 'candidatesOnly=true&limit=17',
            'includeMembers=true&type=event_item_shop&offset=200&limit=17', 'keys=',
            `keys=${encodeURIComponent(finalKey + ',' + firstKey)}&keyOrder=true&limit=2`,
            `series=${firstSeries.seriesGroups[0].key}&limit=200`, 'view=series&group=gacha&status=disabled&limit=17',
            'limit=201', 'status=invalid']) await compare(`/api/content/?${query}`)
        for (const key of [firstKey, finalKey]) await compare(`/api/content/${encodeURIComponent(key)}/discovery`)
        if (process.env.STARPOINT_SNAPSHOT_COMPARE_OUTPUT) fs.writeFileSync(process.env.STARPOINT_SNAPSHOT_COMPARE_OUTPUT,
            JSON.stringify({ frozenTime, revision: 17, parentCount: 1020, comparisonCount: comparisons.length,
                exactJsonEqual: true, scope: 'Controlled identical states/readiness/discovery, real parent catalog and presentation; no performance comparison', comparisons }, null, 2))
    } finally { if (next) await next.close(); if (old) await old.close(); Date.now = originalNow }
})
