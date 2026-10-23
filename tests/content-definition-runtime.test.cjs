'use strict'
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os')
const path = require('node:path'), crypto = require('node:crypto'), Module = require('node:module'), ts = require('typescript')
const root = path.resolve(__dirname, '..'), { buildRuntimeDocument, generate } = require('../tools/build-content-definition-runtime.cjs')
const sha = value => crypto.createHash('sha256').update(value).digest('hex'), hash = digit => digit.repeat(64)
function sourceModule(name, fsApi = fs) {
    const filename = path.join(root, 'src/lib', name + '.ts'), instance = new Module(filename, module)
    instance.filename = filename; instance.paths = Module._nodeModulePaths(path.dirname(filename))
    instance.require = name => name === 'node:fs' ? fsApi : name === './content-history-definition-runtime-identity'
        ? sourceModule('content-history-definition-runtime-identity') : require(name)
    instance._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText, filename)
    return instance.exports
}
const { loadContentHistoryDefinitionRuntime: load } = sourceModule('content-history-definition-runtime')
function fixture(t) {
    const base = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
    const directory = fs.mkdtempSync(path.join(base, 'definition-runtime-'))
    t.after(() => {
        assert.equal(path.dirname(path.resolve(directory)), base)
        assert.ok(path.basename(directory).startsWith('definition-runtime-'))
        fs.rmSync(directory, { recursive: true })
    })
    const assets = path.join(directory, 'assets'); fs.mkdirSync(assets)
    const catalogBody = '{"rows":[]}', catalogSha256 = sha(catalogBody)
    const exact = key => ({ schemaVersion: 1, key, oldDefinitionMatched: true, definitionDigest: hash('1'),
        dependencyDigest: hash('2'), previousServerDefinitionDigest: hash('3'), loaders: { 'src/lib/assets.ts': hash('4') } })
    const parent = { ...exact('rush_event:5'), reviewedExistingChildren: ['2', '1'], newUncataloguedChildren: ['4', '3'] }
    delete parent.oldDefinitionMatched
    const canonical = { schemaVersion: 1, source: { catalogSha256 }, rows: { 'gacha:1': exact('gacha:1'), 'gacha:2': exact('gacha:2') },
        existingEvidenceRebind: {
            'gacha:1': { kind: 'exact', status: 'candidate_requires_reviewed_loader_transition', previousEvidence: exact('gacha:1'),
                evidence: { ...exact('gacha:1'), loaders: { 'src/lib/assets.ts': hash('5') } }, nativeRowMatchesCatalog: true, dependencyDigestUnchanged: true },
            'rush_event:5': { kind: 'currentParent', status: 'candidate_requires_reviewed_loader_transition', previousEvidence: parent,
                evidence: { ...parent, loaders: { 'src/lib/assets.ts': hash('5') } }, nativeRowMatchesCatalog: false, dependencyDigestUnchanged: true } },
        effectiveShopDefinitionEvidence: { deliberatelyNotConsumed: 'offline-only' } }
    const canonicalBody = JSON.stringify(canonical)
    fs.writeFileSync(path.join(assets, 'content_catalog.json'), catalogBody)
    fs.writeFileSync(path.join(assets, 'content_history_definition_evidence.json'), canonicalBody)
    const identity = { schemaVersion: 1, canonicalSha256: sha(canonicalBody), catalogSha256 }
    let document = buildRuntimeDocument(canonical, { canonicalSha256: identity.canonicalSha256, canonicalBytes: Buffer.byteLength(canonicalBody), catalogSha256 })
    const save = value => { const body = typeof value === 'string' ? value : JSON.stringify(value); fs.writeFileSync(path.join(assets, 'content_history_definition_runtime.json'), body); identity.runtimeSha256 = sha(body) }
    save(document)
    return { root: directory, assets, identity, document, canonical, save }
}
test('runtime restores exact consumed evidence, ordered children and booleans with immutable shared dictionaries', t => {
    const f = fixture(t), value = load(f)
    assert.deepEqual(value, { schemaVersion: 1, source: f.canonical.source, rows: f.canonical.rows, existingEvidenceRebind: f.canonical.existingEvidenceRebind })
    assert.equal(value.rows['gacha:1'].loaders, value.rows['gacha:2'].loaders)
    assert.equal(value.existingEvidenceRebind['rush_event:5'].previousEvidence.reviewedExistingChildren,
        value.existingEvidenceRebind['rush_event:5'].evidence.reviewedExistingChildren)
    assert.deepEqual(value.existingEvidenceRebind['rush_event:5'].evidence.reviewedExistingChildren, ['2', '1'])
    assert.equal(value.existingEvidenceRebind['rush_event:5'].nativeRowMatchesCatalog, false)
    for (const object of [value, value.source, value.rows, value.rows['gacha:1'], value.rows['gacha:1'].loaders,
        value.existingEvidenceRebind, value.existingEvidenceRebind['rush_event:5'], value.existingEvidenceRebind['rush_event:5'].evidence.reviewedExistingChildren])
        assert.equal(Object.isFrozen(object), true)
    assert.throws(() => { value.rows['gacha:1'].loaders['src/lib/assets.ts'] = hash('9') }, TypeError)
})
test('runtime never reads or requires the complete original JSON and source hash buffers are bounded', t => {
    const f = fixture(t), reads = [], loadedBefore = new Set(Object.keys(require.cache))
    const fsApi = { ...fs, readFileSync(file, ...args) {
        assert.notEqual(path.basename(file), 'content_history_definition_evidence.json', 'original JSON must only be streamed')
        reads.push(path.basename(file)); return fs.readFileSync(file, ...args)
    }, readSync(fd, buffer, offset, length, position) { assert.ok(length <= 65536); return fs.readSync(fd, buffer, offset, length, position) } }
    const value = sourceModule('content-history-definition-runtime', fsApi).loadContentHistoryDefinitionRuntime(f)
    assert.equal(Object.keys(value.rows).length, 2)
    assert.deepEqual(reads, ['content_history_definition_runtime.json'])
    assert.ok(Object.keys(require.cache).filter(key => !loadedBefore.has(key)).every(key => !key.endsWith('content_history_definition_evidence.json')))
})
test('generator is deterministic and check mode writes nothing or replaces original inputs', t => {
    const f = fixture(t), original = fs.readFileSync(path.join(f.assets, 'content_history_definition_evidence.json'))
    fs.unlinkSync(path.join(f.assets, 'content_history_definition_runtime.json'))
    const first = generate({ root: f.root }), summary = fs.readFileSync(first.output), identity = fs.readFileSync(first.identityFile)
    const second = generate({ root: f.root, check: true })
    assert.equal(second.runtimeSha256, first.runtimeSha256); assert.equal(second.status, 'deterministic_projection_matches')
    assert.deepEqual(fs.readFileSync(first.output), summary); assert.deepEqual(fs.readFileSync(first.identityFile), identity)
    assert.deepEqual(fs.readFileSync(path.join(f.assets, 'content_history_definition_evidence.json')), original)
    assert.throws(() => generate({ root: f.root }), /Refuse to overwrite/)
    assert.throws(() => generate({ root: f.root, output: path.join(f.assets, 'content_history_definition_evidence.json') }), /Never replace/)
})
for (const [name, mutate, expected] of [
    ['schema', d => { d.schemaVersion = 2 }, /schema/],
    ['extra field', d => { d.extra = [] }, /fields/],
    ['source schema', d => { d.source.schemaVersion = 2 }, /provenance/],
    ['source identity', d => { d.source.canonicalSha256 = hash('8') }, /provenance/],
    ['proof reference', d => { d.rows[0][1] = 9999 }, /proofs reference/],
    ['duplicate row', d => { d.rows.push(d.rows[0]) }, /duplicate historical row/],
    ['prototype row key', d => { d.rows[0][0] = '__proto__' }, /historical row/],
    ['loader traversal', d => { d.loaders[0] = { 'src/../outside.ts': hash('1') } }, /loader source/],
    ['invalid proof', d => { d.proofs[0][0] = 'no' }, /proof tuple/],
    ['count mismatch', d => { d.counts.rows += 1 }, /count mismatch/],
    ['unused dictionary', d => { d.statuses.push('unused'); d.counts.statuses += 1 }, /unreferenced statuses/],
    ['invalid boolean', d => { d.rebind[0][5] = 1 }, /transition/],
    ['invalid transition kind', d => { d.rebind[0][1] = 2 }, /transition/],
    ['child reference', d => { d.rebind[1][3][2] = -1 }, /children reference/],
]) test('validly rehashed fixture rejects malformed ' + name, t => {
    const f = fixture(t); mutate(f.document); f.save(f.document)
    assert.throws(() => load(f), expected)
})
test('a valid-looking payload modification cannot pass the fixed generated anchor', t => {
    const f = fixture(t), fixed = { ...f.identity }; f.document.proofs[0][0] = hash('9'); f.save(f.document)
    assert.throws(() => load({ root: f.root, identity: fixed }), /summary SHA/)
})
test('invalid JSON is rejected explicitly after verified fixture identity', t => {
    const f = fixture(t); f.save('{invalid'); assert.throws(() => load(f), /invalid summary JSON/)
})
for (const [file, expected] of [['content_history_definition_runtime.json', /ENOENT/], ['content_history_definition_evidence.json', /ENOENT/], ['content_catalog.json', /ENOENT/]])
    test('missing required ' + file + ' fails without fallback', t => { const f = fixture(t); fs.unlinkSync(path.join(f.assets, file)); assert.throws(() => load(f), expected) })
for (const [file, expected] of [['content_history_definition_evidence.json', /canonical audit identity/], ['content_catalog.json', /catalog identity/]])
    test('changed ' + file + ' fails without fallback', t => { const f = fixture(t); fs.appendFileSync(path.join(f.assets, file), '\n'); assert.throws(() => load(f), expected) })
