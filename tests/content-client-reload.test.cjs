'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const Sqlite = require('better-sqlite3')
// Source-only verification: no out/, services or workspace database writes.
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    fileName: filename,
}).outputText, filename)
const reload = require('../src/lib/content-client-reload.ts')

function fixture(t) {
    const db = new Sqlite(':memory:')
    t.after(() => db.close())
    db.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY,progress TEXT); INSERT INTO players VALUES(1,'keep');
        CREATE TABLE sessions(token TEXT PRIMARY KEY); INSERT INTO sessions VALUES('keep-zat');
        CREATE TABLE player_login_sessions(token TEXT PRIMARY KEY); INSERT INTO player_login_sessions VALUES('keep-login');
        CREATE TABLE players_active_quests(play_id TEXT PRIMARY KEY,player_id INTEGER); INSERT INTO players_active_quests VALUES('old-battle',1)`)
    return { db, store: new reload.ContentClientReloadStore(db) }
}

test('reload CAS and audit are atomic, epoch zero preserves existing sessions and global state stays outside player ownership', t => {
    const { db, store } = fixture(t)
    const preserved = () => ['players', 'sessions', 'player_login_sessions', 'players_active_quests'].map(table => db.prepare(`SELECT * FROM ${table}`).all())
    const before = preserved()
    assert.deepEqual(store.state(), { epoch: 0, updatedAtMs: null })
    assert.equal(store.required(100), false)
    assert.deepEqual(store.request(0, 123), { epoch: 1, updatedAtMs: 123 })
    assert.equal(store.required(100), true)
    assert.throws(() => store.request(0), reload.ContentClientReloadConflict)
    assert.equal(db.prepare('SELECT count(*) AS n FROM content_client_reload_audit').get().n, 1)
    db.exec("CREATE TRIGGER fail_reload_audit BEFORE INSERT ON content_client_reload_audit BEGIN SELECT RAISE(ABORT,'fixture audit failure'); END")
    assert.throws(() => store.request(1), /fixture audit failure/)
    assert.equal(store.state().epoch, 1, 'failed audit must roll back epoch')
    assert.deepEqual(preserved(), before, 'credentials, progress and old battle registration are untouched')
    for (const table of ['content_client_reload_meta', 'content_client_reload_ack', 'content_client_reload_audit', 'content_client_reload_plays']) {
        assert.deepEqual(db.prepare(`PRAGMA foreign_key_list(${table})`).all(), [])
        assert.equal(table.startsWith('players_'), false)
    }
    store.acknowledge(100, 1)
    const reopened = new Sqlite(db.serialize())
    t.after(() => reopened.close())
    const restoredStore = new reload.ContentClientReloadStore(reopened)
    assert.equal(restoredStore.state().epoch, 1)
    assert.equal(restoredStore.required(100), false)
    assert.equal(restoredStore.required(101), true, 'reload epoch and acknowledgements survive connection replacement')
})

test('only owner-observed committed current plays with the exact durable viewer/play identity get reload protection', t => {
    const { db, store } = fixture(t)
    db.exec(`ALTER TABLE players ADD COLUMN account_id INTEGER;
        UPDATE players SET account_id=10 WHERE id=1; INSERT INTO players VALUES(2,'orphan-progress',20);
        ALTER TABLE sessions ADD COLUMN account_id INTEGER; ALTER TABLE sessions ADD COLUMN type INTEGER;
        INSERT INTO sessions VALUES('101',10,2); INSERT INTO sessions VALUES('202',20,2);
        ALTER TABLE players_active_quests ADD COLUMN room_number TEXT;
        ALTER TABLE players_active_quests ADD COLUMN category INTEGER;
        ALTER TABLE players_active_quests ADD COLUMN quest_id INTEGER;
        ALTER TABLE players_active_quests ADD COLUMN is_multi INTEGER;
        UPDATE players_active_quests SET room_number='active-room',category=12,quest_id=34,is_multi=1;
        INSERT INTO players_active_quests VALUES('unaffected-orphan',2,'orphan-room',12,35,1)`)
    const play = { viewerId: 101, playerId: 1, playId: 'old-battle', roomNumber: 'active-room', category: 12, questId: 34 }
    const wrongIdentity = { viewerId: 101, playerId: 2, playId: 'unaffected-orphan', roomNumber: 'orphan-room', category: 12, questId: 35 }
    const before = db.prepare('SELECT * FROM players_active_quests ORDER BY player_id').all()
    store.request(0, 200, [play, wrongIdentity])
    assert.equal(store.preservesPlay(1, 'old-battle'), true)
    assert.equal(store.preservesPlay(2, 'unaffected-orphan'), false)
    assert.equal(store.preservesPlay(1, 'different-play'), false)
    assert.deepEqual(db.prepare('SELECT * FROM players_active_quests ORDER BY player_id').all(), before)
    // Native retirement stays unrecoverable. Protection never fabricates a restore capability.
    const { classifyMultiActiveQuestRecovery } = require('../src/lib/multi-active-quest-recovery.ts')
    const decision = classifyMultiActiveQuestRecovery({ isMulti: true, roomNumber: 'active-room', category: 12, questId: 34, playId: 'old-battle' }, {
        lifecycle: { phase: 'BATTLE', instanceId: 'same-room' }, expected_real_viewer_ids: [101], member_viewer_ids: [101], category: 12, quest_id: 34,
    }, 101, true)
    assert.equal(decision.recoverable, false)
    assert.equal(decision.reason, 'member_not_in_battle')
    assert.equal(store.preservesPlay(1, 'old-battle'), true)
    store.acknowledge(101, 1)
    store.pruneFinishedPlays(1)
    assert.equal(store.preservesPlay(1, 'old-battle'), true, 'successful load does not erase registered old play protection')
    db.prepare('DELETE FROM players_active_quests WHERE player_id=? AND play_id=?').run(1, 'old-battle')
    store.pruneFinishedPlays(1)
    assert.equal(store.preservesPlay(1, 'old-battle'), false, 'protection retires only after active play is actually gone')
})

test('owner preview excludes retired, uncommitted and disconnected battle bindings without opening a DB', t => {
    const { SessionManager } = require('../src/multi/state/SessionManager.ts')
    const contract = require('../src/multi/state/battle-contract.ts')
    const manager = new SessionManager()
    const room = { lifecycle: { phase: 'BATTLE', instanceId: 'room', battleSessionId: 'battle', sceneEpoch: 0 }, lobby_generation: 1,
        expected_real_viewer_ids: [101, 202, 303, 404], member_viewer_ids: [101, 202, 303, 404],
        member_player_ids: { 101: 1, 202: 2, 303: 3, 404: 4 }, category: 12, quest_id: 34 }
    contract.ensureBattleSessionContract(room)
    contract.bindBattlePlay(room, 101, 1, 'current-play')
    contract.bindBattlePlay(room, 202, 2, 'already-retired')
    contract.markBattleMemberPhase(room, 202, 'RETIRED')
    contract.bindBattlePlay(room, 404, 4, 'disconnected-play')
    for (const viewerId of [101, 202, 303, 404]) manager.clients.set(String(viewerId), { viewerId, roomNumber: 'active-room', socket: { destroyed: viewerId === 404 } })
    const Module = require('node:module'), original = Module._load
    Module._load = function (id, ...args) { return id === '../room/manager' ? { getRoom: () => room } : original.call(this, id, ...args) }
    try {
        assert.deepEqual(manager.contentReloadActivePlays(), [{ viewerId: 101, playerId: 1, playId: 'current-play', roomNumber: 'active-room', category: 12, questId: 34 }])
    } finally { Module._load = original }
})

test('bulk transport selection closes stale lobby and battle-only sockets once, leaving acknowledged viewers connected', async t => {
    const previousRole = process.env.MULTI_REALTIME_OWNER_CHILD
    process.env.MULTI_REALTIME_OWNER_CHILD = '1' // Any accidental player DB access must fail closed.
    t.after(() => { if (previousRole === undefined) delete process.env.MULTI_REALTIME_OWNER_CHILD; else process.env.MULTI_REALTIME_OWNER_CHILD = previousRole })
    const { SessionManager } = require('../src/multi/state/SessionManager.ts')
    const manager = new SessionManager()
    const Socket = require('node:net').Socket
    const lobby = new Socket(), battle = new Socket(), acknowledged = new Socket(), dead = new Socket()
    t.after(() => { lobby.destroy(); battle.destroy(); acknowledged.destroy(); dead.destroy() })
    dead.destroy()
    let closes = 0
    lobby.once('close', () => { closes++ })
    battle.once('close', () => { closes++ })
    const oldLobby = { viewerId: 101, socket: lobby }
    manager.clients.set('lobby', oldLobby)
    manager.clients.set('acknowledged', { viewerId: 202, socket: acknowledged })
    manager.clients.set('already-closed', { viewerId: 303, socket: dead })
    manager.cidToBattleClient.set('duplicate-lobby-reference', oldLobby)
    manager.cidToBattleClient.set('battle-without-lobby', { viewerId: 101, socket: battle })
    assert.deepEqual(manager.contentReloadViewerIds().sort(), [101, 202])
    assert.deepEqual(manager.disconnectAllForContentReload(new Set([101, 999])), [101])
    assert.equal(lobby.destroyed, true)
    assert.equal(battle.destroyed, true)
    assert.equal(acknowledged.destroyed, false)
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(closes, 2)
})

test('load acknowledgement cannot clear a newer signal or regress a newer acknowledgement, and rollback leaves stale clients stale', t => {
    const { db, store } = fixture(t)
    store.request(0)
    const capturedEpoch = store.state().epoch
    store.request(1)
    store.acknowledge(101, capturedEpoch)
    assert.equal(store.required(101), true)
    store.acknowledge(101, 2)
    assert.equal(store.required(101), false)
    store.acknowledge(101, 1)
    assert.equal(store.required(101), false)
    assert.throws(() => db.transaction(() => { store.acknowledge(102, 2); throw new Error('failed load') })(), /failed load/)
    assert.equal(store.required(102), true)
    assert.throws(() => store.acknowledge(102, 3), /Invalid reload acknowledgement/)
    assert.equal(store.required(102), true)
})

test('CN and legacy HTTP stale sessions get native 101 while load/auth/assets/bootstrap and management routes stay available', async t => {
    const { store } = fixture(t)
    const app = require('fastify')()
    t.after(() => app.close())
    require('../src/lib/cn-response-hook.ts').installCnResponseEncoding(app, {
        pool: { encode: require('../src/lib/cn-response-encoding.ts').encodeCnResponse, close: async () => {} },
        compression: { mode: 'off', log: false },
    })
    const decode = result => require('msgpackr').unpack(Buffer.from(result.body, 'base64'))
    reload.installContentClientReloadGuard(app, { store: () => store, headers: viewerId => ({ viewer_id: viewerId, result_code: 101, servertime: 12345 }) })
    const prefixes = ['/api/index.php', '/latest/api/index.php']
    for (const prefix of prefixes) for (const endpoint of ['load', 'tool/auth', 'tool/signup', 'asset/get_path', 'content_operations', 'party/edit']) {
        app.post(`${prefix}/${endpoint}`, async () => ({ ok: true }))
    }
    app.post('/api/server/clientReload', async () => ({ ok: true }))
    store.request(0)
    for (const prefix of prefixes) {
        for (const endpoint of ['load', 'tool/auth', 'tool/signup', 'asset/get_path']) {
            const result = await app.inject({ method: 'POST', url: `${prefix}/${endpoint}?bootstrap=1`, payload: { viewer_id: 101 } })
            assert.deepEqual(result.json(), { ok: true })
        }
        for (const endpoint of ['content_operations', 'party/edit']) {
            const stale = await app.inject({ method: 'POST', url: `${prefix}/${endpoint}?ignore=1`, payload: { viewer_id: 101 } })
            assert.equal(stale.statusCode, 200, stale.body)
            assert.equal(decode(stale).data_headers.result_code, 101)
            assert.equal(decode(stale).data_headers.servertime, 12345)
            assert.equal(decode(stale).data.message, reload.CONTENT_CLIENT_RELOAD_MESSAGE)
            assert.deepEqual((await app.inject({ method: 'POST', url: `${prefix}/${endpoint}`, payload: {} })).json(), { ok: true })
        }
    }
    assert.deepEqual((await app.inject({ method: 'POST', url: '/api/server/clientReload', payload: { viewer_id: 101 } })).json(), { ok: true })
    store.acknowledge(101, 1)
    assert.deepEqual((await app.inject({ method: 'POST', url: '/api/index.php/content_operations', payload: { viewer_id: 101 } })).json(), { ok: true })
    assert.equal(store.required(102), true, 'another viewer still needs a successful load')
})
