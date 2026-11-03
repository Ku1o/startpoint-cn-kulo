const test = require('node:test')
const assert = require('node:assert/strict')
const { createSlowOperationDiagnostics } = require('../out/lib/slow-operation-diagnostics')

function fixture(enabled = true) {
    let elapsed = 0
    let cpuUsed = 0
    let cpuReads = 0
    const epoch = Date.UTC(2026, 10, 3, 10, 54)
    const diagnostics = createSlowOperationDiagnostics({
        enabled, thresholdMs: 2,
        clock: {
            now: () => elapsed,
            epoch: () => epoch + elapsed,
            cpu: () => {
                cpuReads++
                return { user: cpuUsed, system: 0 }
            },
        },
    })
    return {
        ...diagnostics,
        advance(wallMs, cpuMs = 0) {
            elapsed += wallMs
            cpuUsed += cpuMs * 1000
        },
        cpuReads: () => cpuReads,
    }
}

test('slow synchronous work preserves return and exception identity and records bounded metadata', () => {
    const d = fixture()
    const value = { private: 'private payload' }
    const failure = new Error('private error text')
    d.withContext({ domain: 'admin', operation: 'inspect:private account' }, () => {
        assert.equal(d.measure('db.body', () => {
            d.advance(5, 1.5)
            return value
        }), value)
        assert.throws(() => d.measure('sensitive path / example', () => {
            d.advance(7, 2)
            throw failure
        }), error => error === failure)
        d.measure('under.threshold', () => d.advance(1))
    })
    assert.deepEqual(d.drain(), {
        count: 2,
        omitted: 0,
        maxWallMs: 7,
        observerErrors: 0,
        samples: [
            {
                domain: 'admin', operation: 'inspect', phase: 'db.body', kind: 'sync',
                startedAt: '2026-11-03T10:54:00.000Z', endedAt: '2026-11-03T10:54:00.005Z',
                wallMs: 5, threadCpuMs: 1.5, failed: false,
            },
            {
                domain: 'admin', operation: 'inspect', phase: 'unknown', kind: 'sync',
                startedAt: '2026-11-03T10:54:00.005Z', endedAt: '2026-11-03T10:54:00.012Z',
                wallMs: 7, threadCpuMs: 2, failed: true,
            },
        ],
    })
})

test('interleaved async operations retain their own context and wait phases omit CPU', async () => {
    const d = fixture()
    let releaseFirst
    const firstGate = new Promise(resolve => { releaseFirst = resolve })
    let releaseSecond
    const secondGate = new Promise(resolve => { releaseSecond = resolve })
    const first = d.withContext({ domain: 'player', operation: 'first' }, async () => {
        const wait = d.begin('queue.wait', 'wait')
        await firstGate
        d.end(wait)
        d.measure('db.body', () => d.advance(3, 1))
    })
    const second = d.withContext({ domain: 'mail', operation: 'second' }, async () => {
        const wait = d.begin('queue.wait', 'wait')
        await secondGate
        d.end(wait, true)
        d.measure('db.body', () => d.advance(4, 2))
    })
    assert.equal(d.cpuReads(), 0)
    d.advance(5, 3)
    releaseSecond()
    await second
    releaseFirst()
    await first
    const outside = d.begin('outside', 'wait')
    d.advance(2)
    d.end(outside)
    const { samples } = d.drain()
    const field = (operation, phase) => samples.find(sample => sample.operation === operation && sample.phase === phase)
    assert.equal(samples.length, 5)
    assert.equal(field('first', 'queue.wait').wallMs, 9)
    assert.equal(field('first', 'queue.wait').threadCpuMs, null)
    assert.equal(field('second', 'queue.wait').wallMs, 5)
    assert.equal(field('second', 'queue.wait').failed, true)
    assert.equal(field('second', 'queue.wait').threadCpuMs, null)
    assert.equal(field('first', 'db.body').domain, 'player')
    assert.equal(field('first', 'db.body').threadCpuMs, 1)
    assert.equal(field('second', 'db.body').domain, 'mail')
    assert.equal(field('second', 'db.body').threadCpuMs, 2)
    assert.equal(field('unscoped', 'outside').domain, 'unscoped')
})

test('samples retain onset plus longest later events, and reset on drain', () => {
    const d = fixture()
    for (let index = 1; index <= 30; index++) {
        const token = d.begin('queue.wait', 'wait', { domain: 'x'.repeat(81), operation: 'fixture:' + index })
        d.advance(index + 1)
        d.end(token)
    }
    const result = d.drain()
    assert.equal(result.count, 30)
    assert.equal(result.omitted, 14)
    assert.equal(result.maxWallMs, 31)
    assert.equal(result.observerErrors, 0)
    assert.deepEqual(result.samples.map(sample => sample.wallMs), [
        2, 3, 4, 5, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
    ])
    assert.ok(result.samples.every(sample => sample.domain === 'unknown' && sample.operation === 'fixture'))
    assert.deepEqual(d.drain(), { count: 0, omitted: 0, maxWallMs: 0, observerErrors: 0, samples: [] })
})

test('disabled diagnostics preserve execution without sampling', () => {
    const d = fixture(false)
    assert.equal(d.withContext({ domain: 'player', operation: 'fixture' }, () =>
        d.measure('db.body', () => {
            d.advance(10, 2)
            return 'result'
        })
    ), 'result')
    assert.equal(d.cpuReads(), 0)
    assert.deepEqual(d.drain(), { count: 0, omitted: 0, maxWallMs: 0, observerErrors: 0, samples: [] })
})

test('observer failures leave business results and exceptions intact and allow sampling to recover', () => {
    let elapsed = 0
    let failClock = false
    let failCpu = false
    const observerFailure = new Error('fixture observer error')
    const businessFailure = new Error('fixture business error')
    const result = {}
    const d = createSlowOperationDiagnostics({
        enabled: true, thresholdMs: 1,
        clock: {
            now: () => {
                if (failClock) throw observerFailure
                return elapsed
            },
            epoch: () => elapsed,
            cpu: () => {
                if (failCpu) throw observerFailure
                return { user: 0, system: 0 }
            },
        },
    })

    failClock = true
    assert.equal(d.measure('begin.clock', () => result), result)
    failClock = false
    failCpu = true
    assert.throws(() => d.measure('begin.cpu', () => { throw businessFailure }), error => error === businessFailure)
    failCpu = false
    assert.throws(() => d.measure('end.clock', () => {
        failClock = true
        throw businessFailure
    }), error => error === businessFailure)
    failClock = false
    assert.equal(d.measure('end.cpu', () => {
        failCpu = true
        elapsed += 5
        return result
    }), result)

    failCpu = false
    d.measure('recovered', () => { elapsed += 5 })
    const summary = d.drain()
    assert.equal(summary.observerErrors, 4)
    assert.equal(summary.count, 1)
    assert.deepEqual(summary.samples.map(sample => sample.phase), ['recovered'])
    assert.deepEqual(d.drain(), { count: 0, omitted: 0, maxWallMs: 0, observerErrors: 0, samples: [] })
})
