const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const Fastify = require('fastify'), { pack, unpack } = require('msgpackr')
const f = require('./helpers/upstream-business-fixture.cjs').fixture('bond-token-shop-compat')
const players = f.load('data/domains/player'), equipment = f.load('data/domains/equipment'), bond = f.load('lib/bond-token-exchange')
const purchase = f.load('data/domains/shopPurchase'); let app
const post = (player, url, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: player.viewer, ...body } })
function data(response) { assert.equal(response.statusCode, 200, response.body); return unpack(Buffer.from(response.body, 'base64')).data }
function create() { const player = f.create(); players.updatePlayerSync({ id: player.id, bondToken: 500 }); return player }
function snapshot(player) { return { bond: players.getPlayerSync(player.id).bondToken, equipment: equipment.getPlayerEquipmentSync(player.id, 5010005),
    count: bond.getBondTokenExchangeCountSync(player.id, 5010005), legacy: purchase.getPlayerShopPurchaseCountSync(player.id, 100001) } }
const buy = player => post(player, '/buy', { shop_type: 8, shop_item_id: 100001, number: 1 })
const bulk = player => post(player, '/bulk_buy', { shop_type: 8, buy_item_list: { 100001: 1 } })
const native = player => post(player, '/native/bond_token', { equipment_id: 5010005 })
before(async () => {
    app = Fastify({ logger: false })
    app.addHook('onSend', (_r, reply, body, done) => done(null, String(reply.getHeader('content-type')).startsWith('application/x-msgpack') ? pack(body).toString('base64') : body))
    await app.register(f.load('routes/api/shop').default)
    await app.register(f.load('routes/api/exchange').default, { prefix: '/native' })
    await app.register(f.load('routes/api/howToGet').default, { prefix: '/how' }); await app.ready()
})
after(async () => { await app.close(); await f.close() })
test('native exchange consumes the same once-only stock shown and enforced by legacy single/bulk shop', async () => {
    const player = create(); data(await native(player)); const committed = snapshot(player)
    assert.equal(committed.bond, 450); assert.equal(committed.legacy, 1)
    assert.equal((await buy(player)).statusCode, 400); data(await bulk(player)); assert.deepEqual(snapshot(player), committed)
    const sales = data(await post(player, '/get_sales_list', { shop_types: [8], event_list: [], boss_coin_shop_category_ids: [], equipment_enhancement_category_ids: [] })).sales_list
    assert.equal(sales.find(item => item.shop_item_id === 100001).stock_quantity, 0)
})
test('either legacy single or bulk purchase prevents a second grant through the native endpoint', async () => {
    for (const purchase of [buy, bulk]) {
        const player = create(); data(await purchase(player)); const committed = snapshot(player)
        assert.equal(committed.bond, 450); assert.equal(committed.count, 1)
        assert.equal((await native(player)).statusCode, 400); assert.deepEqual(snapshot(player), committed)
    }
})
test('target-local receipt protects legacy shop and acquisition stock after an older portable ledger replaces counts', async () => {
    const player = create(); data(await native(player))
    f.db.prepare('DELETE FROM players_shop_purchases WHERE player_id=? AND shop_item_id=100001').run(player.id)
    f.db.prepare('DELETE FROM players_bond_token_exchanges WHERE player_id=? AND equipment_id=5010005').run(player.id)
    const committed = snapshot(player); assert.equal(committed.count, 1); assert.equal(committed.legacy, 0)
    assert.equal((await buy(player)).statusCode, 400); data(await bulk(player)); assert.deepEqual(snapshot(player), committed)
    const sources = data(await post(player, '/how/get_list', { equipment_id: 5010005 })).shop_sales_list
    assert.equal(sources.find(item => item.shop_type === 8 && item.shop_item_id === 100001).stock_quantity, 0)
})
