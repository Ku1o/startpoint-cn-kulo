'use strict'
// Export only original management banners for an offline thumbnail build.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict'), { createHash } = require('node:crypto')
const { execFileSync } = require('node:child_process')
const repo = path.resolve(__dirname, '..'), sha = bytes => createHash('sha256').update(bytes).digest('hex')
function assertExportOutput(root, requested) {
    const directory = path.join(fs.realpathSync(path.dirname(requested)), path.basename(requested))
    assert.ok(!fs.existsSync(directory), 'Use a fresh export directory')
    const inventory = execFileSync('git', ['-c', 'core.quotePath=false', 'worktree', 'list', '--porcelain'], { cwd: root, encoding: 'utf8', windowsHide: true })
    const worktrees = inventory.split(/\r?\n/).filter(line => line.startsWith('worktree ')).map(line => fs.realpathSync(line.slice(9)))
    assert.ok(worktrees.length, 'Cannot establish protected Git worktree inventory')
    for (const protectedRoot of [fs.realpathSync(root), ...worktrees]) { const relative = path.relative(protectedRoot, directory); assert.ok(relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative), 'Export must stay outside code/resource roots') }
    assert.ok(!directory.split(/[\\/]/).some(part => part.replace(/[. ]+$/g, '').toLowerCase() === '.cdn'), 'Protected resource output')
    return directory
}
async function main() {
    const i = process.argv.indexOf('--output'); assert.ok(i >= 0 && process.argv[i + 1], '--output <task directory> required')
    const requested = path.resolve(process.argv[i + 1])
    const directory = assertExportOutput(repo, requested)
    const presentation = fs.readFileSync(path.join(repo, 'assets/content_presentation.json')), manifest = JSON.parse(presentation)
    const chain = fs.readFileSync(path.join(repo, 'assets/asset-patch/manifest.json'))
    assert.equal(sha(chain), manifest.source.manifestSha256, 'Regenerate presentation receipts before exporting a changed chain')
    fs.mkdirSync(directory, { recursive: true }); fs.mkdirSync(path.join(directory, 'originals'))
    const reader = require(path.join(repo, 'out/lib/content-presentation.js')).readContentPresentationImage
    const rows = {}, originals = {}
    for (const [key, row] of Object.entries(manifest.rows)) {
        if (!row.images.some(logical => manifest.resources[logical])) continue
        const image = await reader(key); assert.ok(image, 'Original must decode: ' + key)
        const bytes = image.bytes, pngSha256 = sha(bytes)
        const encodedSha256 = sha(Buffer.concat([Buffer.from([137, 112, 110, 103, 13, 10, 26, 10]), bytes.subarray(8)]))
        const logical = row.images.find(logical => [pngSha256, encodedSha256].includes(manifest.resources[logical]?.sha256))
        assert.ok(logical, 'Actual original must match exact resource receipt: ' + key)
        const resource = manifest.resources[logical]
        assert.equal(bytes.length, resource.bytes)
        if (!originals[pngSha256]) {
            const file = `originals/${pngSha256}.png`; fs.writeFileSync(path.join(directory, file), bytes, { flag: 'wx' })
            originals[pngSha256] = { file, bytes: bytes.length, width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) }
        }
        rows[key] = { sourceLogical: logical, sourceRawSha256: resource.sha256, sourcePngSha256: pngSha256 }
    }
    assert.equal(sha(fs.readFileSync(path.join(repo, 'assets/asset-patch/manifest.json'))), sha(chain))
    const result = { schemaVersion: 1, source: { manifestSha256: sha(chain), presentationSha256: sha(presentation) }, rows, originals }
    fs.writeFileSync(path.join(directory, 'source-exports.json'), JSON.stringify(result, null, 2) + '\n')
    console.log(JSON.stringify({ rows: Object.keys(rows).length, uniqueImages: Object.keys(originals).length, uniqueBytes: Object.values(originals).reduce((n, row) => n + row.bytes, 0), source: path.join(directory, 'source-exports.json') }))
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1 })
module.exports = { assertExportOutput }
