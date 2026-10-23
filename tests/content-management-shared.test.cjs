'use strict'
require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { ContentManagementSharedReads, ContentSharedReadOversized } = require('../src/lib/content-management-shared')
const { contentManagementReadStatus: queueStatus } = require('../src/lib/content-management-work')
const next = () => new Promise(resolve => setImmediate(resolve))
const fixture = () => {
    const raw = new EventEmitter(), response = new EventEmitter(), headers = {}
    return { request: { raw }, reply: { raw: response, header: (key, value) => { headers[key] = value } }, headers }
}
const read = (manager, browser, key, work) => manager.read(browser.request, browser.reply, key, work)

test('eight browsers share one build; a later request builds afresh with no retained result', async () => {
    const manager = new ContentManagementSharedReads()
    let builds = 0, release
    const barrier = new Promise(resolve => { release = resolve })
    const work = async checkpoint => { builds++; await barrier; await checkpoint(); return '{"rows":[1,2]}' }
    const requests = Array.from({ length: 8 }, () => read(manager, fixture(), 'same-revision-query', work))
    while (!builds) await next()
    assert.equal(builds, 1)
    assert.deepEqual(manager.status(), { flights: 1, subscribers: 8 })
    assert.deepEqual(queueStatus(), { running: 1, waiting: 0, capacity: 3 })
    release(); const values = await Promise.all(requests)
    assert.equal(new Set(values).size, 1)
    assert.deepEqual(manager.status(), { flights: 0, subscribers: 0 })
    assert.equal(await read(manager, fixture(), 'same-revision-query', work), values[0])
    assert.equal(builds, 2)
    const independentlyParsed = values.map(JSON.parse)
    independentlyParsed[0].rows.push(99)
    assert.deepEqual(independentlyParsed[1].rows, [1, 2])
})

test('the first browser disconnecting leaves the other subscriber and build intact', async () => {
    const manager = new ContentManagementSharedReads(), first = fixture(), second = fixture()
    let release
    const barrier = new Promise(resolve => { release = resolve })
    const work = async checkpoint => { await barrier; await checkpoint(); return 'kept' }
    const one = read(manager, first, 'shared', work), two = read(manager, second, 'shared', work)
    const rejected = assert.rejects(one, error => error.statusCode === 499)
    first.request.raw.aborted = true; first.request.raw.emit('aborted')
    await rejected
    assert.equal(first.request.raw.listenerCount('aborted'), 0)
    assert.equal(first.reply.raw.listenerCount('close'), 0)
    assert.deepEqual(manager.status(), { flights: 1, subscribers: 1 })
    release(); assert.equal(await two, 'kept')
    assert.equal(second.request.raw.listenerCount('aborted'), 0)
    assert.equal(second.reply.raw.listenerCount('close'), 0)
    assert.deepEqual(manager.status(), { flights: 0, subscribers: 0 })
})

test('all subscribers disconnecting removes queued work without running it', async () => {
    const manager = new ContentManagementSharedReads(), active = fixture(), queued = fixture()
    let release, queuedRan = false
    const barrier = new Promise(resolve => { release = resolve })
    const one = read(manager, active, 'active', async () => { await barrier; return 'active' })
    const two = read(manager, queued, 'queued', async () => { queuedRan = true; return 'queued' })
    await next()
    assert.equal(queueStatus().waiting, 1)
    const rejected = assert.rejects(two, error => error.statusCode === 499)
    queued.reply.raw.destroyed = true; queued.reply.raw.emit('close')
    await rejected
    assert.equal(queueStatus().waiting, 0)
    release(); await one
    assert.equal(queuedRan, false)
    assert.deepEqual(manager.status(), { flights: 0, subscribers: 0 })
})

test('per-read subscriber admission and distinct-query queue overflow stay bounded', async () => {
    const manager = new ContentManagementSharedReads()
    let release
    const barrier = new Promise(resolve => { release = resolve })
    const work = async () => { await barrier; return 'done' }
    const shared = Array.from({ length: 16 }, () => read(manager, fixture(), 'shared', work))
    const overflow = fixture()
    await assert.rejects(read(manager, overflow, 'shared', work), error => error.statusCode === 429)
    assert.equal(overflow.headers['Retry-After'], '1')
    const queued = [1, 2, 3].map(id => read(manager, fixture(), `different-${id}`, work))
    await next()
    const overflowQuery = fixture()
    await assert.rejects(read(manager, overflowQuery, 'one-too-many', work), error => error.statusCode === 429)
    assert.equal(overflowQuery.headers['Retry-After'], '1')
    assert.deepEqual(queueStatus(), { running: 1, waiting: 3, capacity: 3 })
    release(); await Promise.all([...shared, ...queued])
    assert.deepEqual(manager.status(), { flights: 0, subscribers: 0 })
})

test('failed and oversized builds release all subscriptions and are not reused', async () => {
    const manager = new ContentManagementSharedReads()
    const failing = [fixture(), fixture()].map(browser => read(manager, browser, 'failure', async () => { throw Error('isolated failure') }))
    await Promise.all(failing.map(promise => assert.rejects(promise, /isolated failure/)))
    assert.deepEqual(manager.status(), { flights: 0, subscribers: 0 })
    const oversized = [fixture(), fixture()].map(browser => read(manager, browser, 'oversized', async () => 'x'.repeat(2 * 1024 * 1024 + 1)))
    await Promise.all(oversized.map(promise => assert.rejects(promise, ContentSharedReadOversized)))
    assert.deepEqual(manager.status(), { flights: 0, subscribers: 0 })
    assert.equal(await read(manager, fixture(), 'failure', async () => 'recovered'), 'recovered')
    assert.equal(queueStatus().running, 0)
})

test('total subscribers are capped even when every distinct read is admitted', async () => {
    const manager = new ContentManagementSharedReads()
    let release
    const barrier = new Promise(resolve => { release = resolve })
    const work = async () => { await barrier; return 'done' }
    const requests = Array.from({ length: 4 }, (_, group) => Array.from({ length: 16 }, () => read(manager, fixture(), `group-${group}`, work))).flat()
    const overflow = fixture()
    await assert.rejects(read(manager, overflow, 'another-group', work), error => error.statusCode === 429)
    assert.deepEqual(manager.status(), { flights: 4, subscribers: 64 })
    release(); await Promise.all(requests)
    assert.deepEqual(manager.status(), { flights: 0, subscribers: 0 })
})

test('an actual HTTP disconnect cancels only that browser and leaves the shared result available', async () => {
    const http = require('node:http'), app = require('fastify')({ logger: false })
    const manager = new ContentManagementSharedReads()
    let release, builds = 0
    const barrier = new Promise(resolve => { release = resolve })
    const work = async checkpoint => { builds++; await barrier; await checkpoint(); return '{"kept":true}' }
    app.get('/probe', async (request, reply) => {
        const body = await manager.read(request, reply, 'actual-http', work)
        return reply.type('application/json').send(body)
    })
    await app.listen({ host: '127.0.0.1', port: 0 })
    const port = app.server.address().port
    const request = () => {
        let raw
        const promise = new Promise((resolve, reject) => {
            raw = http.get({ host: '127.0.0.1', port, path: '/probe', agent: false }, response => {
                let body = ''; response.setEncoding('utf8'); response.on('data', value => { body += value })
                response.on('end', () => resolve({ status: response.statusCode, body }))
                response.on('error', reject)
            })
            raw.on('error', reject)
        })
        return { raw, promise }
    }
    const first = request(), second = request()
    const firstEnded = first.promise.then(() => assert.fail('cancelled HTTP connection must not complete'), error => error)
    const waitFor = async predicate => {
        const until = Date.now() + 5000
        while (!predicate()) { if (Date.now() >= until) assert.fail('HTTP lifecycle timed out'); await next() }
    }
    try {
        await waitFor(() => manager.status().subscribers === 2)
        first.raw.destroy(); assert.match((await firstEnded).message, /socket hang up/)
        await waitFor(() => manager.status().subscribers === 1)
        release()
        assert.deepEqual(await second.promise, { status: 200, body: '{"kept":true}' })
        assert.equal(builds, 1)
        assert.deepEqual(manager.status(), { flights: 0, subscribers: 0 })
    } finally {
        release(); first.raw.destroy(); second.raw.destroy(); await app.close()
    }
})
