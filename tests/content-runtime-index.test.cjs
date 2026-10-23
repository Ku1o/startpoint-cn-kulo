'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), os = require('node:os')
const ts = require('typescript'), { createHash } = require('node:crypto')
const root = path.resolve(__dirname, '..'), read = name => JSON.parse(fs.readFileSync(path.join(root, 'assets', name), 'utf8'))
const { historyProjection, discoveryProjection, digest } = require('../tools/build-content-runtime-index.cjs')
const plain = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value))
function load(name, directory = root, counters = {}) {
    const source = fs.readFileSync(path.join(root, 'src/lib', name + '.ts'), 'utf8')
    const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText
    const instrumented = new Proxy(fs, { get(target, property) {
        if (property === 'readFileSync') return (file, ...args) => {
            counters.reads ||= []; counters.reads.push(String(file))
            if (String(file).endsWith('content_history_readiness.json')) throw new Error('Runtime must never read the full readiness document')
            return target.readFileSync(file, ...args)
        }
        if (property === 'readSync') return (fd, buffer, offset, length, position) => {
            counters.maxHashBuffer = Math.max(counters.maxHashBuffer || 0, buffer.length)
            counters.hashReadBytes = (counters.hashReadBytes || 0) + length
            return target.readSync(fd, buffer, offset, length, position)
        }
        if (property === 'statSync') return (...args) => { counters.stats = (counters.stats || 0) + 1; return target.statSync(...args) }
        return target[property]
    } })
    const module = { exports: {} }
    vm.runInNewContext(code, { module, exports: module.exports, __dirname: path.join(directory, 'out/lib'),
        require: dependency => dependency === 'node:fs' ? instrumented
            : dependency.startsWith('./') ? load(dependency.slice(2).replace(/\.js$/, ''), directory, counters) : require(dependency) })
    return module.exports
}

test('offline runtime projections retain every parent, action explanation and all ordered character/reward relationships', () => {
    const history = read('content_history_readiness.json'), discovery = read('content_discovery.json')
    const h = read('content_history_readiness_runtime.json'), d = read('content_discovery_runtime.json')
    assert.deepEqual(h, historyProjection(history, digest(path.join(root, 'assets/content_history_readiness.json'))))
    assert.deepEqual(d, discoveryProjection(discovery, digest(path.join(root, 'assets/content_discovery.json'))))
    assert.equal(h.rows.length, 1020); assert.equal(Object.keys(d.rows).length, 1020)
    assert.deepEqual(Object.keys(d.rows).sort(), history.rows.map(row => row.key).sort())
    assert.deepEqual(d.sourceInputs, discovery.sourceInputs); assert.deepEqual(d.source, discovery.source)
    let relations = 0
    const normalized = value => value.normalize('NFKC').toLocaleLowerCase().replace(/[\p{P}\p{S}\s]/gu, '')
    for (const [key, expected] of Object.entries(discovery.rows)) {
        const row = d.rows[key]
        assert.deepEqual(row.characters.map(ref => d.characters[ref].entity), expected.characters, key)
        assert.deepEqual(row.rewards.map(ref => d.rewards[ref].entity), expected.rewards, key)
        assert.deepEqual(row.aliases, expected.aliases, key); assert.equal(row.editionLabel, expected.editionLabel, key)
        for (const [refs, dictionary] of [[row.characters, d.characters], [row.rewards, d.rewards]]) for (const ref of refs) {
            const entry = dictionary[ref]
            assert.deepEqual(entry.fields.map(field => field.text), [entry.entity.name, ...(entry.entity.aliases || [])].map(normalized))
        }
        relations += row.characters.length + row.rewards.length
    }
    assert.equal(relations, 138122)
    assert.ok(fs.statSync(path.join(root, 'assets/content_history_readiness_runtime.json')).size < 300000)
    assert.ok(fs.statSync(path.join(root, 'assets/content_discovery_runtime.json')).size < 2100000)
})

test('runtime serves all 1020 readiness parents without parsing full audit and request readers do no repeated filesystem work', () => {
    const counters = {}, api = load('content-history-readiness', root, counters)
    const canonical = read('content_history_readiness.json'), reader = api.contentHistoryReadinessReader(), stats = counters.stats
    const actions = ['visible', 'enter', 'claim', 'exchange']
    for (const row of canonical.rows) {
        for (let mask = 0; mask < 16; mask++) {
            const selected = actions.filter((_, index) => mask & (1 << index))
            assert.deepEqual(plain(reader.get(row.key, selected)), plain(api.explainContentHistoryReadiness(row, selected)), row.key)
        }
        const page = row.nativePage
        assert.deepEqual(plain(reader.nativePage(row.key)), page ? { kind: page.kind, label: page.label.trim(),
            ...(page.description?.trim() ? { description: page.description.trim() } : {}) } : undefined)
        reader.boxAssociation(row.key)
    }
    assert.equal(counters.stats, stats, 'A captured reader must not stat per parent/action')
    assert.ok(!counters.reads.some(file => file.endsWith('content_history_readiness.json')))
    assert.equal(counters.maxHashBuffer, 65536)
})

test('all runtime details retain exact canonical entities and cards do not hydrate relation arrays', () => {
    const counters = {}, api = load('content-discovery', root, counters), reader = api.contentDiscoveryReader()
    assert.equal(reader.verificationNotice, undefined)
    const canonical = read('content_discovery.json'), catalog = read('content_catalog.json'), presentation = read('content_presentation.json')
    const parents = catalog.rows.filter(row => Object.hasOwn(canonical.rows, row.key))
    for (const parent of parents) {
        parent.presentation = { ...presentation.rows[parent.key], group: parent.type, typeLabel: parent.type }
        const expected = canonical.rows[parent.key], details = reader.details(parent.key)
        assert.deepEqual(plain(details.characters), expected.characters, parent.key)
        assert.deepEqual(plain(details.rewards), expected.rewards, parent.key)
        assert.deepEqual(plain(details.aliases), expected.aliases, parent.key)
        assert.equal(reader.meta(parent).seriesKey, reader.view(parent).seriesKey)
        assert.equal(reader.match(parent, []).matched, true)
        assert.equal(reader.match(parent, api.discoveryTerms(parent.presentation.title)).matched, true)
        const entity = expected.characters[0] || expected.rewards[0]
        if (entity) assert.equal(reader.match(parent, api.discoveryTerms(entity.name)).matched, true, `${parent.key}: ${entity.name}`)
    }
    assert.equal(parents.length, 1020)
    assert.ok(!counters.reads.some(file => file.endsWith('content_discovery.json')))
    assert.equal(counters.maxHashBuffer, 65536)
})

test('changed and malformed projections degrade closed while an already captured request remains consistent', t => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'content-runtime-index-'))
    t.after(() => fs.rmSync(directory, { recursive: true }))
    const write = (name, value) => { const file = path.join(directory, name); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, typeof value === 'string' ? value : JSON.stringify(value)); return digest(file) }
    const hCanonical = write('assets/content_history_readiness.json', { schemaVersion: 1, rows: [] })
    const summary = { schemaVersion: 1, canonicalSha256: hCanonical, rows: [{ key: 'gacha:7', actions: { enter: { status: 'passed', blockers: [] } } }] }
    write('assets/content_history_readiness_runtime.json', summary)
    const h = load('content-history-readiness', directory), snapshot = h.contentHistoryReadinessReader()
    assert.equal(snapshot.get('gacha:7', ['enter']).status, 'passed')
    write('assets/content_history_readiness.json', { changed: true })
    assert.equal(h.contentHistoryReadinessReader().get('gacha:7', ['enter']).status, 'unreviewed')
    assert.equal(snapshot.get('gacha:7', ['enter']).status, 'passed')
    summary.canonicalSha256 = write('assets/content_history_readiness.json', { restored: true })
    summary.rows[0].actions.enter.status = 'invalid'
    write('assets/content_history_readiness_runtime.json', summary)
    assert.equal(h.contentHistoryReadinessReader().get('gacha:7', ['enter']).status, 'unreviewed')
    const source = { manifestSha256: write('assets/asset-patch/manifest.json', {}), catalogSha256: write('assets/content_catalog.json', {}),
        presentationSha256: write('assets/content_presentation.json', { rows: { 'gacha:7': {} } }) }
    const input = write('assets/terms.json', {}), canonical = { schemaVersion: 1, source, sourceInputs: { 'assets/terms.json': input }, rows: {
        'gacha:7': { characters: [{ id: 1, name: '阿尔克', relation: 'up' }], rewards: [], aliases: [], notes: [], status: 'verified' } } }
    const canonicalSha = write('assets/content_discovery.json', canonical), projection = discoveryProjection(canonical, canonicalSha)
    write('assets/content_discovery_runtime.json', projection)
    const discoveryCounters = {}, d = load('content-discovery', directory, discoveryCounters), reader = d.contentDiscoveryReader()
    assert.equal(reader.verificationNotice, undefined); assert.equal(reader.details('gacha:7').characters.length, 1)
    const parent = { key: 'gacha:7', type: 'gacha', name: '测试卡池', originalStartMs: null, originalEndMs: null,
        presentation: { title: '测试卡池', group: 'gacha', typeLabel: '角色扭蛋' } }
    write('assets/terms.json', { changed: true })
    const degraded = d.contentDiscoveryReader()
    assert.ok(degraded.verificationNotice)
    assert.equal(reader.view(parent).highlights.length, 1)
    assert.equal(degraded.view(parent).highlights.length, 0, 'Concurrent readers must not share a card across source versions')
    assert.equal(reader.view(parent).highlights.length, 1)
    assert.equal(d.contentDiscoveryReader().details('gacha:7').characters.length, 0)
    assert.equal(reader.details('gacha:7').characters.length, 1)
    write('assets/terms.json', {}); projection.rows['gacha:7'].characters = [999]
    write('assets/content_discovery_runtime.json', projection)
    assert.ok(d.contentDiscoveryReader().verificationNotice)
    write('assets/content_discovery_runtime.json', '{broken')
    assert.ok(d.contentDiscoveryReader().verificationNotice)
    fs.unlinkSync(path.join(directory, 'assets/content_discovery_runtime.json'))
    write('assets/content_discovery.json', ' '.repeat(13 * 1024 * 1024))
    const readsBefore = discoveryCounters.reads.length
    assert.ok(d.contentDiscoveryReader().verificationNotice, 'No unbounded fallback parse of production full index')
    assert.equal(discoveryCounters.reads.length, readsBefore, 'Missing projection with 13 MiB canonical must not read its bytes')
})
