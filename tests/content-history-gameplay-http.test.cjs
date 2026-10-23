'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-gameplay-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const operations = load('lib/content-operations'), assets = load('lib/assets')
const players = load('data/domains/player'), gachas = load('data/domains/gacha')
const quests = load('data/domains/quest'), active = load('data/domains/quest_active')
const coordinator = load('lib/persistence-coordinator'), transaction = coordinator.runPersistenceTransaction
const poolIds = [216, 3, 15013], eventKeys = ['advent_event:1', 'advent_event:2']
const quote = name => '"' + name.replaceAll('"', '""') + '"'
let app, db, subject, other, tables

function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'history-http', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 880000000 + player.id, token = randomUUID()
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    const types = load('data/types').SessionType
    for (const [key, type] of [[String(viewer), types.VIEWER], [token, types.ZAT]]) {
        db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,?)').run(key, account.id, '2099-01-01T00:00:00Z', type)
    }
    players.updatePlayerSync({ id: player.id, freeVmoney: 10000, vmoney: 5000 })
    return { id: player.id, viewer, token }
}

function snapshot(player = subject) {
    return Object.fromEntries(tables.map(({ name, owner }) => [name,
        db.prepare(`SELECT * FROM ${quote(name)} WHERE ${quote(owner)}=?`).all(player.id)
            .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))]))
}

function control(key, overrides) {
    const store = operations.contentOperations()
    return store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Synthetic historical registered-HTTP regression', actionOverrides: Object.fromEntries(Object.entries(overrides)
            .map(([action, value]) => [action, { endsAtMs: null, readiness: 'verified',
                evidence: 'Actual original master definition; synthetic player and exact scope',
                ...(typeof value === 'boolean' ? { enabled: value } : value) }])) }, Date.now())
}

const post = (url, body = {}, player = subject) => app.inject({ method: 'POST', url,
    payload: { viewer_id: player.viewer, api_count: 1, ...body } })
function response(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
const draw = id => post('/gacha/exec', { gacha_id: id, payment_type: 1, type: 1, number_of_exec: 1 })
const start = (play, quest = 1002) => post('/single/start', { category: 7, quest_id: quest, party_id: 1, play_id: play,
    use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false })
const finish = (play, quest = 1002) => post('/single/finish', { category: 7, quest_id: quest, play_id: play,
    continue_count: 0, elapsed_time_ms: 1000, score: 12345, add_mana: 0, is_accomplished: true, is_restored: false,
    statistics: { clear_phase: 1, party: { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
        equipments: [null, null, null], ability_soul_ids: [null, null, null] }, zones: [] } })

before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    subject = fixture(); other = fixture()
    tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all()
        .map(({ name }) => ({ name, columns: db.prepare(`PRAGMA table_info(${quote(name)})`).all().map(row => row.name) }))
        .filter(row => row.name === 'players' || row.columns.includes('player_id'))
        .map(row => ({ name: row.name, owner: row.name === 'players' ? 'id' : 'player_id' }))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    for (const [module, prefix] of [['gacha', '/gacha'], ['singleBattleQuest', '/single'], ['index', '/'], ['rankingEvent', '/ranking'], ['shop', '/shop']]) {
        await app.register(load(`routes/api/${module}`).default, { prefix })
    }
    await app.ready()
})
after(async () => {
    coordinator.runPersistenceTransaction = transaction
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root)
    fs.rmSync(directory, { recursive: true })
})

test('three historical normal pools start closed then deliver their actual character/equipment and exact charge', async () => {
    const july = require('../assets/content_july_controls.json')
    const untouched = snapshot(other)
    for (const id of poolIds) {
        const key = `gacha:${id}`, definition = assets.getGachaSync(id)
        assert.ok(definition)
        assert.ok(!july.controls.some(row => row.key === key), `${key} is not a July seed`)
        assert.ok(operations.contentCatalog.rows.find(row => row.key === key).originalEndMs < Date.parse('2025-07-20T00:00:00+08:00'))
        const saved = snapshot()
        assert.equal((await draw(id)).statusCode, 400)
        assert.deepEqual(snapshot(), saved)
        control(key, { visible: true, enter: true, exchange: true })
        const before = players.getPlayerSync(subject.id), result = response(await draw(id))
        const equipment = definition.type === 1, draws = result.data[equipment ? 'draw_equipment' : 'draw']
        assert.equal(draws.length, 1)
        const grantedId = draws[0][equipment ? 'equipment_id' : 'character_id']
        assert.ok(Object.values(definition.pool).flat().some(row => row.id === grantedId))
        assert.ok(db.prepare(`SELECT 1 FROM ${equipment ? 'players_equipment' : 'players_characters'} WHERE player_id=? AND id=?`).get(subject.id, grantedId))
        assert.equal(players.getPlayerSync(subject.id).freeVmoney, before.freeVmoney - definition.singleCost)
        assert.equal(players.getPlayerSync(subject.id).vmoney, before.vmoney)
        assert.equal(gachas.getPlayerGachaInfoSync(subject.id, id).gachaExchangePoint, 1)
        assert.equal(db.prepare('SELECT COUNT(*) n FROM players_receive_history WHERE player_id=? AND type_id=?').get(subject.id, grantedId).n >= 1, true)
    }
    assert.deepEqual(snapshot(other), untouched)
})

test('closing one historical pool preserves all instances and leaves the other historical pools usable', async () => {
    const store = operations.contentOperations(), key = 'gacha:3', instance = store.state(key).instanceId
    const points = gachas.getPlayerGachaInfoSync(subject.id, 3).gachaExchangePoint, before = snapshot()
    store.setPublished(key, { expectedRevision: store.revision(), catalogDigest: store.digest, published: false, reason: 'Synthetic history close' }, Date.now())
    assert.equal((await draw(3)).statusCode, 400)
    assert.deepEqual(snapshot(), before)
    for (const id of [216, 15013]) assert.equal(response(await draw(id)).data_headers.result_code, 1)
    const afterOthers = snapshot()
    store.setPublished(key, { expectedRevision: store.revision(), catalogDigest: store.digest, published: true, reason: 'Synthetic history reopen' }, Date.now())
    assert.equal(store.state(key).instanceId, instance)
    assert.deepEqual(snapshot(), afterOthers)
    assert.equal(response(await draw(3)).data_headers.result_code, 1)
    assert.equal(gachas.getPlayerGachaInfoSync(subject.id, 3).gachaExchangePoint, points + 1)
})

test('queued closure of each historical draw cannot consume currency, reward or gacha progress', async () => {
    for (const id of poolIds) {
        control(`gacha:${id}`, { enter: true })
        const before = snapshot(); let queued = false
        coordinator.runPersistenceTransaction = async (context, callback, options) => {
            if (context.operation === 'draw') { queued = true; control(`gacha:${id}`, { enter: false }) }
            return transaction(context, callback, options)
        }
        try { assert.equal((await draw(id)).statusCode, 400); assert.equal(queued, true); assert.deepEqual(snapshot(), before) }
        finally { coordinator.runPersistenceTransaction = transaction }
        control(`gacha:${id}`, { enter: true })
    }
})

test('historical character and equipment exchanges retain exact eligibility, charge once and replay after closure', async () => {
    for (const id of [216, 15013]) {
        const definition = assets.getGachaSync(id), equipment = definition.type === 1
        const item = Object.values(definition.pool).flat().find(row => row.isExchangeable)
        assert.ok(item)
        gachas.updatePlayerGachaInfoSync(subject.id, { gachaId: id, gachaExchangePoint: 500 })
        const url = `/gacha/exchange_${equipment ? 'equipment' : 'character'}`
        const payload = { gacha_id: id, [equipment ? 'equipment_id' : 'character_id']: item.id, request_id: randomUUID() }
        const untouched = snapshot()
        control(`gacha:${id}`, { exchange: false })
        assert.equal((await post(url, payload)).statusCode, 400)
        assert.deepEqual(snapshot(), untouched)
        control(`gacha:${id}`, { exchange: true })
        let queued = false
        coordinator.runPersistenceTransaction = async (context, callback, options) => {
            if (context.operation === `gacha_exchange_${equipment ? 'equipment' : 'character'}`) { queued = true; control(`gacha:${id}`, { exchange: false }) }
            return transaction(context, callback, options)
        }
        try { assert.equal((await post(url, payload)).statusCode, 400); assert.equal(queued, true); assert.deepEqual(snapshot(), untouched) }
        finally { coordinator.runPersistenceTransaction = transaction }
        control(`gacha:${id}`, { exchange: true })
        const granted = response(await post(url, payload)).data
        assert.equal(gachas.getPlayerGachaInfoSync(subject.id, id).gachaExchangePoint, 250)
        control(`gacha:${id}`, { exchange: false })
        const after = snapshot()
        assert.deepEqual(response(await post(url, payload)).data, granted)
        assert.deepEqual(snapshot(), after)
        control(`gacha:${id}`, { exchange: true })
        const rejected = snapshot()
        assert.equal((await post(url, { ...payload, [equipment ? 'equipment_id' : 'character_id']: 999999999, request_id: randomUUID() })).statusCode, 400)
        assert.deepEqual(snapshot(), rejected)
    }
})

test('two expired advents coexist; an earned finish and replay survive closure without another first-clear grant', async () => {
    const untouched = snapshot(other)
    for (let index = 0; index < eventKeys.length; index++) control(eventKeys[index], { visible: true, enter: { enabled: true, questKeys: [`7:${1002 + index * 1000}`] } })
    const play = randomUUID()
    assert.equal(response(await start(play)).data_headers.result_code, 1)
    const registered = active.getPlayerActiveQuestSync(subject.id)
    assert.equal(registered.playId, play)
    control(eventKeys[0], { enter: false })
    const before = snapshot()
    assert.equal(response(await start(randomUUID())).data_headers.result_code, 4050)
    assert.deepEqual(snapshot(), before)
    const settled = response(await finish(play))
    assert.equal(settled.data_headers.result_code, 1)
    assert.equal(active.getPlayerActiveQuestSync(subject.id), null)
    const progress = quests.getPlayerSingleQuestProgressSync(subject.id, 7, 1002)
    assert.equal(progress.finished, true)
    const after = snapshot()
    assert.deepEqual(response(await finish(play)), settled)
    assert.deepEqual(snapshot(), after)
    assert.equal(response(await start(randomUUID(), 2002)).data_headers.result_code, 1)
    const store = operations.contentOperations(), instance = store.state(eventKeys[0]).instanceId
    control(eventKeys[0], { enter: true })
    assert.equal(store.state(eventKeys[0]).instanceId, instance)
    assert.deepEqual(quests.getPlayerSingleQuestProgressSync(subject.id, 7, 1002), progress)
    assert.equal(response(await start(randomUUID(), 1004)).data_headers.result_code, 4050, 'reopening must retain the exact reviewed child scope')
    assert.deepEqual(snapshot(other), untouched)
})

test('actual load includes every manually reviewed historical instance and retains earned gacha/quest state', async () => {
    const points = poolIds.map(id => gachas.getPlayerGachaInfoSync(subject.id, id))
    const progress = quests.getPlayerSingleQuestProgressSync(subject.id, 7, 1002)
    const data = response(await post('/load', { access_token: subject.token })).data
    assert.ok(data.content_operations)
    assert.deepEqual(poolIds.map(id => gachas.getPlayerGachaInfoSync(subject.id, id)), points)
    assert.deepEqual(quests.getPlayerSingleQuestProgressSync(subject.id, 7, 1002), progress)
    const serialized = JSON.stringify(data.content_operations)
    for (const key of [...poolIds.map(id => `gacha:${id}`), ...eventKeys]) assert.ok(serialized.includes(key), key)
})

test('an expired advent keeps its original product cost and stock through parent close/reopen', async () => {
    const id = 203001, key = `event_item_shop:${id}`, shopType = load('lib/types').ShopType.EVENT_ITEM
    const item = assets.getShopItemSync(shopType, id), inventory = load('data/domains/item')
    assert.ok(item && item.stock > 1 && item.costs.length === 1 && item.rewards.length === 1)
    assert.equal(operations.contentCatalog.rows.find(row => row.key === key).parentKey, eventKeys[0])
    for (const cost of item.costs) inventory.setPlayerItemSync(subject.id, cost.id, cost.amount * 3)
    control(eventKeys[0], { exchange: true })
    control(key, { visible: true, exchange: true })
    const buy = () => post('/shop/buy', { shop_type: shopType, shop_item_id: id, number: 1 })
    const costBefore = inventory.getPlayerItemSync(subject.id, item.costs[0].id)
    const rewardBefore = inventory.getPlayerItemSync(subject.id, item.rewards[0].id) ?? 0
    response(await buy())
    assert.equal(inventory.getPlayerItemSync(subject.id, item.costs[0].id), costBefore - item.costs[0].amount)
    assert.equal(inventory.getPlayerItemSync(subject.id, item.rewards[0].id), rewardBefore + item.rewards[0].count)
    const before = snapshot()
    control(eventKeys[0], { exchange: false })
    assert.equal((await buy()).statusCode, 400)
    assert.deepEqual(snapshot(), before)
    control(eventKeys[0], { exchange: true })
    let queued = false
    coordinator.runPersistenceTransaction = async (context, callback, options) => {
        if (context.operation === 'purchase') { queued = true; control(key, { exchange: false }) }
        return transaction(context, callback, options)
    }
    try { assert.equal((await buy()).statusCode, 400); assert.equal(queued, true); assert.deepEqual(snapshot(), before) }
    finally { coordinator.runPersistenceTransaction = transaction }
    control(key, { exchange: true })
    response(await buy())
    assert.equal(inventory.getPlayerItemSync(subject.id, item.costs[0].id), costBefore - item.costs[0].amount * 2)
    assert.equal(inventory.getPlayerItemSync(subject.id, item.rewards[0].id), rewardBefore + item.rewards[0].count * 2)
})
