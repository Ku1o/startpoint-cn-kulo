const test = require('node:test')
const assert = require('node:assert/strict')
const Fastify = require('fastify')
const http = require('node:http')
const net = require('node:net')
const { setTimeout: delay, setImmediate: tick } = require('node:timers/promises')
const { installRequestDiagnostics, setRequestOutcome, measureResponseEncoding } = require('../out/lib/request-diagnostics')

test('reports status, bounded reasons and encoding separately without retaining payloads or URLs', async () => {
    const app = Fastify()
    const monitor = installRequestDiagnostics(app)
    app.addHook('onSend', (req, _reply, payload) => measureResponseEncoding(req, async () => { await delay(20); return payload }))
    app.get('/ok/:id', async request => { setRequestOutcome(request, 'rush_same_folder'); return { ok: true } })
    app.get('/bad', async () => { throw Object.assign(new Error('secret-body'), { code: 'SQLITE_CONSTRAINT_FOREIGNKEY' }) })
    try {
        await app.inject('/ok/private-player?token=secret-token')
        await app.inject('/bad')
        const { summary, routes } = monitor.drain()
        assert.equal(summary.n, 2)
        assert.deepEqual(summary.statuses, { 200: 1, 500: 1 })
        assert.equal(summary.outcomes.SQLITE_CONSTRAINT_FOREIGNKEY, 1)
        assert.equal(summary.outcomes.rush_same_folder, 1)
        const ok = summary.top.find(row => row.route === 'GET /ok/:id')
        assert.ok(ok.stages.customEncoding.avgMs >= 10)
        assert.ok(ok.responseBytes > 0)
        assert.ok(ok.p99UpperMs >= ok.maxMs)
        assert.equal(summary.failures.length, 1)
        assert.equal(summary.slow.length, 1)
        assert.doesNotMatch(JSON.stringify({ summary, routes }), /secret|private-player/)
        assert.equal(monitor.drain().summary.n, 0)
        assert.equal(monitor.drain().summary.p99UpperMs, 0)
    } finally { await app.close() }
})

test('unmatched traffic and large route sets have fixed cardinality and bounded slow samples', async () => {
    const app = Fastify()
    const monitor = installRequestDiagnostics(app)
    for (let i = 0; i < 300; i++) app.get(`/route-${i}`, async () => { throw new Error('private error') })
    try {
        for (let i = 0; i < 300; i++) await app.inject(`/route-${i}`)
        for (let i = 0; i < 80; i++) await app.inject(`/unknown-${i}?private=yes`)
        const { summary, routes } = monitor.drain()
        assert.equal(summary.n, 380)
        assert.equal(summary.statuses['500'], 300)
        assert.equal(summary.statuses['404'], 80)
        assert.equal(routes.length, 256)
        assert.ok(routes.some(([key]) => key === '<overflow>'))
        assert.equal(summary.slow.length, 5)
        assert.equal(summary.omittedSlowSamples, 295)
        assert.equal(summary.outcomes.unclassified_error, 300)
        assert.doesNotMatch(JSON.stringify(summary), /unknown-\d|private/)
    } finally { await app.close() }
})

test('real delayed request bodies are measured before application execution', async () => {
    const app = Fastify()
    const monitor = installRequestDiagnostics(app)
    app.post('/body', async () => { await delay(25); return { ok: true } })
    await app.listen({ port: 0, host: '127.0.0.1' })
    try {
        await new Promise((resolve, reject) => {
            const request = http.request({ host: '127.0.0.1', port: app.server.address().port, path: '/body', method: 'POST',
                headers: { 'content-type': 'application/json', 'content-length': 2 } }, response => {
                response.resume(); response.on('end', resolve)
            })
            request.on('error', reject)
            request.flushHeaders()
            setTimeout(() => request.end('{}'), 50)
        })
        await tick()
        const row = monitor.drain().summary.top[0]
        assert.ok(row.stages.receiveParse.avgMs >= 25)
        assert.ok(row.stages.application.avgMs >= 15)
        assert.equal(row.statuses['200'], 1)
    } finally { await app.close() }
})

test('an aborted request is counted once even when both abort and socket-close fire', async () => {
    const app = Fastify()
    const monitor = installRequestDiagnostics(app)
    let received, aborted
    const started = new Promise(resolve => { received = resolve })
    const closed = new Promise(resolve => { aborted = resolve })
    app.addHook('onRequest', (_req, _reply, done) => { received(); done() })
    app.addHook('onRequestAbort', (_req, done) => { aborted(); done() })
    app.post('/body', async () => ({ ok: true }))
    await app.listen({ port: 0, host: '127.0.0.1' })
    const socket = net.connect(app.server.address().port, '127.0.0.1')
    try {
        socket.write('POST /body HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{')
        await started
        socket.destroy()
        await closed
        await tick()
        const summary = monitor.drain().summary
        assert.equal(summary.n, 1)
        assert.equal(summary.aborted, 1)
        assert.deepEqual(summary.statuses, { aborted: 1 })
    } finally { socket.destroy(); await app.close() }
})

test('socket timeout remains distinct from abort and late handler completion', async () => {
    const app = Fastify({ connectionTimeout: 40 })
    const monitor = installRequestDiagnostics(app)
    app.get('/late', async () => { await delay(150); return { ok: true } })
    await app.listen({ port: 0, host: '127.0.0.1' })
    try {
        await new Promise((resolve, reject) => {
            const request = http.get(`http://127.0.0.1:${app.server.address().port}/late`, response => {
                response.resume(); reject(new Error('Expected socket timeout'))
            })
            request.on('error', error => error.code === 'ECONNRESET' ? resolve() : reject(error))
        })
        await delay(170)
        const summary = monitor.drain().summary
        assert.equal(summary.n, 1)
        assert.equal(summary.timeouts, 1)
        assert.equal(summary.aborted, 0)
        assert.deepEqual(summary.statuses, { timeout: 1 })
    } finally { await app.close() }
})

test('compact monitoring preserves plugin outcomes and custom encoding time', async () => {
    const app = Fastify()
    const monitor = installRequestDiagnostics(app, { detailed: false })
    await app.register(async child => {
        child.get('/plugin', async request => {
            setRequestOutcome(request, 'rush_selected')
            return measureResponseEncoding(request, async () => {
                await delay(15)
                return 'encoded'
            })
        })
    })
    try {
        assert.equal((await app.inject('/plugin')).statusCode, 200)
        const row = monitor.drain().summary.top[0]
        assert.equal(row.outcomes.rush_selected, 1)
        assert.ok(row.stages.customEncoding.avgMs >= 10)
        assert.ok(row.responseBytes > 0)
    } finally { await app.close() }
})

test('compact monitoring records nonzero duration for delayed aborts', async () => {
    const app = Fastify()
    const monitor = installRequestDiagnostics(app, { detailed: false })
    let received
    const started = new Promise(resolve => { received = resolve })
    app.addHook('onRequest', (_request, _reply, done) => { received(); done() })
    app.post('/compact-abort', async () => ({ ok: true }))
    await app.listen({ port: 0, host: '127.0.0.1' })
    const socket = net.connect(app.server.address().port, '127.0.0.1')
    try {
        socket.write('POST /compact-abort HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{')
        await started
        await delay(20)
        socket.destroy()
        await delay(20)
        const summary = monitor.drain().summary
        assert.equal(summary.aborted, 1)
        assert.ok(summary.maxMs >= 10)
    } finally { socket.destroy(); await app.close() }
})

test('compact monitoring separates delayed body receive from application work', async () => {
    const app = Fastify()
    const monitor = installRequestDiagnostics(app, { detailed: false, slowMs: 100 })
    app.post('/compact-body', async () => {
        await delay(20)
        return { ok: true }
    })
    await app.listen({ port: 0, host: '127.0.0.1' })
    try {
        const response = new Promise((resolve, reject) => {
            const socket = net.connect(app.server.address().port, '127.0.0.1')
            let raw = ''
            socket.on('data', chunk => { raw += chunk })
            socket.once('error', reject)
            socket.once('end', () => resolve(raw))
            socket.once('connect', async () => {
                socket.write('POST /compact-body HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{\"value\":')
                await delay(120)
                socket.write('1}')
            })
        })
        assert.match(await response, /200 OK/)
        const slow = monitor.drain().summary.slow[0]
        assert.ok(slow.stages.receiveParse >= 100, JSON.stringify(slow))
        assert.ok(slow.stages.application >= 10, JSON.stringify(slow))
    } finally { await app.close() }
})
