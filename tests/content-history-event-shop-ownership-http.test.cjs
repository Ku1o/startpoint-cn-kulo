'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-event-shop-ownership-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const operations = load('lib/content-operations'), assets = load('lib/assets')
const players = load('data/domains/player'), inventory = load('data/domains/item')
const equipment = load('data/domains/equipment'), purchases = load('data/domains/shopPurchase')
const coordinator = load('lib/persistence-coordinator'), transaction = coordinator.runPersistenceTransaction
const { ShopType } = load('lib/types')
let app, db, tables
const quote = name => '"' + name.replaceAll('"', '""') + '"'

function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'shop-semantics', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 880000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    const types = load('data/types').SessionType
    for (const [token, type] of [[String(viewer), types.VIEWER], [randomUUID(), types.ZAT]]) {
        db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,?)').run(token, account.id, '2099-01-01T00:00:00Z', type)
    }
    return { id: player.id, viewer }
}
function snapshot(player) {
    return Object.fromEntries(tables.map(({ name, owner }) => [name,
        db.prepare(`SELECT * FROM ${quote(name)} WHERE ${quote(owner)}=?`).all(player.id)
            .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))]))
}
function controlKey(key, enabled = true) {
    const store = operations.contentOperations()
    store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Exact historical event equipment ownership regression', actionOverrides: {
            exchange: { enabled, endsAtMs: null, readiness: 'verified',
                evidence: 'Winning native col50 ownership rule and current exact catalog identity; synthetic player only' }
        } }, Date.now())
}
function enableProduct(id) {
    const row = operations.contentCatalog.rows.find(row => row.key === `event_item_shop:${id}`)
    assert.ok(row?.parentKey); controlKey(row.parentKey); controlKey(row.key)
    return row
}
function funded(id) {
    const player = fixture(), item = assets.getShopItemSync(ShopType.EVENT_ITEM, id)
    players.updatePlayerSync({ id: player.id, freeMana: 1000000000, paidMana: 1000000000,
        freeVmoney: 100000000, vmoney: 100000000, bondToken: 100000000 })
    for (const cost of item.costs) inventory.setPlayerItemSync(player.id, cost.id, cost.amount * 20)
    return { player, item }
}
const buy = (player, id, number = 1) => app.inject({ method: 'POST', url: '/shop/buy',
    payload: { viewer_id: player.viewer, api_count: 1, shop_type: ShopType.EVENT_ITEM, shop_item_id: id, number } })
const bulk = (player, ids) => app.inject({ method: 'POST', url: '/shop/bulk_buy',
    payload: { viewer_id: player.viewer, api_count: 1, shop_type: ShopType.EVENT_ITEM,
        buy_item_list: Object.fromEntries(ids.map(id => [id, 1])) } })
const successful = result => assert.equal(result.statusCode, 200, result.body)

before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all()
        .map(({ name }) => ({ name, columns: db.prepare(`PRAGMA table_info(${quote(name)})`).all().map(row => row.name) }))
        .filter(row => row.name === 'players' || row.columns.includes('player_id'))
        .map(row => ({ name: row.name, owner: row.name === 'players' ? 'id' : 'player_id' }))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/shop').default, { prefix: '/shop' }); await app.ready()
})
after(async () => {
    coordinator.runPersistenceTransaction = transaction
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root)
    fs.rmSync(directory, { recursive: true })
})

const uniqueIds = [10001476, 10003146, 10004466, 10004496, 10004526, 10004527, 10005185, 10005255, 10005256]
test('all 8579 associated native rows project the exact nine unique-first-equipment flags', () => {
    const rules = require('../assets/content_history_shop_rules.json')
    assert.equal(Object.keys(rules.products).length, 8579)
    const flagged = []
    for (const [key, node] of Object.entries(rules.products)) {
        const id = Number(key.split(':')[1]), item = assets.getShopItemSync(ShopType.EVENT_ITEM, id)
        assert.ok(item, key)
        assert.equal(item.kind1EquipmentOnlyPossessionOne, node.native.kind1_equipment_only_possession_one, key)
        if (item.kind1EquipmentOnlyPossessionOne) { flagged.push(id); assert.equal(item.rewards[0].type, 4, key) }
    }
    assert.deepEqual(flagged.sort((a, b) => a - b), uniqueIds)
})

test('all nine already-owned unique event products reject single buy and skip bulk without currency, stock or equipment changes', async () => {
    for (const id of uniqueIds) {
        enableProduct(id)
        const { player, item } = funded(id)
        load('lib/equipment').givePlayerEquipmentSync(player.id, item.rewards[0].id, 1)
        const before = snapshot(player)
        assert.equal((await buy(player, id)).statusCode, 400, String(id))
        assert.deepEqual(snapshot(player), before)
        successful(await bulk(player, [id])); assert.deepEqual(snapshot(player), before)
    }
    const first = uniqueIds[0], second = uniqueIds[1]
    enableProduct(first); enableProduct(second)
    const { player, item } = funded(first), nextItem = assets.getShopItemSync(ShopType.EVENT_ITEM, second)
    assert.equal(item.rewards[0].id, nextItem.rewards[0].id)
    for (const cost of nextItem.costs) inventory.setPlayerItemSync(player.id, cost.id,
        Math.max(inventory.getPlayerItemSync(player.id, cost.id) ?? 0, cost.amount * 20))
    successful(await bulk(player, [first, second]))
    assert.equal(equipment.getPlayerEquipmentSync(player.id, item.rewards[0].id).stack, item.rewards[0].count - 1)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, first), 1)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, second), 0)
})

test('a unique first purchase grants exactly once under concurrency; closing and reopening cannot restore that ownership entitlement', async () => {
    const id = uniqueIds[0], row = enableProduct(id), { player, item } = funded(id)
    const results = await Promise.all([buy(player, id), buy(player, id)])
    assert.deepEqual(results.map(result => result.statusCode).sort(), [200, 400])
    assert.equal(equipment.getPlayerEquipmentSync(player.id, item.rewards[0].id).stack, item.rewards[0].count - 1)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, id), 1)
    const after = snapshot(player)
    controlKey(row.parentKey, false)
    assert.equal((await buy(player, id)).statusCode, 400); assert.deepEqual(snapshot(player), after)
    controlKey(row.parentKey, true)
    assert.equal((await buy(player, id)).statusCode, 400); assert.deepEqual(snapshot(player), after)
})

test('equipment arriving while a buy waits in the writer queue is rechecked inside the final transaction', async () => {
    const id = uniqueIds[0]; enableProduct(id)
    const { player, item } = funded(id)
    let queuedSnapshot, queued = false
    coordinator.runPersistenceTransaction = async (context, callback, options) => {
        if (!queued && context.operation === 'purchase') {
            queued = true; load('lib/equipment').givePlayerEquipmentSync(player.id, item.rewards[0].id, 1)
            queuedSnapshot = snapshot(player)
        }
        return transaction(context, callback, options)
    }
    try { assert.equal((await buy(player, id)).statusCode, 400); assert.ok(queued); assert.deepEqual(snapshot(player), queuedSnapshot) }
    finally { coordinator.runPersistenceTransaction = transaction }
})

test('unflagged event equipment remains purchasable by an owner within its original quota', async () => {
    const id = 10000647; enableProduct(id)
    const { player, item } = funded(id), reward = item.rewards[0]
    assert.equal(item.kind1EquipmentOnlyPossessionOne, false)
    load('lib/equipment').givePlayerEquipmentSync(player.id, reward.id, 1)
    const old = equipment.getPlayerEquipmentSync(player.id, reward.id)
    successful(await buy(player, id))
    assert.equal(equipment.getPlayerEquipmentSync(player.id, reward.id).stack, old.stack + reward.count)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, id), 1)

    // These two actual historical products grant the same equipment. The first
    // has no unique flag; its already-planned reward must still block the second.
    const normalId = 10000647, uniqueId = uniqueIds[0]
    enableProduct(normalId); enableProduct(uniqueId)
    const pending = funded(normalId), next = assets.getShopItemSync(ShopType.EVENT_ITEM, uniqueId)
    assert.equal(pending.item.kind1EquipmentOnlyPossessionOne, false)
    assert.equal(pending.item.rewards[0].id, next.rewards[0].id)
    for (const cost of next.costs) inventory.setPlayerItemSync(pending.player.id, cost.id,
        Math.max(inventory.getPlayerItemSync(pending.player.id, cost.id) ?? 0, cost.amount * 20))
    successful(await bulk(pending.player, [normalId, uniqueId]))
    assert.equal(equipment.getPlayerEquipmentSync(pending.player.id, next.rewards[0].id).stack, pending.item.rewards[0].count - 1)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(pending.player.id, normalId), 1)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(pending.player.id, uniqueId), 0)
})

test('unique event purchase rolls back payment and equipment on a receipt failure, then a retry grants once', async () => {
    const id = uniqueIds[0]; enableProduct(id)
    const { player, item } = funded(id), before = snapshot(player)
    db.exec(`CREATE TEMP TRIGGER event_shop_ownership_rollback BEFORE INSERT ON players_shop_purchases
        WHEN NEW.player_id=${player.id} BEGIN SELECT RAISE(ABORT, 'synthetic event ownership receipt failure'); END`)
    try { assert.equal((await buy(player, id)).statusCode, 500); assert.deepEqual(snapshot(player), before) }
    finally { db.exec('DROP TRIGGER event_shop_ownership_rollback') }
    successful(await buy(player, id))
    assert.equal(equipment.getPlayerEquipmentSync(player.id, item.rewards[0].id).stack, item.rewards[0].count - 1)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, id), 1)
})
