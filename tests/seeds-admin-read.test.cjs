'use strict'
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const ts = require('typescript'), Fastify = require('fastify')
const root = path.resolve(__dirname, '..')
const plain = value => JSON.parse(JSON.stringify(value))
function load(relative, imports, globals = {}) {
    const filename = path.join(root, relative), module = { exports: {} }
    const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { reportDiagnostics: true,
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } })
    assert.equal(compiled.diagnostics.filter(d => d.category === ts.DiagnosticCategory.Error).length, 0)
    vm.runInNewContext(compiled.outputText, { module, exports: module.exports, URL, process, __dirname: path.dirname(filename),
        console: { log() {}, error() {} }, require(name) { if (name in imports) return imports[name]; if (name.endsWith('.css')) return {}; throw new Error(`Unexpected import ${name}`) }, ...globals }, { filename })
    return module.exports
}
const noPersistence = { SeedPersistence: class { update() { throw new Error('read must not persist') } } }
const validatorModule = load('src/lib/seed-validator.ts', {
    path, './atomic-json-file': { readJsonWithBackupSync: () => null, writeJsonAtomicSync: () => { throw new Error('read must not write') } },
    './seed-persistence': noPersistence, './seed-feedback-guard': { SeedFeedbackGuard: class {} },
})
const { SeedValidator } = validatorModule
function pool({ confirm = [], play = [], verified = [], pending = [] } = {}) {
    return { confirmPool: new Map(confirm), playPool: new Map(play), verifiedPool: new Map(verified), pendingPool: new Map(pending), sentSeeds: new Map(), sentPlayFlags: new Map() }
}
function fixture() {
    const validator = new SeedValidator('/synthetic-no-files')
    validator.pools = new Map([
        ['fes', pool({ confirm: [[1, 0], [2, 0]], play: [[2, { r: 0, tag: '热血躲避球', play: true }]], verified: [[3, 1]], pending: [[4, null]] })],
        ['fes_guarantee', pool({ confirm: [[10, 1]], verified: [[11, 2]] })],
        ['normal', pool({ confirm: [[100, 0], [101, 1], [102, 2]], play: [[103, { r: 2, tag: '未测试' }]] })],
    ])
    return validator
}
function virtualCounts() {
    const files = new Map(), reads = new Map()
    const seedFile = (movie, seeds, signature = 1) => files.set(`gacha_movie_seeds_${movie}.json`, { contents: JSON.stringify({ character: { normal: seeds } }), signature })
    seedFile('fes', [1, 2, 3]); seedFile('fes_guarantee', [4, 5]); seedFile('normal', [6]); seedFile('normal_guarantee', [7])
    const io = {
        readdirSync: () => [...files.keys(), 'confirmed_seeds.json'],
        statSync: file => { const item = files.get(path.basename(file)); if (!item) throw new Error('missing'); return { dev: 1n, ino: BigInt(item.signature), size: BigInt(item.contents.length), mtimeNs: 1n, ctimeNs: BigInt(item.signature) } },
        readFileSync: file => { const name = path.basename(file); reads.set(name, (reads.get(name) || 0) + 1); return files.get(name).contents },
    }
    const { SeedFileCountCache } = load('src/lib/seed-file-count-cache.ts', { fs: io, path })
    return { counts: new SeedFileCountCache('/synthetic-assets'), files, reads, seedFile }
}

test('static count cache avoids unchanged parsing and detects replacement/add/delete/corruption without caching live learned data', () => {
    const { counts, reads, seedFile, files } = virtualCounts()
    assert.equal(counts.snapshot().total, 7); assert.equal([...reads.values()].reduce((a, b) => a + b, 0), 4)
    assert.equal(counts.snapshot().byMovie.get('fes'), 3); assert.equal([...reads.values()].reduce((a, b) => a + b, 0), 4)
    assert.equal(counts.snapshot().catalogs.get('fes').size, 3); assert.equal(counts.snapshot().catalogs.get('fes').byteLength, 12)
    // Same byte size and mtime, different inode/ctime: original atomic file replacement invalidates.
    seedFile('fes', [8, 9, 0], 2); assert.equal(counts.snapshot().total, 7); assert.equal(reads.get('gacha_movie_seeds_fes.json'), 2)
    seedFile('normal', [1, 2, 3, 4], 3); assert.equal(counts.snapshot().total, 10)
    files.delete('gacha_movie_seeds_normal_guarantee.json'); assert.equal(counts.snapshot().total, 9)
    files.set('gacha_movie_seeds_extra.json', { contents: '{broken', signature: 4 }); assert.equal(counts.snapshot().byMovie.get('extra'), 0)
    counts.snapshot(); assert.equal(reads.get('gacha_movie_seeds_extra.json'), 1)
    seedFile('extra', [1, 2], 5); assert.equal(counts.snapshot().byMovie.get('extra'), 2)
    seedFile('extra', [4294967305, 7, 7], 6)
    const exact = counts.snapshot().catalogs.get('extra'); assert.equal(exact.size, 2); assert.equal(exact.byteLength, 16)
    assert.equal(exact.has(4294967305), true); assert.equal(exact.has(4294967296), false); assert.equal(exact.has(7), true)
    files.clear(); assert.equal(counts.snapshot().total, 19941)
})

test('checked-in static file totals match the legacy valid-file calculation offline', () => {
    const { SeedFileCountCache } = load('src/lib/seed-file-count-cache.ts', { fs, path })
    const directory = path.join(root, 'assets'), snapshot = new SeedFileCountCache(directory).snapshot()
    let total = 0
    for (const filename of fs.readdirSync(directory).filter(name => /^gacha_movie_seeds_.*\.json$/.test(name))) {
        const data = JSON.parse(fs.readFileSync(path.join(directory, filename), 'utf8'))
        const count = Object.values(data).reduce((sum, group) => sum + Object.values(group).reduce((n, seeds) => n + seeds.length, 0), 0)
        assert.equal(snapshot.byMovie.get(filename.slice('gacha_movie_seeds_'.length, -5)), count); total += count
    }
    assert.equal(snapshot.total, total)
    assert.equal([...snapshot.catalogs.values()].reduce((sum, catalog) => sum + catalog.byteLength, 0), total * 4, 'current uint32 catalogs use four bytes per entry')
})

test('management summary counts only requested movies and deduplicates tested seeds within each movie', () => {
    const validator = fixture(), beforePools = validator.pools.size, selected = validator.getSelectedMovieId()
    const summary = validator.getAdminGroupSummary(['fes', 'fes_guarantee'])
    assert.deepEqual(plain(summary.movies.map(row => [row.movieId, row.learned])), [['fes', 3], ['fes_guarantee', 2]])
    assert.equal(summary.movies[0].columns.play.r3, 1); assert.equal(summary.movies[1].columns.verified.r5b, 1)
    validator.getAdminGroupSummary(['absent']); validator.getAdminSeedPage(['absent'], 'play', 1, 10)
    assert.equal(validator.pools.size, beforePools); assert.equal(validator.getSelectedMovieId(), selected)
    validator.pools.get('fes').verifiedPool.set(5, 2)
    assert.equal(validator.getAdminGroupSummary(['fes']).movies[0].learned, 4, 'live mutations are read without a stale summary cache')
})

test('paged management lists retain movie identity/order and never call full legacy list materialization', () => {
    const validator = fixture()
    validator.pools.get('fes').playPool = new Map([[20, { r: 0, tag: '未测试' }], [21, { r: 1, tag: '冷血躲避球' }], [22, { r: 2, tag: '普通躲避球' }]])
    validator.pools.get('fes_guarantee').playPool = new Map([[23, { r: 1, tag: '热血躲避球' }], [24, { r: 2, tag: '未测试' }]])
    validator.getPlayList = validator.getVerifiedList = () => { throw new Error('must not create full arrays') }
    const first = validator.getAdminSeedPage(['fes', 'fes_guarantee'], 'play', 1, 2)
    const second = validator.getAdminSeedPage(['fes', 'fes_guarantee'], 'play', 2, 2)
    const last = validator.getAdminSeedPage(['fes', 'fes_guarantee'], 'play', 999, 2)
    assert.deepEqual(plain(first.rows.map(row => row.seed)), [20, 21]); assert.equal(first.total, 5)
    assert.deepEqual(plain(second.rows.map(row => [row.seed, row.movie, row.rarity])), [[22, 'fes', 5], [23, 'fes_guarantee', 4]])
    assert.equal(second.rows[1].isGuarantee, true); assert.equal(last.page, 3); assert.deepEqual(plain(last.rows.map(row => row.seed)), [24])
})

test('registered group APIs are bounded/read-only, reject invalid selectors, and preserve legacy stats/list default response', async t => {
    const validator = fixture(), cache = { snapshot: () => ({ total: 115, byMovie: new Map([['fes', 10], ['fes_guarantee', 5], ['normal', 100]]),
        catalogs: new Map([['fes', { valid: true, size: 10, has: seed => seed >= 1 && seed <= 10 }], ['fes_guarantee', { valid: true, size: 5, has: seed => seed >= 10 && seed <= 14 }]]) }) }
    const { createSeedsAdminRoutes } = load('src/routes/web_api/seeds.ts', {
        '../../lib/seed-validator': { __esModule: true, default: validator }, path,
        '../../lib/seed-file-count-cache': { SeedFileCountCache: class {} },
    })
    const app = Fastify({ logger: false }); t.after(() => app.close())
    await app.register(createSeedsAdminRoutes(validator, cache), { prefix: '/api/seeds' })
    const body = async url => { const response = await app.inject({ method: 'GET', url }); assert.equal(response.statusCode, 200, response.body); return response.json() }
    const overview = await body('/api/seeds/group/fes/overview')
    assert.equal(overview.total, 15); assert.equal(overview.tested, 5); assert.equal(overview.learned, 5); assert.equal(overview.externalKnown, 0); assert.equal(overview.unknown, 10); assert.equal(overview.coverage, 5 / 15 * 100)
    assert.equal('rows' in overview, false); assert.equal('playRows' in overview, false)
    assert.equal((await body('/api/seeds/group/fes/list?kind=verified&page=1&pageSize=1')).rows.length, 1)
    const legacyStats = await body('/api/seeds/stats')
    const expected = validator.stats('fes'), known = expected.confirm_total + expected.play_total + expected.verified_total
    assert.deepEqual(legacyStats, { movieId: 'fes', unknown: 10 - expected.confirm - expected.mov_play - expected.verified,
        movie_total: 10, confirm: expected.confirm, confirm_total: expected.confirm_total, play_r3: expected.play_r3,
        play_r4: expected.play_r4, play_r5: expected.play_r5, play_total: expected.play_total, mov_play: expected.mov_play,
        verified: expected.verified, verified_total: expected.verified_total, pending: expected.pending, pending_total: expected.pending_total,
        test_seeds: plain(expected.test_seeds), mode: expected.mode, selectedMovieId: expected.selectedMovieId,
        movieIds: plain(expected.movieIds), total: 115, tested: known, coverage: Math.round(known / 115 * 100) })
    assert.deepEqual(await body('/api/seeds/list'), { movieId: 'fes', play: plain(validator.getPlayList('fes')), verified: plain(validator.getVerifiedList('fes')) })
    const verifiedPage = await body('/api/seeds/group/fes/list?kind=verified'); assert.equal('tag' in verifiedPage.rows[0], false, 'verified rows do not invent a play tag')
    validator.setTag = () => false
    validator.flushPersistence = () => { throw new Error('no failed tag write to flush') }
    for (const options of [
        { method: 'POST', url: '/api/seeds/tag', payload: { seed: 3, tag: '热血躲避球', movieId: 'fes' } },
        { method: 'DELETE', url: '/api/seeds/test-seed?rarity=3' },
    ]) { const response = await app.inject(options); assert.equal(response.statusCode, 409); assert.equal(response.json().ok, false); assert.ok(response.json().error) }
    assert.equal((await app.inject({ method: 'POST', url: '/api/seeds/mode', payload: { mode: 'invalid' } })).statusCode, 400)
    for (const url of ['/api/seeds/group/__proto__/overview', '/api/seeds/group/fes/overview?extra=1', '/api/seeds/group/fes/list?kind=all',
        '/api/seeds/group/fes/list?kind=play&page=0', '/api/seeds/group/fes/list?kind=play&pageSize=201', '/api/seeds/group/fes/list?kind=play&page=1.2', '/api/seeds/group/fes/list?kind=play&extra=1']) {
        assert.equal((await app.inject({ method: 'GET', url })).statusCode, 400, url)
    }
})

test('Seeds source queries request one summary initially and enable only the requested paged list with cancellation', async () => {
    const queries = [], calls = [], state = []; let cursor = 0
    const react = { useState(initial) { const index = cursor++; if (!(index in state)) state[index] = initial; return [state[index], value => { state[index] = typeof value === 'function' ? value(state[index]) : value }] }, useEffect() {}, useRef: value => ({ current: value }) }
    const jsx = (type, props) => ({ type, props: props || {} })
    const antd = new Proxy({ Typography: { Text: 'Text' }, message: { success() {}, error() {} } }, { get: (target, key) => key in target ? target[key] : String(key) })
    const data = { mode: 'natural', testSeeds: [null, null, null], testSeedTags: [null, null, null], confirm: 0, pending: 0, unknown: 10, verified: 2, play: 2,
        baseConfirm: 0, gtConfirm: 0, total: 10, tested: 0, coverage: 0, columns: { play: {}, verified: {} }, catalogAvailable: true, catalogKnown: 0, catalogTotal: 10, learned: 0, externalKnown: 0 }
    const { default: Seeds } = load('admin/src/pages/Seeds.tsx', {
        react, 'react/jsx-runtime': { jsx, jsxs: jsx }, antd, '@ant-design/icons': { ReloadOutlined: 'Reload', CloseOutlined: 'Close' },
        '@tanstack/react-query': { useQuery(options) { queries.push(options); return { data: options.queryKey[2] === 'overview' ? data : undefined, isLoading: false, isError: false, refetch() {} } },
            useMutation: () => ({ mutate() {} }), useQueryClient: () => ({ invalidateQueries() {} }) },
        '../api/client': { apiGet: (url, options) => { calls.push({ url, signal: options.signal }); return Promise.resolve(data) }, apiPost() {}, apiDelete() {} },
        '../components/AdminPage': { AdminPage: 'AdminPage', StateCard: 'StateCard' },
        '../lib/editGuard': { useAdminEditGuard() {} }, '../lib/seedAdminActions': load('admin/src/lib/seedAdminActions.ts', {}),
    })
    const render = () => { queries.length = 0; cursor = 0; return Seeds() }
    const walk = node => !node || typeof node !== 'object' ? [] : [node, ...Object.values(node.props || {}).flatMap(value => Array.isArray(value) ? value.flatMap(walk) : walk(value))]
    const tree = render(); assert.deepEqual(queries.map(query => query.enabled), [undefined, false, false])
    const signal = new AbortController().signal
    await queries[0].queryFn({ signal }); assert.equal(calls.length, 1); assert.equal(calls[0].url, '/api/seeds/group/fes/overview'); assert.equal(calls[0].signal, signal)
    walk(tree).find(node => node.type === 'Button' && node.props.children === '查看验证池列表').props.onClick()
    render(); assert.deepEqual(queries.map(query => query.enabled), [undefined, true, false])
    await queries[1].queryFn({ signal }); assert.match(calls[1].url, /kind=verified&page=1&pageSize=100/); assert.equal(calls[1].signal, signal)
})

test('a populated old 300-percent fixture reports exact catalog intersection, external records, and unavailable catalog status', async t => {
    const validator = fixture()
    validator.pools = new Map([
        ['fes', pool({ confirm: [...Array.from({ length: 50 }, (_, i) => [i + 1, 0]), ...Array.from({ length: 250 }, (_, i) => [1001 + i, 0])] })],
        ['fes_guarantee', pool()],
    ])
    const { counts, seedFile, files } = virtualCounts()
    seedFile('fes', Array.from({ length: 100 }, (_, i) => i + 1), 11); seedFile('fes_guarantee', [], 12)
    const { createSeedsAdminRoutes } = load('src/routes/web_api/seeds.ts', {
        '../../lib/seed-validator': { __esModule: true, default: validator }, path, '../../lib/seed-file-count-cache': { SeedFileCountCache: class {} },
    })
    const app = Fastify({ logger: false }); t.after(() => app.close())
    await app.register(createSeedsAdminRoutes(validator, counts), { prefix: '/api/seeds' })
    const before = validator.stats('fes'); assert.equal((before.confirm + before.mov_play + before.verified) / 100 * 100, 300)
    const actual = (await app.inject({ method: 'GET', url: '/api/seeds/group/fes/overview' })).json()
    assert.equal(actual.catalogAvailable, true); assert.equal(actual.catalogTotal, 100); assert.equal(actual.catalogKnown, 50)
    assert.equal(actual.learned, 300); assert.equal(actual.externalKnown, 250); assert.equal(actual.tested, 50); assert.equal(actual.coverage, 50); assert.equal(actual.unknown, 50)
    files.delete('gacha_movie_seeds_fes_guarantee.json')
    const missing = (await app.inject({ method: 'GET', url: '/api/seeds/group/fes/overview' })).json()
    assert.equal(missing.catalogAvailable, false); assert.equal(missing.coverage, null); assert.equal(missing.tested, null); assert.equal(missing.externalKnown, null)
})

test('all explicit false operation results are failures; old valid mode response is supported and near-full coverage is not rounded to 100', () => {
    const { assertSeedActionSucceeded, formatCatalogCoverage } = load('admin/src/lib/seedAdminActions.ts', {})
    for (const action of [{ kind: 'mode', mode: 'play' }, { kind: 'tag', seed: 1, tag: '未测试', movie: 'fes' },
        { kind: 'set-test', rarity: 3, seed: 1 }, { kind: 'clear-test', rarity: 3 }]) {
        assert.throws(() => assertSeedActionSucceeded({ ok: false, mode: 'play', error: 'synthetic explicit rejection' }, action), /synthetic explicit rejection/)
        assert.throws(() => assertSeedActionSucceeded({}, action))
    }
    assert.doesNotThrow(() => assertSeedActionSucceeded({ mode: 'play' }, { kind: 'mode', mode: 'play' }))
    assert.equal(formatCatalogCoverage(50, 100), '50%'); assert.equal(formatCatalogCoverage(999999, 1000000), '>99.99%')
    assert.equal(formatCatalogCoverage(1, 1000000), '<0.01%'); assert.equal(formatCatalogCoverage(300, 100), '不可用')
})

test('global per-rarity test seed still wins before each original mode without changing getSeed', () => {
    const validator = fixture(); validator.testSeeds = [null, 123456789, null]
    for (const mode of ['natural', 'play', 'test']) {
        validator.setMode(mode)
        assert.equal(validator.getSeed('fes', 4, [], 1), 123456789)
        assert.equal(validator.getSeed('normal_guarantee', 4, [], 1), 123456789)
    }
})
