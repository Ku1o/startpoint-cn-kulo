'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'challenge-shop-period-'))
const { randomUUID } = require('node:crypto')
Object.assign(process.env, { DATA_DIR: directory, GACHA_SEED_DIR: path.join(directory, 'seeds'),
    CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const operations = load('lib/content-operations'), assets = load('lib/assets'), clock = load('utils')
const inventory = load('data/domains/item'), purchases = load('data/domains/shopPurchase')
const parentKey = 'challenge_dungeon_event:1'
const productRows = operations.contentCatalog.rows.filter(row => row.parentKey === parentKey)
const productIds = productRows.map(row => row.id)
let app, db, store, player, viewer, loginToken, apiCount = 0
const review = (enabled, questKeys) => ({ enabled, endsAtMs: null, readiness: 'verified',
    evidence: 'Exact native challenge quest and product periods; isolated regression', ...(questKeys ? { questKeys } : {}) })
function update(key, actionOverrides) {
    return store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Challenge shop period regression', actionOverrides }, Date.now())
}
function selectPeriod(first, enter = true) {
    const keys = [...Array.from({ length: 19 }, (_, i) => `13:${1001 + i}`),
        ...Array.from({ length: 3 }, (_, i) => `13:${first + i}`)]
    update(parentKey, { visible: review(true, keys), enter: review(enter, keys), exchange: review(true) })
}
const post = (url, payload) => app.inject({ method: 'POST', url, headers: { login_token: loginToken },
    payload: { viewer_id: viewer, api_count: ++apiCount, ...payload } })
const sales = async () => {
    const response = await post('/shop/get_sales_list', { shop_types: [], boss_coin_shop_category_ids: [],
        event_list: [{ event_type: 4, event_ids: [1] }] })
    assert.equal(response.statusCode, 200, response.body)
    return JSON.parse(response.body).data.sales_list
}
const buy = id => post('/shop/buy', { shop_type: 4, shop_item_id: id, number: 1 })
const snapshot = () => JSON.stringify({
    items: db.prepare('SELECT * FROM players_items WHERE player_id=? ORDER BY id').all(player.id),
    purchases: db.prepare('SELECT * FROM players_shop_purchases WHERE player_id=? ORDER BY shop_item_id').all(player.id),
})

before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'challenge-shop', idpId: '', status: 'normal' })
    player = load('data/domains/player').insertDefaultPlayerSync(account.id); viewer = 880000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,?)').run(String(viewer), account.id, '2099-01-01T00:00:00Z', 2)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,?)').run(randomUUID(), account.id, '2099-01-01T00:00:00Z', 1)
    const identities = load('lib/gameplay-request-identity')
    identities.initializeGameplayRequestIdentitySchemaSync(db)
    loginToken = db.transaction(() => identities.issueGameplayLoginTokenSync(db, {
        accountId: account.id, viewerId: viewer, udid: 'challenge-shop-fixture', expiresAt: Date.now() + 86400000,
    }))()
    store = operations.contentOperations()
    db.transaction(() => {
        for (const id of productIds) update(`event_item_shop:${id}`, { visible: review(true), exchange: review(true) })
    })()
    for (const id of productIds) for (const cost of assets.getShopItemSync(4, id).costs)
        inventory.setPlayerItemSync(player.id, cost.id, 1000000)
    clock.setServerTime(new Date('2026-10-31T12:00:00Z'))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/shop').default, { prefix: '/shop' })
    await app.register(load('routes/api/howToGet').default, { prefix: '/how' }); await app.ready()
})
after(async () => {
    clock.setServerTime(null)
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    fs.rmSync(directory, { recursive: true })
})

test('all seven quest periods expose exactly their own native shop batch despite all 381 products being opened', async () => {
    assert.equal(productIds.length, 381)
    const expectedCounts = [26, 34, 39, 44, 49, 54, 10]
    for (let period = 0; period < 7; period++) {
        selectPeriod(1020 + period * 3)
        const expected = productIds.filter(id => period < 6 ? Math.floor(id / 1000) === 100 + period : id >= 106127)
        assert.equal(expected.length, expectedCounts[period])
        const { shopContentDecision } = load('lib/content-economy-operations')
        assert.deepEqual(productIds.filter(id => shopContentDecision(4, id, 'visible') === true), expected)
        const actual = await sales()
        const { isShopItemInSelectedLineupSync } = load('lib/shop-campaign-lineup')
        assert.deepEqual(actual.map(row => row.shop_item_id).sort((a, b) => a - b),
            expected.filter(id => isShopItemInSelectedLineupSync(player.id, 4, id)))
    }
})

test('permanent beast period retains only the active monthly batch and switches at its original boundary', async () => {
    selectPeriod(1038)
    const { challengeShopPeriodAllows } = load('lib/content-challenge-shop-period')
    const monthly = productIds.filter(id => id >= 106001)
    const batches = new Map()
    for (const id of monthly) {
        const item = assets.getShopItemSync(4, id), list = batches.get(item.availableFrom) ?? []
        list.push(id); batches.set(item.availableFrom, list)
    }
    assert.equal(batches.size, 14)
    for (const [from, expected] of batches) {
        const now = new Date(from.replace(' ', 'T') + 'Z')
        assert.deepEqual(monthly.filter(id => challengeShopPeriodAllows(id, ['13:1038'], now)), expected)
        const until = assets.getShopItemSync(4, expected[0]).availableUntil
        if (until) {
            const end = new Date(until.replace(' ', 'T') + 'Z')
            assert.deepEqual(monthly.filter(id => challengeShopPeriodAllows(id, ['13:1040'], end)), expected)
            assert.ok(expected.every(id => !challengeShopPeriodAllows(id, ['13:1039'], new Date(end.getTime() + 1))))
        }
    }
    try {
    for (const [time, first, last] of [
        ['2023-10-26T12:00:00Z', 106001, 106009], ['2023-11-01T04:59:58Z', 106001, 106009],
        ['2023-11-01T05:00:00Z', 106010, 106018], ['2024-11-01T05:00:00Z', 106127, 106136],
    ]) {
        clock.setServerTime(new Date(time))
        assert.deepEqual((await sales()).map(row => row.shop_item_id), productIds.filter(id => id >= first && id <= last))
    }
    } finally { clock.setServerTime(new Date('2026-10-31T12:00:00Z')) }
})

test('stale single and mixed bulk purchases cannot consume currency or stock from another quest or monthly period', async () => {
    selectPeriod(1038)
    const before = snapshot()
    for (const id of [100010, 105000, 106001, 106126]) assert.equal((await buy(id)).statusCode, 400)
    assert.deepEqual(snapshot(), before)
    const response = await post('/shop/bulk_buy', { shop_type: 4, buy_item_list: { 100030: 1, 106001: 1, 106127: 1 } })
    assert.equal(response.statusCode, 200, response.body)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, 100030), 0)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, 106001), 0)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, 106127), 1)
    const current = (await sales()).find(row => row.shop_item_id === 106127)
    assert.equal(current.total_purchase_num, 1)
})

test('switching away and back preserves purchases and sold-out stock; entry closure alone still allows the selected exchange', async () => {
    selectPeriod(1020)
    load('data/domains/shop-campaign-lineup').selectPlayerShopCampaignLineupSync(player.id, 4, 10, 1010)
    const first = await buy(100010)
    assert.equal(first.statusCode, 200, first.body)
    const purchased = snapshot()
    selectPeriod(1038); selectPeriod(1020, false)
    assert.deepEqual(snapshot(), purchased)
    assert.equal((await sales()).find(row => row.shop_item_id === 100010).stock_quantity, 0)
    assert.equal((await buy(100010)).statusCode, 400)
    assert.equal((await buy(100030)).statusCode, 200)
    update(`event_item_shop:100040`, { exchange: review(false) })
    const closed = snapshot()
    assert.equal((await buy(100040)).statusCode, 400)
    assert.deepEqual(snapshot(), closed)
})

test('acquisition navigation follows the same period and a hidden or invalid mixed parent cannot authorize purchases', async () => {
    selectPeriod(1038)
    const equipmentId = assets.getShopItemSync(4, 106127).rewards[0].id
    const response = await post('/how/get_list', { equipment_id: equipmentId })
    assert.equal(response.statusCode, 200, response.body)
    const associated = JSON.parse(response.body).data.shop_sales_list.filter(row => productIds.includes(row.shop_item_id))
    assert.deepEqual(associated.map(row => row.shop_item_id), [106127])
    const state = store.state(parentKey)
    const unchanged = snapshot()
    for (const scope of [undefined, null, [...state.actionOverrides.visible.questKeys, '13:1020']]) {
        const malformed = structuredClone(state)
        malformed.actionOverrides.visible.questKeys = scope
        db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(malformed), parentKey)
        assert.deepEqual(await sales(), [])
        assert.equal((await buy(106128)).statusCode, 400)
        assert.deepEqual(snapshot(), unchanged)
    }
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(state), parentKey)
    update(parentKey, { visible: review(false), enter: review(false) })
    assert.deepEqual(await sales(), [])
    assert.equal((await buy(106128)).statusCode, 400)
    assert.deepEqual(snapshot(), unchanged)
})

test('a period switch while purchase waits for its transaction is rechecked for both single and bulk buys', async () => {
    const coordinator = load('lib/persistence-coordinator'), original = coordinator.runPersistenceTransaction
    try {
        for (const bulk of [false, true]) {
            selectPeriod(1038)
            const unchanged = snapshot()
            let switched = false
            coordinator.runPersistenceTransaction = async (context, callback, options) => {
                if (!switched && ['purchase', 'bulk_purchase'].includes(context.operation)) { switched = true; selectPeriod(1020) }
                return original(context, callback, options)
            }
            const response = bulk ? await post('/shop/bulk_buy', { shop_type: 4, buy_item_list: { 106128: 1 } }) : await buy(106128)
            assert.ok(switched)
            assert.equal(response.statusCode, bulk ? 200 : 400, response.body)
            assert.deepEqual(snapshot(), unchanged)
        }
    } finally { coordinator.runPersistenceTransaction = original }
})
