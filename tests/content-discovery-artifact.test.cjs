'use strict'
// Exercise the shipped indexes, not optional generated-fragment fixtures.
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), { createHash } = require('node:crypto')
const ts = require('typescript'), { discoveryProjection } = require('../tools/build-content-runtime-index.cjs')
const root = path.resolve(__dirname, '..'), sha = bytes => createHash('sha256').update(bytes).digest('hex')
const bytes = fs.readFileSync(path.join(root, 'assets/content_discovery.json'))
const canonical = JSON.parse(bytes), runtime = JSON.parse(fs.readFileSync(path.join(root, 'assets/content_discovery_runtime.json')))
const presentation = JSON.parse(fs.readFileSync(path.join(root, 'assets/content_presentation.json')))
const plain = value => JSON.parse(JSON.stringify(value))
function actualReader() {
    const module = { exports: {} }, file = path.join(root, 'src/lib/content-discovery.ts')
    const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true,
    } }).outputText
    vm.runInNewContext(compiled, { require, module, exports: module.exports, __dirname: path.join(root, 'out/lib') }, { filename: file })
    return module.exports.contentDiscoveryReader()
}
test('shipped discovery artifacts bind every current source and preserve exact parent coverage', () => {
    const stale = []
    const expected = { 'assets/content_presentation.json': canonical.source.presentationSha256,
        'assets/content_catalog.json': canonical.source.catalogSha256, ...canonical.sourceInputs }
    assert.ok(Object.keys(canonical.sourceInputs).length > 0)
    for (const [relative, digest] of Object.entries(expected)) {
        if (relative === 'assets/asset-patch/manifest.json') continue // capture provenance, not a relation dependency
        assert.match(relative, /^(?:assets|src|tools|docs)\/[a-zA-Z0-9_./-]+$/)
        assert.ok(!relative.split('/').some(part => !part || part === '.' || part === '..'))
        assert.match(digest, /^[a-f0-9]{64}$/)
        if (sha(fs.readFileSync(path.join(root, relative))) !== digest) stale.push(relative)
    }
    assert.deepEqual(stale, [], 'Shipped discovery source bindings are stale; regenerate verified fragments and both indexes')
    const keys = Object.keys(presentation.rows).sort()
    assert.deepEqual(Object.keys(canonical.rows).sort(), keys)
    assert.deepEqual(Object.keys(runtime.rows).sort(), keys)
    assert.equal(canonical.coverage.parents, keys.length)
})
test('shipped runtime is the exact canonical projection, including all dictionary references', () => {
    assert.deepEqual(runtime, discoveryProjection(canonical, sha(bytes)))
})
test('actual source reader retains shipped character and reward relations in search', () => {
    const reader = actualReader()
    assert.equal(reader.verificationNotice, undefined, 'Actual shipped artifacts must not degrade related search')
    for (const field of ['characters', 'rewards']) {
        const selected = Object.entries(canonical.rows).find(([key, row]) => row[field].length && (field !== 'characters' || key.startsWith('gacha:')))
        assert.ok(selected, 'Missing actual ' + field + ' relation fixture')
        const [key, row] = selected, p = presentation.rows[key], entity = row[field][0]
        const parent = { key, type: p.type, name: '', originalStartMs: null, originalEndMs: null,
            presentation: { title: '', group: p.group || '', typeLabel: '' } }
        // Blank title fields ensure this proves relation search rather than a coincidental name match.
        assert.deepEqual(plain(reader.details(key)[field]), row[field])
        const term = entity.name.normalize('NFKC').toLocaleLowerCase().replace(/[\p{P}\p{S}\s]/gu, '')
        assert.ok(term.length)
        const match = reader.match(parent, [term])
        assert.equal(match.matched, true, key + ': ' + entity.name)
        assert.ok(match.reasons.some(reason => reason.endsWith('：' + entity.name)), 'Expected a relation-specific match reason')
    }
})

test('shipped mech search relations match the restored settlement materials', () => {
    const reader = actualReader()
    for (const [eventId, gear, core] of [[1001,40402,40408],[1002,40403,40409],[1003,40404,40410],
        [1004,40401,40407],[1005,40406,40412],[1006,40405,40411]]) {
        const row = reader.details('hard_multi_event:' + eventId)
        for (const id of [gear, core]) assert.ok(row.rewards.some(r => r.kind === 'item' && r.id === id && r.relation === 'drop'))
        assert.ok(!row.rewards.some(r => [49300,10000092,10000093].includes(r.id) && r.relation === 'drop'))
    }
})
