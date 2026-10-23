'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), ts = require('typescript')
const root = path.resolve(__dirname, '..')
const source = fs.readFileSync(path.join(root, 'src/lib/content-box-associations.ts'), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText
const read = relative => fs.readFileSync(path.join(root, relative))
const asset = JSON.parse(read('assets/content_box_associations.json'))
const catalog = JSON.parse(read('assets/content_catalog.json'))
const hash = raw => crypto.createHash('sha256').update(raw).digest('hex')
const stable = value => Array.isArray(value) ? '[' + value.map(stable).join(',') + ']'
    : value !== null && typeof value === 'object' ? '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stable(value[key])).join(',') + '}' : JSON.stringify(value)
const clone = value => JSON.parse(JSON.stringify(value))
function fixture(change = () => {}, actual = false) {
    const artifact = clone(asset), calls = new Map(), files = new Map(), opens = new Map(), jsonCalls = new Map(), chunks = [], descriptors = new Map()
    const selected = new Set(artifact.associations.flatMap(row => [row.parentKey, row.boxKey]))
    const fixtureCatalog = actual ? catalog : { rows: clone(catalog.rows.filter(row => selected.has(row.key))), resources: catalog.resources }
    const catalogRaw = actual ? read('assets/content_catalog.json') : Buffer.from(JSON.stringify(fixtureCatalog))
    artifact.catalogSha256 = hash(catalogRaw)
    files.set('assets/content_catalog.json', catalogRaw)
    files.set('assets/asset-patch/manifest.json', read('assets/asset-patch/manifest.json'))
    for (const name of Object.keys(artifact.serverSources)) files.set(name, read(name))
    // Cached JSON objects are deliberately independent of the raw-byte fixtures.
    const jsonModules = new Map([["assets/content_catalog.json", fixtureCatalog]])
    for (const name of ["assets/box_gacha.json", "assets/box_reward.json", "assets/box_gacha_1001_settings.json"]) jsonModules.set(name, JSON.parse(files.get(name)))
    change({ artifact, files, fixtureCatalog, jsonModules })
    artifact.associationsDigest = hash(stable(artifact.associations))
    files.set('assets/content_box_associations.json', Buffer.from(JSON.stringify(artifact)))
    const module = { exports: {} }
    const fakeFs = { readFileSync(file) {
        const key = path.relative(root, file).replaceAll('\\', '/')
        calls.set(key, (calls.get(key) ?? 0) + 1)
        if (!files.has(key)) throw Error('Fixture missing file: ' + key)
        return files.get(key)
    }, openSync(file, flags) {
        assert.equal(flags, 'r')
        const key = path.relative(root, file).replaceAll('\\', '/')
        opens.set(key, (opens.get(key) ?? 0) + 1)
        if (!files.has(key)) throw Error('Fixture missing file: ' + key)
        const fd = descriptors.size + 1
        descriptors.set(fd, { raw: files.get(key), offset: 0 })
        return fd
    }, readSync(fd, buffer, offset, length, position) {
        assert.equal(position, null); chunks.push(length)
        const entry = descriptors.get(fd), count = Math.min(length, entry.raw.length - entry.offset)
        entry.raw.copy(buffer, offset, entry.offset, entry.offset + count); entry.offset += count
        return count
    }, closeSync(fd) { assert.ok(descriptors.delete(fd)) } }
    const customRequire = name => {
        if (name === 'node:fs') return fakeFs
        if (name.startsWith('../../assets/')) {
            const key = name.slice(6)
            jsonCalls.set(key, (jsonCalls.get(key) ?? 0) + 1)
            if (!jsonModules.has(key)) throw Error('Fixture missing JSON module: ' + key)
            return jsonModules.get(key)
        }
        return require(name)
    }
    new Function('exports', 'require', 'module', '__filename', '__dirname', code)(module.exports, customRequire, module,
        path.join(root, 'src/lib/content-box-associations.ts'), path.join(root, 'src/lib'))
    return { api: module.exports, calls, opens, jsonCalls, chunks, descriptors, artifact, files }
}

test('current artifact binds all native pairs, exact fields and server definitions', () => {
    const { api } = fixture(() => {}, true)
    assert.deepEqual(api.getContentBoxAssociationStatus(), { available: true, relationshipsMatch: true })
    const rows = api.getContentBoxAssociations()
    assert.equal(rows.length, 48)
    assert.equal(rows.filter(row => row.parentKey.startsWith('world_story_event:')).length, 41)
    assert.equal(rows.filter(row => row.parentKey.startsWith('raid_event:')).length, 7)
    assert.equal(new Set(rows.map(row => row.boxKey)).size, 48)
    for (const row of rows) {
        assert.equal(row.relationshipMatches, true)
        assert.equal(api.getContentBoxAssociation(row.parentKey), row)
        assert.equal(api.getContentBoxAssociation(row.boxKey), row)
        assert.ok(Object.isFrozen(row))
    }
    assert.ok(Object.isFrozen(rows))
    assert.equal(api.getContentBoxAssociation('rush_event:700099'), undefined)
})
test('bindings are validated once, not once for each catalog row', () => {
    const { api, calls, opens, jsonCalls, chunks, descriptors } = fixture()
    for (let i = 0; i < 200; i++) {
        api.getContentBoxAssociation('world_story_event:200100')
        api.getContentBoxAssociations(); api.getContentBoxAssociationStatus(); api.isContentBoxAssociationIndexAvailable()
    }
    assert.deepEqual(api.getContentBoxAssociationStatus(), { available: true, relationshipsMatch: true })
    assert.ok([...calls.values()].every(count => count === 1))
    assert.deepEqual([...calls.keys()], ['assets/content_box_associations.json'])
    assert.equal(opens.size, 6)
    assert.ok([...opens.values()].every(count => count === 1))
    assert.equal(jsonCalls.size, 4)
    assert.ok([...jsonCalls.values()].every(count => count === 1))
    assert.ok(chunks.length > 6 && chunks.every(length => length === 64 * 1024))
    assert.equal(descriptors.size, 0)
})
for (const relative of ['assets/content_catalog.json', 'assets/asset-patch/manifest.json', 'assets/box_gacha.json', 'assets/box_reward.json', 'assets/box_gacha_1001_settings.json', 'src/lib/assets.ts']) {
    test(`changed binding ${relative} keeps safe pair metadata but cannot authorize opening`, () => {
        const { api } = fixture(({ files }) => files.set(relative, Buffer.from('changed input')))
        const status = api.getContentBoxAssociationStatus()
        assert.equal(status.available, true); assert.equal(status.relationshipsMatch, false)
        assert.equal(api.getContentBoxAssociations().length, 48)
        assert.ok(api.getContentBoxAssociations().every(row => row.relationshipMatches === false))
    })
}
for (const corruption of ['missing-file', 'invalid-json']) {
    test(`unreadable ${corruption} asset fails closed without throwing into the operations route`, () => {
        const { api, files } = fixture()
        if (corruption === 'missing-file') files.delete('assets/content_box_associations.json')
        else files.set('assets/content_box_associations.json', Buffer.from('{'))
        assert.equal(api.getContentBoxAssociationStatus().available, false)
        assert.equal(api.getContentBoxAssociationStatus().relationshipsMatch, false)
        assert.deepEqual(api.getContentBoxAssociations(), [])
    })
}
test('a matching whole catalog hash cannot conceal a mismatched native row digest', () => {
    const { api } = fixture(({ artifact, files, fixtureCatalog }) => {
        fixtureCatalog.rows[0].definitionDigest = 'f'.repeat(64)
        const raw = Buffer.from(JSON.stringify(fixtureCatalog)); files.set('assets/content_catalog.json', raw); artifact.catalogSha256 = hash(raw)
    })
    assert.equal(api.getContentBoxAssociationStatus().relationshipsMatch, false)
    assert.equal(api.getContentBoxAssociationStatus().reason, 'catalog_row_identity_mismatch')
})
test('swapping two boxes cannot pass merely because both independent row hashes exist', () => {
    const { api } = fixture(({ artifact }) => {
        const [first, second] = artifact.associations
        ;[first.boxKey, second.boxKey] = [second.boxKey, first.boxKey]
        ;[first.box, second.box] = [second.box, first.box]
        first.parent.boxId = first.box.rowId; second.parent.boxId = second.box.rowId
    })
    assert.deepEqual(api.getContentBoxAssociationStatus(), { available: false, relationshipsMatch: false, reason: 'association_index_unavailable' })
    assert.deepEqual(api.getContentBoxAssociations(), [])
})
for (const corruption of ['duplicate', 'missing', 'wrong-native-field']) {
    test(`untrustworthy ${corruption} index is distinguishable from standalone content`, () => {
        const { api } = fixture(({ artifact }) => {
            if (corruption === 'duplicate') artifact.associations[1] = clone(artifact.associations[0])
            if (corruption === 'missing') artifact.associations.pop()
            if (corruption === 'wrong-native-field') artifact.associations[0].parent.fieldIndex = 3
        })
        assert.equal(api.isContentBoxAssociationIndexAvailable(), false)
        assert.equal(api.getContentBoxAssociationStatus().available, false)
        assert.deepEqual(api.getContentBoxAssociations(), [])
        assert.equal(api.getContentBoxAssociation('world_story_event:200100'), undefined)
    })
}
