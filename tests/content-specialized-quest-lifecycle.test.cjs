const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = modulePath => require(`../${compiled ? 'out' : 'src'}/${modulePath}`)

const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')
const temporaryRoot = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(temporaryRoot, { recursive: true })
const directory = fs.mkdtempSync(path.join(temporaryRoot, 'specialized-quest-lifecycle-'))
Object.assign(process.env, {
    DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0',
    GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off',
})
fs.mkdirSync(process.env.GACHA_SEED_DIR)

const db = load('data/db').getDb()
const players = load('data/domains/player')
const quests = load('data/domains/quest')
const active = load('data/domains/quest_active')
const items = load('data/domains/item')
const operations = load('lib/content-operations')
const coordinator = load('lib/persistence-coordinator')
const originalTransaction = coordinator.runPersistenceTransaction
const raidKey = 'raid_event:7', storyKey = 'world_story_event:400001'
let app

function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'lifecycle', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id)
    const viewer = 870000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00.000Z')
    return { id: player.id, viewer }
}

function control(key, enabled, questKeys) {
    const store = operations.contentOperations()
    const review = { endsAtMs: null, readiness: 'verified', evidence: 'Synthetic native API lifecycle regression' }
    return store.update(key, {
        expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Isolated lifecycle regression',
        actionOverrides: {
            visible: { ...review, enabled: true },
            enter: { ...review, enabled, questKeys },
        },
    }, Date.now())
}

function state(playerId) {
    return {
        portable: load('data/snapshots/player-snapshot').createPlayerSaveSnapshotV2Sync(playerId, db).data.tables,
        active: active.getPlayerActiveQuestSync(playerId),
    }
}

async function post(player, url, body = {}) {
    const response = await app.inject({ method: 'POST', url, payload: { viewer_id: player.viewer, api_count: 1, ...body } })
    assert.equal(response.statusCode, 200, response.body)
    return response.json()
}

function raidBody(playId = randomUUID(), questId = 7001) {
    return { event_id: 7, quest_id: questId, party_group_id: 1, play_id: playId, use_auto_start_point: false, is_auto_start_mode: false }
}

async function closeAfterAdmission(operation, close, request) {
    let reached = false
    coordinator.runPersistenceTransaction = async (context, callback, options) => {
        if (context.operation === operation) { reached = true; close() }
        return originalTransaction(context, callback, options)
    }
    try {
        const response = await request()
        assert.ok(reached, 'fixture must close the operation after the initial admission check')
        assert.equal(response.data_headers.result_code, 4050)
    } finally {
        coordinator.runPersistenceTransaction = originalTransaction
    }
}

before(async () => {
    assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory) + path.sep))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object'
            ? JSON.stringify(body) : body))
    await app.register(load('routes/api/raidEvent').default, { prefix: '/event/raid' })
    await app.register(load('routes/api/storyQuest').default, { prefix: '/story_quest' })
    await app.register(load('routes/api/questUnlock').default, { prefix: '/quest' })
    await app.ready()
})

after(async () => {
    coordinator.runPersistenceTransaction = originalTransaction
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db.open) db.close()
    assert.equal(path.dirname(directory), temporaryRoot)
    fs.rmSync(directory, { recursive: true })
})

test('Raid7 initializes from its real summary and closed/scoped starts never alter progress or charge', async () => {
    const player = fixture()
    control(raidKey, false, ['23:7001'])
    const summary = await post(player, '/event/raid/summary', { event_id: 7 })
    assert.equal(summary.data_headers.result_code, 1)
    assert.equal(summary.data.endless_battle_next_round, 1)
    assert.ok(db.prepare('SELECT 1 FROM players_rush_events WHERE player_id=? AND event_id=7').get(player.id))
    const before = state(player.id)
    assert.equal((await post(player, '/event/raid/battle/start', raidBody())).data_headers.result_code, 4050)
    assert.deepEqual(state(player.id), before)
    control(raidKey, true, ['23:7001'])
    assert.equal((await post(player, '/event/raid/battle/start', raidBody(randomUUID(), 7002))).data_headers.result_code, 4050)
    assert.deepEqual(state(player.id), before)
    await closeAfterAdmission('raid_start', () => control(raidKey, false, ['23:7001']), () => post(player, '/event/raid/battle/start', raidBody()))
    assert.deepEqual(state(player.id), before)
    control(raidKey, true, ['23:7001'])
    const body = raidBody()
    assert.equal((await post(player, '/event/raid/battle/start', body)).data_headers.result_code, 1)
    const started = state(player.id)
    assert.equal(started.active.playId, body.play_id)
    assert.equal(started.active.category, 23)
    assert.equal(started.active.questId, 7001)
    assert.deepEqual(started.portable, before.portable)
    control(raidKey, false, ['23:7001'])
    assert.equal((await post(player, '/event/raid/battle/start', body)).data_headers.result_code, 1)
    assert.deepEqual(state(player.id), started, 'exact committed replay retains its original start clock and state')
    assert.equal((await post(player, '/event/raid/battle/start', raidBody())).data_headers.result_code, 4050)
    assert.deepEqual(state(player.id), started)
})

test('Raid folder selection and reset recheck closure without clearing existing parties or progress', async () => {
    const player = fixture()
    control(raidKey, false, ['23:7001'])
    await post(player, '/event/raid/summary', { event_id: 7 })
    db.prepare('UPDATE players_rush_events SET active_rush_battle_folder_id=1 WHERE player_id=? AND event_id=7').run(player.id)
    db.prepare('INSERT INTO players_rush_events_played_parties(player_id,event_id,round,battle_type,character_id_1) VALUES(?,7,7001,?,111001)')
        .run(player.id, load('data/types').RushEventBattleType.FOLDER)
    const before = state(player.id)
    const requests = [
        ['raid_select_folder', '/event/raid/select_folder', { event_id: 7, folder_id: 2 }],
        ['raid_reset', '/event/raid/reset', { event_id: 7, quest_type: 1 }],
    ]
    for (const [operation, url, body] of requests) {
        assert.equal((await post(player, url, body)).data_headers.result_code, 4050)
        assert.deepEqual(state(player.id), before)
        control(raidKey, true, ['23:7001'])
        await closeAfterAdmission(operation, () => control(raidKey, false, ['23:7001']), () => post(player, url, body))
        assert.deepEqual(state(player.id), before)
    }
    control(raidKey, true, ['23:7001'])
    assert.equal((await post(player, '/event/raid/select_folder', { event_id: 7, folder_id: 2 })).data_headers.result_code, 1)
    assert.equal(db.prepare('SELECT active_rush_battle_folder_id value FROM players_rush_events WHERE player_id=? AND event_id=7').get(player.id).value, 2)
    assert.equal((await post(player, '/event/raid/reset', { event_id: 7, quest_type: 1 })).data_headers.result_code, 1)
    assert.equal(db.prepare('SELECT COUNT(*) count FROM players_rush_events_played_parties WHERE player_id=? AND event_id=7').get(player.id).count, 0)
})

test('closed Raid summary still grants accrued global kill rewards exactly once', async () => {
    const player = fixture()
    control(raidKey, false, ['23:7001'])
    db.prepare('INSERT OR REPLACE INTO raid_event_global_state VALUES(7,200,0,5,?)').run(Date.now())
    db.prepare('INSERT INTO players_raid_event_overall_rewards VALUES(?,7,199,?)').run(player.id, Date.now())
    const before = players.getPlayerSync(player.id)
    const response = await post(player, '/event/raid/summary', { event_id: 7 })
    assert.equal(response.data_headers.result_code, 1)
    assert.equal(response.data.kill_count_reward_data.received_up_to, 200)
    const rewarded = state(player.id)
    assert.equal(players.getPlayerSync(player.id).freeVmoney, before.freeVmoney + 600)
    await post(player, '/event/raid/summary', { event_id: 7 })
    assert.deepEqual(state(player.id), rewarded)
    const rankingReward = await post(player, '/event/raid/ranking_reward', { event_id: 7 })
    assert.equal(rankingReward.data_headers.result_code, 1)
})

test('both story completion endpoints reject new closed/scoped grants but preserve completed replay', async () => {
    for (const endpoint of ['/story_quest/finish', '/story_quest/finish_with_skip']) {
        const player = fixture()
        const body = { category: 18, quest_id: 400001001, party_id: 1 }
        control(storyKey, false, ['18:400001001'])
        const before = state(player.id)
        assert.equal((await post(player, endpoint, body)).data_headers.result_code, 4050)
        assert.deepEqual(state(player.id), before)
        control(storyKey, true, ['18:400001001'])
        assert.equal((await post(player, endpoint, { ...body, quest_id: 400001002 })).data_headers.result_code, 4050)
        await closeAfterAdmission('story_finish', () => control(storyKey, false, ['18:400001001']), () => post(player, endpoint, body))
        assert.deepEqual(state(player.id), before)
        control(storyKey, true, ['18:400001001'])
        assert.equal((await post(player, endpoint, body)).data_headers.result_code, 1)
        assert.ok(quests.getPlayerSingleQuestProgressSync(player.id, 18, body.quest_id).finished)
        const rewarded = state(player.id)
        assert.notDeepEqual(rewarded, before)
        control(storyKey, false, ['18:400001001'])
        assert.equal((await post(player, endpoint, body)).data_headers.result_code, 1)
        assert.deepEqual(state(player.id), rewarded, 'closed completed story replay must not grant twice')
    }
})

test('seasonal paid unlock checks parent, exact child and transaction closure without charging', async () => {
    const player = fixture(), body = { category: 18, quest_id: 400001102 }
    items.setPlayerItemSync(player.id, 60001, 4)
    control(storyKey, false, ['18:400001102'])
    const before = state(player.id)
    assert.equal((await post(player, '/quest/unlock', body)).data_headers.result_code, 4050)
    assert.deepEqual(state(player.id), before)
    control(storyKey, true, ['18:400001001'])
    assert.equal((await post(player, '/quest/unlock', body)).data_headers.result_code, 4050)
    control(storyKey, true, ['18:400001102'])
    await closeAfterAdmission('quest_unlock', () => control(storyKey, false, ['18:400001102']), () => post(player, '/quest/unlock', body))
    assert.deepEqual(state(player.id), before)
    control(storyKey, true, ['18:400001102'])
    assert.equal((await post(player, '/quest/unlock', body)).data_headers.result_code, 1)
    assert.equal(items.getPlayerItemSync(player.id, 60001), 3)
    assert.ok(quests.getPlayerSingleQuestProgressSync(player.id, 18, body.quest_id).unlocked)
    const unlocked = state(player.id)
    control(storyKey, false, ['18:400001102'])
    const replay = await app.inject({ method: 'POST', url: '/quest/unlock', payload: { ...body, viewer_id: player.viewer } })
    assert.equal(replay.statusCode, 400, 'existing already-unlocked response stays unchanged')
    assert.deepEqual(state(player.id), unlocked, 'closed replay must preserve unlock and never spend again')
})

test('ordinary main story and ordinary main unlock retain their original availability', async () => {
    const player = fixture()
    const main = require('../assets/main_quest.json')
    const storyId = Number(Object.keys(main).find(id => main[id].clearRewardId !== undefined && main[id].sPlusRewardId === undefined))
    assert.ok(storyId)
    assert.equal(operations.contentQuestDecision(1, storyId), null)
    assert.equal((await post(player, '/story_quest/finish', { category: 1, quest_id: storyId, party_id: 1 })).data_headers.result_code, 1)
    const unlockId = Number(Object.keys(main).find(id => Number(id) !== storyId && !require('../assets/quest_unlock_costs.json')[id]))
    assert.ok(unlockId)
    assert.equal((await post(player, '/quest/unlock', { category: 1, quest_id: unlockId })).data_headers.result_code, 1)
})
