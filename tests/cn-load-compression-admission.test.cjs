const test = require('node:test')
const assert = require('node:assert/strict')
const http = require('node:http')
const zlib = require('node:zlib')
const Fastify = require('fastify')
const { unpack } = require('msgpackr')
const {
    acceptsHttpEncoding,
    compressCnLoadHttpBody,
    getCnLoadHttpCompressionConfig,
    getCnLoadCompressionStats,
} = require('../out/lib/cn-load-http-compression')
const { CnResponseWorkerPool } = require('../out/lib/cn-response-worker-pool')
const { installCnResponseEncoding } = require('../out/lib/cn-response-hook')

function configuration(concurrent = 1, bytes = 1024) {
    return getCnLoadHttpCompressionConfig({
        CN_LOAD_HTTP_COMPRESSION: 'gzip',
        CN_LOAD_HTTP_COMPRESSION_MIN_BYTES: '0',
        CN_LOAD_HTTP_COMPRESSION_MAX_CONCURRENT: String(concurrent),
        CN_LOAD_HTTP_COMPRESSION_MAX_INPUT_BYTES: String(bytes),
    })
}

function holdGzip(t) {
    const jobs = []
    let nextSubmission
    t.mock.method(zlib, 'gzip', (input, _options, callback) => {
        jobs.push({ input, callback })
        nextSubmission?.()
        nextSubmission = undefined
    })
    function finish(error = null) {
        const { input, callback } = jobs.shift()
        callback(error, error ? undefined : zlib.gzipSync(input))
    }
    function waitForSubmission() {
        if (jobs.length) return Promise.resolve()
        return new Promise(resolve => { nextSubmission = resolve })
    }
    return { jobs, finish, waitForSubmission }
}

test('gzip checks concurrent count and input bytes before submission and recovers after native completion', async t => {
    const { jobs, finish } = holdGzip(t)
    const config = configuration(2, 10)
    const before = getCnLoadCompressionStats()
    assert.equal(config.maxConcurrent, 2)
    assert.equal(config.maxInputBytes, 10)
    const first = compressCnLoadHttpBody('abcdef', 'gzip', config)
    const blockedByBytes = await compressCnLoadHttpBody('12345', 'gzip', config)
    assert.equal(blockedByBytes.reason, 'capacity')
    assert.equal(blockedByBytes.encoding, null)
    assert.equal(blockedByBytes.body.toString(), '12345')
    const second = compressCnLoadHttpBody(Buffer.from('xy'), 'gzip', config)
    const blockedByCount = await compressCnLoadHttpBody('z', 'gzip, identity;q=0', config)
    assert.equal(blockedByCount.reason, 'capacity')
    assert.equal(blockedByCount.statusCode, 503)
    assert.equal(blockedByCount.body.length, 0)
    assert.equal(jobs.length, 2)
    let stats = getCnLoadCompressionStats()
    assert.equal(stats.active, 2)
    assert.equal(stats.inputBytes, 8)
    assert.equal(stats.rejected - before.rejected, 2)

    finish()
    assert.equal(zlib.gunzipSync((await first).body).toString(), 'abcdef')
    stats = getCnLoadCompressionStats()
    assert.equal(stats.active, 1)
    assert.equal(stats.inputBytes, 2)
    const resumed = compressCnLoadHttpBody('next', 'gzip', config)
    assert.equal(jobs.length, 2)
    finish()
    finish()
    assert.equal(zlib.gunzipSync((await second).body).toString(), 'xy')
    assert.equal(zlib.gunzipSync((await resumed).body).toString(), 'next')
    const oversized = await compressCnLoadHttpBody('12345678901', 'gzip', config)
    assert.equal(oversized.reason, 'capacity')
    assert.equal(oversized.body.toString(), '12345678901')
    assert.equal(jobs.length, 0)
    assert.equal(getCnLoadCompressionStats().active, 0)
    assert.equal(getCnLoadCompressionStats().inputBytes, 0)
})

test('sync zlib throws and async callback errors both release reservations', async t => {
    const before = getCnLoadCompressionStats()
    const config = configuration()
    const syncError = new Error('sync fixture')
    const asyncError = new Error('async fixture')
    t.mock.method(zlib, 'gzip', () => { throw syncError })
    await assert.rejects(compressCnLoadHttpBody('first', 'gzip', config), error => error === syncError)
    assert.equal(getCnLoadCompressionStats().active, 0)
    assert.equal(getCnLoadCompressionStats().inputBytes, 0)
    t.mock.restoreAll()
    const { jobs, finish } = holdGzip(t)
    const pending = compressCnLoadHttpBody('second', 'gzip', config)
    assert.equal(jobs.length, 1)
    assert.equal(getCnLoadCompressionStats().active, 1)
    const failure = assert.rejects(pending, error => error === asyncError)
    finish(asyncError)
    await failure
    assert.equal(getCnLoadCompressionStats().active, 0)
    assert.equal(getCnLoadCompressionStats().inputBytes, 0)
    assert.equal(getCnLoadCompressionStats().failed - before.failed, 2)
    const recovered = compressCnLoadHttpBody('third', 'gzip', config)
    finish()
    assert.equal(zlib.gunzipSync((await recovered).body).toString(), 'third')
})

test('encoding negotiation respects explicit identity and wildcard exclusions and preserves gzip/br bytes', async () => {
    assert.equal(acceptsHttpEncoding(undefined, 'identity'), true)
    assert.equal(acceptsHttpEncoding('gzip', 'identity'), true)
    assert.equal(acceptsHttpEncoding('gzip, identity;q=0', 'identity'), false)
    assert.equal(acceptsHttpEncoding('*;q=0', 'identity'), false)
    assert.equal(acceptsHttpEncoding('*;q=0, identity;q=1', 'identity'), true)
    assert.equal(acceptsHttpEncoding('gzip;q=0, *;q=1', 'gzip'), false)
    const config = configuration()
    const unavailable = await compressCnLoadHttpBody('data', 'gzip;q=0, identity;q=0', config)
    assert.equal(unavailable.statusCode, 406)
    assert.equal(unavailable.body.length, 0)
    const identity = await compressCnLoadHttpBody('data', 'gzip;q=0', config)
    assert.equal(identity.encoding, null)
    assert.equal(identity.body.toString(), 'data')
    const small = await compressCnLoadHttpBody('tiny', 'gzip, identity;q=0', {
        ...config, minimumBytes: 100,
    })
    assert.equal(small.encoding, 'gzip')
    assert.equal(zlib.gunzipSync(small.body).toString(), 'tiny')
    const source = Buffer.from([0, 1, 127, 128, 255])
    for (const [mode, decode] of [['gzip', zlib.gunzipSync], ['br', zlib.brotliDecompressSync]]) {
        const result = await compressCnLoadHttpBody(source, mode + ', *;q=0', { ...config, mode })
        assert.equal(result.encoding, mode)
        assert.deepEqual(decode(result.body), source)
    }
})

test('production onSend shares worker and local compression admission and maps the HTTP response', { timeout: 5000 }, async t => {
    const { jobs, finish, waitForSubmission } = holdGzip(t)
    const config = configuration(1, 32 * 1024)
    const app = Fastify({ logger: false })
    const pool = new CnResponseWorkerPool({ size: 1, minimumObjectBytes: 0 })
    installCnResponseEncoding(app, { compression: config, pool })
    const data = { value: 'admission fixture', repeat: Array(50).fill('repeat') }
    app.get('/fixture/load', async (_request, reply) => reply.header('vary', 'Origin').type('application/x-msgpack').send(data))
    app.get('/fixture/finish', async (_request, reply) => reply.type('application/x-msgpack').send(data))
    const inject = (encoding, url = '/fixture/load') =>
        app.inject({ method: 'GET', url, headers: { 'accept-encoding': encoding } })

    const occupied = pool.encode({ payload: data, compression: { config, acceptEncoding: 'gzip' } })
    try {
        await waitForSubmission()
        assert.equal(jobs.length, 1)
        const identity = await inject('gzip')
        assert.equal(identity.statusCode, 200)
        assert.equal(identity.headers['content-encoding'], undefined)
        assert.equal(Number(identity.headers['content-length']), identity.rawPayload.length)
        assert.deepEqual(identity.headers.vary.split(/,\s*/).sort(), ['Accept-Encoding', 'Origin'])
        assert.deepEqual(unpack(Buffer.from(identity.payload, 'base64')), data)
        assert.equal(pool.snapshot().completedObjects, 1)
        assert.equal(jobs.length, 1)

        const rejected = await inject('gzip, identity;q=0')
        assert.equal(rejected.statusCode, 503)
        assert.equal(String(rejected.headers['retry-after']), '1')
        assert.equal(rejected.headers['content-encoding'], undefined)
        assert.equal(rejected.rawPayload.length, 0)
        assert.equal(Number(rejected.headers['content-length'] ?? 0), 0)
        const unavailable = await inject('gzip;q=0, identity;q=0')
        assert.equal(unavailable.statusCode, 406)
        assert.equal(unavailable.headers['content-encoding'], undefined)
        assert.equal(unavailable.rawPayload.length, 0)
        const finishResponse = await inject('gzip, identity;q=0', '/fixture/finish')
        assert.equal(finishResponse.statusCode, 200)
        assert.equal(finishResponse.headers['content-encoding'], undefined)
        assert.equal(jobs.length, 1)

        finish()
        await occupied
        const compressed = inject('gzip, identity;q=0')
        await waitForSubmission()
        assert.equal(jobs.length, 1)
        finish()
        const response = await compressed
        assert.equal(response.statusCode, 200)
        assert.equal(response.headers['content-encoding'], 'gzip')
        assert.equal(Number(response.headers['content-length']), response.rawPayload.length)
        assert.deepEqual(zlib.gunzipSync(response.rawPayload), identity.rawPayload)

        const failed = inject('gzip, identity;q=0')
        await waitForSubmission()
        finish(new Error('fixture compression error'))
        const failedResponse = await failed
        assert.equal(failedResponse.statusCode, 503)
        assert.equal(String(failedResponse.headers['retry-after']), '1')
        assert.equal(failedResponse.headers['content-encoding'], undefined)
        assert.equal(failedResponse.rawPayload.length, 0)
    } finally {
        while (jobs.length) finish()
        await occupied
        await app.close()
    }
})

test('aborted HTTP request retains its compression reservation until the native callback', { timeout: 5000 }, async t => {
    const { jobs, finish, waitForSubmission } = holdGzip(t)
    const config = configuration(1, 32 * 1024)
    const app = Fastify({ logger: false })
    const pool = new CnResponseWorkerPool({ size: 0 })
    installCnResponseEncoding(app, { compression: config, pool })
    app.get('/fixture/load', async (_request, reply) =>
        reply.type('application/x-msgpack').send({ value: 'disconnect fixture' }))
    await app.listen({ host: '127.0.0.1', port: 0 })
    const request = http.get({
        host: '127.0.0.1',
        port: app.server.address().port,
        path: '/fixture/load',
        headers: { 'accept-encoding': 'gzip' },
    })
    const closed = new Promise(resolve => {
        request.on('error', () => {})
        request.once('close', resolve)
    })
    try {
        await waitForSubmission()
        request.destroy()
        await closed
        assert.equal(jobs.length, 1)
        assert.equal(getCnLoadCompressionStats().active, 1)
        const fallback = await compressCnLoadHttpBody('next', 'gzip', config)
        assert.equal(fallback.reason, 'capacity')
        assert.equal(fallback.encoding, null)
        assert.equal(jobs.length, 1)
        finish()
        // Let the compressor's Promise continuation release the native reservation.
        await new Promise(resolve => setImmediate(resolve))
        assert.equal(getCnLoadCompressionStats().active, 0)
        assert.equal(getCnLoadCompressionStats().inputBytes, 0)
    } finally {
        request.destroy()
        while (jobs.length) finish()
        await app.close()
    }
})
