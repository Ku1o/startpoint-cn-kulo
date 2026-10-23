'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os')
const { randomUUID } = require('node:crypto'), { EventEmitter } = require('node:events'), { spawn } = require('node:child_process')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-rescue-pass-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', MULTI_REALTIME_PROCESS: '0',
    MULTI_REALTIME_OWNER_CHILD: '0', MULTI_SETTLEMENT_BARRIER_MS: '10', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const interval = global.setInterval
global.setInterval = (...args) => { const timer = interval(...args); timer.unref(); return timer }
const players = load('data/domains/player'), missions = load('data/domains/mission')
const master = load('lib/mission/master-data'), operations = load('lib/content-operations')
const rooms = load('multi/room/manager'), manager = load('multi/state/SessionManager').sessionManager
const recruitment = load('multi/recruitment')
global.setInterval = interval
const CATEGORY = 2, QUEST = 1001001
let db, app, activePass
class Socket extends EventEmitter {
    destroyed = false; readable = true; writable = true
    remoteAddress = '127.0.0.1'
    write() { return true }
    end() { this.writable = false }
    destroy() { this.destroyed = true; this.writable = false; this.emit('close') }
}
function player() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'history-rescue', idpId: randomUUID(), status: 'normal' })
    const p = players.insertDefaultPlayerSync(account.id), viewerId = 895000000 + p.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, p.id)
    load('data/domains/session').insertSessionWithTokenSync({ token: String(viewerId), accountId: account.id, type: 2, expires: new Date('2099-01-01T00:00:00Z') })
    return { id: p.id, viewerId }
}
const rescueMission = id => master.getMissionMasterDefinitions(7).find(row => row.eventId === id && row.patternType === 20).missionId
function control(id, enabled, claim = false, exclude = false) {
    const store = operations.contentOperations(), keys = [6, 7, 8].flatMap(category => master.getMissionMasterDefinitions(category)
        .filter(row => row.eventId === id).map(row => `${category}:${row.missionId}`))
    const review = { readiness: 'verified', evidence: 'Accepted random rescue server admission and native pass weekly condition20', endsAtMs: null }
    store.update(`pass_card_event:${id}`, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Synthetic historical rescue completed battle regression', actionOverrides: {
            visible: { ...review, enabled }, enter: { ...review, enabled, missionKeys: keys.filter(key => !exclude || key !== `7:${rescueMission(id)}`) },
            claim: { ...review, enabled: claim, missionKeys: keys },
        } }, Date.now())
}
function open(id) {
    if (activePass && activePass !== id) control(activePass, false, true)
    control(id, true); activePass = id
}
const post = (url, p, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: p.viewerId, api_count: 1, ...body } })
function data(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
const value = (p, event) => missions.getPlayerCategoryMissionsSync(p.id, 7)[rescueMission(event)]?.progress ?? 0
const registration = (p, play) => load('data/domains/player-operation-receipt').getPlayerOperationReceiptSync(p.id, 'mission.rescue_battle', play)
function enter(p, room) {
    const client = manager.createClient(new Socket(), p.viewerId, room.room_number, `rescue-test-${p.id}`, p.id)
    client.enterData = {}; client.isReady = true
    client.yourself = { viewerId: p.viewerId, playerId: p.id, connectionId: client.connectionId,
        comId: 0, currentPartyId: 1, state: [1], autoplayMode: false,
        party: { characters: [[0, { id: 1 }]], unison_characters: [], equipments: [], abilitySoulIds: [] } }
    manager.addClientToRoom(client); rooms.addRoomMember(room.room_number, p.viewerId, p.id)
    return client
}
async function setup(t, kind = 'rescue', category = CATEGORY, quest = QUEST) {
    const host = player(), guest = player()
    const mode = load('multi/five-boss/contract').FIVE_BOSS_GAUNTLET
    if (quest === mode.visibleQuestId) for (const p of [host, guest]) {
        players.updatePlayerSync({ id: p.id, rankPoint: 1000000000, stamina: 100, staminaHealTime: new Date() })
        load('data/domains/item').setPlayerItemSync(p.id, mode.ticketItemId, 10)
    }
    const room = rooms.createRoom(host.viewerId, host.id, 1, category, quest, 0, 1)
    const clients = [enter(host, room)]
    if (kind === 'rescue') {
        recruitment.publishRandomRecruitment(room.room_number)
        assert.equal(recruitment.takeRandomRecruitments(guest.viewerId, 1, row => row.roomNumber === room.room_number).length, 1)
    }
    const selected = data(await post('/lobby/select_room', guest, { room_number: room.room_number,
        category, quest_id: quest, accepted_type: kind === 'rescue' || kind === 'forged' ? 2 : 1 }))
    t.after(() => { manager.commitRoomDisband(room.room_number, 'history_rescue_test_cleanup'); clients.forEach(client => client.socket.destroy()) })
    if (kind === 'forged') { assert.equal(selected.data.port, 0); return { host, guest, room } }
    assert.ok(selected.data.port > 0)
    if (kind === 'helper') manager.markRescueGuest(room.room_number, guest.viewerId, true, false)
    clients.push(enter(guest, room)); clients.forEach(client => { client.mates = clients.map(peer => peer.yourself) })
    assert.equal(manager.isRescueFragmentEligibleGuest(room.room_number, guest.viewerId), kind === 'rescue')
    const play = randomUUID(), start = extra => post('/multi/start', guest, { category, quest_id: quest, party_id: 1,
        room_number: room.room_number, play_id: play, use_boost_point: false, use_boss_boost_point: false,
        is_auto_start_mode: false, mate_player_ids: [], mate_party_ids: [], is_rescue: true, ...extra })
    const body = { category, quest_id: quest, room_number: room.room_number, play_id: play,
        is_accomplished: true, elapsed_time_ms: 1000, score: 100, add_mana: 0, continue_count: 0,
        mate_player_result: [], is_rescue: true, statistics: { clear_phase: 1,
            party: { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null], equipments: [null, null, null], ability_soul_ids: [null, null, null] } } }
    return { host, guest, room, play, start, body, finish: extra => post('/multi/finish', guest, { ...body, ...extra }) }
}
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(async route => load('multi/http/lobby').registerLobbyRoutes(route), { prefix: '/lobby' })
    await app.register(async route => load('multi/http/battle').registerBattleRoutes(route), { prefix: '/multi' })
    await app.ready()
})
after(async () => {
    if (app) await app.close()
    load('multi/coordinator/default-runtime').getRoomCommandGateway().close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root); fs.rmSync(directory, { recursive: true })
})

test('all nineteen native pass rescue missions count an accepted random-rescue HTTP finish once', async t => {
    for (let event = 1; event <= 19; event++) {
        open(event)
        const x = await setup(t)
        const started = data(await x.start())
        assert.equal(started.data.play_id, x.play)
        assert.ok(registration(x.guest, x.play)); assert.equal(registration(x.host, x.play), null)
        const finished = data(await x.finish())
        assert.equal(finished.data_headers.result_code, 1)
        assert.equal(value(x.guest, event), 1, `pass${event}`)
        assert.equal(value(x.host, event), 0)
        data(await x.finish())
        assert.equal(value(x.guest, event), 1, `pass${event} replay`)
    }
})

test('forged notices, direct guests, generic helpers and failed rescues do not count', async t => {
    open(1)
    const forged = await setup(t, 'forged')
    assert.equal(manager.isRescueGuest(forged.room.room_number, forged.guest.viewerId), false)
    for (const kind of ['direct', 'helper']) {
        const x = await setup(t, kind)
        data(await x.start()); assert.equal(registration(x.guest, x.play), null)
        data(await x.finish())
        assert.equal(value(x.guest, 1), 0, kind)
    }
    const failed = await setup(t)
    data(await failed.start()); data(await failed.finish({ is_accomplished: false }))
    assert.equal(value(failed.guest, 1), 0)
})

test('publication closure and exact weekly scopes exclude new rescue progress without clearing retained state', async t => {
    open(1)
    const closed = await setup(t)
    missions.updatePlayerCategoryMissionSync(closed.guest.id, 7, rescueMission(1), 2)
    data(await closed.start()); control(1, false, true)
    data(await closed.finish()); assert.equal(value(closed.guest, 1), 2)
    control(1, true)
    assert.equal(value(closed.guest, 1), 2)
    const excluded = await setup(t)
    control(1, true, true, true)
    data(await excluded.start()); data(await excluded.finish())
    assert.equal(value(excluded.guest, 1), 0)
})

test('start registration and finished rescue facts roll back with their owning business transactions', async t => {
    open(1)
    const x = await setup(t)
    db.exec("CREATE TEMP TRIGGER fail_rescue_registration BEFORE INSERT ON player_operation_receipts WHEN NEW.operation='mission.rescue_battle' BEGIN SELECT RAISE(ABORT,'synthetic rescue start rollback'); END")
    assert.equal((await x.start()).statusCode, 500)
    db.exec('DROP TRIGGER fail_rescue_registration')
    assert.equal(load('data/domains/quest_active').getPlayerActiveQuestSync(x.guest.id), null)
    assert.equal(registration(x.guest, x.play), null)
    data(await x.start())
    db.exec(`CREATE TEMP TRIGGER fail_rescue_fact BEFORE INSERT ON players_category_missions WHEN NEW.player_id=${x.guest.id} AND NEW.category=7 AND NEW.id=${rescueMission(1)} BEGIN SELECT RAISE(ABORT,'synthetic rescue finish rollback'); END`)
    assert.equal((await x.finish()).statusCode, 500)
    db.exec('DROP TRIGGER fail_rescue_fact')
    assert.equal(value(x.guest, 1), 0)
    assert.equal(load('data/domains/quest_active').getPlayerActiveQuestSync(x.guest.id).playId, x.play)
    data(await x.finish()); assert.equal(value(x.guest, 1), 1)
})

test('a fresh process finishes from persistent rescue binding without owner memory or frozen snapshot', async t => {
    open(14)
    const x = await setup(t); data(await x.start())
    const childCode = `
      if(process.env.STARPOINT_TEST_COMPILED!=='1')require('ts-node/register/transpile-only');
      const assert=require('node:assert/strict');const load=n=>require('./'+(process.env.STARPOINT_TEST_COMPILED==='1'?'out':'src')+'/'+n);
      const interval=global.setInterval;global.setInterval=(...args)=>{const timer=interval(...args);timer.unref();return timer};
      (async()=>{load('data').initializeDatabase();const db=load('data/db').getDb();const x=JSON.parse(process.env.STARPOINT_RESCUE_FIXTURE);
      const app=require('fastify')({logger:false});app.addHook('onSend',(_req,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')&&typeof body==='object'?JSON.stringify(body):body));
      load('multi/http/battle').registerBattleRoutes(app);await app.ready();
      assert.equal(load('multi/settlement-snapshot').getMultiSettlementSnapshot(x.playerId,x.body.play_id),undefined);
      const result=await app.inject({method:'POST',url:'/finish',payload:{viewer_id:x.viewerId,...x.body}});
      assert.equal(result.statusCode,200,result.body);assert.equal(result.json().data_headers.result_code,1);
      assert.equal(load('data/domains/mission').getPlayerCategoryMissionsSync(x.playerId,7)[56].progress,1);
      await app.close();load('multi/coordinator/default-runtime').getRoomCommandGateway().close();await load('lib/seed-validator').default.close();db.close();
      console.log('fresh rescue finish passed');})().catch(error=>{console.error(error);process.exitCode=1});`
    const output = await new Promise((resolve, reject) => {
        const child = spawn(process.execPath, ['-e', childCode], { cwd: path.resolve(__dirname, '..'), windowsHide: true,
            env: { ...process.env, STARPOINT_RESCUE_FIXTURE: JSON.stringify({ playerId: x.guest.id, viewerId: x.guest.viewerId, body: x.body }) } })
        let output = ''
        const timer = setTimeout(() => { child.kill(); reject(new Error('fresh rescue finish timed out')) }, 20000)
        child.stdout.on('data', data => { output += data }); child.stderr.on('data', data => { output += data })
        child.on('error', error => { clearTimeout(timer); reject(error) })
        child.on('exit', code => { clearTimeout(timer); code === 0 ? resolve(output) : reject(new Error(output)) })
    })
    assert.match(output, /fresh rescue finish passed/)
    assert.equal(value(x.guest, 14), 1)
    data(await x.finish()); assert.equal(value(x.guest, 14), 1)
})

test('five-boss rescued guests count only one successful final run receipt, never phase signals, failed runs or direct helpers', async t => {
    open(1)
    const mode = load('multi/five-boss/contract').FIVE_BOSS_GAUNTLET
    const ledger = load('data/domains/fiveBossGauntletRun')
    for (const kind of ['rescue', 'direct', 'failed', 'closed']) {
        const x = await setup(t, kind === 'direct' ? 'direct' : 'rescue', mode.category, mode.visibleQuestId)
        const started = data(await x.start())
        assert.equal(started.data.play_id, x.play)
        assert.equal(!!registration(x.guest, x.play), kind !== 'direct')
        assert.equal(missions.getPlayerCategoryMissionsSync(x.host.id, 6)[4]?.progress, mode.staminaCost)
        assert.equal(missions.getPlayerCategoryMissionsSync(x.host.id, 7)[1]?.progress, mode.staminaCost)
        assert.equal(missions.getPlayerCategoryMissionsSync(x.guest.id, 6)[4]?.progress ?? 0, 0)
        data(await x.start())
        assert.equal(missions.getPlayerCategoryMissionsSync(x.host.id, 6)[4]?.progress, mode.staminaCost, 'a repeated or guest-first run start charges and records the host once')
        const run = ledger.getFiveBossRunByClientSync({ playerId: x.guest.id, clientPlayId: x.play })
        assert.ok(run)
        for (const signal of ['scene_ready', 'level_next', 'finalize']) {
            ledger.recordMemberBattleSignalSync({ runId: run.runId, playerId: x.guest.id, roomNumber: x.room.room_number, signal })
            assert.equal(value(x.guest, 1), 0, signal)
        }
        if (kind === 'closed') control(1, false, true)
        const first = data(await x.finish({ is_accomplished: kind !== 'failed' }))
        assert.equal(first.data_headers.result_code, 1)
        assert.equal(value(x.guest, 1), kind === 'rescue' ? 1 : 0)
        const count = db.prepare('SELECT COUNT(*) AS n FROM five_boss_gauntlet_receipts WHERE run_id=? AND player_id=?').get(run.runId, x.guest.id).n
        assert.equal(count, kind === 'failed' ? 0 : 1)
        if (kind === 'closed') control(1, true)
        data(await x.finish({ is_accomplished: kind !== 'failed' }))
        assert.equal(value(x.guest, 1), kind === 'rescue' ? 1 : 0, 'old or replayed final receipts never backfill mission progress')
    }
})
