'use strict'
const { test, after } = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), os = require('node:os')
const Module = require('node:module'), ts = require('typescript'), { createHash } = require('node:crypto')
const repo = path.resolve(__dirname, '..'), sha = bytes => createHash('sha256').update(bytes).digest('hex')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir()), directory = fs.mkdtempSync(path.join(root, 'admin-thumbnails-'))
const source = fs.readFileSync(path.join(repo, 'src/lib/content-presentation.ts'), 'utf8')
const javascript = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText
const index = JSON.parse(fs.readFileSync(path.join(repo, 'assets/content_thumbnails/index.json')))
const key = Object.keys(index.rows)[0], hash = index.rows[key].image, originalUrl = `/api/content/${encodeURIComponent(key)}/image`
let sequence = 0
function moduleAt(base) {
    const filename = path.join(base, 'src/lib/content-presentation.ts'), instance = new Module(filename, module)
    instance.filename = filename; instance.paths = Module._nodeModulePaths(path.join(repo, 'src/lib'))
    instance._compile(javascript, filename)
    return instance.exports
}
function fixture(change) {
    const base = path.join(directory, String(++sequence)), assets = path.join(base, 'assets')
    fs.mkdirSync(path.join(assets, 'asset-patch'), { recursive: true }); fs.mkdirSync(path.join(assets, 'content_thumbnails'))
    fs.copyFileSync(path.join(repo, 'assets/content_presentation.json'), path.join(assets, 'content_presentation.json'))
    fs.copyFileSync(path.join(repo, 'assets/asset-patch/manifest.json'), path.join(assets, 'asset-patch/manifest.json'))
    const copy = structuredClone(index)
    change?.(copy, assets)
    fs.writeFileSync(path.join(assets, 'content_thumbnails/index.json'), JSON.stringify(copy))
    return { base, assets, api: moduleAt(base), copy }
}
after(() => { assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(root)); fs.rmSync(directory, { recursive: true }) })

test('all784 actual banners have shared content-hash URLs, original fallbacks and verified compressed bytes', () => {
    const api = process.env.STARPOINT_TEST_COMPILED === '1' ? require('../out/lib/content-presentation') : moduleAt(repo), unique = new Set()
    assert.equal(Object.keys(index.rows).length, 784)
    for (const [key, row] of Object.entries(index.rows)) {
        const presentation = api.getContentPresentation(key), image = api.readContentPresentationThumbnail(row.image)
        assert.equal(presentation.imageUrl, `/api/content/thumbnail/${row.image}.webp`)
        assert.equal(presentation.imageFallbackUrl, `/api/content/${encodeURIComponent(key)}/image`)
        assert.ok(image, key); assert.equal(image.contentType, 'image/webp')
        assert.equal(sha(image.bytes), row.image); assert.equal(image.etag, `"${row.image}"`)
        assert.equal(image.bytes.length, index.images[row.image].bytes)
        assert.strictEqual(api.readContentPresentationThumbnail(row.image), image)
        unique.add(presentation.imageUrl)
    }
    assert.equal(unique.size, Object.keys(index.images).length)
    assert.ok(unique.size < 784)
    assert.equal(api.readContentPresentationThumbnail(hash, () => false), null, 'catalog ownership is rechecked even for cached bytes')
})
test('missing or corrupt thumbnail files fail closed and retain the exact original-image fallback', () => {
    const missing = fixture()
    assert.equal(missing.api.readContentPresentationThumbnail(hash), null)
    assert.equal(missing.api.getContentPresentation(key).imageFallbackUrl, originalUrl)
    const corrupt = fixture((_, assets) => fs.writeFileSync(path.join(assets, 'content_thumbnails', hash + '.webp'), Buffer.alloc(index.images[hash].bytes)))
    assert.equal(corrupt.api.readContentPresentationThumbnail(hash), null)
    assert.equal(corrupt.api.getContentPresentation(key).imageFallbackUrl, originalUrl)
})
test('stale presentation identity, raw-source proof or unsafe file mapping falls back before requesting a thumbnail', () => {
    for (const alter of [value => value.source.presentationSha256 = '0'.repeat(64),
        value => value.rows[key].sourceRawSha256 = '0'.repeat(64), value => value.images[hash].file = '../outside.webp']) {
        const { api } = fixture(alter)
        assert.equal(api.getContentPresentation(key).imageUrl, originalUrl)
        assert.equal(api.readContentPresentationThumbnail(hash), null)
    }
})
test('a changed active resource chain invalidates even a previously cached thumbnail', () => {
    const f = fixture((_, assets) => fs.copyFileSync(path.join(repo, 'assets/content_thumbnails', hash + '.webp'), path.join(assets, 'content_thumbnails', hash + '.webp')))
    assert.ok(f.api.readContentPresentationThumbnail(hash))
    fs.appendFileSync(path.join(f.assets, 'asset-patch/manifest.json'), '\n ')
    assert.equal(f.api.getContentPresentation(key).imageUrl, originalUrl)
    assert.equal(f.api.readContentPresentationThumbnail(hash), null)
})
test('absent index and unlisted or malformed hashes never become arbitrary-file readers', () => {
    const f = fixture()
    fs.unlinkSync(path.join(f.assets, 'content_thumbnails/index.json'))
    assert.equal(moduleAt(f.base).getContentPresentation(key).imageUrl, originalUrl)
    for (const value of ['../config/keys', '__proto__', 'constructor', '0'.repeat(64), hash.toUpperCase(), hash + '.webp'])
        assert.equal(f.api.readContentPresentationThumbnail(value), null)
})

test('invalid new resource manifests keep rejecting cached thumbnails on repeated reads', () => {
    for (const invalid of ['{invalid-json', JSON.stringify({ patches: [{ enabled: true, archive: '../outside.zip' }] })]) {
        const f = fixture((_, assets) => fs.copyFileSync(path.join(repo, 'assets/content_thumbnails', hash + '.webp'), path.join(assets, 'content_thumbnails', hash + '.webp')))
        assert.ok(f.api.readContentPresentationThumbnail(hash))
        fs.writeFileSync(path.join(f.assets, 'asset-patch/manifest.json'), invalid)
        for (let repeat = 0; repeat < 2; repeat++) {
            assert.equal(f.api.readContentPresentationThumbnail(hash), null)
            assert.equal(f.api.getContentPresentation(key).imageUrl, originalUrl)
        }
    }
})
