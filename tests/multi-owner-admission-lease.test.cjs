const { test, afterEach } = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const { EventEmitter } = require('node:events')
const { performance } = require('node:perf_hooks')
process.env.MULTI_REALTIME_OWNER_CHILD = '1'
const out = process.env.STARPOINT_TEST_OUT_DIR || path.resolve(__dirname, '../out')
const rpc = require(path.join(out, 'multi/coordinator/business-rpc'))
let respond
rpc.installRealtimeBusinessTransport((kind, payload) => respond(kind, payload))
const admission = require(path.join(out, 'multi/coordinator/socket-admission'))
class Socket extends EventEmitter {
    destroyed = false
    destroy() { this.destroyed = true; this.emit('close') }
}
afterEach(() => admission.stopSocketAdmission())
function clock(t) {
    let now = 100; const deadlines = [], polls = []
    t.mock.method(performance, 'now', () => now)
    t.mock.method(global, 'setTimeout', (fn, ms) => { const timer = { fn, ms, unref() {} }; deadlines.push(timer); return timer })
    t.mock.method(global, 'setInterval', (fn, ms) => { const timer = { fn, ms, unref() {} }; polls.push(timer); return timer })
    t.mock.method(global, 'clearTimeout', () => {}); t.mock.method(global, 'clearInterval', () => {})
    return { advance: ms => now += ms, deadlines, polls }
}
test('business RPC queue/transit time cannot extend an admission capability', async t => {
    const c = clock(t), socket = new Socket()
    respond = async kind => { assert.equal(kind, 'admission.lease'); c.advance(5000); return { ok: true, remainingMs: 60000 } }
    assert.equal(await admission.authorizeSocketAdmission(socket, 'synthetic-token', 'synthetic-session'), true)
    assert.equal(c.deadlines.at(-1).ms, 55000)
    c.advance(55001)
    assert.equal(admission.checkSocketAdmission(socket, '', ''), false)
    c.deadlines.at(-1).fn(); assert.equal(socket.destroyed, true)
})
test('owner deadline closes an idle socket while parent refresh is pending, and its late ACK cannot resurrect it', async t => {
    const c = clock(t), socket = new Socket(); let complete
    respond = async (kind, payload) => kind === 'admission.lease' ? { ok: true, remainingMs: 10000 }
        : new Promise(resolve => complete = () => resolve(payload.items.map(item => ({ id: item.id, ok: true, remainingMs: 60000 }))))
    assert.equal(await admission.authorizeSocketAdmission(socket, null, null), true)
    assert.equal(admission.checkSocketAdmission(socket, null, null), true)
    c.polls[0].fn(); await Promise.resolve()
    assert.equal(typeof complete, 'function')
    c.advance(10001); c.deadlines.at(-1).fn()
    assert.equal(socket.destroyed, true)
    complete(); await new Promise(resolve => setImmediate(resolve))
    assert.equal(admission.checkSocketAdmission(socket, null, null), false)
    assert.equal(c.deadlines.length, 1, 'late ACK cannot create another lease after expiry')
})
test('a capability already exhausted during authorization is refused', async t => {
    const c = clock(t), socket = new Socket()
    respond = async () => { c.advance(5000); return { ok: true, remainingMs: 4000 } }
    assert.equal(await admission.authorizeSocketAdmission(socket, null, null), false)
    assert.equal(socket.destroyed, true)
})
