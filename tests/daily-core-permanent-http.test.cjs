'use strict'
if (!process.env.STARPOINT_TEST_COMPILED_ROOT) require('ts-node/register/transpile-only')
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')
const { spawnSync } = require('node:child_process')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'daily-core-permanent-'))
Object.assign(process.env, { DATA_DIR: directory, GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0',
    GAME_ROUTINE_LOGS: 'off', GAME_VERBOSE_LOGS: 'false', TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const compiledRoot = process.env.STARPOINT_TEST_COMPILED_ROOT
const load = name => require(compiledRoot ? path.join(compiledRoot, name) : `../src/${name}`)
const players = load('data/domains/player'), missions = load('data/domains/mission')
const operations = load('lib/content-operations'), master = load('lib/mission/master-data')
const clock = load('utils'), snapshots = load('lib/mission/snapshot')
const transaction = load('lib/persistence-coordinator').runPersistenceTransactionSync
const core = [11, 13, 14, 16, 17, 10075], all = [...core, 800392]
const clientCases = []
let db, app
function at(value) { clock.setServerTimeOffset(Date.parse(value) - Date.now()) }
function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'daily-core', idpId: randomUUID(), status: 'normal' })
    const p = players.insertDefaultPlayerSync(account.id), viewer = 870000000 + p.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, p.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    players.updatePlayerSync({ id: p.id, lastLoginTime: clock.getServerDate(), totalDashes: 0, totalStaminaUsed: 0 })
    snapshots.initializePeriodicMissionSnapshots(p.id, players.getPlayerSync(p.id))
    return { id: p.id, viewer }
}
const post = (p, url, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: p.viewer, api_count: 1, ...body } })
function response(r) { assert.equal(r.statusCode, 200, r.body); return r.json() }
const progress = p => missions.getPlayerCategoryMissionsSync(p.id, 2)
const value = (p, id) => progress(p)[id]?.progress ?? 0
const read = p => post(p, '/mission/get_mission_progress', { category_list: [{ category: 2 }] })
const receipts = p => db.prepare('SELECT * FROM players_receive_history WHERE player_id=? ORDER BY id').all(p.id)
function control(id, enabled, claim = enabled) {
    const store = operations.contentOperations()
    store.update(`mission_daily:${id}`, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Synthetic daily core closure regression', readiness: 'verified', evidence: 'Original daily task exact definition', endsAtMs: null,
        flags: { visible: enabled, enter: enabled, claim, exchange: false } }, Date.now())
}
function clearControls() { db.prepare('DELETE FROM content_operations_state WHERE content_key LIKE ?').run('mission_daily:%') }
function captureClientCase(name) {
    const native = require('../assets/mission_daily.json')
    clientCases.push({ name, snapshot: operations.contentOperations().snapshot(Date.now()),
        nativeMissions: [...all, 1].map(id => {
            const row = native[id][0], definition = master.getMissionMasterDefinition(2, id)
            return { id, key: `mission_daily:${id}`, missionKey: `2:${id}`, name: row[1], enableStart: row[25], enableEnd: row[26],
                showStart: row[27], showEnd: row[28], displayRank: row[34],
                serverDecision: Object.fromEntries(['visible', 'enter', 'claim'].map(action => [action, operations.contentMissionDecision(2, id, action)])),
                expected: Object.fromEntries(['visible', 'enter', 'claim'].map(action => [action,
                    master.isMissionDefinitionEnabledAt(definition, clock.getServerDate(), undefined, action)])) }
        }) })
    if (process.env.STARPOINT_DAILY_SNAPSHOT_OUTPUT) fs.writeFileSync(process.env.STARPOINT_DAILY_SNAPSHOT_OUTPUT,
        JSON.stringify({ source: 'Actual ContentOperationsStore.snapshot on isolated test database; unmodified complete schema2 snapshots',
            expectedMeaning: 'visible/enter/claim control and original dates only; claim does not grant progress, rank, or reward eligibility', cases: clientCases }, null, 2))
}
async function battle(p, success = true, dash = 0) {
    const play = randomUUID(), category = 1, quest = 1001002
    response(await post(p, '/single/start', { category, quest_id: quest, party_id: 1, play_id: play,
        use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false }))
    const body = { category, quest_id: quest, play_id: play, continue_count: 0, elapsed_time_ms: 1000, score: 12345,
        add_mana: 0, is_accomplished: success, is_restored: false, statistics: { clear_phase: 1, use_dash_count: dash,
            party: { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
                equipments: [null, null, null], ability_soul_ids: [null, null, null] }, zones: [{ use_dash_count: dash }] } }
    const result = response(await post(p, '/single/finish', body))
    assert.equal(result.data_headers.result_code, 1)
    return { body, result }
}
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    at('2025-07-20T04:00:00Z')
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/mission').default, { prefix: '/mission' })
    await app.register(load('routes/api/singleBattleQuest').default, { prefix: '/single' })
    await app.ready()
})
after(async () => {
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root)
    fs.rmSync(directory, { recursive: true })
})

test('exact six defaults and client legacy keys restore seven current daily definitions without opening historical tasks', async () => {
    const p = fixture(), store = operations.contentOperations()
    const snapshot = store.snapshot(Date.now())
    for (const id of core) {
        assert.equal(operations.contentMissionDecision(2, id, 'visible'), null)
        assert.equal(operations.contentMissionDecision(2, id, 'enter'), null)
        assert.ok(snapshot.default_policy.actions.visible.legacy_keys.includes(`mission_daily:${id}`))
        assert.ok(snapshot.default_policy.actions.enter.legacy_keys.includes(`mission_daily:${id}`))
        assert.equal(master.isMissionDefinitionEnabledAt(master.getMissionMasterDefinition(2, id), clock.getServerDate()), true)
    }
    assert.equal(operations.contentMissionDecision(2, 800392, 'enter'), null)
    const result = response(await read(p))
    assert.deepEqual(result.data.mission_progress_list.map(x => x.mission_id).sort((a, b) => a - b), [...all].sort((a, b) => a - b))
    for (const id of [1, 800391]) assert.equal(operations.contentMissionDecision(2, id, 'enter'), false)
    for (const id of [400093, 400094, 400095, 400096]) assert.equal(operations.contentMissionDecision(3, id, 'enter'), false)
    assert.equal(load('lib/content-operations-defaults').unknownMissionContentDecision(2, '2050-12-31 04:59:59'), false)
    captureClientCase('restored-defaults-and-historical-finite-control')
})

test('actual finish and authoritative data counters settle the five basic dailies and all-clear once without lifetime leakage', async () => {
    const p = fixture()
    players.updatePlayerSync({ id: p.id, totalDashes: 1000, totalStaminaUsed: 1000 })
    snapshots.initializePeriodicMissionSnapshots(p.id, players.getPlayerSync(p.id))
    response(await read(p))
    assert.equal(value(p, 14), 0); assert.equal(value(p, 16), 0)
    let accepted
    for (let n = 0; n < 3; n++) accepted = await battle(p, true, 4)
    // Multi counters are the real accepted-result data API; no alternate mission calculator is used.
    load('data/domains/mission_battle_facts').recordMissionBattleResultSync(p.id, { isMulti: true, isHost: true, accomplished: true, clearRank: 5 })
    const current = players.getPlayerSync(p.id)
    assert.ok(current.totalDashes >= 1010, 'actual HTTP finishes recorded dash statistics')
    players.updatePlayerSync({ id: p.id, totalStaminaUsed: 1050 })
    response(await read(p))
    for (const [id, expected] of [[11, 3], [13, 1], [14, 10], [16, 50], [17, 4], [800392, 3]]) {
        assert.equal(value(p, id), expected, String(id))
        assert.equal(progress(p)[id].stages['1'], true, `received ${id}`)
    }
    const saved = progress(p), before = receipts(p), player = players.getPlayerSync(p.id)
    response(await read(p)); response(await read(p))
    assert.deepEqual(progress(p), saved); assert.deepEqual(receipts(p), before)
    assert.equal(players.getPlayerSync(p.id).freeVmoney, player.freeVmoney)
    assert.deepEqual(response(await post(p, '/single/finish', accepted.body)), accepted.result)
    assert.deepEqual(progress(p), saved); assert.deepEqual(receipts(p), before)
})

test('infinite training requires the exact original score event; failures and transaction retries cannot grant extra rewards', async () => {
    const p = fixture(), record = load('lib/mission/daily-battle-facts').recordDailyMissionBattleFacts
    const score = require('../assets/score_attack_event_quest.json')
    const exact = Number(Object.keys(score).find(id => score[id].eventId === 1)), other = 999999999
    assert.ok(exact); assert.equal(score[other], undefined)
    assert.equal(master.getMissionMasterDefinition(2, 10075).row[7], '20')
    assert.equal(master.getMissionMasterDefinition(2, 10075).row[8], '1')
    const context = { playerId: p.id, questCategory: 27, questId: exact, questAccomplished: true, isMulti: false }
    const apply = ctx => transaction({ domain: 'battle', playerId: p.id, operation: 'synthetic_daily_score_finish' }, () => record(ctx, clock.getServerDate()))
    apply({ ...context, questAccomplished: false }); apply({ ...context, questCategory: 1 }); apply({ ...context, questId: other })
    assert.equal(value(p, 10075), 0)
    assert.throws(() => transaction({ domain: 'battle', playerId: p.id, operation: 'synthetic_daily_score_rollback' }, () => {
        record(context, clock.getServerDate()); throw new Error('accepted finish rollback')
    }), /accepted finish rollback/)
    assert.equal(value(p, 10075), 0); assert.equal(value(p, 800392), 2, 'two accomplished wrong-scope battles still satisfy the existing any-battle task')
    apply(context); response(await read(p))
    assert.equal(value(p, 10075), 1); assert.equal(progress(p)[10075].stages['1'], true)
    const received = receipts(p), item = load('data/domains/item').getPlayerItemSync(p.id, 40501)
    response(await read(p)); response(await read(p))
    assert.deepEqual(receipts(p), received); assert.deepEqual(load('data/domains/item').getPlayerItemSync(p.id, 40501), item)
})

test('05:00 reset clears participating daily progress and receipts but preserves closed historical and explicitly closed task rights', async () => {
    const p = fixture()
    at('2025-07-20T20:59:59Z')
    players.updatePlayerSync({ id: p.id, lastLoginTime: clock.getServerDate() })
    for (const id of all) {
        missions.updatePlayerCategoryMissionSync(p.id, 2, id, 999)
        missions.updatePlayerCategoryMissionStageSync(p.id, 2, 1, id, true)
    }
    missions.updatePlayerCategoryMissionSync(p.id, 2, 1, 77)
    missions.updatePlayerCategoryMissionStageSync(p.id, 2, 1, 1, true)
    control(13, false)
    const closed = progress(p)[13], historical = progress(p)[1]
    assert.equal(players.dailyResetPlayerDataSync(players.getPlayerSync(p.id), clock.getServerDate()), false)
    assert.equal(value(p, 11), 999)
    at('2025-07-20T21:00:01Z')
    assert.equal(players.dailyResetPlayerDataSync(players.getPlayerSync(p.id), clock.getServerDate()), true)
    for (const id of all.filter(id => id !== 13)) assert.equal(progress(p)[id], undefined, String(id))
    assert.deepEqual(progress(p)[13], closed); assert.deepEqual(progress(p)[1], historical)
    const once = progress(p)
    assert.equal(players.dailyResetPlayerDataSync(players.getPlayerSync(p.id), clock.getServerDate()), false)
    assert.deepEqual(progress(p), once)
    clearControls(); at('2025-07-20T04:00:00Z')
})

test('explicit closure and corrupt control remain closed; saved excess and received rewards survive closure and reopening', async () => {
    const p = fixture()
    missions.updatePlayerCategoryMissionSync(p.id, 2, 11, 999)
    missions.updatePlayerCategoryMissionStageSync(p.id, 2, 1, 11, true)
    const saved = progress(p)[11], before = receipts(p)
    control(11, false, false)
    captureClientCase('explicitly-closed-11')
    assert.equal(operations.contentMissionDecision(2, 11, 'enter'), false)
    assert.ok(!response(await read(p)).data.mission_progress_list.some(x => x.mission_id === 11))
    assert.deepEqual(progress(p)[11], saved)
    clearControls(); response(await read(p))
    assert.deepEqual(progress(p)[11], saved); assert.deepEqual(receipts(p), before)
    control(14, false, false)
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run('{broken', 'mission_daily:14')
    captureClientCase('invalid-persisted-control-14')
    assert.equal(operations.contentMissionDecision(2, 14, 'visible'), false)
    assert.equal(operations.contentMissionDecision(2, 14, 'enter'), false)
    assert.ok(!response(await read(p)).data.mission_progress_list.some(x => x.mission_id === 14))
    clearControls()
})

test('a missing reviewed catalog entry never receives the six-ID fallback', () => {
    const script = `const path=require('node:path');const compiled=process.env.STARPOINT_TEST_COMPILED_ROOT;
      if(!compiled)require('ts-node/register/transpile-only');
      const load=n=>require(compiled?path.join(compiled,n):'./src/'+n);
      const assert=require('node:assert/strict');const c=require(compiled?path.resolve(compiled,'../assets/content_catalog.json'):'./assets/content_catalog.json');
      c.rows=c.rows.filter(r=>!${JSON.stringify(core)}.includes(r.type==='mission_daily'?r.id:-1));
      for(const id of ${JSON.stringify(core)})delete c.missionMap['2:'+id];
      const operations=load('lib/content-operations');
      for(const id of ${JSON.stringify(core)})assert.equal(operations.contentMissionDecision(2,id,'enter'),false);
      load('data/db').getDb().close();`
    const childDir = path.join(directory, 'missing-catalog')
    fs.mkdirSync(childDir)
    const child = spawnSync(process.execPath, ['-e', script], { cwd: path.resolve(__dirname, '..'),
        env: { ...process.env, DATA_DIR: childDir, GACHA_SEED_DIR: path.join(childDir, 'seeds') }, encoding: 'utf8' })
    assert.equal(child.status, 0, child.stdout + child.stderr)
})
