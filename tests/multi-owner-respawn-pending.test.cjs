'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const out = process.env.STARPOINT_TEST_OUT_DIR || path.resolve(__dirname, '../out')
const load = name => require(path.join(out, name))
const flush = async () => { for (let i = 0; i < 40; i++) await Promise.resolve() }

test('pending old decisions drain after confirmed exit without consuming the only respawn attempt', async t => {
    process.env.MULTI_REALTIME_PROCESS = '1'
    process.env.MULTI_REALTIME_OWNER_CHILD = '0'
    process.env.MULTI_REALTIME_RESPAWN_MAX = '1'
    for (const name of ['error', 'warn', 'log']) t.mock.method(console, name, () => {})
    t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'] })
    const transports = [], submissions = []
    let confirmExit
    const exit = new Promise(resolve => { confirmExit = resolve })
    class FakeTransport {
        constructor() { this.ownerEpoch = `owner-${transports.length}`; this.pid = 100 + transports.length; transports.push(this) }
        async start() { this.isReady = true }
        async abort() { this.isReady = false; await exit }
        async submit(command) {
            submissions.push(this.ownerEpoch)
            return { commandId: command.commandId, ownerEpoch: this.ownerEpoch, status: 'unknown', outcomeUnknown: true }
        }
        async queryResult(id) { return { commandId: id, ownerEpoch: this.ownerEpoch, status: 'unknown', outcomeUnknown: true } }
        bootstrapMetadata() { return null }
        diagnostics() { return { ready: this.isReady } }
    }
    const transportPath = require.resolve(path.join(out, 'multi/coordinator/command-process'))
    require.cache[transportPath] = { id: transportPath, filename: transportPath, loaded: true, exports: { CommandProcessTransport: FakeTransport } }
    const runtime = load('multi/coordinator/default-runtime')
    const events = load('multi/coordinator/durable-owner-event')
    await runtime.startRealtimeSessionServer()
    await events.publishDurableOwnerDecision('battle.settlement.committed', { alreadyCommitted: true })
    await events.publishDurableOwnerDecision('fiveBoss.terminal', { alreadyCommitted: true })
    assert.equal(events.inspectDurableOwnerEvents().pending, 2)
    const failed = runtime.failRealtimeOwner()
    assert.equal(await events.publishDurableOwnerDecision('battle.play.commit', {}), undefined)
    t.mock.timers.tick(30_000); await flush()
    assert.equal(transports.length, 1, 'no replacement before old child exit')
    confirmExit(); await flush()
    // Pending reconciliation lasts far longer than the old 5-second retry budget.
    for (let i = 0; i < 12 && events.inspectDurableOwnerEvents().pending; i++) {
        t.mock.timers.tick(5000); await flush()
        assert.equal(transports.length, 1, 'reconciliation does not fork or consume the one attempt')
    }
    await failed
    assert.equal(events.inspectDurableOwnerEvents().pending, 0)
    t.mock.timers.tick(5000); await flush()
    assert.equal(transports.length, 2)
    assert.equal(runtime.realtimeOwnerStatus().phase, 'running')
    assert.equal(runtime.realtimeOwnerStatus().ready, true)
    t.mock.timers.tick(120_000); await flush()
    assert.equal(transports.length, 2, 'no old timer can seal the replacement')
    assert.ok(submissions.every(epoch => epoch === 'owner-0'), 'old decisions never execute in the replacement epoch')
})

test('an explicit start also waits for old child exit and notification drain', async t => {
    for (const name of ['error', 'warn', 'log']) t.mock.method(console, name, () => {})
    t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'] })
    let confirmExit, confirmDrain, forks = 0, drained = false, sealed = false
    const exit = new Promise(resolve => { confirmExit = resolve })
    const drain = new Promise(resolve => { confirmDrain = () => { drained = true; resolve() } })
    class FakeTransport {
        constructor() { this.ownerEpoch = `explicit-${++forks}` }
        async start() { this.isReady = true }
        async abort() { this.isReady = false; await exit }
        bootstrapMetadata() { return null }
        diagnostics() { return { ready: this.isReady } }
    }
    const stub = (name, exports) => {
        const filename = require.resolve(path.join(out, name))
        require.cache[filename] = { id: filename, filename, loaded: true, exports }
    }
    stub('multi/coordinator/command-process', { CommandProcessTransport: FakeTransport })
    stub('multi/coordinator/durable-owner-event', {
        sealDurableOwnerEvents() { sealed = true },
        drainDurableOwnerEvents: () => drain,
        resumeDurableOwnerEvents() { assert.equal(drained, true) },
    })
    delete require.cache[require.resolve(path.join(out, 'multi/coordinator/default-runtime'))]
    const runtime = load('multi/coordinator/default-runtime')
    await runtime.startRealtimeSessionServer()
    const failure = runtime.failRealtimeOwner()
    const explicitStart = runtime.startRealtimeSessionServer()
    await flush(); assert.equal(sealed, true); assert.equal(forks, 1)
    confirmExit(); await flush(); assert.equal(forks, 1, 'exit alone is insufficient while decisions remain')
    confirmDrain(); await Promise.all([failure, explicitStart])
    assert.equal(forks, 2)
    assert.equal(runtime.realtimeOwnerStatus().phase, 'running')
    t.mock.timers.tick(60_000); await flush()
    assert.equal(forks, 2, 'supervisor timer cannot duplicate an explicit replacement')
})
