const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const crypto = require('node:crypto')

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-degree-assets-'))
process.env.DATA_DIR = path.join(temporary, 'db')
process.env.GACHA_SEED_DIR = path.join(temporary, 'isolated-seeds')
fs.mkdirSync(process.env.GACHA_SEED_DIR)
process.env.CDN_DIR = path.join(temporary, 'cdn')
for (const platform of ['common', 'medium', 'android', 'ios']) {
    for (const kind of ['full', 'diff']) {
        fs.mkdirSync(path.join(process.env.CDN_DIR, 'cn', `archive-${platform}-${kind}`), { recursive: true })
    }
}
const Fastify = require('fastify')
const repo = path.resolve(__dirname, '..')
const manifest = require('../assets/asset-patch/manifest.json')
const patch = manifest.patches.find(entry => entry.id === 'reborn-character-degrees-1.4.108')
const assetRoutes = require('../out/routes/cn/asset').default
const { compareVersion } = require('../out/lib/version')
const sha = raw => crypto.createHash('sha256').update(raw).digest('hex')

test.after(() => {
    const db = require('../out/data/db').getDb()
    if (db.open) db.close()
    const resolved = fs.realpathSync(temporary)
    assert.equal(path.dirname(resolved), fs.realpathSync(os.tmpdir()))
    assert.ok(path.basename(resolved).startsWith('starpoint-degree-assets-'))
    fs.rmSync(resolved, { recursive: true })
})

for (const device of ['Android', 'iOS']) {
    test(`${device}: .107 receives the .108 nameplate archive and current clients have no update`, async t => {
        assert.ok(compareVersion(manifest.cdn_version, '1.4.108') >= 0)
        assert.equal(patch.depends_on, '1.4.107')
        assert.equal(patch.enabled, true)
        const app = Fastify({ logger: false })
        await app.register(assetRoutes, { prefix: '/asset' })
        // Same active-archive file root and public URL prefix used by cn-server.
        await app.register(require('@fastify/static'), {
            root: path.join(repo, 'assets/asset-patch/active'), prefix: '/patch/cn/asset-patch/active/',
        })
        await app.ready()
        t.after(() => app.close())
        for (const asset_size of ['fulfill', 'shortened', 'delayed']) {
            const headers = { host: '127.0.0.1:8001', device, res_ver: '1.4.107', asset_size }
            const response = await app.inject({ method: 'POST', url: '/asset/get_path', headers, payload: {} })
            assert.equal(response.statusCode, 200)
            const update = response.json()
            assert.equal(update.data_headers.asset_update, true)
            assert.equal(update.data.info.target_asset_version, manifest.cdn_version)
            if (manifest.cdn_version === '1.4.108') assert.equal(update.data.diff.length, 1)
            const edge = update.data.diff.find(group => group.version === '1.4.108')
            assert.ok(edge)
            assert.equal(edge.original_version, '1.4.107')
            assert.equal(edge.version, '1.4.108')
            assert.deepEqual(edge.archive.map(file => path.posix.basename(file.location)), patch.chain || [patch.archive])
            assert.ok(edge.archive.some(file => path.posix.basename(file.location) === 'pinball-1.4.107-1.4.108-1-reborn-character-degrees.zip'))
            assert.equal(edge.archive.reduce((sum, file) => sum + file.size, 0), patch.archive_size)
            for (const archive of edge.archive) {
                const integrity = patch.archive_integrity.find(file => file.name === path.posix.basename(archive.location))
                assert.ok(integrity)
                assert.equal(archive.size, integrity.size)
                const download = await app.inject({ method: 'GET', url: new URL(archive.location).pathname })
                assert.equal(download.statusCode, 200)
                assert.equal(download.rawPayload.length, integrity.size)
                assert.equal(sha(download.rawPayload), integrity.sha256)
            }
            const size = await app.inject({ method: 'POST', url: '/asset/version_info', headers, payload: {} })
            assert.equal(size.statusCode, 200)
            const expectedBytes = update.data.diff.flatMap(group => group.archive).reduce((sum, file) => sum + file.size, 0)
            assert.equal(size.json().data.total_size, expectedBytes)
            if (manifest.cdn_version === '1.4.108') assert.equal(expectedBytes, patch.archive_size)
            const current = (await app.inject({ method: 'POST', url: '/asset/get_path',
                headers: { ...headers, res_ver: manifest.cdn_version }, payload: {} })).json()
            assert.equal(current.data_headers.asset_update, false)
            assert.equal(current.data.full, null)
            assert.equal(current.data.diff, null)
        }
    })
}
