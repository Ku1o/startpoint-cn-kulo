'use strict'
require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { runContentManagementRead: run, contentManagementReadStatus: status } = require('../src/lib/content-management-work')
const next = () => new Promise(resolve => setImmediate(resolve))
const fixture = () => {
    const raw = new EventEmitter(), response = new EventEmitter(), headers = {}
    return { request: { raw }, reply: { raw: response, header: (key, value) => { headers[key] = value } }, headers }
}
const enqueue = (context, work) => run(context.request, context.reply, work)

test('one administrative read runs at a time, overflow is bounded and failures release the slot', async () => {
    let release, active = 0, max = 0
    const barrier = new Promise(resolve => { release = resolve })
    const contexts = Array.from({ length: 5 }, fixture)
    const one = enqueue(contexts[0], async () => { active++; max = Math.max(max, active); await barrier; active--; return 1 })
    const queued = contexts.slice(1, 4).map((context, index) => enqueue(context, async checkpoint => {
        active++; max = Math.max(max, active); await checkpoint(); active--; return index + 2
    }))
    assert.deepEqual(status(), { running: 1, waiting: 3, capacity: 3 })
    await assert.rejects(enqueue(contexts[4], () => assert.fail('overflow must not run')), error => error.statusCode === 429)
    assert.equal(contexts[4].headers['Retry-After'], '1')
    release(); assert.deepEqual(await Promise.all([one, ...queued]), [1, 2, 3, 4])
    assert.equal(max, 1)
    await assert.rejects(enqueue(fixture(), () => { throw new Error('synthetic read failure') }), /synthetic read failure/)
    assert.equal(await enqueue(fixture(), () => 'recovered'), 'recovered')
    assert.equal(status().running, 0)
})

test('disconnected queued reads are removed without capturing data and listeners are released', async () => {
    let release
    const barrier = new Promise(resolve => { release = resolve })
    const active = fixture(), obsolete = fixture()
    const one = enqueue(active, () => barrier)
    const old = enqueue(obsolete, () => assert.fail('cancelled queue entry must not run'))
    const rejection = assert.rejects(old, error => error.statusCode === 499)
    obsolete.request.raw.aborted = true; obsolete.request.raw.emit('aborted')
    await rejection
    assert.equal(status().waiting, 0)
    assert.equal(obsolete.request.raw.listenerCount('aborted'), 0)
    assert.equal(obsolete.reply.raw.listenerCount('close'), 0)
    release(); await one
})

test('checkpoints serve other event-loop work and stop an active disconnected query', async () => {
    const context = fixture()
    let ran = false, proceeded = false
    const pending = enqueue(context, async checkpoint => {
        setImmediate(() => { ran = true; context.reply.raw.destroyed = true; context.reply.raw.emit('close') })
        await checkpoint(); proceeded = true
    })
    await assert.rejects(pending, error => error.statusCode === 499)
    assert.equal(ran, true); assert.equal(proceeded, false)
    assert.equal(status().running, 0)
    assert.equal(context.reply.raw.listenerCount('close'), 0)
    await next()
})
