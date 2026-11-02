'use strict'
// Offline, scoped metadata revision. Never reads or writes a player database.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const assert = require('node:assert/strict')
const { buildRuntimeDocument, identitySource } = require('./build-content-definition-runtime.cjs')
const { discoveryProjection } = require('./build-content-runtime-index.cjs')
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex')
const files = ['assets/gacha.json', 'assets/gacha_cnmod.json', 'assets/gacha_rank_p5b.json']
const pools = [990001, 990002]
function refresh(root, previous, check = false) {
    const read = (base, name) => fs.readFileSync(path.join(base, name))
    const old = name => JSON.parse(read(previous, name))
    const current = name => JSON.parse(read(root, name))
    const beforeManifest = old('assets/asset-patch/manifest.json'), manifest = current('assets/asset-patch/manifest.json')
    assert.equal(beforeManifest.cdn_version, '1.4.355')
    assert.equal(manifest.cdn_version, '1.4.356')
    assert.ok(JSON.stringify(manifest.patches.slice(0, -1)) === JSON.stringify(beforeManifest.patches), 'Preserve every historical resource edge')
    const patch = manifest.patches.at(-1), resourceReport = current('assets/asset-patch/audit/epuration-gacha-1.4.356/report.json')
    assert.equal(patch.id, 'epuration-gacha-restore-1.4.356')
    const source = { assetVersion: '1.4.356', manifestSha256: sha(read(root, 'assets/asset-patch/manifest.json')) }
    const outputs = new Map(), changed = []
    function encodeLike(name, value) {
        const raw = read(previous, name).toString(), pretty = raw.startsWith('{\r\n  ') || raw.startsWith('{\n  ')
        const newline = raw.includes('\r\n') ? '\r\n' : '\n'
        return Buffer.from(JSON.stringify(value, null, pretty ? 2 : undefined).replace(/\n/g, newline) + newline)
    }
    function add(name, value) { outputs.set(name, encodeLike(name, value)) }
    const catalog = old('assets/content_catalog.json')
    const sourceHashes = Object.fromEntries(files.map(file => [file, sha(read(root, file))]))
    for (const file of files) catalog.serverResources[file].sha256 = sourceHashes[file]
    const reboundRows = []
    for (const row of catalog.rows) {
        const sources = row.definitionEvidence?.serverSources || []
        if (!sources.some(file => files.includes(file))) continue
        assert.equal(row.type, 'gacha', 'Unexpected consumer of a gacha table')
        row.serverDefinitionDigest = sha(JSON.stringify(sources.map(file => [file,
            sourceHashes[file] || catalog.serverResources[file].sha256])))
        reboundRows.push(row.key)
    }
    const resourceSource = old('assets/content_resource_source.json')
    assert.equal(resourceSource.source.assetVersion, '1.4.350')
    resourceSource.source = source
    for (const row of resourceReport.pools) {
        const entry = catalog.resources[row.logical]
        assert.ok(entry && resourceSource.resources[row.logical])
        assert.equal(resourceSource.resources[row.logical].sha256, row.beforeSha256)
        const archive = 'assets/asset-patch/active/' + patch.archive
        catalog.resources[row.logical] = { ...entry, archive, sha256: row.afterSha256 }
        resourceSource.resources[row.logical] = { archive, sha256: row.afterSha256 }
    }
    add('assets/content_catalog.json', catalog)
    add('assets/content_resource_source.json', resourceSource)
    const catalogSha256 = sha(outputs.get('assets/content_catalog.json'))
    for (const name of ['content_history_quest_rules.json', 'content_history_shop_rules.json']) {
        const relative = 'assets/' + name, document = old(relative)
        document.source = { ...document.source, ...source, catalogSha256 }
        add(relative, document)
    }
    const boxes = old('assets/content_box_associations.json')
    Object.assign(boxes, source, { catalogSha256 })
    add('assets/content_box_associations.json', boxes)
    const canonicalName = 'assets/content_history_definition_evidence.json', evidence = old(canonicalName)
    evidence.source.catalogSha256 = catalogSha256
    add(canonicalName, evidence)
    const canonical = outputs.get(canonicalName), canonicalSha256 = sha(canonical)
    const runtime = buildRuntimeDocument(evidence, { canonicalSha256, canonicalBytes: canonical.length, catalogSha256 })
    const body = Buffer.from(JSON.stringify(runtime) + '\n')
    outputs.set('assets/content_history_definition_runtime.json', body)
    outputs.set('src/lib/content-history-definition-runtime-identity.ts', Buffer.from(identitySource({
        schemaVersion: 1, canonicalSha256, catalogSha256, runtimeSha256: sha(body),
    })))
    const presentation = old('assets/content_presentation.json')
    Object.assign(presentation.source, source)
    add('assets/content_presentation.json', presentation)
    const presentationSha256 = sha(outputs.get('assets/content_presentation.json'))
    const thumbnails = old('assets/content_thumbnails/index.json')
    // This changes provenance only; image bytes and thumbnail rows stay untouched.
    thumbnails.source = { ...thumbnails.source, manifestSha256: source.manifestSha256, presentationSha256 }
    outputs.set('assets/content_thumbnails/index.json', Buffer.from(JSON.stringify(thumbnails) + '\n'))
    const discovery = old('assets/content_discovery.json')
    const text = current('assets/cdndata/character_text_rank_p5b.json')['179981'][0]
    const entity = { id: 179981, name: text[0] + '（' + text[3] + '）', aliases: [text[0]] }
    for (const id of pools) {
        const row = discovery.rows['gacha:' + id]
        assert.equal(row.characters.some(item => item.id === 179981), false)
        const gacha = current('assets/' + (id === 990001 ? 'gacha_cnmod.json' : 'gacha_rank_p5b.json'))[id]
        const target = gacha.pool['1'].find(item => item.id === 179981)
        assert.ok(target.odds > 0 && target.isRateUp && target.isExchangeable)
        for (const relation of ['exchange', 'pool', 'up']) row.characters.push({ ...entity, relation })
        row.characters.sort((a, b) => `${a.id}:${a.relation}`.localeCompare(`${b.id}:${b.relation}`, 'en'))
    }
    discovery.coverage.characters += 6
    discovery.source = { ...discovery.source, manifestSha256: source.manifestSha256, presentationSha256, catalogSha256 }
    for (const file of Object.keys(discovery.sourceInputs)) {
        if (files.includes(file)) discovery.sourceInputs[file] = sourceHashes[file]
        else if (outputs.has(file)) discovery.sourceInputs[file] = sha(outputs.get(file))
    }
    add('assets/content_discovery.json', discovery)
    const discoveryRaw = outputs.get('assets/content_discovery.json')
    outputs.set('assets/content_discovery_runtime.json', Buffer.from(JSON.stringify(discoveryProjection(discovery, sha(discoveryRaw))) + '\n'))
    // Original readiness and its projection stay byte-for-byte unchanged.
    // Check every preimage before the first mutation; avoid partial application
    // when another task changed a later file. Large buffers never enter assert diffs.
    for (const [name, bytes] of outputs) {
        const actual = read(root, name)
        if (check) assert.ok(actual.equals(bytes), 'Stale derived metadata: ' + name)
        else if (!actual.equals(bytes)) {
            assert.ok(actual.equals(read(previous, name)), 'Concurrent metadata edit: ' + name)
        }
        if (!fs.existsSync(path.join(previous, name)) || !read(previous, name).equals(bytes)) changed.push(name)
    }
    if (!check) for (const [name, bytes] of outputs)
        if (!read(root, name).equals(bytes)) fs.writeFileSync(path.join(root, name), bytes)
    return { source, catalogSha256, reboundGachaRows: reboundRows.length, changed }
}
module.exports = { refresh }
if (require.main === module) {
    const args = process.argv.slice(2), at = args.indexOf('--previous')
    assert.ok(at >= 0 && args[at + 1], 'Use --previous <fixed-old-source> [--check]')
    console.log(JSON.stringify(refresh(path.resolve(__dirname, '..'), path.resolve(args[at + 1]), args.includes('--check')), null, 2))
}
