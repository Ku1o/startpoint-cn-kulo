'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), os = require('node:os'), vm = require('node:vm')
const { createHash } = require('node:crypto'), ts = require('typescript')
const sha = bytes => createHash('sha256').update(bytes).digest('hex')
const source = fs.readFileSync(path.join(__dirname, '../src/lib/content-discovery.ts'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText
function fixture(t) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'content-discovery-'))
    assert.ok(path.basename(directory).startsWith('content-discovery-'))
    t.after(() => fs.rmSync(directory, { recursive: true }))
    const write = (relative, value) => { const file = path.join(directory, relative); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, JSON.stringify(value)); return sha(fs.readFileSync(file)) }
    const source = { manifestSha256: write('assets/asset-patch/manifest.json', { chain: 'verified' }), presentationSha256: write('assets/content_presentation.json', { rows: { 'gacha:7': { title: '流星节扭蛋' } } }), catalogSha256: write('assets/content_catalog.json', { fixture: 'catalog' }) }
    const row = { characters: [{ id: 1, name: '阿尔克', relation: 'up', aliases: ['勇者阿尔克'] }, { id: 2, name: '白', relation: 'pool' }],
        rewards: [{ kind: 'equipment', id: 8, name: '勇气之剑', relation: 'exchange' }], aliases: ['星光庆典'], notes: [], publicNotes: [], status: 'verified' }
    const index = { schemaVersion: 1, source, sourceInputs: { 'assets/terms.json': write('assets/terms.json', { term: 7 }) }, rows: { 'gacha:7': row } }
    write('assets/content_discovery.json', index)
    const module = { exports: {} }
    vm.runInNewContext(compiled, { require, module, exports: module.exports, __dirname: path.join(directory, 'out/lib') })
    const parent = { key: 'gacha:7', type: 'gacha', name: '流星节扭蛋', originalStartMs: Date.UTC(2025, 6, 19, 16), originalEndMs: Date.UTC(2025, 6, 30),
        presentation: { title: '流星节扭蛋', group: 'gacha', typeLabel: '角色扭蛋', subtitle: '可靠的活动说明' } }
    return { api: module.exports, directory, index, parent, write }
}
test('multi-keyword search finds names, verified UP/pool/exchange associations, aliases and UTC+8 schedules', t => {
    const { api, parent } = fixture(t), reader = api.contentDiscoveryReader()
    assert.equal(reader.verificationNotice, undefined)
    for (const query of ['流星节 阿尔克', '星光庆典 勇气之剑', '2025-07-20 阿尔克', '２０２５年７月２０日 流星节', 'gacha:7']) {
        assert.equal(reader.match(parent, api.discoveryTerms(query)).matched, true, query)
    }
    assert.equal(reader.match(parent, api.discoveryTerms('流星节 不存在的角色')).matched, false)
    assert.deepEqual(Array.from(reader.match(parent, api.discoveryTerms('阿尔克')).reasons), ['UP角色：阿尔克'])
    assert.deepEqual(Array.from(reader.match(parent, api.discoveryTerms('白')).reasons), ['池内可获得角色：白'])
    const view = reader.view(parent)
    assert.ok(view.highlights.some(item => item.label === 'UP角色' && item.names.includes('阿尔克')))
    assert.ok(!view.highlights.find(item => item.label === 'UP角色').names.includes('白'))
    assert.equal(reader.details('gacha:7').rewards[0].name, '勇气之剑')
})
test('title matches outrank incidental reward/alias matches and same-name grouping never merges distinct keys', t => {
    const { api, parent } = fixture(t), reader = api.contentDiscoveryReader(), terms = api.discoveryTerms('勇气之剑')
    const titleParent = { ...parent, key: 'story_event:8', type: 'story_event', presentation: { ...parent.presentation, title: '勇气之剑' } }
    assert.ok(reader.match(titleParent, terms).score > reader.match(parent, terms).score)
    assert.equal(reader.view({ ...parent, key: 'gacha:8' }).seriesKey, reader.view(parent).seriesKey)
    assert.notEqual(reader.view({ ...parent, type: 'story_event' }).seriesKey, reader.view(parent).seriesKey)
})
test('changed source input rejects old associations while retaining title and date search; restored input recovers', t => {
    const f = fixture(t)
    assert.equal(f.api.contentDiscoveryReader().match(f.parent, ['阿尔克']).matched, true)
    f.write('assets/terms.json', { term: 8 })
    for (let i = 0; i < 2; i++) {
        const reader = f.api.contentDiscoveryReader()
        assert.ok(reader.verificationNotice)
        assert.equal(reader.match(f.parent, ['阿尔克']).matched, false)
        assert.equal(reader.match(f.parent, ['流星节']).matched, true)
    }
    f.write('assets/terms.json', { term: 7 })
    assert.equal(f.api.contentDiscoveryReader().match(f.parent, ['阿尔克']).matched, true)
})
test('invalid index JSON and unsafe source identities remain rejected on repeated reads after a warm cache', t => {
    const f = fixture(t)
    assert.equal(f.api.contentDiscoveryReader().verificationNotice, undefined)
    fs.writeFileSync(path.join(f.directory, 'assets/content_discovery.json'), '{broken')
    for (let i = 0; i < 2; i++) assert.ok(f.api.contentDiscoveryReader().verificationNotice)
    f.index.sourceInputs['assets/../outside.json'] = 'a'.repeat(64)
    f.write('assets/content_discovery.json', f.index)
    for (let i = 0; i < 2; i++) assert.ok(f.api.contentDiscoveryReader().verificationNotice)
})
test('partially documented content retains verified relations and explicit public limitations without technical notes', t => {
    const f = fixture(t), row = f.index.rows['gacha:7']
    row.status = 'unavailable'; row.notes = ['internal/path code:7']; row.publicNotes = ['部分名称沿用原版文字，尚无已确认的中文译名。']
    f.write('assets/content_discovery.json', f.index)
    const reader = f.api.contentDiscoveryReader(), details = reader.details('gacha:7')
    assert.equal(reader.match(f.parent, ['阿尔克']).matched, true)
    assert.ok(details.notes[0].includes('中文译名')); assert.ok(!JSON.stringify(details).includes('internal/path'))
    assert.equal(reader.details('__proto__').characters.length, 0)
})
test('malformed but source-bound relation metadata degrades safely instead of breaking all listings', t => {
    const f = fixture(t)
    f.index.rows['gacha:7'].characters = [null]
    f.write('assets/content_discovery.json', f.index)
    let reader = f.api.contentDiscoveryReader()
    assert.ok(reader.verificationNotice); assert.equal(reader.match(f.parent, ['流星节']).matched, true)
    assert.equal(reader.details('gacha:7').characters.length, 0)
    f.index.rows['gacha:7'].characters = []; f.index.rows['gacha:7'].aliases = [1]
    f.write('assets/content_discovery.json', f.index)
    reader = f.api.contentDiscoveryReader(); assert.ok(reader.verificationNotice)
    f.index.rows = {}; f.write('assets/content_discovery.json', f.index)
    assert.ok(f.api.contentDiscoveryReader().verificationNotice, 'Missing parent coverage must be visible rather than silently dropping associations')
})
test('every keyword within the API length limit remains mandatory, including terms beyond the twenty-fourth', t => {
    const { api, parent } = fixture(t), reader = api.contentDiscoveryReader()
    const query = Array.from({length: 25}, (_, i) => `词${i}`).join(' '), terms = api.discoveryTerms(query)
    assert.ok(query.length <= 200); assert.equal(terms.length, 25)
    const longTitle = { ...parent, presentation: { ...parent.presentation, title: terms.slice(0,24).join(' ') } }
    assert.equal(reader.match(longTitle, terms).matched, false)
})
