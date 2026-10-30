const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const Module = require('node:module')
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')

function loadCompiled(relative, stubs = new Map()) {
    const filename = path.resolve(__dirname, compiled ? '../out' : '../src',
        compiled ? relative : relative.replace(/\.js$/, '.ts'))
    const isolated = new Module(filename, module)
    isolated.filename = filename
    isolated.paths = Module._nodeModulePaths(path.dirname(filename))
    const realRequire = Module.createRequire(filename)
    isolated.require = request => stubs.has(request) ? stubs.get(request) : realRequire(request)
    const source = fs.readFileSync(filename, 'utf8')
    const code = compiled ? source : require('typescript').transpileModule(source, {
        compilerOptions: { module: 1, target: 6, esModuleInterop: true },
    }).outputText
    isolated._compile(code, filename)
    return isolated.exports
}

function fingerprints(extra = []) {
    return loadCompiled('multi/tcp/state-fingerprint.js', new Map([
        ['../state/SessionManager', { sessionManager: {} }],
        ['../room/manager', { getRoom: () => undefined }],
        ['../state/battle-contract', {}],
        ...extra,
    ]))
}

function packet(api, hp = 100) {
    return [0, [5, { kind: 'wf-fp', v: 1, schema: api.FINGERPRINT_SCHEMA, build: 'offline-test',
        epoch: 0, seq: 0, part: 0, parts: 1, events: [], gaps: [],
        rows: [{ battleId: 'boss', battleEpoch: 0, postFrame: 0, phase: 'initial', zone: null,
            floor: 0, mode: 'full', inputs: [], unsupported: [], eventCursor: 0,
            values: { '/battle/id': 'boss', '/battle/currentFrame': 0, '/member/11/hp': hp } }] }]]
}

test('diagnostics default off creates no files and does not retain packets', t => {
    const previous = { fp: process.env.MULTI_FINGERPRINT_DIR, relay: process.env.MULTI_RELAY_RECORD_DIR }
    delete process.env.MULTI_FINGERPRINT_DIR; delete process.env.MULTI_RELAY_RECORD_DIR
    t.after(() => {
        for (const [key, value] of [['MULTI_FINGERPRINT_DIR', previous.fp], ['MULTI_RELAY_RECORD_DIR', previous.relay]]) {
            if (value === undefined) delete process.env[key]; else process.env[key] = value
        }
    })
    const forbiddenFs = new Proxy({}, { get() { return () => { throw new Error('disabled diagnostics attempted filesystem I/O') } } })
    const api = fingerprints([['fs', forbiddenFs]])
    assert.equal(api.isStateFingerprintEnabled(), false)
    assert.deepEqual(api.stateFingerprintService.receivePacket({ viewerId: 11, connectionId: 'c11', roomNumber: 'r' },
        packet(api)), { accepted: false, reason: 'disabled' })
    assert.deepEqual(api.stateFingerprintService.getAllRuns(), [])
    const recorder = loadCompiled('multi/tcp/relay-recorder.js', new Map([['fs', forbiddenFs]]))
    recorder.recordBattleFrame('r', 1, 11, 'c11', [0, [5]])
})

test('fingerprints validate envelope limits, duplicate keys and fragment completeness', () => {
    const api = fingerprints()
    assert.equal(api.validateFingerprintPacket(packet(api)).parts, 1)
    const duplicate = JSON.stringify(packet(api)).replace('"v":1', '"v":1,"v":1')
    assert.throws(() => api.validateFingerprintPacket(duplicate), /duplicate object key/)
    const oversized = packet(api); oversized[1][1].build = 'x'.repeat(20_000)
    assert.throws(() => api.validateFingerprintPacket(oversized), /physical packet exceeded/)
    const logical = JSON.stringify({ rows: [], events: [], gaps: [] })
    const half = Math.floor(logical.length / 2)
    const fragments = [logical.slice(0, half), logical.slice(half)].map((chunk, part) =>
        [0, [5, { kind: 'wf-fp', v: 1, schema: api.FINGERPRINT_SCHEMA, build: 'offline-test',
            epoch: 0, seq: 0, part, parts: 2, chunk }]])
    assert.deepEqual(api.reassembleFragments(fragments), { rows: [], events: [], gaps: [] })
    assert.throws(() => api.reassembleFragments(fragments.slice(0, 1)), /missing|incomplete/i)
    assert.equal(api.isStateFingerprintNotify([5]), false)
    assert.equal(api.isStateFingerprintNotify([5, {}]), true)
})

test('enabled fingerprints keep the frozen roster, suppress duplicate packets and report divergence', t => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'multi-fingerprint-'))
    t.after(() => fs.rmSync(directory, { recursive: true }))
    const api = fingerprints()
    const service = new api.StateFingerprintService({ outputDir: directory, nowMs: () => 1_000, stderrWrite() {} })
    const expectedMembers = [11, 12].map(viewerId => ({ viewerId, connectionId: 'c' + viewerId, observerId: 'c' + viewerId }))
    const context = viewerId => ({ viewerId, connectionId: 'c' + viewerId, roomNumber: 'room',
        roomInstanceId: 'instance', battleSessionId: 'battle', generation: 1, sceneEpoch: 0, expectedMembers })
    assert.equal(service.receivePacket(context(11), packet(api)).accepted, true)
    assert.equal(service.receivePacket(context(11), packet(api)).duplicate, true)
    assert.equal(service.receivePacket(context(99), packet(api)).reason, 'unauthorized_observer')
    assert.equal(service.receivePacket(context(12), packet(api, 90)).accepted, true)
    assert.equal(service.diagnostics.desyncReports > 0, true)
    assert.equal(service.diagnostics.writeErrors, 0)
    const files = fs.readdirSync(directory)
    assert.ok(files.some(name => name.endsWith('.jsonl')))
    const reportFile = files.find(name => name.startsWith('desync-first-'))
    assert.ok(reportFile)
    const report = JSON.parse(fs.readFileSync(path.join(directory, reportFile), 'utf8'))
    assert.equal(report.roomInstanceId, 'instance')
    assert.equal(report.battleSessionId, 'battle')
    assert.ok(report.fieldPath.includes('hp'))
})

test('extended heartbeats are consumed without ordinary ACK while normal heartbeats still ACK', () => {
    const frames = [], quiet = () => {}
    const client = { isBattle: true, connectionId: 'c11', viewerId: 11, roomNumber: 'room', roomGeneration: 1 }
    const manager = {
        findClientBySocket: () => client, isCurrentBattleClient: () => true, noteBattleActivity: quiet,
        sendJson: (_socket, data) => frames.push(data),
    }
    const api = fingerprints()
    const { handleBattleMessage } = loadCompiled('multi/tcp/battle.js', new Map([
        ['../state/SessionManager', { sessionManager: manager }],
        ['./relay', { relayToBattleRoom: quiet }],
        ['./chain-diagnostic', { recordBattleNotify: quiet }],
        ['../room/manager', { getRoom: () => undefined }],
        ['../five-boss/lobby-runtime', { recordFiveBossSignal: quiet }],
        ['../five-boss/connection-diagnostic', { fiveBossConnectionDiagnostics: { packet: quiet, socketEvent: quiet } }],
        ['../coordinator/business-facts', { notifyRealtimePresence: quiet }],
        ['../battle-telemetry', { battleTelemetry: { packet: quiet } }],
        ['../state/battle-contract', { markBattleMemberPhase: quiet }],
        ['../coordinator/room-start-claims', { deferPinnedRoomControl: () => false }],
        ['../coordinator/business-rpc', {}],
        ['./relay-recorder', { recordBattleFrame: quiet }],
        ['./state-fingerprint', { ...api, isStateFingerprintEnabled: () => false, handleBattleFingerprintNotify: quiet }],
    ]))
    handleBattleMessage({}, packet(api))
    assert.equal(frames.length, 0)
    handleBattleMessage({}, [0, [5]])
    assert.equal(frames.length, 1)
    assert.deepEqual(frames[0].slice(0, 1), [1])
    assert.deepEqual(frames[0][1].slice(0, 3), [3, 0, 0])
})

test('resource consistency is optional and forwards stale status through prepare and restore', async t => {
    const previous = process.env.MULTI_REQUIRE_CURRENT_ASSETS
    delete process.env.MULTI_REQUIRE_CURRENT_ASSETS
    t.after(() => {
        if (previous === undefined) delete process.env.MULTI_REQUIRE_CURRENT_ASSETS
        else process.env.MULTI_REQUIRE_CURRENT_ASSETS = previous
    })
    const decisions = [], lookups = []
    const identity = { instanceId: 'instance', generation: 1, battleSessionId: null, sceneEpoch: 0 }
    const gateway = {
        async execute(kind, payload) {
            if (kind === 'room.query') return { room_number: 'room', category: 2, quest_id: 1001, identity }
            decisions.push({ kind, payload })
            return { status: 'ready', connection: { room_number: 'room', raising_state: 1 } }
        },
    }
    const quiet = () => {}
    const routes = loadCompiled('multi/http/room.js', new Map([
        ['../../utils', { generateDataHeaders: () => ({}) }],
        ['../room/serializer', { getDisplayHost: () => 'test-host' }],
        ['../npc/builder', { buildNpcMates: () => ({}) }],
        ['../../lib/game-logging', { gameVerboseLog: quiet }],
        ['../mode15-room-gate', { isMode15RoomClosed: () => false }],
        ['../player-context', { resolveMultiPlayerContext: async () => ({ playerId: 1 }) }],
        ['../attention-config', { getAttentionConfig: () => ({}) }],
        ['../coordinator/default-runtime', { getRoomCommandGateway: () => gateway }],
        ['../coordinator/command-protocol', { createRoomCommandId: () => 'command', RoomCommandError: Error }],
        ['../../lib/version', { computeAssetTarget(version) {
            lookups.push(version)
            return { isFirstTime: version === 'first', targetVersion: '1.4.343' }
        } }],
    ]))
    const app = require('fastify')(), { pack } = require('msgpackr')
    app.addHook('onSend', (_request, reply, payload, done) =>
        done(null, reply.getHeader('content-type') === 'application/x-msgpack' ? pack(payload).toString('base64') : payload))
    routes.registerRoomRoutes(app)
    t.after(() => app.close())
    const request = (url, version) => app.inject({ method: 'POST', url,
        headers: version ? { res_ver: version } : {},
        payload: { viewer_id: 11, room_number: 'room', category: 2, quest_id: 1001 } })
    assert.equal((await request('/prepare', '1.4.136')).statusCode, 200)
    assert.equal(decisions.at(-1).payload.assetStale, false)
    assert.deepEqual(lookups, [])
    process.env.MULTI_REQUIRE_CURRENT_ASSETS = '1'
    for (const url of ['/prepare', '/restore_room']) {
        assert.equal((await request(url, '1.4.136')).statusCode, 200)
        assert.equal(decisions.at(-1).payload.assetStale, true)
    }
    for (const version of ['1.4.343', 'first', undefined]) {
        assert.equal((await request('/prepare', version)).statusCode, 200)
        assert.equal(decisions.at(-1).payload.assetStale, false)
    }
})
