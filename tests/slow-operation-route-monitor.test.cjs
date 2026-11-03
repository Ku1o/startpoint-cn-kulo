const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

// Each mode loads the production singleton with a fresh environment.
for (const enabled of [true, false]) {
    test('Fastify route monitor ' + (enabled ? 'flushes and resets slow samples' : 'skips disabled sampling and timer'), () => {
        const child = spawnSync(process.execPath, ['-e', `
            const assert = require('node:assert/strict')
            const Fastify = require('fastify')
            const { installRoutePerformanceMonitor } = require('./out/lib/route-performance')
            const { measureSlowOperation, drainSlowOperationDiagnostics } = require('./out/lib/slow-operation-diagnostics')
            const enabled = process.env.ROUTE_PERF_SUMMARY === 'true'
            const app = Fastify({ logger: false })
            const originalSetInterval = global.setInterval
            const originalWarn = console.warn
            const timers = []
            const warnings = []
            const slowLogs = () => warnings.filter(line => line.startsWith('[SLOW-OPERATIONS] '))
            const configLogs = () => warnings.filter(line => line.startsWith('[SLOW-OPERATIONS-CONFIG] '))
            global.setInterval = callback => {
                timers.push(callback)
                return { unref() {} }
            }
            console.warn = line => warnings.push(line)
            try {
                installRoutePerformanceMonitor(app)
            } finally {
                global.setInterval = originalSetInterval
            }
            app.get('/fixture', async () => measureSlowOperation('route.fixture', () => {
                Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 5)
                return { fixture: true }
            }))
            ;(async () => {
                try {
                    const reply = await app.inject({ method: 'GET', url: '/fixture' })
                    assert.equal(reply.statusCode, 200)
                    assert.deepEqual(reply.json(), { fixture: true })
                    if (!enabled) {
                        assert.equal(timers.length, 0)
                        assert.equal(configLogs().length, 0)
                        assert.equal(slowLogs().length, 0)
                        assert.deepEqual(drainSlowOperationDiagnostics(), {
                            count: 0, omitted: 0, maxWallMs: 0, observerErrors: 0, samples: [],
                        })
                        return
                    }
                    assert.equal(timers.length, 1)
                    assert.equal(configLogs().length, 1)
                    const config = JSON.parse(configLogs()[0].slice('[SLOW-OPERATIONS-CONFIG] '.length))
                    assert.equal(config.enabled, true)
                    assert.equal(config.thresholdMs, 1)
                    assert.equal(config.maxSamples, 16)
                    assert.equal(slowLogs().length, 0)
                    timers[0]()
                    assert.equal(slowLogs().length, 1)
                    const flushed = JSON.parse(slowLogs()[0].slice('[SLOW-OPERATIONS] '.length))
                    assert.equal(flushed.count, 1)
                    assert.equal(flushed.observerErrors, 0)
                    assert.equal(flushed.samples[0].phase, 'route.fixture')
                    timers[0]()
                    assert.equal(slowLogs().length, 1)
                    assert.equal(drainSlowOperationDiagnostics().count, 0)
                } finally {
                    console.warn = originalWarn
                    await app.close()
                }
            })().catch(error => { console.error(error); process.exitCode = 1 })
        `], {
            cwd: path.resolve(__dirname, '..'),
            env: {
                ...process.env,
                ROUTE_PERF_SUMMARY: String(enabled),
                SLOW_OPERATION_DIAGNOSTICS: 'true',
                SLOW_OPERATION_MS: '1',
                MEMORY_DIAGNOSTICS: 'false',
                SQLITE_DIAGNOSTICS: 'false',
            },
            encoding: 'utf8',
            timeout: 10000,
        })
        assert.ifError(child.error)
        assert.equal(child.status, 0, child.stdout + child.stderr)
    })
}
