'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { randomUUID } = require('node:crypto')
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require('../' + (compiled ? 'out/' : 'src/') + name)
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'production-multi-continue-'))
Object.assign(process.env, { DATA_DIR: directory, CN_WRITER_THREAD: '0', MULTI_REALTIME_PROCESS: '0',
    MULTI_REALTIME_OWNER_CHILD: '0', GAME_ROUTINE_LOGS: 'off', GAME_VERBOSE_LOGS: 'false',
    GACHA_SEED_DIR: path.join(directory, 'seeds') })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
let players, active, activeQuests, coordinator, withPlayerWriteQueue, db, app, seedValidator
test.before(async () => {
    const { getDb } = load('data/db')
    seedValidator = load('lib/seed-validator').default
    players = load('data/domains/player')
    active = load('data/domains/quest_active')
    activeQuests = load('routes/api/singleBattleQuest').activeQuests
    coordinator = load('lib/persistence-coordinator')
    withPlayerWriteQueue = load('lib/sqlite-write-coordinator').withPlayerWriteQueue
    db = getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object'
            ? JSON.stringify(body) : body))
    load('multi/http/battle').registerBattleRoutes(app)
    await app.ready()
})
test.after(async () => {
    await app?.close()
    await seedValidator?.close()
    if (db?.open) db.close()
    fs.rmSync(directory, { recursive: true })
})

function fixture(category, questId, continueCount = 0) {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '',
        idpCode: 'multi-continue-policy', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id)
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    const viewer = 876000000 + player.id, play = randomUUID(), room = 'room-' + player.id
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)')
        .run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    players.updatePlayerSync({ id: player.id, freeVmoney: 100, vmoney: 100, freeMana: 1000 })
    active.insertPlayerActiveQuestSync(player.id, { playerId: player.id, category, questId, playId: play,
        isMulti: true, isMultiHost: true, roomNumber: room, useBossBoostPoint: false,
        useBoostPoint: false, isAutoStartMode: false, continueCount, startedAtMs: Date.now(), clockVersion: 1 })
    return { id: player.id, viewer, play, category, questId, room }
}
function wallet(p) {
    const player = players.getPlayerSync(p.id)
    return [player.freeVmoney, player.vmoney, player.freeMana]
}
function post(p, overrides = {}) {
    return app.inject({ method: 'POST', url: '/play_continue', payload: {
        viewer_id: p.viewer, category: p.category, quest_id: p.questId, play_id: p.play,
        api_count: 1, statistics: { continue_count: 0 }, ...overrides,
    } })
}
async function rejectedWithoutMutation(p, overrides = {}) {
    const beforeRun = active.getPlayerActiveQuestSync(p.id), beforeWallet = wallet(p)
    const response = await post(p, overrides)
    assert.equal(response.statusCode, 400, response.body)
    assert.match(response.body, /difficulty/)
    assert.deepEqual(active.getPlayerActiveQuestSync(p.id), beforeRun)
    assert.deepEqual(wallet(p), beforeWallet)
}

test('real multiplayer HTTP rejects hell pumpkin and all seven highest five-boss rows without mutation', async () => {
    for (const [category, quest] of [[8, 300097005],
        ...[1099051, 1099052, 1099053, 1099054, 1099055, 1099056, 1099057].map(id => [2, id])]) {
        await rejectedWithoutMutation(fixture(category, quest))
    }
})

test('forged category/quest and cached low-tier identity cannot bypass the persisted highest-tier policy', async () => {
    for (const [category, quest] of [[8, 300097005], [2, 1099051], [2, 1099057]]) {
        const p = fixture(category, quest)
        activeQuests[p.id] = { playId: p.play, category: 1, questId: 1001, continueCount: 0, isMulti: true }
        for (const forged of [
            { category: 1, quest_id: 1001 }, { category: 8, quest_id: 300097004 },
            { category: 2, quest_id: 1099031 }, { category: 2, quest_id: 1099001 },
        ]) await rejectedWithoutMutation(p, forged)
        assert.equal(activeQuests[p.id].continueCount, 0)
        delete activeQuests[p.id]
    }
})

test('lower multiplayer tiers preserve their increment/no-debit behavior and use the persisted count', async () => {
    for (const [category, quest] of [[8, 300097001], [8, 300097004], [2, 1099002], [2, 1099031]]) {
        const p = fixture(category, quest, 2), beforeWallet = wallet(p)
        activeQuests[p.id] = { playId: p.play, category, questId: quest, continueCount: 99, isMulti: true }
        const response = await post(p, { category: 2, quest_id: 1099057 })
        assert.equal(response.statusCode, 200, response.body)
        assert.equal(response.json().data.continue_count, 3)
        assert.equal(active.getPlayerActiveQuestSync(p.id).continueCount, 3)
        assert.equal(activeQuests[p.id].continueCount, 3)
        assert.deepEqual(wallet(p), beforeWallet)
        assert.equal((await post(p)).json().data.continue_count, 4)
        delete activeQuests[p.id]
    }
})

test('transaction rechecks the persisted difficulty after waiting in the real player queue', async t => {
    const p = fixture(8, 300097004), beforeWallet = wallet(p)
    let release, entered
    const held = new Promise(resolve => { release = resolve })
    const blocker = withPlayerWriteQueue(p.id, () => held)
    const observed = new Promise(resolve => { entered = resolve })
    const original = coordinator.runPersistenceTransaction
    t.mock.method(coordinator, 'runPersistenceTransaction', (context, operation, options) => {
        const result = original(context, operation, options)
        if (context.playerId === p.id && context.operation === 'continue') entered()
        return result
    })
    const pending = post(p).then(response => response)
    try {
        await observed
        db.prepare('UPDATE players_active_quests SET quest_id=? WHERE player_id=?')
            .run(300097005, p.id)
    } finally { release() }
    await blocker
    const response = await pending
    assert.equal(response.statusCode, 400, response.body)
    assert.match(response.body, /difficulty/)
    assert.equal(active.getPlayerActiveQuestSync(p.id).questId, 300097005)
    assert.equal(active.getPlayerActiveQuestSync(p.id).continueCount, 0)
    assert.deepEqual(wallet(p), beforeWallet)
    delete activeQuests[p.id]
})

test('missing or replaced play retains the neutral stale acknowledgement without changing a newer run', async () => {
    const p = fixture(8, 300097005), beforeWallet = wallet(p), original = active.getPlayerActiveQuestSync(p.id)
    const stale = await post(p, { play_id: 'old-play' })
    assert.equal(stale.statusCode, 200, stale.body)
    assert.equal(stale.json().data.continue_count, 0)
    assert.deepEqual(active.getPlayerActiveQuestSync(p.id), original)
    active.deletePlayerActiveQuestSync(p.id)
    const missing = await post(p)
    assert.equal(missing.statusCode, 200, missing.body)
    assert.equal(missing.json().data.continue_count, 0)
    assert.equal(active.getPlayerActiveQuestSync(p.id), null)
    assert.deepEqual(wallet(p), beforeWallet)
})

test('registered legacy 1099001 keeps its paid-once handler, identity rejection and stale recovery', async () => {
    const p = fixture(2, 1099001), now = new Date().toISOString(), runId = randomUUID()
    db.prepare(`INSERT INTO five_boss_gauntlet_runs(run_id,host_player_id,route_id,room_number,ticket_item_id,
        expected_member_count,status,created_at,updated_at) VALUES (?,?,?,?,?,1,'active',?,?)`)
        .run(runId, p.id, 'five_boss_coop_v1', p.room, 10000143, now, now)
    db.prepare(`INSERT INTO five_boss_gauntlet_members(run_id,player_id,client_play_id,is_auto_mode,started_at)
        VALUES (?,?,?,0,?)`).run(runId, p.id, p.play, now)
    const invalid = await post(p, { quest_id: 1099003 })
    assert.equal(invalid.statusCode, 400, invalid.body)
    assert.deepEqual(wallet(p), [100, 100, 1000])
    const first = await post(p)
    assert.equal(first.statusCode, 200, first.body)
    assert.equal(first.json().data.continue_count, 1)
    assert.deepEqual(wallet(p), [50, 100, 1000])
    assert.equal(active.getPlayerActiveQuestSync(p.id).continueCount, 1)
    assert.equal((await post(p, { api_count: 99 })).statusCode, 200)
    assert.deepEqual(wallet(p), [50, 100, 1000])
    assert.equal(db.prepare('SELECT COUNT(*) AS count FROM five_boss_continue_receipts WHERE player_id=?')
        .get(p.id).count, 1)
    db.prepare('UPDATE five_boss_gauntlet_members SET finalized_at=? WHERE run_id=? AND player_id=?')
        .run(now, runId, p.id)
    const stale = await post(p)
    assert.equal(stale.statusCode, 200, stale.body)
    assert.equal(stale.json().data.continue_count, 1)
    assert.deepEqual(wallet(p), [50, 100, 1000])
    delete activeQuests[p.id]
})
