'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID, createHash } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-native-quests-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off', DROP_MULTIPLIER: '1' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const rules = require('../assets/content_history_quest_rules.json')
const readiness = require('../assets/content_history_readiness.json')
const assets = load('lib/assets'), adapter = load('lib/content-quest-rules')
const players = load('data/domains/player'), quests = load('data/domains/quest')
const operations = load('lib/content-operations')
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex')
const referenceFields = { clearRewardId: 'clearReward', sPlusRewardId: 'sPlusReward', scoreRewardGroupId: 'scoreRewardGroupId' }
const scalarRewards = ['rankPointReward', 'characterExpReward', 'manaReward', 'poolExpReward']
let app, db

function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'native-quest-http', idpId: randomUUID(), status: 'normal' })
    const p = players.insertDefaultPlayerSync(account.id), viewer = 880000000 + p.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, p.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    return { id: p.id, viewer }
}
function control(key, questKeys, enabled = true) {
    const store = operations.contentOperations(), reviewed = { readiness: 'verified', evidence: 'Exact original native quest and synthetic registered HTTP settlement', endsAtMs: null }
    store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic native column regression',
        actionOverrides: { visible: { ...reviewed, enabled: true }, enter: { ...reviewed, enabled, questKeys } } }, Date.now())
}
const post = (p, url, body) => app.inject({ method: 'POST', url, payload: { viewer_id: p.viewer, api_count: 1, ...body } })
function response(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
const item = (p, id) => db.prepare('SELECT amount FROM players_items WHERE player_id=? AND id=?').get(p.id, id)?.amount ?? 0
const character = (p, id) => db.prepare('SELECT * FROM players_characters WHERE player_id=? AND id=?').get(p.id, id)
const start = (p, play) => post(p, '/single/start', { category: 10, quest_id: 201011001, play_id: play, party_id: 1,
    use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false })
const finishBody = play => ({ category: 10, quest_id: 201011001, play_id: play, continue_count: 0, elapsed_time_ms: 1000,
    score: 12345, add_mana: 0, is_accomplished: true, is_restored: false,
    statistics: { clear_phase: 1, party: { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
        equipments: [null, null, null], ability_soul_ids: [null, null, null] }, zones: [] } })

before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/singleBattleQuest').default, { prefix: '/single' })
    await app.register(load('routes/api/storyQuest').default, { prefix: '/story' })
    await app.ready()
})
after(async () => {
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root)
    fs.rmSync(directory, { recursive: true })
})

test('all native getters correct the exact named fields, preserve raw tables and distinguish single/multi categories', () => {
    assert.equal(Object.keys(rules.quests).length, 3512)
    const tables = new Map(), july = new Set(require('../assets/content_july_controls.json').controls
        .flatMap(row => row.actionOverrides?.enter?.enabled ? row.actionOverrides.enter.questKeys || [] : []))
    let julyCount = 0
    for (const [key, rule] of Object.entries(rules.quests)) {
        const [category, id] = key.split(':').map(Number), source = readiness.childIndex.quests[key].serverDefinition.source
        const table = require('../' + source)
        if (!tables.has(source)) tables.set(source, { table, hash: digest(table) })
        const raw = table[id], got = assets.getQuestFromCategorySync(category, id)
        assert.ok(raw && got, key)
        if (july.has(key)) julyCount++
        const endless = key === '24:700100099'
        for (const [field, native] of Object.entries(rule.fields)) {
            if (endless && (scalarRewards.includes(field) || Object.hasOwn(referenceFields, field))) continue
            if (rule.currentOverlayPriorityFields.includes(field)) continue
            if (field === 'clearRewardId' || field === 'sPlusRewardId') {
                assert.deepEqual(got[referenceFields[field]], native == null ? undefined : assets.getClearRewardSync(native) ?? undefined, `${key}:${field}`)
            } else assert.equal(got[field], native == null ? undefined : native, `${key}:${field}`)
        }
        for (const field of ['name', 'eventId', 'folderId', 'fixedParty', 'rushEventId', 'rushEventFolderId', 'rushEventRound',
            'scoreAttackQuestId', 'bRankScore', 'aRankScore', 'sRankScore', 'ssRankScore', 'timeLimitMs']) {
            if (!Object.hasOwn(rule.fields, field)) assert.deepEqual(got[field], raw[field], `${key}:${field}`)
        }
    }
    assert.equal(julyCount, 748)
    for (const { table, hash } of tables.values()) assert.equal(digest(table), hash)
})

test('native None removes old reward references and native zero survives without mutating caller objects', () => {
    for (const field of ['clearRewardId', 'sPlusRewardId', 'scoreRewardGroupId']) {
        const [key] = Object.entries(rules.quests).find(([, row]) => row.fields[field] === null && !row.currentOverlayPriorityFields.includes(field))
        const [category, id] = key.split(':').map(Number), input = Object.freeze({ name: 'synthetic', fixedParty: 77, [field]: 123456 })
        const output = adapter.applyContentQuestRules(category, id, input)
        assert.equal(Object.hasOwn(output, field), false, `${key}:${field}`)
        assert.equal(input[field], 123456); assert.equal(output.fixedParty, 77)
    }
    const key = Object.keys(rules.quests).find(key => rules.quests[key].fields.element === 0)
    const [category, id] = key.split(':').map(Number)
    assert.equal(adapter.applyContentQuestRules(category, id, { name: '', element: 999 }).element, 0)
    const core = Object.freeze({ name: 'synthetic core', rankPointReward: 7 })
    assert.equal(adapter.applyContentQuestRules(2, 201011001, core), core)
    assert.equal(adapter.applyContentQuestRules(26, 999999999, core), core)
})

test('explicit Expert, Abyss, CN boss/five-boss and CN score overrides keep final precedence', () => {
    for (const [key, row] of Object.entries(rules.quests).filter(([key]) => key.startsWith('21:'))) {
        if (row.kind === 'Story') continue
        assert.deepEqual(assets.getQuestFromCategorySync(21, Number(key.split(':')[1])).sPlusReward, { type: 0, id: 14040, count: 3 })
    }
    for (const [key, rule] of Object.entries(rules.quests).filter(([, row]) => row.currentOverlayPriorityFields.includes('rankPointReward'))) {
        const [category, id] = key.split(':').map(Number), raw = require('../assets/rush_event_quest.json')[id]
        const got = assets.getQuestFromCategorySync(category, id)
        for (const field of scalarRewards) assert.equal(got[field], key === '24:700100099' ? 0 : raw[field] ?? 0, `${key}:${field}`)
    }
    const endless = assets.getQuestFromCategorySync(24, 700100099)
    for (const field of ['clearReward', 'sPlusReward', 'scoreRewardGroupId', 'scoreRewardGroup']) assert.equal(endless[field], undefined)
    const bosses = { ...require('../assets/boss_battle_quest.json'), ...require('../assets/boss_battle_quest_cnmod.json') }
    for (const id of new Set(['1099001', ...Object.keys(require('../assets/boss_battle_quest_cnmod.json'))])) {
        const got = assets.getBossBattleQuestSync(id), raw = bosses[id]
        assert.ok(got && raw, id)
        for (const field of ['element', 'fixedParty', ...scalarRewards]) assert.equal(got[field], raw[field], `${id}:${field}`)
    }
    for (const [id, row] of Object.entries(require('../assets/score_reward_cnmod.json'))) assert.deepEqual(assets.getScoreRewardGroup(id), row)
    for (const [id, row] of Object.entries(require('../assets/rare_score_reward_cnmod.json'))) assert.deepEqual(assets.getRareScoreRewardGroup(id), row)
})

test('historical registered battle settles native first-clear, SS and scalar rewards once even after closure', async () => {
    const p = fixture(), key = 'story_event:201011', scoped = ['10:201011001'], play = randomUUID()
    assert.ok(!require('../assets/content_july_controls.json').controls.some(row => row.key === key))
    control(key, scoped)
    const before = players.getPlayerSync(p.id), ssBefore = item(p, 99)
    assert.equal(character(p, 243013), undefined)
    assert.equal(response(await start(p, play)).data_headers.result_code, 1)
    control(key, scoped, false)
    assert.equal(response(await start(p, randomUUID())).data_headers.result_code, 4050)
    const body = finishBody(play), result = response(await post(p, '/single/finish', body))
    assert.equal(result.data_headers.result_code, 1)
    assert.ok(character(p, 243013)); assert.equal(item(p, 99), ssBefore + 10)
    const after = players.getPlayerSync(p.id)
    assert.equal(after.rankPoint - before.rankPoint, 3)
    assert.equal(result.data.rewards.reward_mana, 3)
    assert.equal(result.data.rewards.reward_pool_exp, 3)
    assert.equal(after.freeMana - before.freeMana, 23, 'native base Mana 3 plus actual score-group Mana 20')
    assert.ok(after.expPool - before.expPool >= 23, 'native base pool EXP 3 and score EXP 20 are persisted')
    const received = digest({ player: after, character: character(p, 243013), item: item(p, 99), progress: quests.getPlayerSingleQuestProgressSync(p.id, 10, 201011001) })
    assert.deepEqual(response(await post(p, '/single/finish', body)), result)
    assert.equal(digest({ player: players.getPlayerSync(p.id), character: character(p, 243013), item: item(p, 99), progress: quests.getPlayerSingleQuestProgressSync(p.id, 10, 201011001) }), received)
})

test('native correction never backfills a previously completed clear or SS reward on replay/reopen', async () => {
    const p = fixture(), key = 'story_event:201011', scoped = ['10:201011001']
    quests.insertPlayerQuestProgressSync(p.id, 10, { questId: 201011001, finished: true, clearRank: 5 })
    const oldProgress = quests.getPlayerSingleQuestProgressSync(p.id, 10, 201011001), ssBefore = item(p, 99)
    control(key, scoped, false)
    assert.deepEqual(quests.getPlayerSingleQuestProgressSync(p.id, 10, 201011001), oldProgress)
    assert.equal(character(p, 243013), undefined)
    control(key, scoped)
    const play = randomUUID()
    assert.equal(response(await start(p, play)).data_headers.result_code, 1)
    assert.equal(response(await post(p, '/single/finish', finishBody(play))).data_headers.result_code, 1)
    assert.equal(character(p, 243013), undefined)
    assert.equal(item(p, 99), ssBefore)
    assert.equal(quests.getPlayerSingleQuestProgressSync(p.id, 10, 201011001).clearRank, 5)
})

test('native Story stays on registered story finish and its completed reward remains idempotent while closed', async () => {
    const p = fixture(), key = 'story_event:100006', body = { category: 10, quest_id: 100006001 }, scoped = ['10:100006001']
    const before = players.getPlayerSync(p.id).freeVmoney
    control(key, scoped)
    assert.equal(assets.getQuestFromCategorySync(10, body.quest_id).sPlusReward, undefined)
    assert.equal(response(await post(p, '/story/finish', body)).data_headers.result_code, 1)
    assert.equal(players.getPlayerSync(p.id).freeVmoney - before, 15)
    const progress = quests.getPlayerSingleQuestProgressSync(p.id, 10, body.quest_id)
    control(key, scoped, false)
    response(await post(p, '/story/finish', body))
    assert.equal(players.getPlayerSync(p.id).freeVmoney - before, 15)
    assert.deepEqual(quests.getPlayerSingleQuestProgressSync(p.id, 10, body.quest_id), progress)
})

test('native main Story joins only on a new first clear, without repairing older completed saves', async () => {
    const fresh = fixture(), body = { category: 1, quest_id: 2009007 }
    const joins = load('lib/story-join-character')
    assert.deepEqual(joins.getQuestJoinCharacterIds(1, 2009007), [10])
    assert.deepEqual(joins.getQuestJoinCharacterIds(1, 10015003), [213013])
    assert.deepEqual(joins.getQuestJoinCharacterIds(10, 2009007), [])
    assert.equal(character(fresh, 10), undefined)
    const first = response(await post(fresh, '/story/finish', body))
    assert.deepEqual(first.data.story_join_character_id_list, [10])
    assert.ok(first.data.character_list.some(row => row.character_id === 10))
    assert.ok(character(fresh, 10))
    const saved = character(fresh, 10)
    const repeated = response(await post(fresh, '/story/finish', body))
    assert.deepEqual(repeated.data, [])
    assert.deepEqual(character(fresh, 10), saved)

    const old = fixture()
    quests.insertPlayerQuestProgressSync(old.id, 1, { questId: body.quest_id, finished: true, clearRank: 5 })
    assert.deepEqual(response(await post(old, '/story/finish', body)).data, [])
    assert.equal(character(old, 10), undefined)

    const owned = fixture()
    assert.ok(load('lib/character').givePlayerCharacterSync(owned.id, 10))
    const ownedJoin = response(await post(owned, '/story/finish', body)).data
    assert.deepEqual(ownedJoin.story_join_character_id_list, [])
    assert.ok(quests.getPlayerSingleQuestProgressSync(owned.id, 1, body.quest_id).finished)
})

test('failed story join rolls back the first clear and reward for a retry', async () => {
    const p = fixture(), body = { category: 1, quest_id: 2009007 }
    const before = players.getPlayerSync(p.id)
    db.exec(`CREATE TRIGGER deny_story_join BEFORE INSERT ON players_characters
        WHEN NEW.player_id=${p.id} AND NEW.id=10
        BEGIN SELECT RAISE(ABORT, 'story join rollback'); END`)
    try {
        assert.equal((await post(p, '/story/finish', body)).statusCode, 500)
        assert.equal(quests.getPlayerSingleQuestProgressSync(p.id, 1, body.quest_id), null)
        assert.equal(character(p, 10), undefined)
        assert.equal(players.getPlayerSync(p.id).freeVmoney, before.freeVmoney)
    } finally {
        db.exec('DROP TRIGGER deny_story_join')
    }
    assert.deepEqual(response(await post(p, '/story/finish', body)).data.story_join_character_id_list, [10])
})

test('ordinary revive replays the same zone count without charging twice and rejects gaps', async () => {
    const parseCount = load('lib/quest/single-continue-request').parseSingleContinueExpectedCount
    assert.equal(parseCount({ zones: [{ continue_count: 1 }, { continue_count: 2 }] }), 3)
    assert.equal(parseCount(JSON.stringify({ zones: [{ continue_count: 1 }, { continue_count: 2 }] })), 3)
    assert.equal(parseCount({ zones: [{ continue_count: 0 }, { continue_count: -1 }] }), null)
    assert.equal(parseCount({ zones: [] }), null)
    assert.equal(parseCount('{bad JSON'), null)
    assert.equal(parseCount(JSON.stringify({ zones: Array.from({ length: 129 }, () => ({ continue_count: 0 })) })), null)
    assert.equal(parseCount(' '.repeat(64 * 1024 + 1)), null)
    assert.equal(parseCount(undefined), null)
    const p = fixture(), play = randomUUID(), identity = { category: 2, quest_id: 1001001, play_id: play }
    players.updatePlayerSync({ id: p.id, freeVmoney: 120, vmoney: 0 })
    assert.equal(response(await post(p, '/single/start', { ...identity, party_id: 1,
        use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false })).data_headers.result_code, 1)
    const revive = count => post(p, '/single/play_continue', { ...identity, payment_type: 1,
        statistics: { zones: [{ continue_count: count }] } })
    const reviveGet = count => app.inject({ method: 'GET', url: '/single/play_continue?' + new URLSearchParams({
        viewer_id: String(p.viewer), api_count: '1', category: String(identity.category),
        quest_id: String(identity.quest_id), play_id: identity.play_id, payment_type: '1',
        statistics: JSON.stringify({ zones: [{ continue_count: count }] }),
    }) })
    assert.equal(response(await reviveGet(0)).data.user_info.free_vmoney, 70)
    const afterFirst = players.getPlayerSync(p.id)
    assert.equal(response(await reviveGet(0)).data.user_info.free_vmoney, 70)
    assert.equal(players.getPlayerSync(p.id).freeVmoney, afterFirst.freeVmoney)
    assert.equal(load('data/domains/quest_active').getPlayerActiveQuestSync(p.id).continueCount, 1)
    assert.equal((await revive(3)).statusCode, 400)
    assert.equal(response(await revive(1)).data.user_info.free_vmoney, 20)
    assert.equal((await revive(2)).statusCode, 400, 'insufficient funds cannot advance the persisted count')
    assert.equal(load('data/domains/quest_active').getPlayerActiveQuestSync(p.id).continueCount, 2)
    assert.equal(players.getPlayerSync(p.id).freeVmoney, 20)
})

test('7014002 forced loss advances only story completion, retaining actual failed battle facts', async () => {
    const p = fixture(), play = randomUUID(), body = { category: 1, quest_id: 7014002, play_id: play }
    assert.equal(response(await post(p, '/single/start', { ...body, party_id: 1,
        use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false })).data_headers.result_code, 1)
    const before = load('data/domains/mission_battle_facts').getMissionBattleCountersSync(p.id)
    const result = response(await post(p, '/single/finish', { ...body, continue_count: 0,
        elapsed_time_ms: 1000, score: 0, add_mana: 0, is_accomplished: false, is_lose: true,
        is_restored: false, statistics: { clear_phase: 0, party: { characters: [{ id: 1 }, null, null],
            unison_characters: [null, null, null], equipments: [null, null, null],
            ability_soul_ids: [null, null, null] }, zones: [] } }))
    assert.equal(result.data_headers.result_code, 1)
    assert.equal(quests.getPlayerSingleQuestProgressSync(p.id, 1, body.quest_id).finished, true)
    const after = load('data/domains/mission_battle_facts').getMissionBattleCountersSync(p.id)
    assert.equal(after.singlePlayCount, before.singlePlayCount + 1)
    assert.equal(after.singleClearCount, before.singleClearCount)
    const replay = response(await post(p, '/single/finish', { ...body, continue_count: 0,
        elapsed_time_ms: 1000, score: 0, add_mana: 0, is_accomplished: false, is_lose: true,
        is_restored: false, statistics: { clear_phase: 0, party: { characters: [{ id: 1 }, null, null],
            unison_characters: [null, null, null], equipments: [null, null, null],
            ability_soul_ids: [null, null, null] }, zones: [] } }))
    assert.deepEqual(replay, result)
    assert.deepEqual(load('data/domains/mission_battle_facts').getMissionBattleCountersSync(p.id), after)
})
