'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os')
const { randomUUID } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-pass-facts-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const players = load('data/domains/player'), missions = load('data/domains/mission')
const master = load('lib/mission/master-data'), operations = load('lib/content-operations')
let db, app
function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'history-pass-facts', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 890000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    return { id: player.id, viewer }
}
function control(enabled, claim = false, excluded = []) {
    const store = operations.contentOperations()
    const allKeys = [6, 7, 8].flatMap(category => master.getMissionMasterDefinitions(category)
        .filter(row => row.eventId === 1).map(row => `${category}:${row.missionId}`))
    const review = { readiness: 'verified', evidence: 'Original historical pass1 conditions and accepted finish facts', endsAtMs: null }
    store.update('pass_card_event:1', { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Synthetic historical pass exact fact regression', actionOverrides: {
            visible: { ...review, enabled: true },
            enter: { ...review, enabled, missionKeys: allKeys.filter(key => key !== '7:4' && !excluded.includes(key)) },
            claim: { ...review, enabled: claim, missionKeys: allKeys },
        } }, Date.now())
}
const post = (p, url, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: p.viewer, api_count: 1, ...body } })
function response(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
const value = (p, category, id) => missions.getPlayerCategoryMissionsSync(p.id, category)[id]?.progress ?? 0
const read = p => post(p, '/mission/get_mission_progress', { category_list: [6, 7, 8].map(category => ({ category, event_id: 1 })) })
async function battle(p, stats = {}, success = true) {
    const play = randomUUID(), category = 1, quest = 1001002
    const start = response(await post(p, '/single/start', { category, quest_id: quest, party_id: 1, play_id: play,
        use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false }))
    assert.equal(start.data_headers.result_code, 1)
    const body = { category, quest_id: quest, play_id: play, continue_count: 0, elapsed_time_ms: 1000, score: 12345,
        add_mana: 0, is_accomplished: success, is_restored: false,
        statistics: { clear_phase: 1, party: { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
            equipments: [null, null, null], ability_soul_ids: [null, null, null] }, zones: [], ...stats } }
    const finish = response(await post(p, '/single/finish', body))
    assert.equal(finish.data_headers.result_code, 1)
    return { body, finish }
}
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/singleBattleQuest').default, { prefix: '/single' })
    await app.register(load('routes/api/mission').default, { prefix: '/mission' })
    await app.ready()
})
after(async () => {
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root)
    fs.rmSync(directory, { recursive: true })
})

test('controlled historical pass reads never backfill old lifetime, periodic or login totals', async () => {
    const p = fixture(); control(true)
    players.updatePlayerSync({ id: p.id, totalDashes: 999999, totalStaminaUsed: 999999, totalLoginDays: 999 })
    db.prepare('INSERT INTO players_pass_cards(player_id,event_id,point,is_buy,login_baseline) VALUES(?,?,?,?,?)').run(p.id, 1, 0, 0, 0)
    for (let index = 0; index < 3; index++) load('data/domains/mission_battle_facts').recordMissionBattleResultSync(p.id,
        { isMulti: false, isHost: false, accomplished: true, clearRank: 5 })
    missions.updatePlayerCategoryMissionSync(p.id, 7, 4, 2)
    response(await read(p))
    for (const category of [6, 7, 8]) for (const row of master.getMissionMasterDefinitions(category).filter(row => row.eventId === 1)) {
        assert.equal(value(p, category, row.missionId), category === 7 && row.missionId === 4 ? 2 : 0)
    }
    assert.equal(db.prepare('SELECT login_baseline FROM players_pass_cards WHERE player_id=? AND event_id=1').get(p.id).login_baseline, 0)
    assert.equal(db.prepare("SELECT COUNT(*) AS n FROM players_periodic_snapshots WHERE player_id=? AND period_type LIKE 'pass_week_%'").get(p.id).n, 0)
})

test('real single finish, replay, closure and reopening only count enabled new pass battle facts', async () => {
    const p = fixture(); control(true)
    const first = await battle(p, { use_dash_count: 2 })
    assert.equal(value(p, 6, 1), 1); assert.equal(value(p, 6, 2), 2)
    assert.equal(value(p, 6, 3), 0); assert.equal(value(p, 7, 2), 0)
    response(await post(p, '/single/finish', first.body))
    assert.equal(value(p, 6, 2), 2)
    control(false)
    await battle(p, { use_dash_count: 1000, use_emotion_count: 5 })
    control(true)
    response(await read(p))
    assert.equal(value(p, 6, 2), 2, 'a reopened pass must not catch up closed interval dash totals')
    assert.equal(value(p, 7, 3), 0)
    await battle(p, { use_dash_count: 2 })
    assert.equal(value(p, 6, 2), 4)
    await battle(p, { use_dash_count: 1000, use_emotion_count: 2 }, false)
    assert.equal(value(p, 6, 2), 4, 'failed finishes do not count successful-clear dash facts')
    assert.equal(value(p, 7, 3), 2, 'existing emotion facts accept failed battles')
    assert.equal(value(p, 7, 4), 0, 'ordinary or failed battles cannot impersonate a completed accepted rescue')
})

test('exact daily scopes, multi facts and transaction rollback retain original progress', async () => {
    const p = fixture(); control(true, false, ['6:2'])
    missions.updatePlayerCategoryMissionSync(p.id, 6, 1, 99)
    await battle(p, { use_dash_count: 8 })
    assert.equal(value(p, 6, 1), 99, 'legacy above-target progress is retained')
    assert.equal(value(p, 6, 2), 0, 'a supported condition outside the exact scope cannot count')
    const context = { playerId: p.id, questCategory: 1, questId: 1001002, questAccomplished: true, clearTime: 1000,
        clearRank: 5, party: { characters: [{ id: 1 }], unison_characters: [] }, statistics: {},
        player: players.getPlayerSync(p.id), questPreviouslyCompleted: false, questProgress: null, isMulti: true, isMultiHost: false }
    const transaction = load('lib/persistence-coordinator').runPersistenceTransactionSync
    const record = () => load('lib/mission/pass-battle-facts').recordPassMissionBattleFacts(context, new Date())
    transaction({ domain: 'battle', playerId: p.id, operation: 'synthetic_accepted_pass_multi_finish' }, record)
    assert.equal(value(p, 6, 3), 1); assert.equal(value(p, 7, 2), 1); assert.equal(value(p, 6, 1), 99)
    assert.throws(() => transaction({ domain: 'battle', playerId: p.id, operation: 'synthetic_pass_fact_rollback' }, () => {
        record(); throw new Error('synthetic pass rollback')
    }), /synthetic pass rollback/)
    assert.equal(value(p, 7, 2), 1)
})

test('closed pass earned daily points and stage receipts remain claimable exactly once', async () => {
    const p = fixture(); control(true)
    await battle(p)
    assert.equal(load('data/domains/pass-card').getPlayerPassCardStateSync(p.id, 1).point, 0)
    control(false, true)
    response(await read(p))
    const earned = load('data/domains/pass-card').getPlayerPassCardStateSync(p.id, 1).point
    assert.ok(earned > 0)
    const saved = missions.getPlayerCategoryMissionsSync(p.id, 6)
    response(await read(p))
    assert.equal(load('data/domains/pass-card').getPlayerPassCardStateSync(p.id, 1).point, earned)
    assert.deepEqual(missions.getPlayerCategoryMissionsSync(p.id, 6), saved)
})
