'use strict'
// Merge independently verified relations; this tool does not open a database or alter game resources.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict'), { createHash } = require('node:crypto')
const { execFileSync } = require('node:child_process')
const sha = bytes => createHash('sha256').update(bytes).digest('hex')
const shaPattern = /^[a-f0-9]{64}$/
const safeRelative = relative => /^(?:assets|src|tools|docs)\/[a-zA-Z0-9_./-]+$/.test(relative) && !relative.split('/').some(part => !part || part === '.' || part === '..')
function text(value) { assert.equal(typeof value, 'string'); assert.ok(value.trim() && value.length <= 2000); return value.trim() }
function uniqueTexts(values = []) { assert.ok(Array.isArray(values)); return [...new Set(values.map(text))] }
function entities(parts, field) {
    const result = new Map()
    for (const part of parts) for (const value of part[field] || []) {
        assert.ok(Number.isSafeInteger(value.id) && value.id >= 0)
        const name = text(value.name), relation = text(value.relation), aliases = uniqueTexts(value.aliases)
        assert.ok((field === 'characters' ? ['up','pool','exchange','reward'] : ['up','pool','drop','firstClear','mission','box','exchange','ranking','overall','pass']).includes(relation))
        const kind = field === 'rewards' ? text(value.kind) : undefined
        const key = `${kind || ''}:${value.id}:${relation}`, old = result.get(key)
        if (old) {
            assert.equal(old.name, name, `Conflicting entity name: ${key}`)
            old.aliases = uniqueTexts([...(old.aliases || []), ...aliases])
        } else result.set(key, { ...(kind ? { kind } : {}), id: value.id, name, relation, ...(aliases.length ? { aliases } : {}) })
    }
    return [...result.values()].sort((a,b) => `${a.kind || ''}:${a.id}:${a.relation}`.localeCompare(`${b.kind || ''}:${b.id}:${b.relation}`, 'en'))
}
function merge({ repo, fragments }) {
    repo = fs.realpathSync(repo)
    const expected = { manifestSha256: sha(fs.readFileSync(path.join(repo, 'assets/asset-patch/manifest.json'))),
        presentationSha256: sha(fs.readFileSync(path.join(repo, 'assets/content_presentation.json'))),
        catalogSha256: sha(fs.readFileSync(path.join(repo, 'assets/content_catalog.json'))) }
    const presentation = JSON.parse(fs.readFileSync(path.join(repo, 'assets/content_presentation.json')))
    const keys = Object.keys(presentation.rows).sort(), allowed = new Set(keys), sourceInputs = {}, byKey = new Map(), fragmentHashes = []
    for (const file of fragments) {
        const bytes = fs.readFileSync(file), fragment = JSON.parse(bytes)
        assert.equal(fragment.schemaVersion, 1); assert.deepEqual(fragment.source, expected, 'Fragment source identities differ')
        assert.ok(fragment.sourceInputs && Object.keys(fragment.sourceInputs).length, 'Source inputs are required')
        for (const [relative, digest] of Object.entries(fragment.sourceInputs)) {
            assert.ok(safeRelative(relative) && shaPattern.test(digest), 'Unsafe source input')
            assert.equal(sha(fs.readFileSync(path.join(repo, relative))), digest, `Changed source: ${relative}`)
            if (sourceInputs[relative]) assert.equal(sourceInputs[relative], digest)
            sourceInputs[relative] = digest
        }
        for (const [key, value] of Object.entries(fragment.rows)) {
            assert.ok(allowed.has(key), `Unknown parent: ${key}`)
            assert.ok(['verified', 'unavailable', 'not_applicable'].includes(value.status), `Missing coverage status: ${key}`)
            if (!byKey.has(key)) byKey.set(key, [])
            byKey.get(key).push(value)
        }
        fragmentHashes.push(sha(bytes))
    }
    const self = path.relative(repo, __filename).replaceAll(path.sep, '/')
    if (safeRelative(self)) sourceInputs[self] = sha(fs.readFileSync(__filename))
    const rows = {}, coverage = { parents: keys.length, verified: 0, unavailable: 0, not_applicable: 0, characters: 0, rewards: 0, types: {} }
    for (const key of keys) {
        const parts = byKey.get(key); assert.ok(parts?.length, `Missing parent coverage: ${key}`)
        const status = parts.some(part => part.status === 'unavailable') ? 'unavailable'
            : parts.every(part => part.status === 'not_applicable') ? 'not_applicable' : 'verified'
        const editions = uniqueTexts(parts.map(part => part.editionLabel).filter(Boolean)); assert.ok(editions.length <= 1, `Conflicting edition: ${key}`)
        rows[key] = { characters: entities(parts, 'characters'), rewards: entities(parts, 'rewards'),
            aliases: uniqueTexts(parts.flatMap(part => part.aliases || [])), notes: uniqueTexts(parts.flatMap(part => part.notes || [])),
            publicNotes: uniqueTexts(parts.flatMap(part => part.publicNotes || [])), status,
            ...(editions.length ? { editionLabel: editions[0] } : {}) }
        coverage[status]++; coverage.characters += rows[key].characters.length; coverage.rewards += rows[key].rewards.length
        coverage.types[presentation.rows[key].type] = (coverage.types[presentation.rows[key].type] || 0) + 1
    }
    assert.equal(byKey.size, keys.length)
    return { schemaVersion: 1, source: expected, sourceInputs: Object.fromEntries(Object.entries(sourceInputs).sort()), fragmentHashes, coverage, rows }
}
function assertDiscoveryOutput(repo, output) {
    const inventory = execFileSync('git', ['-c', 'core.quotePath=false', 'worktree', 'list', '--porcelain'], { cwd: repo, encoding: 'utf8', windowsHide: true })
    const worktrees = inventory.split(/\r?\n/).filter(line => line.startsWith('worktree ')).map(line => fs.realpathSync(line.slice(9)))
    assert.ok(worktrees.length, 'Cannot establish protected Git worktree inventory')
    const physical = path.join(fs.realpathSync(path.dirname(output)), path.basename(output))
    for (const protectedRoot of [worktrees[0]]) {
        const relative = path.relative(protectedRoot, physical)
        assert.ok(relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative), 'Protected source output')
    }
    assert.ok(!physical.split(/[\\/]/).some(part => part.replace(/[. ]+$/g,'').toLowerCase() === '.cdn'), 'Protected resource output')
    assert.equal(physical, path.join(repo, 'assets/content_discovery.json'), 'Write only the worktree discovery index')
    return physical
}
function main() {
    const args = process.argv.slice(2), option = name => { const i = args.indexOf(name); assert.ok(i >= 0 && args[i+1], `${name} required`); return args[i+1] }
    const repo = fs.realpathSync(path.resolve(__dirname, '..')), output = path.resolve(option('--output'))
    const physical = assertDiscoveryOutput(repo, output)
    const result = merge({ repo, fragments: [option('--gacha'), option('--rewards')] })
    fs.writeFileSync(physical, JSON.stringify(result) + '\n')
    console.log(JSON.stringify({ ...result.coverage, bytes: fs.statSync(physical).size, sha256: sha(fs.readFileSync(physical)) }))
}
if (require.main === module) main()
module.exports = { merge, assertDiscoveryOutput }
