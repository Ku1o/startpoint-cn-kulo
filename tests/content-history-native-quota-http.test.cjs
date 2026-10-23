'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), { randomUUID, createHash } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-native-quota-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off', DROP_MULTIPLIER: '1' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const rules = require('../assets/content_history_quest_rules.json'), lookup = require('../assets/daily_challenge_point_lookup.json')
const adapter = load('lib/content-quest-rules'), assets = load('lib/assets'), players = load('data/domains/player')
const quests = load('data/domains/quest'), active = load('data/domains/quest_active'), operations = load('lib/content-operations')
const coordinator = load('lib/persistence-coordinator'), originalTransaction = coordinator.runPersistenceTransaction
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex')
const A = '10:201011001', B = '18:100400030', EXPERT = '21:1001'
let app, db
function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'native-quota-http', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 880000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    return { id: player.id, viewer }
}
function control(key, enabled = true) {
    const store = operations.contentOperations(), parent = rules.quests[key]?.parentKey ?? operations.contentCatalog.questMap[key]
    assert.equal(typeof parent, 'string', key)
    const review = { readiness: 'verified', evidence: 'Native daily quota field and registered synthetic HTTP regression', endsAtMs: null }
    const association = load('lib/content-box-associations').getContentBoxAssociation(parent)
    if (association) assert.equal(association.relationshipMatches, true, 'The native reward-box association must match')
    // Linked activities require the parent exchange and box entrance together.
    // Configure those real prerequisites without invoking any box transaction.
    db.transaction(() => {
        store.update(parent, { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic native quota lifecycle',
            actionOverrides: { visible: { ...review, enabled: true }, enter: { ...review, enabled, questKeys: [key] },
                ...(association ? { exchange: { ...review, enabled: true } } : {}) } }, Date.now())
        if (association) store.update(association.boxKey, { expectedRevision: store.revision(), catalogDigest: store.digest,
            reason: 'Synthetic native quota linked entrance', actionOverrides: {
                visible: { ...review, enabled: true }, enter: { ...review, enabled: true } } }, Date.now())
    })()
    const { category, quest_id } = identity(key)
    assert.equal(operations.contentQuestDecision(category, quest_id, Date.now()), enabled)
}
const identity = key => { const [category, quest_id] = key.split(':').map(Number); return { category, quest_id } }
const post = (p, url, body) => app.inject({ method: 'POST', url, payload: { viewer_id: p.viewer, api_count: 1, ...body } })
const start = (p, key, play) => post(p, '/single/start', { ...identity(key), play_id: play, party_id: 1,
    use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false })
const finishBody = (key, play, accomplished = true) => ({ ...identity(key), play_id: play, continue_count: 0,
    elapsed_time_ms: 1000, score: 12345, add_mana: 0, is_accomplished: accomplished, is_restored: false,
    statistics: { clear_phase: accomplished ? 1 : 0, party: { characters: [{ id: 1 }, null, null],
        unison_characters: [null, null, null], equipments: [null, null, null], ability_soul_ids: [null, null, null] }, zones: [] } })
const finish = (p, key, play, accomplished = true) => post(p, '/single/finish', finishBody(key, play, accomplished))
function response(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
async function acceptedStart(p, key, play) {
    const result = response(await start(p, key, play))
    assert.equal(result.data_headers.result_code, 1, `${key} must be accepted before settlement`)
    assert.equal(active.getPlayerActiveQuestSync(p.id)?.playId, play, `${key} must persist this accepted play`)
    return result
}
const point = (p, id) => db.prepare('SELECT point FROM daily_challenge_point_list_entries WHERE player_id=? AND id=?').get(p.id, id)?.point
const setPoint = (p, id, value) => players.updatePlayerDailyChallengePointSync(p.id, id, value)
const item = (p, id) => db.prepare('SELECT amount FROM players_items WHERE player_id=? AND id=?').get(p.id, id)?.amount ?? 0
const character = (p, id) => db.prepare('SELECT * FROM players_characters WHERE player_id=? AND id=?').get(p.id, id)
function snapshot(p) {
    return { player: players.getPlayerSync(p.id), active: active.getPlayerActiveQuestSync(p.id),
        points: players.getPlayerDailyChallengePointListSync(p.id),
        characters: db.prepare('SELECT * FROM players_characters WHERE player_id=? ORDER BY id').all(p.id),
        items: db.prepare('SELECT * FROM players_items WHERE player_id=? ORDER BY id').all(p.id),
        progress: quests.getPlayerQuestProgressSync(p.id),
        receipts: db.prepare('SELECT operation,request_key,response_json FROM player_operation_receipts WHERE player_id=? ORDER BY operation,request_key').all(p.id) }
}
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_q, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/singleBattleQuest').default, { prefix: '/single' }); await app.ready()
})
after(async () => {
    coordinator.runPersistenceTransaction = originalTransaction
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root); fs.rmSync(directory, { recursive: true })
})

test('all279 exact native quota identities project without touching raw rules, lookup policy, or old July scopes', () => {
    const before = digest({ rules, lookup }), counts = {}, parents = new Set(), july = new Set(require('../assets/content_july_controls.json').controls.map(row => row.key))
    let total = 0
    for (const [key, rule] of Object.entries(rules.quests)) {
        const { category, quest_id } = identity(key), raw = rule.nativeEligibility?.daily_challenge_point_id
        const expected = raw == null || raw === '(None)' || rule.kind === 'Story' ? null : Number(raw)
        const actual = adapter.getContentNativeDailyChallengePointId(category, quest_id)
        assert.equal(actual, expected, key)
        if (actual !== null) {
            total++; counts[category] = (counts[category] ?? 0) + 1; parents.add(rule.parentKey)
            assert.ok(lookup[actual], key); assert.equal(july.has(rule.parentKey), false, key)
            assert.ok(assets.getQuestFromCategorySync(category, quest_id))
        }
    }
    assert.equal(total, 279); assert.deepEqual(counts, { 10: 235, 18: 44 }); assert.equal(parents.size, 53)
    assert.equal(adapter.getContentNativeDailyChallengePointId(2, 1099001), null)
    assert.equal(adapter.getContentNativeDailyChallengePointId(26, 999999999), null)
    assert.equal(adapter.getContentNativeDailyChallengePointId(24, 700100099), null)
    assert.equal(digest({ rules, lookup }), before)
})

test('missing/exhausted native points reject new starts without fees, progress, or registration; accepted same-play retries retain their entry', async () => {
    control(A); const p = fixture(), play = randomUUID()
    setPoint(p, 30, 0); const empty = digest(snapshot(p))
    assert.equal((await start(p, A, play)).statusCode, 400); assert.equal(digest(snapshot(p)), empty)
    db.prepare('DELETE FROM daily_challenge_point_list_entries WHERE player_id=? AND id=30').run(p.id)
    const missing = digest(snapshot(p)); assert.equal((await start(p, A, play)).statusCode, 400)
    assert.equal(digest(snapshot(p)), missing); assert.equal(point(p, 30), undefined)
    players.insertPlayerDailyChallengePointListSync(p.id, [{ id: 30, point: 1, campaignList: [] }])
    await acceptedStart(p, A, play); assert.equal(point(p, 30), 1)
    setPoint(p, 30, 0); control(A, false)
    const accepted = digest(snapshot(p)); await acceptedStart(p, A, play)
    assert.equal(digest(snapshot(p)), accepted)
    control(A)
    assert.equal((await start(p, A, randomUUID())).statusCode, 400); assert.equal(digest(snapshot(p)), accepted)
})

test('queued new starts recheck the actual point row before any player mutation', async () => {
    control(A); const p = fixture(); setPoint(p, 30, 1)
    let drained = false
    coordinator.runPersistenceTransaction = (context, callback, options) => {
        if (context.playerId === p.id && context.domain === 'single-quest' && context.operation === 'start' && !drained) { drained = true; setPoint(p, 30, 0) }
        return originalTransaction(context, callback, options)
    }
    const playerBefore = digest(players.getPlayerSync(p.id))
    try { assert.equal((await start(p, A, randomUUID())).statusCode, 400) }
    finally { coordinator.runPersistenceTransaction = originalTransaction }
    assert.equal(drained, true); assert.equal(point(p, 30), 0); assert.equal(active.getPlayerActiveQuestSync(p.id), null)
    assert.equal(digest(players.getPlayerSync(p.id)), playerBefore)
})

test('actual story/world victories merge all existing point IDs and campaigns, consuming only their own native identity', async () => {
    control(A); control(B); const p = fixture()
    setPoint(p, 30, 3); setPoint(p, 4, 4)
    db.prepare('INSERT INTO daily_challenge_point_list_campaigns(campaign_id,additional_point,list_entry_id,player_id) VALUES(?,?,?,?)').run(700, 2, 30, p.id)
    const initial = players.getPlayerDailyChallengePointListSync(p.id)
    const a = randomUUID(); await acceptedStart(p, A, a); assert.equal(point(p, 30), 3)
    const first = response(await finish(p, A, a)).data.user_daily_challenge_point_list
    assert.equal(point(p, 30), 2); assert.equal(point(p, 4), 4)
    assert.deepEqual(first.find(row => row.id === 30).campaign_list, [{ campaign_id: 700, additional_point: 2 }])
    assert.equal(first.length, initial.length); assert.equal(first.find(row => row.id === 4).point, 4)
    const b = randomUUID(); await acceptedStart(p, B, b); const second = response(await finish(p, B, b)).data.user_daily_challenge_point_list
    assert.equal(point(p, 30), 2); assert.equal(point(p, 4), 3)
    assert.equal(second.find(row => row.id === 30).point, 2); assert.equal(second.find(row => row.id === 4).point, 3)
    for (const entry of initial.filter(row => ![30, 4].includes(row.id))) assert.equal(second.find(row => row.id === entry.id).point, entry.point)
})

test('historical failure keeps its point and clear state, gives no first-clear/SS reward, then one real victory consumes and rewards once', async () => {
    control(A); const p = fixture(), failed = randomUUID(), success = randomUUID(), ss = item(p, 99)
    await acceptedStart(p, A, failed); const failure = response(await finish(p, A, failed, false))
    assert.equal(point(p, 30), 1); assert.equal(quests.getPlayerSingleQuestProgressSync(p.id, 10, 201011001), null)
    assert.equal(character(p, 243013), undefined); assert.equal(item(p, 99), ss)
    await acceptedStart(p, A, success)
    assert.deepEqual(response(await finish(p, A, failed, true)), failure, 'changing a finished loss body cannot manufacture a victory')
    assert.equal(active.getPlayerActiveQuestSync(p.id).playId, success); assert.equal(point(p, 30), 1)
    const won = response(await finish(p, A, success)); assert.equal(point(p, 30), 0)
    assert.equal(quests.getPlayerSingleQuestProgressSync(p.id, 10, 201011001).finished, true)
    assert.ok(character(p, 243013)); assert.equal(item(p, 99), ss + 10)
    const settled = digest(snapshot(p)); assert.deepEqual(response(await finish(p, A, success)), won)
    assert.equal(digest(snapshot(p)), settled)
})

test('closing a parent retains accepted battle settlement; concurrent and expired permanent replays never consume another point', async () => {
    control(B); const p = fixture(), play = randomUUID(); setPoint(p, 4, 2)
    await acceptedStart(p, B, play); control(B, false)
    assert.equal(response(await start(p, B, randomUUID())).data_headers.result_code, 4050)
    const both = await Promise.all([finish(p, B, play), finish(p, B, play)])
    assert.deepEqual(response(both[0]), response(both[1])); assert.equal(point(p, 4), 1)
    const old = Date.now() - 49 * 3600_000
    db.prepare('UPDATE battle_settlement_ledger SET settled_at=? WHERE player_id=? AND play_id=?').run(old, p.id, play)
    db.prepare("UPDATE player_operation_receipts SET created_at=? WHERE player_id=? AND operation='quest_finish.single' AND request_key=?").run(old, p.id, play)
    control(B)
    assert.equal((await start(p, B, play)).statusCode, 400)
    const next = randomUUID(); await acceptedStart(p, B, next); const before = digest(snapshot(p))
    assert.equal((await finish(p, B, play)).statusCode, 400); assert.equal(digest(snapshot(p)), before)
    response(await finish(p, B, next)); assert.equal(point(p, 4), 0)
})

test('a real SQLite point-update failure rolls the whole finish back and the same accepted play can retry exactly once', async () => {
    control(A); const p = fixture(), play = randomUUID(); setPoint(p, 30, 2)
    await acceptedStart(p, A, play); const before = digest(snapshot(p))
    db.exec(`CREATE TRIGGER fail_native_point BEFORE UPDATE ON daily_challenge_point_list_entries WHEN NEW.player_id=${p.id} AND NEW.id=30 BEGIN SELECT RAISE(ABORT,'synthetic native point failure'); END`)
    assert.equal((await finish(p, A, play)).statusCode, 500); assert.equal(digest(snapshot(p)), before)
    db.exec('DROP TRIGGER fail_native_point')
    response(await finish(p, A, play)); assert.equal(point(p, 30), 1)
    const settled = digest(snapshot(p)); response(await finish(p, A, play)); assert.equal(digest(snapshot(p)), settled)
})

test('Expert retains its original mapped loss/success consumption, while old historical clear records and over-default remaining points are preserved', async () => {
    control(EXPERT); const p = fixture(); setPoint(p, 1, 3)
    const loss = randomUUID(); await acceptedStart(p, EXPERT, loss); response(await finish(p, EXPERT, loss, false)); assert.equal(point(p, 1), 2)
    const win = randomUUID(); await acceptedStart(p, EXPERT, win); const result = response(await finish(p, EXPERT, win))
    assert.equal(point(p, 1), 1); assert.equal(result.data.user_daily_challenge_point_list.find(row => row.id === 1).point, 1)
    response(await finish(p, EXPERT, win)); assert.equal(point(p, 1), 1)
    const old = fixture(); setPoint(old, 30, 7)
    quests.insertPlayerQuestProgressSync(old.id, 10, { questId: 201011001, finished: true, clearRank: 5 })
    const progress = digest(quests.getPlayerSingleQuestProgressSync(old.id, 10, 201011001)), ssBefore = item(old, 99)
    control(A, false); assert.equal(point(old, 30), 7)
    assert.equal(digest(quests.getPlayerSingleQuestProgressSync(old.id, 10, 201011001)), progress)
    control(A); const another = randomUUID(); await acceptedStart(old, A, another); assert.equal(point(old, 30), 7)
    response(await finish(old, A, another)); assert.equal(point(old, 30), 6)
    assert.equal(character(old, 243013), undefined); assert.equal(item(old, 99), ssBefore)
})

test('the existing daily-reset policy and lookup values remain unchanged for both original isRecovery flags', () => {
    const p = fixture(), originalLookup = digest(lookup)
    assert.equal(lookup[30].isRecovery, false); assert.equal(lookup[4].isRecovery, true)
    setPoint(p, 30, 0); setPoint(p, 4, 0)
    db.prepare('INSERT INTO daily_challenge_point_list_campaigns(campaign_id,additional_point,list_entry_id,player_id) VALUES(?,?,?,?)').run(701, 2, 30, p.id)
    const future = new Date(Date.now() + 3 * 86400000)
    assert.equal(players.dailyResetPlayerDataSync(players.getPlayerSync(p.id), future), true)
    assert.equal(point(p, 30), lookup[30].maxPoint + 2); assert.equal(point(p, 4), lookup[4].maxPoint)
    assert.equal(digest(lookup), originalLookup)
})
