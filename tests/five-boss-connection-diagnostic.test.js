const { test } = require('node:test')
const assert = require('node:assert/strict')
const { FiveBossConnectionDiagnostics } = require('../out/multi/five-boss/connection-diagnostic')

function room(run = 'run-a', number = '123456') {
    return { room_number: number, lobby_generation: 1, five_boss_runtime: { runId: run,
        expectedRealPlayerIds: [10, 20], battleIdentityByViewerId: {
            100: { playerId: 10, connectionId: 'private-connection', remoteAddress: 'private-address' },
            200: { playerId: 20, connectionId: 'guest-connection', remoteAddress: 'guest-address' },
        } } }
}
function client() {
    return { socket: {}, playerId: 10, viewerId: 100, connectionId: 'private-connection', roomGeneration: 1 }
}

test('normal traffic stays in bounded counters, without logs, payloads, addresses or raw connection ids', () => {
    let emitted = 0, nowCalls = 0
    const trace = new FiveBossConnectionDiagnostics(512, 16, 60000, () => ++nowCalls, () => emitted++)
    const r = room(), c = client(), ordinarySocket = {}
    const before = nowCalls
    for (let i = 0; i < 1000; i++) trace.packet(ordinarySocket, true)
    assert.equal(nowCalls, before, 'ordinary multiplayer packets must not read time')
    trace.bind(r, c)
    trace.socketEvent(c.socket, 'accepted')
    for (let i = 0; i < 10000; i++) trace.packet(c.socket, true)
    const state = trace.snapshot('run-a', 10)
    assert.equal(state.connections[0].packets, 10000)
    assert.equal(state.totalEvents, 3)
    assert.equal(state.connections[0].unindexedPackets, 0)
    assert.equal(emitted, 0)
    assert.doesNotMatch(JSON.stringify(state), /private-connection|private-address|guest-address/)
    assert.equal(trace.snapshot('run-a', 20).connections.length, 0)
})

test('late unindexed packets and both proof writes remain visible after the first failure', () => {
    const emitted = [], trace = new FiveBossConnectionDiagnostics(512, 16, 60000, () => 100,
        (run, player, event, snapshot) => emitted.push({ run, player, event, state: snapshot() }))
    const c = client(); trace.bind(room(), c)
    trace.memberEvent('run-a', 10, 'finish_rejected', 'battle_proof_missing')
    for (let i = 0; i < 1000; i++) trace.packet(c.socket, false)
    trace.socketEvent(c.socket, 'level_next_recorded', 'tcp')
    trace.socketEvent(c.socket, 'finalize_recorded', 'tcp')
    assert.deepEqual(emitted.map(row => row.event), ['packet_unindexed', 'level_next_recorded', 'finalize_recorded'])
    const state = trace.snapshot('run-a', 10)
    assert.equal(state.connections[0].unindexedPackets, 1000)
    assert.equal(state.counts.packet_unindexed.count, 1)
    assert.equal(state.counts.finalize_recorded.count, 1)
    assert.equal(trace.snapshot('run-a', 20).counts.finish_rejected, undefined)
})

test('event flood and reconnect churn have fixed bounds while first/last event times remain available', () => {
    let now = 0
    const trace = new FiveBossConnectionDiagnostics(2, 4, 60000, () => ++now)
    const r = room()
    for (let i = 0; i < 10; i++) {
        const c = client(); trace.bind(r, c); trace.socketEvent(c.socket, 'accepted')
        for (let j = 0; j < 100; j++) trace.socketEvent(c.socket, 'scene_ready')
    }
    const state = trace.snapshot('run-a', 10)
    assert.equal(state.events.length, 4)
    assert.equal(state.connections.length, 3)
    assert.equal(state.counts.scene_ready.count, 1000)
    assert.ok(state.counts.scene_ready.firstAt < state.counts.scene_ready.lastAt)
    assert.equal(state.totalEvents - state.droppedEvents, 4)
    state.events[0].event = 'tampered'
    assert.notEqual(trace.snapshot('run-a', 10).events[0].event, 'tampered')
})

test('retention and capacity discard old evidence without mixing reused room numbers', () => {
    let now = 0
    const trace = new FiveBossConnectionDiagnostics(2, 4, 100, () => now), old = client()
    trace.bind(room('old'), old)
    trace.begin(room('current'))
    trace.seatEvent('123456', 100, 'seat_expired')
    assert.equal(trace.snapshot('old', 10).counts.seat_expired, undefined)
    assert.equal(trace.snapshot('current', 10).counts.seat_expired.count, 1)
    trace.begin(room('third', '654321'))
    trace.socketEvent(old.socket, 'socket_close')
    assert.equal(trace.snapshot('old', 10).available, false)
    assert.equal(trace.snapshot('current', 10).available, true)
    now = 101
    assert.equal(trace.snapshot('current', 10).available, false)
    assert.equal(trace.snapshot('third', 10).available, false)
})

test('a failing diagnostic writer cannot interrupt disconnect and later signal handling', () => {
    const trace = new FiveBossConnectionDiagnostics(2, 16, 100, () => 0, () => { throw Error('sink failed') })
    const c = client(); trace.bind(room(), c)
    trace.memberEvent('run-a', 10, 'finish_rejected')
    assert.doesNotThrow(() => trace.socketEvent(c.socket, 'socket_error', 'ECONNRESET'))
    assert.doesNotThrow(() => trace.socketEvent(c.socket, 'finalize_recorded', 'tcp'))
    assert.equal(trace.snapshot('run-a', 10).counts.finalize_recorded.count, 1)
})
