const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const vm = require('node:vm')
const { pack, unpack, Packr, Unpackr } = require('msgpackr')
const { gunzipSync, brotliDecompressSync } = require('node:zlib')
const { fixUint32Tags, encodeCnResponse } = require('../out/lib/cn-response-encoding')
const { CnResponseWorkerPool } = require('../out/lib/cn-response-worker-pool')
const { getCnLoadHttpCompressionConfig } = require('../out/lib/cn-load-http-compression')
const { installCnResponseEncoding } = require('../out/lib/cn-response-hook')

const payload = JSON.stringify({ result: 1, data: Array.from({length: 8000}, (_, i) => ({
    id: i + 0x80000000, name: '世界弹射物语', count: 65536 + i, flags: [true, false, null],
})) })
const config = mode => getCnLoadHttpCompressionConfig({ CN_LOAD_HTTP_COMPRESSION: mode })

test('AIR integer conversion preserves nested values and string/binary bytes', () => {
    const input = { values: [0, -1, 255, 256, 65535, 65536, 0x7fffffff, 0x80000000, 0xffffffff],
        text: '测试 CE 你好', nested: { value: 0x80000001 }, binary: Buffer.from([0xce, 0xff, 0, 0xce]) }
    assert.deepEqual(unpack(fixUint32Tags(pack(input))), input)
    assert.equal(fixUint32Tags(Buffer.from([0xce, 0x7f, 0xff, 0xff, 0xff])).toString('hex'), 'd27fffffff')
    assert.equal(fixUint32Tags(Buffer.from([0xce, 0x80, 0, 0, 0])).toString('hex'), 'cb41e0000000000000')
    const string = pack(payload)
    assert.equal(fixUint32Tags(string), string) // Large opaque payload needs no byte-by-byte copy.
})

test('MessagePack extension type bytes do not misalign the following integer', () => {
    const packr = new Packr({ useRecords: false, moreTypes: true })
    const unpackr = new Unpackr({ moreTypes: true })
    const input = [new Date('2026-09-24T00:00:00Z'), 0xffffffff, new Set([65536])]
    assert.deepEqual(unpackr.unpack(fixUint32Tags(packr.pack(input))), input)
    for (const [tag, length] of [[0xd4, 1], [0xd5, 2], [0xd6, 4], [0xd7, 8], [0xd8, 16]]) {
        const extension = Buffer.concat([Buffer.from([tag, 42]), Buffer.alloc(length, 0xce)])
        const input = Buffer.concat([extension, Buffer.from([0xce, 0x80, 0, 0, 0])])
        const output = fixUint32Tags(input)
        assert.deepEqual(output.subarray(0, extension.length), extension)
        assert.equal(output[extension.length], 0xcb)
    }
    assert.throws(() => fixUint32Tags(Buffer.from([0xdb, 0, 0, 0, 5])), /Truncated/)
})

test('worker output matches local output under parallel requests and encoding negotiation', async () => {
    const pool = new CnResponseWorkerPool({ size: 2, minimumLength: 0 })
    try {
        const inputs = ['off', 'observe', 'gzip', 'br', 'auto', 'auto'].map((mode, i) => ({
            payload: payload + i, compression: { config: config(mode), acceptEncoding: i === 5 ? 'gzip;q=0, br;q=0' : 'gzip, br' },
        }))
        const expected = await Promise.all(inputs.map(encodeCnResponse))
        const actual = await Promise.all(inputs.map(input => pool.encode(input)))
        for (let i = 0; i < inputs.length; i++) {
            assert.deepEqual(actual[i].body, expected[i].body)
            assert.deepEqual(actual[i].compression, expected[i].compression)
            let body = actual[i].body
            if (actual[i].compression.encoding === 'gzip') body = gunzipSync(body).toString('ascii')
            if (actual[i].compression.encoding === 'br') body = brotliDecompressSync(body).toString('ascii')
            assert.equal(unpack(Buffer.from(body, 'base64')), inputs[i].payload)
        }
        assert.equal(pool.snapshot().completed, inputs.length)
        assert.equal(pool.snapshot().retainedBytes, 0)
        assert.equal(pool.snapshot().fallback, 0)
    } finally { await pool.close() }
})

test('saturation, crashes, timeouts and shutdown fall back without retained jobs', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'response-worker-faults-'))
    const crashed = path.join(dir, 'crash.cjs'), stalled = path.join(dir, 'stall.cjs')
    fs.writeFileSync(crashed, 'process.exit(7)')
    fs.writeFileSync(stalled, 'require("node:worker_threads").parentPort.on("message", () => {})')
    try {
        for (const options of [
            { workerPath: crashed },
            { workerPath: stalled, timeoutMs: 80 },
            { workerPath: stalled, timeoutMs: 80, maxPending: 1 },
            { maxPendingBytes: 1 },
        ]) {
            const pool = new CnResponseWorkerPool({ size: 1, minimumLength: 0, ...options })
            try {
                const results = await Promise.all([pool.encode({payload}), pool.encode({payload: payload + '2'})])
                assert.equal(unpack(Buffer.from(results[0].body, 'base64')), payload)
                assert.equal(unpack(Buffer.from(results[1].body, 'base64')), payload + '2')
                assert.equal(pool.snapshot().fallback, 2)
                assert.equal(pool.snapshot().retainedBytes, 0)
                assert.equal(pool.snapshot().pending, 0)
            } finally { await pool.close() }
        }
        const pool = new CnResponseWorkerPool({ size: 1, minimumLength: 0, workerPath: stalled })
        const pending = pool.encode({payload})
        await pool.close()
        assert.equal(unpack(Buffer.from((await pending).body, 'base64')), payload)
        assert.equal(pool.snapshot().retainedBytes, 0)
    } finally {
        assert.equal(path.dirname(fs.realpathSync(dir)), fs.realpathSync(os.tmpdir()))
        fs.rmSync(dir, {recursive: true})
    }
})

test('optimized encoder is byte-identical to a supplied legacy source for JSON responses', {skip: !process.env.PERF_BASELINE_ROOT}, async () => {
    const source = fs.readFileSync(path.join(process.env.PERF_BASELINE_ROOT, 'src/cn-server.ts'), 'utf8')
    const start = source.indexOf('function fixUint32Tags('), end = source.indexOf('\nfunction appendVaryAcceptEncoding', start)
    const ts = require('typescript')
    const code = ts.transpileModule(source.slice(start, end), {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText
    const legacy = vm.runInNewContext(code + '\nfixUint32Tags', {Buffer})
    for (const value of [payload, {numbers: [65536, 0x80000000, 0xffffffff], strings: ['甲', '乙'], nested: [true, {a: null}]}]) {
        assert.deepEqual(fixUint32Tags(pack(value)), legacy(pack(value)))
        assert.equal((await encodeCnResponse({payload: value})).body, legacy(pack(value)).toString('base64'))
    }
})

test('production HTTP hook keeps load headers, binary body and ordinary JSON responses correct', async () => {
    const Fastify = require('fastify')
    const app = Fastify()
    const pool = new CnResponseWorkerPool({ size: 2, minimumLength: 0 })
    installCnResponseEncoding(app, { pool, compression: config('auto') })
    app.get('/load', async (_, reply) => reply.type('application/x-msgpack').header('vary', 'Origin').send(payload))
    app.get('/other', async (_, reply) => reply.type('application/x-msgpack').send(payload))
    app.get('/plain', async () => ({ok: true}))
    try {
        const gzip = await app.inject({url: '/load?test=1', headers: {'accept-encoding': 'gzip'}})
        assert.equal(gzip.statusCode, 200)
        assert.equal(gzip.headers['content-encoding'], 'gzip')
        assert.equal(gzip.headers.vary, 'Origin, Accept-Encoding')
        assert.equal(unpack(Buffer.from(gunzipSync(gzip.rawPayload).toString('ascii'), 'base64')), payload)
        const identity = await app.inject('/load')
        assert.equal(identity.headers['content-encoding'], undefined)
        assert.equal(unpack(Buffer.from(identity.body, 'base64')), payload)
        const ordinary = await app.inject({url: '/other', headers: {'accept-encoding': 'br'}})
        assert.equal(ordinary.headers['content-encoding'], undefined)
        assert.equal(unpack(Buffer.from(ordinary.body, 'base64')), payload)
        assert.deepEqual((await app.inject('/plain')).json(), {ok: true})
    } finally { await app.close() }
    assert.equal(pool.snapshot().workers, 0)
})
