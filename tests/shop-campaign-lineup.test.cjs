const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const Fastify = require('fastify'), { pack, unpack } = require('msgpackr')
const f = require('./helpers/upstream-business-fixture.cjs').fixture('shop-campaign-lineup')
const player = f.create(), other = f.create(), utils = f.load('utils'), items = f.load('data/domains/item')
const coordinator = f.load('lib/persistence-coordinator'), originalTransaction = coordinator.runPersistenceTransaction
const selections = f.load('data/domains/shop-campaign-lineup'), quota = f.load('data/domains/shopPurchase')
const originalDate = utils.getServerDate; let at = new Date('2022-12-23T12:00:00Z'), app
const post = (url, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: player.viewer, ...body } })
function data(response) { assert.equal(response.statusCode, 200, response.body); return unpack(Buffer.from(response.body, 'base64')).data }
const campaign = { shop_type: 4, campaign_id: 10 }
const buy = id => post('/buy', { shop_type: 4, shop_item_id: id, number: 1 })
const snapshot = () => ({ money: items.getPlayerItemSync(player.id, 30005),
    choices: f.db.prepare('SELECT * FROM players_shop_campaign_lineups WHERE player_id=?').all(player.id),
    buys: quota.getPlayerShopPurchasesMapSync(player.id) })
function control(enabled) {
    const store = f.load('lib/content-operations').contentOperations()
    const review = { readiness: 'verified', evidence: 'Isolated campaign selection route fixture', endsAtMs: null, enabled }
    const memberships = require('../assets/shop_item_campaign.json')['4']
    f.db.transaction(() => {
        for (const key of ['challenge_dungeon_event:1', ...Object.entries(memberships).filter(([, value]) => value.campaignId === 10).map(([id]) => `event_item_shop:${id}`)]) {
            store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Isolated campaign route fixture',
                actionOverrides: { visible: review, exchange: review } }, Date.now())
        }
    })()
}
before(async () => {
    utils.getServerDate = () => new Date(at)
    items.setPlayerItemSync(player.id, 30005, 100)
    control(true)
    app = Fastify({ logger: false })
    app.addHook('onSend', (_r, reply, body, done) => done(null, String(reply.getHeader('content-type')).startsWith('application/x-msgpack') ? pack(body).toString('base64') : body))
    await app.register(f.load('routes/api/shop').default)
    await app.register(f.load('routes/api/howToGet').default, { prefix: '/how' }); await app.ready()
})
after(async () => { utils.getServerDate = originalDate; coordinator.runPersistenceTransaction = originalTransaction; await app.close(); await f.close() })

test('unselected campaign hides alternate lineups and direct/bulk requests cannot bypass the choice', async () => {
    assert.equal(data(await post('/get_campaign_lineup_id', campaign)).lineup_id, null)
    const before = snapshot()
    assert.equal((await buy(100010)).statusCode, 400)
    data(await post('/bulk_buy', { shop_type: 4, buy_item_list: { 100010: 1, 100020: 1 } }))
    const sales = data(await post('/get_sales_list', { shop_types: [4], event_list: [{ event_type: 4, event_ids: [1] }], boss_coin_shop_category_ids: [], equipment_enhancement_category_ids: [] })).sales_list
    assert.equal(sales.some(item => item.shop_item_id === 100010 || item.shop_item_id === 100020), false)
    assert.equal(data(await post('/how/get_list', { equipment_id: 5020025 })).shop_sales_list.some(item => item.shop_item_id === 100010), false)
    assert.deepEqual(snapshot(), before)
})
test('validated lineup is immutable, idempotent, player-scoped and shared by list/single/bulk checks', async () => {
    assert.equal((await post('/set_campaign_lineup_id', { ...campaign, lineup_id: 99999 })).statusCode, 400)
    assert.equal((await post('/set_campaign_lineup_id', { ...campaign, campaign_id: 99999, lineup_id: 1010 })).statusCode, 400)
    data(await post('/set_campaign_lineup_id', { ...campaign, lineup_id: 1010 }))
    data(await post('/set_campaign_lineup_id', { ...campaign, lineup_id: 1010 }))
    assert.equal((await post('/set_campaign_lineup_id', { ...campaign, lineup_id: 1020 })).statusCode, 400)
    assert.equal(data(await post('/get_campaign_lineup_id', campaign)).lineup_id, 1010)
    assert.equal(selections.getPlayerShopCampaignLineupSync(other.id, 4, 10), null)
    assert.equal((await buy(100020)).statusCode, 400)
    const sales = data(await post('/get_sales_list', { shop_types: [4], event_list: [{ event_type: 4, event_ids: [1] }], boss_coin_shop_category_ids: [], equipment_enhancement_category_ids: [] })).sales_list
    assert.equal(sales.some(item => item.shop_item_id === 100010), true)
    assert.equal(sales.some(item => item.shop_item_id === 100020), false)
    assert.equal(data(await post('/how/get_list', { equipment_id: 5020025 })).shop_sales_list.some(item => item.shop_item_id === 100010), true)
    data(await buy(100010)); assert.equal(items.getPlayerItemSync(player.id, 30005), 95)
    const committed = snapshot()
    assert.equal((await buy(100010)).statusCode, 400, 'existing lifetime stock remains enforced')
    data(await post('/bulk_buy', { shop_type: 4, buy_item_list: { 100010: 9, 100020: 9 } }))
    assert.deepEqual(snapshot(), committed)
    const disk = new (require('better-sqlite3'))(f.db.name, { readonly: true })
    try { assert.equal(disk.prepare('SELECT lineup_id FROM players_shop_campaign_lineups WHERE player_id=?').get(player.id).lineup_id, 1010) }
    finally { disk.close() }
    const archive = f.load('data/snapshots/player-snapshot').createPlayerSaveSnapshotV2Sync(player.id, f.db)
    assert.equal(archive.data.tables.players_shop_campaign_lineups.rows.length, 1)
})
test('selection and purchase failures roll back without changing the durable choice or balances', async () => {
    const before = snapshot()
    coordinator.runPersistenceTransaction = (context, run, options) => originalTransaction(context, () => {
        const result = run(); if (context.operation === 'select_campaign_lineup' || context.operation === 'purchase') throw new Error('injected shop rollback')
        return result
    }, options)
    try {
        assert.equal((await post('/set_campaign_lineup_id', { viewer_id: other.viewer, ...campaign, lineup_id: 1020 })).statusCode, 500)
        assert.equal(selections.getPlayerShopCampaignLineupSync(other.id, 4, 10), null)
        assert.equal((await buy(100011)).statusCode, 500)
        assert.deepEqual(snapshot(), before)
    } finally { coordinator.runPersistenceTransaction = originalTransaction }
})
test('unavailable campaign uses the client period code and invalid sessions cannot read or select', async () => {
    at = new Date('2020-01-01T00:00:00Z')
    control(false)
    const result = await post('/set_campaign_lineup_id', { viewer_id: other.viewer, ...campaign, lineup_id: 1020 })
    assert.equal(result.statusCode, 200)
    assert.equal(unpack(Buffer.from(result.body, 'base64')).data_headers.result_code, 1652)
    assert.equal(selections.getPlayerShopCampaignLineupSync(other.id, 4, 10), null)
    assert.equal((await post('/get_campaign_lineup_id', { viewer_id: 1, ...campaign })).statusCode, 400)
})
test('chosen campaign survives V1 replacement and travels with the V2 player archive', () => {
    const saves = f.load('data/snapshots/player-snapshot'), players = f.load('data/domains/player')
    players.replacePlayerDataSync(f.load('data/utils/player-data').getMergedPlayerDataSync(player.id))
    assert.equal(selections.getPlayerShopCampaignLineupSync(player.id, 4, 10), 1010)
    const archive = saves.createPlayerSaveSnapshotV2Sync(player.id, f.db)
    saves.restorePlayerSaveSnapshotV2Sync(archive, other.id, {}, f.db)
    assert.equal(selections.getPlayerShopCampaignLineupSync(other.id, 4, 10), 1010)
    assert.equal(selections.selectPlayerShopCampaignLineupSync(other.id, 4, 10, 1020), 'conflict')
})
