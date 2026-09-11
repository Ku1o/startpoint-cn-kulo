const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'session-cdn-check-'))
process.env.DATA_DIR = dataDir
const Fastify = require('fastify')
const routes = require('../out/routes/cn/asset').default
const manifest = require('../assets/asset-patch/manifest.json')
const edge = manifest.patches.find(x => x.id === 'abyss-lens0910-consolidated-1.4.104')

test.after(() => {
    const db = require('../out/data/db').getDb()
    if (db.open) db.close()
    assert.equal(path.dirname(dataDir), os.tmpdir())
    fs.rmSync(dataDir, { recursive: true, force: true })
})

test('cloud .103 receives one .104 archive; current and higher cached clients do not regress', async () => {
    assert.equal(manifest.cdn_version, '1.4.104')
    assert.equal(edge.depends_on, '1.4.103')
    assert.deepEqual(edge.chain, [edge.archive])
    const app = Fastify({ logger: false })
    await app.register(routes)
    try {
        for (const device of ['Android', 'iOS']) {
            for (const version of ['1.4.103', '1.4.104', '1.4.112']) {
                const res = await app.inject({ method: 'POST', url: '/get_path',
                    headers: { device, res_ver: version }, payload: {} })
                assert.equal(res.statusCode, 200)
                const data = res.json().data
                assert.equal(data.info.target_asset_version, version === '1.4.112' ? version : '1.4.104')
                assert.deepEqual(data.full.archive, [])
                if (version === '1.4.103') {
                    assert.equal(data.diff.length, 1)
                    assert.equal(data.diff[0].version, '1.4.104')
                    assert.equal(data.diff[0].original_version, '1.4.103')
                    assert.equal(data.diff[0].archive.length, 1)
                    assert.ok(data.diff[0].archive[0].location.endsWith('/' + edge.archive))
                    assert.equal(data.diff[0].archive[0].size, edge.archive_size)
                } else assert.deepEqual(data.diff, [])
            }
        }
    } finally { await app.close() }
})
