'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-collect-battle-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const players = load('data/domains/player'), missions = load('data/domains/mission')
const master = load('lib/mission/master-data'), operations = load('lib/content-operations')
const target = id => load('lib/mission/stages').getMissionFinalTargetProgress(4, id)
const definitions = master.getMissionMasterDefinitions(4)
let db, app
function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'history-collect-battle', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 880000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    return { id: player.id, viewer }
}
function control(eventId, keys, enabled = true, claim = false) {
    const store = operations.contentOperations(), review = { readiness: 'verified', evidence: 'Original collect condition and accepted battle facts', endsAtMs: null }
    const missionKeys = keys.map(id => `4:${id}`)
    store.update(`collect_item_event:${eventId}`, { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic history collect HTTP regression',
        actionOverrides: { visible: { ...review, enabled: true }, enter: { ...review, enabled, missionKeys }, claim: { ...review, enabled: claim, missionKeys } } }, Date.now())
}
const post = (p, url, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: p.viewer, api_count: 1, ...body } })
function response(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
const progress = p => missions.getPlayerCategoryMissionsSync(p.id, 4)
const value = (p, id) => progress(p)[id]?.progress ?? 0
async function battle(p, stats = {}, success = true) {
    const play = randomUUID(), category = 1, quest = 1001002
    const result = response(await post(p, '/single/start', { category, quest_id: quest, party_id: 1, play_id: play,
        use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false }))
    assert.equal(result.data_headers.result_code, 1)
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

test('historical battle missions use only accepted scoped finishes, preserve max-chain semantics and ignore old lifetime totals', async () => {
    const p = fixture(), event = 10002
    const selected = definitions.filter(row => row.eventId === event && [14, 28, 31].includes(Number(row.row[4])))
    assert.ok(selected.length > 5)
    control(event, selected.map(row => row.missionId))
    players.updatePlayerSync({ id: p.id, totalDashes: 999999, totalPowerflips: 999999, totalStaminaUsed: 999999 })
    response(await post(p, '/mission/get_mission_progress', { category_list: [{ category: 4, event_id: event }] }))
    for (const row of selected) assert.equal(value(p, row.missionId), 0)
    const stats = { use_dash_count: 2, use_skill_count: 4, use_power_flip_count: 5, fever_count: 3,
        enemy_kill_count: 7, weak_point_attack_count: 6, max_skill_chain_count: 6 }
    const accepted = await battle(p, stats)
    for (const row of selected) {
        const condition = Number(row.row[4]), stat = Number(row.row[5])
        const inMainRange = row.row[9] === '(None)'
        const amount = !inMainRange ? 0 : condition === 14 ? 1 : condition === 31 ? 6 : ({ 0: 6, 1: 5, 2: 2, 4: 4, 5: 3, 7: 7 })[stat]
        assert.equal(value(p, row.missionId), Math.min(target(row.missionId), amount), `${row.missionId}`)
    }
    const once = progress(p)
    assert.deepEqual(response(await post(p, '/single/finish', accepted.body)), accepted.finish)
    assert.deepEqual(progress(p), once)
    control(event, selected.map(row => row.missionId), false)
    await battle(p, { ...stats, max_skill_chain_count: 99 })
    assert.deepEqual(progress(p), once)
    control(event, selected.map(row => row.missionId))
    await battle(p, { max_skill_chain_count: 8 })
    for (const row of selected.filter(row => Number(row.row[4]) === 31)) assert.equal(value(p, row.missionId), Math.min(target(row.missionId), 8))
    const beforeFailure = progress(p)
    await battle(p, stats, false)
    assert.deepEqual(progress(p), beforeFailure)
})

test('host/guest and exact quest selectors write separate original mission rows within the accepted finish transaction', () => {
    const p = fixture(), ids = [1748, 1753, 1653]
    control(10002, ids.filter(id => id !== 1653)); control(10001, [1653])
    const context = { playerId: p.id, questCategory: 2, questId: 1009001, questAccomplished: true, clearTime: 1000,
        clearRank: 5, party: { characters: [{ id: 1 }], unison_characters: [] }, statistics: {},
        player: players.getPlayerSync(p.id), questPreviouslyCompleted: false, questProgress: null, isMulti: true, isMultiHost: true }
    const record = load('lib/mission/collect-battle-facts').recordCollectMissionBattleFacts
    const transaction = load('lib/persistence-coordinator').runPersistenceTransactionSync
    const apply = () => transaction({ domain: 'battle', playerId: p.id, operation: 'synthetic_accepted_collect_finish' }, () => record(context, new Date()))
    apply()
    assert.equal(value(p, 1748), 1); assert.equal(value(p, 1753), 0); assert.equal(value(p, 1653), 1)
    context.isMultiHost = false; context.questId = 1008001
    apply()
    assert.equal(value(p, 1748), 1); assert.equal(value(p, 1753), 1); assert.equal(value(p, 1653), 1, 'a different boss chapter cannot satisfy the exact selector')
    const saved = progress(p)
    assert.throws(() => transaction({ domain: 'battle', playerId: p.id, operation: 'synthetic_failed_collect_finish' }, () => {
        record(context, new Date()); throw new Error('synthetic rollback')
    }), /synthetic rollback/)
    assert.deepEqual(progress(p), saved)
})

test('all-task dependencies persist before closure and old excess progress still claims once without re-counting', async () => {
    const p = fixture(), last = 1659, aggregate = 1660
    const refs = master.getMissionMasterDefinition(4, aggregate).row[19].split(',').map(Number)
    for (const id of refs) missions.updatePlayerCategoryMissionSync(p.id, 4, id, target(id) - (id === last ? 1 : 0))
    control(10001, [last, aggregate])
    await battle(p)
    assert.equal(value(p, last), target(last)); assert.equal(value(p, aggregate), target(aggregate))
    missions.updatePlayerCategoryMissionSync(p.id, 4, last, target(last) + 99)
    control(10001, [last, aggregate], false, true)
    const read = () => post(p, '/mission/get_mission_progress', { category_list: [{ category: 4, event_id: 10001 }] })
    response(await read())
    assert.equal(value(p, last), target(last) + 99)
    assert.ok(Object.keys(progress(p)[aggregate].stages).length > 0)
    const saved = load('data/snapshots/player-snapshot').createPlayerSaveSnapshotV2Sync(p.id, db).data.tables
    response(await read())
    assert.deepEqual(load('data/snapshots/player-snapshot').createPlayerSaveSnapshotV2Sync(p.id, db).data.tables, saved)
})

test('non-item collect conditions never read a stale item-id field as earned progress', () => {
    const p = fixture(), id = 1761, collect = load('lib/mission/collect-progress')
    assert.equal(master.getMissionMasterDefinition(4, id).row[4], '46')
    assert.equal(master.getMissionMasterDefinition(4, id).row[14], '50200')
    load('data/domains/item').setPlayerItemSync(p.id, 50200, 1000000)
    assert.equal(collect.getCollectMissionItemId(id), undefined)
    const context = collect.CollectComputer.buildContext(p.id, 4, new Date(), [id])
    assert.equal(collect.CollectComputer.compute(id, context, 0), 0)
})

test('original event quest and SS conditions remain selective alongside a real main-quest HTTP finish', async () => {
    const p = fixture(), exact = 1806, ss = 1760
    control(10005, [exact]); control(10003, [ss])
    const context = { playerId: p.id, questCategory: 7, questId: 100002002, questAccomplished: true, clearTime: 1000,
        clearRank: 5, party: { characters: [{ id: 1 }], unison_characters: [] }, statistics: {},
        player: players.getPlayerSync(p.id), questPreviouslyCompleted: false, questProgress: null, isMulti: false }
    const record = load('lib/mission/collect-battle-facts').recordCollectMissionBattleFacts
    const transaction = load('lib/persistence-coordinator').runPersistenceTransactionSync
    const apply = () => transaction({ domain: 'battle', playerId: p.id, operation: 'synthetic_exact_collect_finish' }, () => record(context, new Date()))
    apply()
    assert.equal(value(p, exact), 1); assert.equal(value(p, ss), 1)
    context.questId = 100001002; context.clearRank = 4
    apply()
    assert.equal(value(p, exact), 1); assert.equal(value(p, ss), 1)
    await battle(p)
    assert.equal(value(p, exact), 1, 'main quests cannot impersonate the configured advent')
    assert.equal(value(p, ss), 2)
})
