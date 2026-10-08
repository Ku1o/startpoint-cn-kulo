const test = require('node:test')
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const http = require('node:http')
const { pack } = require('msgpackr')
const { planLatestEdge, planRange, decodeApiResponse, runProbe } = require('../tools/cdn-http-probe.cjs')

const sha = data => crypto.createHash('sha256').update(data).digest('hex')
const clone = data => JSON.parse(JSON.stringify(data))

function fixture(from = '2.8.9', to = '2.8.10') {
    const bytes = new Map([[`pinball-${from}-${to}-1-fixture-a.zip`, Buffer.from('first shared archive')],
        [`pinball-${from}-${to}-2-fixture-b.zip`, Buffer.from('second shared archive')]])
    const integrity = [...bytes].map(([name, data]) => ({ name, size: data.length, sha256: sha(data) }))
    const patch = (id, files) => ({ id, type: 'patch', enabled: true, depends_on: from,
        version: to, archive: files[0].name, chain: files.map(x => x.name),
        archive_size: files.reduce((n, x) => n + x.size, 0), archive_integrity: files })
    const manifest = { cdn_version: to, patches: [
        { ...patch('history', [integrity[0]]), depends_on: '1.0.0', version: '1.0.1' },
        patch('latest-a', [integrity[0]]), patch('latest-b', [integrity[1]]),
        { ...patch('disabled-future', [integrity[0]]), enabled: false, version: '99.0.0' },
        { ...patch('non-patch-future', [integrity[0]]), type: 'snapshot', version: '100.0.0' },
    ] }
    return { from, to, bytes, integrity, manifest }
}

test('plans numeric versions and merges only enabled records on the highest edge', () => {
    for (const [from, to] of [['2.8.9', '2.8.10'], ['19.0.99', '19.1.0']]) {
        const f = fixture(from, to)
        const plan = planLatestEdge(f.manifest)
        assert.equal(plan.from, from)
        assert.equal(plan.to, to)
        assert.deepEqual([...plan.patchIds].sort(), ['latest-a', 'latest-b'])
        assert.deepEqual([...plan.archives].sort((a, b) => a.name.localeCompare(b.name)), f.integrity)
    }
})

test('rejects missing integrity and conflicting metadata on a shared archive', () => {
    const missing = fixture().manifest
    missing.patches[1].archive_integrity = []
    assert.throws(() => planLatestEdge(missing))
    for (const change of [{ sha256: '0'.repeat(64) }, { size: 999 }]) {
        const f = fixture()
        const duplicate = clone(f.manifest.patches[1])
        duplicate.id = 'conflicting-part'
        Object.assign(duplicate.archive_integrity[0], change)
        f.manifest.patches.push(duplicate)
        assert.throws(() => planLatestEdge(f.manifest))
    }
})

function rangeFixture() {
    const f = fixture()
    f.from = '2.8.8'
    const name = 'pinball-2.8.8-2.8.9-1-range-fixture.zip'
    const bytes = Buffer.from('earlier edge inside the selected range')
    f.bytes.set(name, bytes)
    f.manifest.patches.unshift({ id: 'selected-earlier', type: 'patch', enabled: true,
        depends_on: f.from, version: '2.8.9', archive: name, chain: [name],
        archive_integrity: [{ name, size: bytes.length, sha256: sha(bytes) }] })
    return f
}

test('plans only the explicit contiguous baseline-to-target range', () => {
    const f = rangeFixture()
    const plan = planRange(f.manifest, f.from)
    assert.deepEqual(plan.edges.map(edge => [edge.from, edge.to]), [['2.8.8', '2.8.9'], ['2.8.9', '2.8.10']])
    assert.equal(plan.archives.length, 3)
    assert.ok(!plan.patchIds.includes('history'))
    assert.equal(planLatestEdge(f.manifest).archives.length, 2)
    assert.throws(() => planRange(f.manifest, '2.8.7'), /not contiguous/)
})

test('decodes JSON and Base64 MessagePack API responses', () => {
    const body = { data_headers: { asset_update: true }, data: { diff: [], info: { target_asset_version: '8.0.1' } } }
    assert.deepEqual(decodeApiResponse(Buffer.from(JSON.stringify(body))), body)
    assert.deepEqual(decodeApiResponse(Buffer.from(pack(body).toString('base64'))), body)
    assert.throws(() => decodeApiResponse(Buffer.from('invalid response')))
})

async function withServer(t, f, alter = () => {}, corrupt = false) {
    const repoRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-cdn-probe-test-'))
    const active = path.join(repoRoot, 'assets', 'asset-patch', 'active')
    fs.mkdirSync(active, { recursive: true })
    for (const [name, data] of f.bytes) fs.writeFileSync(path.join(active, name), data)
    const token = 'fixture-admission-secret'
    const requests = []
    const failures = []
    const server = http.createServer(async (req, res) => {
        res.setHeader('Connection', 'close')
        try {
            requests.push({ method: req.method, url: req.url, headers: { ...req.headers } })
            if (req.url === '/api/index.php/asset/get_path') {
                assert.equal(req.method, 'POST')
                assert.equal(req.headers.res_ver, f.from)
                assert.equal(req.headers['x-sp-admission'], token)
                assert.match(req.headers.device, /^(android|ios)$/i)
                for await (const _ of req) { /* Drain the request without credentials or database access. */ }
                const body = { data_headers: { asset_update: true }, data: {
                    info: { target_asset_version: f.to, client_asset_version: f.from }, full: { archive: [] },
                    diff: [{ original_version: f.from, version: f.to, archive: f.integrity.map(x => ({
                        location: `http://unrelated.invalid/patch/cn/asset-patch/active/${x.name}`, size: x.size,
                    })) }],
                } }
                alter(body)
                const raw = /^ios$/i.test(req.headers.device)
                    ? pack(body).toString('base64') : JSON.stringify(body)
                res.writeHead(200); res.end(raw)
                return
            }
            assert.equal(req.method, 'GET')
            const name = req.url.split('/').at(-1)
            assert.equal(req.url, `/patch/cn/asset-patch/active/${name}`)
            assert.ok(f.bytes.has(name), 'Historical or unexpected archive downloaded')
            let raw = Buffer.from(f.bytes.get(name))
            if (corrupt === 'truncated') raw = raw.subarray(0, raw.length - 1)
            else if (corrupt) raw[0] ^= 1
            res.writeHead(200)
            // Deliberately deliver multiple chunks to exercise the streamed size/hash check.
            res.write(raw.subarray(0, 3)); setImmediate(() => res.end(raw.subarray(3)))
        } catch (err) {
            failures.push(err)
            res.writeHead(500); res.end('fixture assertion failed')
        }
    })
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    t.after(async () => {
        server.closeAllConnections()
        await new Promise(resolve => server.close(resolve))
        const resolved = fs.realpathSync(repoRoot)
        assert.equal(path.dirname(resolved), fs.realpathSync(os.tmpdir()))
        assert.ok(path.basename(resolved).startsWith('starpoint-cdn-probe-test-'))
        fs.rmSync(resolved, { recursive: true })
        assert.deepEqual(failures, [])
    })
    return { repoRoot, manifest: f.manifest, baseUrl: `http://127.0.0.1:${server.address().port}`,
        timeoutMs: 2000, admissionToken: token, requests, token }
}

test('probes both platforms, remaps advertised hosts, and downloads each shared archive once', async t => {
    const f = fixture('31.4.9', '31.4.10')
    const options = await withServer(t, f)
    const result = await runProbe({ ...options, download: true })
    assert.equal(result.status, 'passed')
    assert.equal(result.from, f.from)
    assert.equal(result.to, f.to)
    for (const platform of ['android', 'ios']) {
        assert.equal(result.platforms[platform].target, f.to)
        assert.equal(result.platforms[platform].archives, 2)
    }
    assert.equal(result.archiveDownloads, 2)
    assert.deepEqual([...result.downloads].sort((a, b) => a.name.localeCompare(b.name)), f.integrity)
    assert.equal(options.requests.filter(x => x.method === 'POST').length, 2)
    assert.equal(options.requests.filter(x => x.method === 'GET').length, 2)
    assert.ok(!JSON.stringify(result).includes(options.token), 'Admission token leaked into result')
})

test('default metadata mode only requests the two platform lists and never downloads ZIPs', async t => {
    const f = fixture()
    const options = await withServer(t, f)
    const result = await runProbe(options)
    assert.equal(result.status, 'passed')
    assert.equal(result.from, f.from)
    assert.equal(result.to, f.to)
    for (const platform of ['android', 'ios']) {
        assert.equal(result.platforms[platform].target, f.to)
        assert.equal(result.platforms[platform].archives, 2)
    }
    assert.deepEqual(result.downloads, [])
    assert.equal(result.archiveDownloads, 0)
    assert.deepEqual(options.requests.map(x => x.method), ['POST', 'POST'])
    assert.ok(!JSON.stringify(result).includes(options.token), 'Admission token leaked into result')
})

test('multiple selected versions use two platform requests with no ZIP downloads', async t => {
    const f = rangeFixture()
    const plan = planRange(f.manifest, f.from)
    const options = await withServer(t, f, body => {
        body.data.diff = plan.edges.map(edge => ({ original_version: edge.from, version: edge.to,
            archive: edge.archives.map(a => ({ location: `http://unrelated.invalid/patch/cn/asset-patch/active/${a.name}`, size: a.size })) }))
    })
    const result = await runProbe({ ...options, fromVersion: f.from })
    assert.equal(result.from, f.from)
    assert.equal(result.to, f.to)
    assert.equal(result.platforms.android.archives, 3)
    assert.equal(result.platforms.ios.archives, 3)
    assert.equal(result.archiveDownloads, 0)
    assert.equal(result.apiRequests, 2)
    assert.deepEqual(options.requests.map(req => req.method), ['POST', 'POST'])
})

for (const [name, alter, expected] of [
    ['old target', body => { body.data.info.target_asset_version = '1.0.1' }, /target differs/],
    ['historical edge mixed in', body => { body.data.diff.push({ original_version: '1.0.0', version: '1.0.1', archive: [] }) }, /historical or missing/],
    ['missing archive', body => { body.data.diff[0].archive.pop() }, /archive count/],
    ['non-active download path', body => { body.data.diff[0].archive[0].location = 'http://unrelated.invalid/patch/cn/archive-common-diff/part-a.zip' }, /archive path/],
]) {
    test(`rejects ${name}`, async t => {
        const options = await withServer(t, fixture(), alter)
        await assert.rejects(runProbe(options), expected)
        assert.equal(options.requests.filter(x => x.method === 'GET').length, 0)
    })
}

test('rejects wrong streamed hash even when archive size is correct', async t => {
    const options = await withServer(t, fixture(), () => {}, true)
    await assert.rejects(runProbe({ ...options, download: true }), /size or hash mismatch/)
})

test('rejects a truncated streamed archive', async t => {
    const options = await withServer(t, fixture(), () => {}, 'truncated')
    await assert.rejects(runProbe({ ...options, download: true }), /size or hash mismatch/)
})
