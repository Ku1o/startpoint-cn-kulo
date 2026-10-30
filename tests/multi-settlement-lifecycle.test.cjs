const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const { EventEmitter } = require('node:events')
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')

// Run the real compiled session/score logic without networking or a database.
function loadCompiled(relative, stubs, locals = {}) {
    const filename = path.resolve(__dirname, compiled ? '../out' : '../src',
        compiled ? relative : relative.replace(/\.js$/, '.ts'))
    const isolated = new Module(filename, module)
    isolated.filename = filename
    isolated.paths = Module._nodeModulePaths(path.dirname(filename))
    const realRequire = Module.createRequire(filename)
    isolated.require = request => stubs.has(request) ? stubs.get(request) : realRequire(request)
    isolated.fixture = locals
    const bindings = Object.keys(locals).map(name => `const ${name} = module.fixture.${name};`).join('\n')
    const source = fs.readFileSync(filename, 'utf8')
    const code = compiled ? source : require('typescript').transpileModule(source, {
        compilerOptions: { module: 1, target: 6, esModuleInterop: true },
    }).outputText
    isolated._compile(bindings + '\n' + code, filename)
    return isolated.exports
}

function clock() {
    let now = 1_000
    const timers = new Map()
    const schedule = (callback, delay = 0) => {
        const timer = { at: now + delay, callback, unref() {} }
        timers.set(timer, timer)
        return timer
    }
    return {
        now: () => now,
        timers,
        locals: {
            setTimeout: schedule, clearTimeout: timer => timers.delete(timer),
            setImmediate: callback => schedule(callback, 0),
        },
        async advance(ms) {
            const target = now + ms
            for (;;) {
                const timer = [...timers.values()].filter(entry => entry.at <= target)
                    .sort((a, b) => a.at - b.at)[0]
                if (!timer) break
                timers.delete(timer); now = timer.at; timer.callback()
                await Promise.resolve()
                await Promise.resolve()
            }
            now = target
        },
    }
}

function fixture(t) {
    const timer = clock(), rooms = new Map(), disbands = [], frames = []
    const contract = loadCompiled('multi/state/battle-contract.js',
        new Map([['node:perf_hooks', { performance: { now: timer.now } }]]))
    const coordinator = { enqueueRoomCommand: (_room, callback) => Promise.resolve().then(callback) }
    let manager
    const roomManager = {
        getRoom: number => rooms.get(number),
        disbandRoom(number, reason) {
            if (!rooms.delete(number)) return false
            disbands.push({ number, reason })
            manager.removeRoomState(number)
            return true
        },
    }
    const quiet = () => {}
    const stubs = new Map([
        ['node:perf_hooks', { performance: { now: timer.now } }],
        ['../../lib/routine-game-logging', { routineGameLog: quiet }],
        ['../../lib/game-logging', { gameVerboseLog: quiet }],
        ['../../lib/memory-diagnostics', { registerMemoryCounters: quiet }],
        ['../../lib/server-work-performance', { recordServerWork: quiet }],
        ['../../lib/realtime-diagnostics', { recordRealtimeDiagnostic: quiet }],
        ['../tcp/reliable-send', { clearReliableSendState: quiet, sendFrameReliably: () => 'sent' }],
        ['../tcp/chain-diagnostic', { clearChainDiagnosticRoom: quiet }],
        ['../tcp/disconnect-diagnostics', { markTcpDisconnectReason: quiet }],
        ['../coordinator/embedded', { embeddedMultiCoordinator: coordinator }],
        ['../room/admission', { roomAdmissionRegistry: {} }],
        ['../five-boss/connection-diagnostic', { fiveBossConnectionDiagnostics: { socketEvent: quiet } }],
        ['../five-boss/contract', { isFiveBossGauntletQuest: (_category, quest) => quest === 1099001999 }],
        ['../battle-telemetry', { battleTelemetry: {} }],
        ['../room/equipment-ready', { clearEquipmentBlock: quiet }],
        ['../tcp/battle-relay/bridge', {
            battleRelayBridge: { scheduleMembership: quiet }, isRelayProxySocket: () => false,
        }],
        ['../coordinator/room-start-claims', { hasRoomStartClaims: () => false }],
        ['../tcp/lobby', { clearLobbyRoomState: quiet }],
        ['../room/manager', roomManager],
        ['./battle-contract', contract],
    ])
    const { SessionManager } = loadCompiled('multi/state/SessionManager.js', stubs,
        { ...timer.locals, console: { warn: quiet, error: quiet, log: quiet } })
    manager = new SessionManager()
    manager.sendJson = (socket, data) => { frames.push({ socket, data }); return 'sent' }
    const room = {
        room_number: '654321', category: 2, quest_id: 1001, lobby_generation: 1,
        member_viewer_ids: [11, 12], member_player_ids: { 11: 21, 12: 22 },
        expected_real_viewer_ids: [11, 12],
        lifecycle: { instanceId: 'instance-a', battleSessionId: 'battle-a',
            phase: 'BATTLE', sceneEpoch: 0, version: 1 },
    }
    rooms.set(room.room_number, room)
    contract.ensureBattleSessionContract(room)
    const clients = [11, 12].map(viewer => {
        const socket = new EventEmitter()
        Object.assign(socket, { destroyed: false, writable: true, readable: true,
            end() { this.writable = false }, destroy() { this.destroyed = true } })
        const client = manager.createClient(socket, viewer, room.room_number, 'cid-' + viewer, viewer + 10)
        client.isBattle = true; client.roomGeneration = 1
        manager.cidToBattleClient.set(client.connectionId, client)
        manager.socketClients.set(socket, client)
        contract.bindBattleConnection(room, client)
        contract.markBattleMemberPhase(room, viewer, 'READY')
        contract.markBattleMemberPhase(room, viewer, 'ACTIVE')
        return client
    })
    manager.battleClients.set(room.room_number, new Set(clients.map(client => client.connectionId)))
    const settling = () => {
        room.lifecycle.phase = 'RETURNING'
        clients[0].finalizeSent = true
        contract.markBattleMemberPhase(room, 11, 'FINALIZED')
        contract.markBattleMemberPhase(room, 11, 'SETTLED')
    }
    const keys = ['BATTLE_HEARTBEAT_LEASE_MS', 'BATTLE_SETTLING_HEARTBEAT_LEASE_MS',
        'BATTLE_ROOM_TIMEOUT_MS', 'MULTI_DISBAND_SETTLEMENT_WAIT_MS', 'MULTI_SERVER_CONFIRMED_CLEAR']
    const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]))
    for (const key of keys) delete process.env[key]
    t.after(() => {
        manager.removeRoomState(room.room_number)
        for (const key of keys) {
            if (previous[key] === undefined) delete process.env[key]
            else process.env[key] = previous[key]
        }
    })
    return { timer, rooms, room, clients, manager, contract, disbands, frames, settling }
}

test('unfinished teammate gets a 120 second settling lease, bounded from its last activity', async t => {
    const x = fixture(t), guest = x.clients[1]
    x.settling()
    x.manager.armActiveBattleHeartbeatLease(guest.connectionId)
    await x.timer.advance(119_999)
    assert.equal(guest.socket.destroyed, false)
    await x.timer.advance(1)
    assert.equal(guest.socket.destroyed, true)
})

for (const variant of ['ordinary battle', 'finalized member', 'five boss', 'superseded connection']) {
    test(variant + ' retains the normal 25 second heartbeat expiry', async t => {
        const x = fixture(t), guest = x.clients[1]
        if (variant !== 'ordinary battle') x.settling()
        if (variant === 'finalized member') guest.finalizeSent = true
        if (variant === 'five boss') x.room.quest_id = 1099001999
        if (variant === 'superseded connection') guest.superseded = true
        x.manager.armActiveBattleHeartbeatLease(guest.connectionId)
        await x.timer.advance(25_000)
        assert.equal(guest.socket.destroyed, true)
    })
}

test('host disband waits for unfinished teammate and commits after Finalize', async t => {
    const x = fixture(t)
    x.settling()
    assert.equal(x.manager.commitRoomDisband(x.room.room_number, 'host_left'), true)
    assert.equal(x.disbands.length, 0)
    assert.equal(x.clients[1].socket.destroyed, false)
    assert.equal(x.manager.deferredDisbands.get(x.room.room_number).deadline, x.timer.now() + 900_000)
    x.clients[1].finalizeSent = true
    x.contract.markBattleMemberPhase(x.room, 12, 'FINALIZED')
    await x.timer.advance(2_000)
    assert.deepEqual(x.disbands, [{ number: x.room.room_number, reason: 'host_left' }])
    assert.equal(x.manager.deferredDisbands.size, 0)
    await x.timer.advance(5_000)
    assert.equal(x.disbands.length, 1)
})

test('repeated disband requests cannot extend the bounded settling deadline', async t => {
    const x = fixture(t)
    x.settling(); process.env.MULTI_DISBAND_SETTLEMENT_WAIT_MS = '200'
    x.manager.commitRoomDisband(x.room.room_number, 'host_left')
    const deadline = x.manager.deferredDisbands.get(x.room.room_number).deadline
    await x.timer.advance(100)
    x.manager.commitRoomDisband(x.room.room_number, 'host_left')
    assert.equal(x.manager.deferredDisbands.get(x.room.room_number).deadline, deadline)
    await x.timer.advance(100)
    assert.equal(x.disbands.length, 1)
})

for (const replacement of ['room instance', 'battle session']) {
    test('old deferred disband cannot close a replacement ' + replacement, async t => {
        const x = fixture(t)
        x.settling()
        x.manager.commitRoomDisband(x.room.room_number, 'host_left')
        if (replacement === 'room instance') x.room.lifecycle.instanceId = 'instance-b'
        else x.room.lifecycle.battleSessionId = 'battle-b'
        await x.timer.advance(2_000)
        assert.equal(x.disbands.length, 0)
        assert.equal(x.manager.deferredDisbands.size, 0)
        assert.equal(x.rooms.get(x.room.room_number), x.room)
    })
}

test('room cleanup removes pending disband and stale asset state', async t => {
    const x = fixture(t)
    x.settling(); x.manager.markStaleAssetViewer(x.room.room_number, 12)
    x.manager.commitRoomDisband(x.room.room_number, 'host_left')
    x.manager.removeRoomState(x.room.room_number)
    assert.equal(x.manager.deferredDisbands.size, 0)
    assert.equal(x.manager.staleAssetViewers.size, 0)
    await x.timer.advance(3_000)
    assert.equal(x.disbands.length, 0)
})

test('server-confirmed clear defaults off and enabled sends are fenced and idempotent', t => {
    const x = fixture(t)
    x.settling()
    assert.equal(x.manager.sendServerConfirmedClear(x.room.room_number, 11, 'battle-a'), 0)
    assert.equal(x.frames.length, 0)
    process.env.MULTI_SERVER_CONFIRMED_CLEAR = '1'
    assert.equal(x.manager.sendServerConfirmedClear(x.room.room_number, 11, 'old-battle'), 0)
    assert.equal(x.manager.sendServerConfirmedClear(x.room.room_number, 11, 'battle-a'), 1)
    assert.deepEqual(x.frames.map(frame => frame.data), [[1, [2]]])
    assert.equal(x.manager.sendServerConfirmedClear(x.room.room_number, 11, 'battle-a'), 0)
})

test('stale asset markers are one-shot, expire, and belong to the original room instance', t => {
    const x = fixture(t), number = x.room.room_number
    x.manager.markStaleAssetViewer(number, 12)
    assert.equal(x.manager.takeStaleAssetViewer(number, 12), true)
    assert.equal(x.manager.takeStaleAssetViewer(number, 12), false)
    x.manager.markStaleAssetViewer(number, 12)
    x.manager.staleAssetViewers.get(number + ':12').expiresAt = Date.now() - 1
    assert.equal(x.manager.takeStaleAssetViewer(number, 12), false)
    x.manager.markStaleAssetViewer(number, 12)
    x.room.lifecycle.instanceId = 'replacement'
    assert.equal(x.manager.takeStaleAssetViewer(number, 12), false)
})

test('late score submission retains earlier authoritative scores for 15 minutes', async t => {
    const timer = clock()
    const previous = process.env.MULTI_SETTLEMENT_SNAPSHOT_RETENTION_MS
    delete process.env.MULTI_SETTLEMENT_SNAPSHOT_RETENTION_MS
    t.after(() => {
        if (previous === undefined) delete process.env.MULTI_SETTLEMENT_SNAPSHOT_RETENTION_MS
        else process.env.MULTI_SETTLEMENT_SNAPSHOT_RETENTION_MS = previous
    })
    const settlement = loadCompiled('multi/settlement.js',
        new Map([['../lib/memory-diagnostics', { registerMemoryCounters() {} }]]), timer.locals)
    const input = { key: 'battle', participants: [{ viewerId: 11, comId: 0 }, { viewerId: 12, comId: 0 }],
        expectedRealViewerIds: [11, 12], ownContributionScore: 30, mateResults: [], waitMs: 0 }
    await settlement.mergeMultiSettlementResults({ ...input, viewerId: 11, ownScore: 700 })
    await timer.advance(130_000)
    const late = await settlement.mergeMultiSettlementResults({ ...input, viewerId: 12, ownScore: 800,
        mateResults: [{ viewer_id: 11, com_id: 0, score: 1, contribution_score: 1 }] })
    assert.equal(late.mateResults[0].score, 700)
    await timer.advance(770_000)
    const expired = await settlement.mergeMultiSettlementResults({ ...input, viewerId: 12, ownScore: 900 })
    assert.deepEqual(expired.synthesizedViewerIds, [11])
    settlement.clearMultiSettlementSnapshot('battle')
})
