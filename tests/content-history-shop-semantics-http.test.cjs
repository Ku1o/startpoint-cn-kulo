'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-shop-semantics-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const operations = load('lib/content-operations'), assets = load('lib/assets')
const players = load('data/domains/player'), inventory = load('data/domains/item')
const equipment = load('data/domains/equipment'), purchases = load('data/domains/shopPurchase')
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
function control(id) {
    const store = operations.contentOperations()
    store.update(`general_shop:${id}`, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Focused synthetic server transaction semantics', actionOverrides: {
            exchange: { enabled: true, endsAtMs: null, readiness: 'verified',
                evidence: 'Current exact catalog identity; this test verifies only existing currency and equipment transaction behavior' }
        } }, Date.now())
}
const buy = (player, id, number = 1) => app.inject({ method: 'POST', url: '/shop/buy',
    payload: { viewer_id: player.viewer, api_count: 1, shop_type: ShopType.GENERAL, shop_item_id: id, number } })
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
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root)
    fs.rmSync(directory, { recursive: true })
})

test('all 302 current general products are in the original sales whitelist', () => {
    const raw = require('../assets/general_shop.json'), whitelist = require('../assets/cdn_general_shop_whitelist.json')
    assert.equal(Object.keys(raw).length, 302)
    const keys = Array.isArray(whitelist) ? whitelist.map(String) : Object.keys(whitelist)
    assert.deepEqual(Object.keys(raw).sort(), keys.sort())
})

test('general equipment may already be owned: BondToken is required and original cumulative stock still applies', async () => {
    const player = fixture(), id = 100001, item = assets.getShopItemSync(ShopType.GENERAL, id)
    assert.deepEqual(item.userCost, { type: 2, amount: 50 }); assert.equal(item.stock, 1)
    control(id)
    load('lib/equipment').givePlayerEquipmentSync(player.id, item.rewards[0].id, 1)
    players.updatePlayerSync({ id: player.id, bondToken: 49, freeMana: 100000000, freeVmoney: 100000 })
    const insufficient = snapshot(player)
    assert.equal((await buy(player, id)).statusCode, 400); assert.deepEqual(snapshot(player), insufficient)
    players.updatePlayerSync({ id: player.id, bondToken: 100 })
    const currency = players.getPlayerSync(player.id), owned = equipment.getPlayerEquipmentSync(player.id, item.rewards[0].id)
    successful(await buy(player, id))
    assert.equal(equipment.getPlayerEquipmentSync(player.id, item.rewards[0].id).stack, owned.stack + 1)
    const after = players.getPlayerSync(player.id)
    assert.equal(after.bondToken, 50); assert.equal(after.freeMana, currency.freeMana); assert.equal(after.freeVmoney, currency.freeVmoney)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, id), 1)
    const exhausted = snapshot(player)
    assert.equal((await buy(player, id)).statusCode, 400); assert.deepEqual(snapshot(player), exhausted)
})

test('current Mana general product pays free first then paid and rejects insufficient funds without partial reward', async () => {
    const player = fixture(), id = 9100012, item = assets.getShopItemSync(ShopType.GENERAL, id)
    assert.equal(item.userCost.type, 1); assert.equal(item.userCost.amount, 10000000)
    control(id)
    const price = item.userCost.amount, reward = item.rewards[0]
    players.updatePlayerSync({ id: player.id, freeMana: price - 1, paidMana: 0 })
    const insufficient = snapshot(player)
    assert.equal((await buy(player, id)).statusCode, 400); assert.deepEqual(snapshot(player), insufficient)
    players.updatePlayerSync({ id: player.id, freeMana: price + 7, paidMana: price })
    const count = inventory.getPlayerItemSync(player.id, reward.id) ?? 0
    successful(await buy(player, id, 2))
    const paid = players.getPlayerSync(player.id)
    assert.equal(paid.freeMana, 0); assert.equal(paid.paidMana, 7)
    assert.equal(inventory.getPlayerItemSync(player.id, reward.id), count + reward.count * 2)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, id), 2)
})

test('failure after currency/reward changes rolls the whole purchase back and a retry grants once', async () => {
    const player = fixture(), id = 100001, item = assets.getShopItemSync(ShopType.GENERAL, id)
    control(id); players.updatePlayerSync({ id: player.id, bondToken: 100 })
    const before = snapshot(player)
    db.exec(`CREATE TEMP TRIGGER shop_semantics_rollback BEFORE INSERT ON players_shop_purchases
        WHEN NEW.player_id=${player.id} BEGIN SELECT RAISE(ABORT, 'synthetic shop receipt failure'); END`)
    try { assert.equal((await buy(player, id)).statusCode, 500); assert.deepEqual(snapshot(player), before) }
    finally { db.exec('DROP TRIGGER shop_semantics_rollback') }
    successful(await buy(player, id))
    assert.equal(players.getPlayerSync(player.id).bondToken, 50)
    assert.equal(equipment.getPlayerEquipmentSync(player.id, item.rewards[0].id).stack, item.rewards[0].count - 1)
    assert.equal(purchases.getPlayerShopPurchaseCountSync(player.id, id), 1)
})
