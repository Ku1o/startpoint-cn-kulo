const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const Fastify = require('fastify')
const { installCustomCdnResourceRoutes } = require('../out/lib/custom-cdn-resource-routes')

test('all four native roots prefer custom bytes and retain pristine fallback', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cn-resource-routes-'))
    const patchRoot = path.join(dir, 'patch'), cdnRoot = path.join(dir, 'cdn')
    const hash = 'a'.repeat(38), missing = 'b'.repeat(38)
    const app = Fastify()
    installCustomCdnResourceRoutes(app, { patchRoot, cdnRoot })
    try {
        for (const root of ['upload', 'medium_upload', 'android_upload', 'ios_upload']) {
            const custom = Buffer.from(`custom-${root}`), original = Buffer.from(`pristine-${root}`)
            const p = path.join(patchRoot, 'production', root, 'ab', hash)
            const b = path.join(cdnRoot, 'cn/dummy/download/production', root, 'ab', hash)
            fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, custom)
            fs.mkdirSync(path.dirname(b), { recursive: true }); fs.writeFileSync(b, original)
            const url = `/patch/cn/dummy/download/production/${root}/ab/${hash}`
            const response = await app.inject(url)
            assert.equal(response.statusCode, 200); assert.deepEqual(response.rawPayload, custom)
            fs.unlinkSync(p)
            const fallback = await app.inject(url)
            assert.equal(fallback.statusCode, 200); assert.deepEqual(fallback.rawPayload, original)
            assert.deepEqual(fs.readFileSync(b), original)
            assert.equal((await app.inject(`/patch/cn/dummy/download/production/${root}/ab/${missing}`)).statusCode, 404)
        }
        for (const suffix of ['ios_upload/ab/short', `ios_upload/../${hash}`, `other/ab/${hash}`]) {
            assert.equal((await app.inject('/patch/cn/dummy/download/production/' + suffix)).statusCode, 404)
        }
    } finally {
        await app.close()
        fs.rmSync(dir, { recursive: true, force: true })
    }
})
