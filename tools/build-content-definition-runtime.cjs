'use strict'
// Offline projection only. The complete review report stays unchanged.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), assert = require('node:assert/strict')
const sha = value => crypto.createHash('sha256').update(value).digest('hex')
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const hashPattern = /^[a-f0-9]{64}$/, keyPattern = /^[a-z_]+:\d+$/
const exactFields = ['schemaVersion', 'key', 'oldDefinitionMatched', 'definitionDigest', 'dependencyDigest', 'loaders', 'previousServerDefinitionDigest']
const parentFields = ['schemaVersion', 'key', 'definitionDigest', 'dependencyDigest', 'loaders', 'previousServerDefinitionDigest', 'reviewedExistingChildren', 'newUncataloguedChildren']
const exactKeys = (value, fields, label) => assert.deepEqual(Object.keys(value).sort(), fields.slice().sort(), label)
function fileSha(file) {
    const fd = fs.openSync(file, 'r'), block = Buffer.allocUnsafe(65536), value = crypto.createHash('sha256')
    try { let count; while ((count = fs.readSync(fd, block, 0, block.length, null))) value.update(block.subarray(0, count)); return value.digest('hex') }
    finally { fs.closeSync(fd) }
}
function buildRuntimeDocument(canonical, source) {
    assert.ok(record(canonical) && canonical.schemaVersion === 1 && record(canonical.source) && record(canonical.rows) && record(canonical.existingEvidenceRebind), 'Unsupported review report')
    assert.equal(canonical.source.catalogSha256, source.catalogSha256, 'Review report does not match current catalog bytes')
    for (const field of ['canonicalSha256', 'catalogSha256']) assert.match(source[field], hashPattern, field)
    assert.ok(Number.isSafeInteger(source.canonicalBytes) && source.canonicalBytes > 0)
    const loaders = [], proofs = [], children = [], statuses = [], rows = [], rebind = []
    const indices = { loaders: new Map(), proofs: new Map(), children: new Map(), statuses: new Map() }
    let evidenceReferences = 0
    const pool = (name, values, value) => {
        const signature = JSON.stringify(value), previous = indices[name].get(signature)
        if (previous !== undefined) return previous
        const index = values.length; indices[name].set(signature, index); values.push(value); return index
    }
    const receipt = (value, key, kind) => {
        assert.ok(record(value), 'Missing evidence: ' + key)
        exactKeys(value, kind === 0 ? exactFields : parentFields, 'Unsupported evidence fields: ' + key)
        assert.equal(value.schemaVersion, 1); assert.equal(value.key, key)
        if (kind === 0) assert.equal(value.oldDefinitionMatched, true, 'Exact evidence must preserve its reviewed boolean: ' + key)
        const proof = ['definitionDigest', 'dependencyDigest', 'previousServerDefinitionDigest'].map(field => {
            assert.match(value[field], hashPattern, key + ' ' + field); return value[field]
        })
        assert.ok(record(value.loaders) && Object.keys(value.loaders).length > 0)
        const normalized = Object.fromEntries(Object.entries(value.loaders).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([name, hash]) => {
            assert.match(name, /^src\/[A-Za-z0-9_./-]+\.ts$/)
            assert.ok(!name.split('/').some(part => part === '..' || part === '.' || !part)); assert.match(hash, hashPattern)
            return [name, hash]
        }))
        const result = [pool('proofs', proofs, proof), pool('loaders', loaders, normalized)]
        if (kind === 1) for (const field of ['reviewedExistingChildren', 'newUncataloguedChildren']) {
            const list = value[field]
            assert.ok(Array.isArray(list) && list.every(item => typeof item === 'string' && /^\d+$/.test(item)), key + ' ' + field)
            result.push(pool('children', children, list.slice()))
        }
        evidenceReferences++; return result
    }
    for (const [key, value] of Object.entries(canonical.rows)) {
        assert.match(key, keyPattern); rows.push([key, ...receipt(value, key, 0)])
    }
    for (const [key, value] of Object.entries(canonical.existingEvidenceRebind)) {
        assert.match(key, keyPattern); assert.ok(record(value), 'Invalid existing-evidence transition')
        const kind = value.kind === 'exact' ? 0 : value.kind === 'currentParent' ? 1 : -1
        assert.notEqual(kind, -1, 'Unknown existing-evidence kind')
        assert.ok(typeof value.status === 'string' && value.status.length > 0 && value.status.length <= 500)
        assert.equal(typeof value.nativeRowMatchesCatalog, 'boolean'); assert.equal(typeof value.dependencyDigestUnchanged, 'boolean')
        rebind.push([key, kind, pool('statuses', statuses, value.status), receipt(value.previousEvidence, key, kind),
            receipt(value.evidence, key, kind), value.nativeRowMatchesCatalog, value.dependencyDigestUnchanged])
    }
    return { schemaVersion: 1, source: { schemaVersion: canonical.schemaVersion, ...source },
        loaders, proofs, children, statuses, rows, rebind,
        counts: { rows: rows.length, rebind: rebind.length, evidenceReferences, loaders: loaders.length, proofs: proofs.length, children: children.length, statuses: statuses.length } }
}
function identitySource(identity) {
    return '// Generated by tools/build-content-definition-runtime.cjs; no timestamp or self-referential hash.\n'
        + 'export const CONTENT_HISTORY_DEFINITION_RUNTIME_IDENTITY = Object.freeze(' + JSON.stringify(identity, null, 2) + ' as const)\n'
}
function generate(options = {}) {
    const root = path.resolve(options.root || path.join(__dirname, '..'))
    const canonicalFile = path.join(root, 'assets/content_history_definition_evidence.json'), catalogFile = path.join(root, 'assets/content_catalog.json')
    const output = path.resolve(options.output || path.join(root, 'assets/content_history_definition_runtime.json'))
    const identityFile = path.resolve(options.identity || path.join(root, 'src/lib/content-history-definition-runtime-identity.ts'))
    for (const file of [output, identityFile]) for (const input of [canonicalFile, catalogFile])
        assert.notEqual(file.toLowerCase(), input.toLowerCase(), 'Never replace the original review or catalog')
    assert.notEqual(output.toLowerCase(), identityFile.toLowerCase(), 'Summary and identity must be separate files')
    const raw = fs.readFileSync(canonicalFile), canonicalSha256 = sha(raw), canonical = JSON.parse(raw.toString('utf8'))
    const catalogSha256 = fileSha(catalogFile)
    const value = buildRuntimeDocument(canonical, { canonicalSha256, canonicalBytes: raw.length, catalogSha256 })
    const body = JSON.stringify(value) + '\n', runtimeSha256 = sha(body)
    const identity = { schemaVersion: 1, canonicalSha256, catalogSha256, runtimeSha256 }
    const generatedIdentity = identitySource(identity)
    if (options.check) {
        assert.equal(fs.readFileSync(output, 'utf8'), body, 'Runtime summary is stale')
        assert.equal(fs.readFileSync(identityFile, 'utf8'), generatedIdentity, 'Runtime identity is stale')
    } else {
        for (const file of [output, identityFile]) {
            fs.mkdirSync(path.dirname(file), { recursive: true })
            if (!options.overwrite) assert.equal(fs.existsSync(file), false, 'Refuse to overwrite without --overwrite: ' + file)
        }
        fs.writeFileSync(output, body); fs.writeFileSync(identityFile, generatedIdentity)
    }
    assert.equal(fileSha(canonicalFile), canonicalSha256, 'Review source changed during generation')
    assert.equal(fileSha(catalogFile), catalogSha256, 'Catalog changed during generation')
    const report = { status: options.check ? 'deterministic_projection_matches' : 'generated', source: canonicalFile, output, identityFile,
        canonicalBytes: raw.length, runtimeBytes: Buffer.byteLength(body), identityBytes: Buffer.byteLength(generatedIdentity),
        bytesSaved: raw.length - Buffer.byteLength(body), reductionPercent: 100 * (1 - Buffer.byteLength(body) / raw.length),
        ...identity, counts: value.counts, sharedLoaderReferences: value.counts.evidenceReferences - value.counts.loaders,
        ignoredDiagnosticFields: Object.keys(canonical).filter(key => !['schemaVersion', 'source', 'rows', 'existingEvidenceRebind'].includes(key)) }
    if (options.report) { fs.mkdirSync(path.dirname(options.report), { recursive: true }); fs.writeFileSync(options.report, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' }) }
    return report
}
if (require.main === module) {
    try {
        const args = process.argv.slice(2), options = {}
        for (let index = 0; index < args.length; index++) {
            const name = args[index]
            if (['--check', '--overwrite'].includes(name)) options[name.slice(2)] = true
            else if (['--root', '--output', '--identity', '--report'].includes(name) && args[index + 1]) options[name.slice(2)] = args[++index]
            else throw Error('Use --root <repo> [--output <runtime.json>] [--identity <identity.ts>] [--report <task-report.json>] [--check | --overwrite]')
        }
        console.log(JSON.stringify(generate(options), null, 2))
    } catch (error) { console.error(error.stack); process.exitCode = 1 }
}
module.exports = { buildRuntimeDocument, generate, identitySource }
