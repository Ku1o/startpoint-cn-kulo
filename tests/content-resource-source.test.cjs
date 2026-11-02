'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs')
const path = require('node:path'), os = require('node:os'), { createHash } = require('node:crypto'), { crc32 } = require('node:zlib')
require('ts-node/register/transpile-only')
const { readContentResourceSourceSync: read } = require('../src/lib/content-resource-source')
const sha = body => createHash('sha256').update(body).digest('hex')
const source = { assetVersion: '1.4.350', manifestSha256: '4cb3dd337ac062af6845591b85cf27d3bc203160923f74c2cf1c7a2883b76843' }
const logicals = ['master/quest/event/advent_event.orderedmap', 'master/quest/event/advent_event_quest.orderedmap',
    'master/gacha/gacha.orderedmap', 'master/shop/event_item_shop.orderedmap']
const member = logical => { const value = createHash('sha1').update(logical + 'K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy').digest('hex'); return 'production/upload/' + value.slice(0, 2) + '/' + value.slice(2) }
function zip(entries) {
    const local = [], central = []; let offset = 0
    for (const [logical, text] of Object.entries(entries)) {
        const name = Buffer.from(member(logical)), body = Buffer.from(text), header = Buffer.alloc(30), entry = Buffer.alloc(46)
        header.writeUInt32LE(0x04034b50); header.writeUInt16LE(20, 4); header.writeUInt32LE(crc32(body), 14)
        header.writeUInt32LE(body.length, 18); header.writeUInt32LE(body.length, 22); header.writeUInt16LE(name.length, 26)
        entry.writeUInt32LE(0x02014b50); entry.writeUInt16LE(20, 4); entry.writeUInt16LE(20, 6); entry.writeUInt32LE(crc32(body), 16)
        entry.writeUInt32LE(body.length, 20); entry.writeUInt32LE(body.length, 24); entry.writeUInt16LE(name.length, 28); entry.writeUInt32LE(offset, 42)
        local.push(header, name, body); central.push(entry, name); offset += header.length + name.length + body.length
    }
    const directory = Buffer.concat(central), end = Buffer.alloc(22)
    end.writeUInt32LE(0x06054b50); end.writeUInt16LE(central.length / 2, 8); end.writeUInt16LE(central.length / 2, 10)
    end.writeUInt32LE(directory.length, 12); end.writeUInt32LE(offset, 16)
    return Buffer.concat([...local, directory, end])
}
function fixture(t) {
    const base = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir()), root = fs.mkdtempSync(path.join(base, 'content-source-'))
    t.after(() => { assert.equal(path.dirname(root), base); fs.rmSync(root, { recursive: true }) })
    const write = (relative, value) => { const file = path.join(root, relative); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(value)); return file }
    const baseline = 'assets/asset-patch/active/base.zip', values = Object.fromEntries(logicals.map((name, i) => [name, 'reviewed business ' + i]))
    write(baseline, zip(values))
    const resources = Object.fromEntries(logicals.map(name => [name, { archive: baseline, sha256: sha(values[name]) }]))
    write('assets/content_catalog.json', { resources }); write('assets/content_history_quest_rules.json', { source: { resources: {} } })
    write('assets/content_history_shop_rules.json', { source: { resources: {} } })
    const reference = { schemaVersion: 1, source, resources }
    write('assets/content_resource_source.json', reference)
    const manifest = { cdn_version: '1.4.350', patches: [{ enabled: true, archive: 'base.zip' }] }
    write('assets/asset-patch/manifest.json', manifest)
    const append = entries => { write('assets/asset-patch/active/update.zip', zip(entries)); manifest.cdn_version = '1.4.352'; manifest.patches.push({ enabled: true, archive: 'update.zip' }); write('assets/asset-patch/manifest.json', manifest) }
    return { root, write, reference, manifest, values, append }
}

test('art, music, battle layout and version/format updates preserve the deployed content identity', t => {
    const f = fixture(t)
    assert.deepEqual(read(f.root), source)
    f.append({ 'character/new.png': 'art', 'sound/music.mp3': 'music', 'master/battle/floor.orderedmap': 'new battle balance' })
    assert.deepEqual(read(f.root), source)
    f.write('assets/asset-patch/manifest.json', JSON.stringify(f.manifest, null, 3))
    assert.deepEqual(read(f.root), source)
    f.append({ [logicals[0]]: f.values[logicals[0]] })
    assert.deepEqual(read(f.root), source, 'repacking identical business bytes remains compatible')
})
for (const logical of logicals) test('an actual changed business member is rejected: ' + logical, t => {
    const f = fixture(t); read(f.root); f.append({ [logical]: 'changed business' })
    assert.throws(() => read(f.root), error => /business definitions changed/.test(error.message) && error.message.includes(logical))
})
test('archive mutation invalidates a warm cache even when manifest bytes are unchanged', t => {
    const f = fixture(t); read(f.root)
    f.write('assets/asset-patch/active/base.zip', zip({ ...f.values, [logicals[3]]: 'different price/stock' }))
    assert.throws(() => read(f.root), /business definitions changed/)
})
test('missing archives, corrupt ZIPs and incomplete resource scope cannot inherit old controls', t => {
    const f = fixture(t); read(f.root)
    f.write('assets/asset-patch/active/base.zip', 'broken zip')
    assert.throws(() => read(f.root))
    f.write('assets/asset-patch/active/base.zip', zip(f.values)); fs.unlinkSync(path.join(f.root, 'assets/asset-patch/active/base.zip'))
    assert.throws(() => read(f.root), /ENOENT/)
    f.write('assets/asset-patch/active/base.zip', zip(f.values)); delete f.reference.resources[logicals[0]]
    f.write('assets/content_resource_source.json', f.reference)
    assert.throws(() => read(f.root), /scope/)
})
test('the real resource chain binds the reviewed Epuration business revision', () => assert.deepEqual(read(), {
    assetVersion: '1.4.356', manifestSha256: '01f9a3036c8eb6f35043dfa8d8da0eddfcecd40d4178ae6cd6356cb542446c45',
}))
