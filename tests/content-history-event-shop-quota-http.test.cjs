'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID, createHash } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-event-quota-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
const assets = load('lib/assets'), operations = load('lib/content-operations'), quota = load('lib/shop-quota')
const players = load('data/domains/player'), inventory = load('data/domains/item'), purchases = load('data/domains/shopPurchase')
const utils = load('utils'), coordinator = load('lib/persistence-coordinator')
const transaction = coordinator.runPersistenceTransaction, getDate = utils.getServerDate
const rules = require('../assets/content_history_shop_rules.json'), master = load('lib/content-master')
const anchor = Date.parse('2026-10-20T12:00:00Z')
let at = new Date(anchor), app, db, tables
const quote = value => '"' + value.replaceAll('"', '""') + '"'
function fixture(id) {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'history-event-quota', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 880000000 + player.id
    db.transaction(() => load('lib/server-clock-state').ensurePlayerClockStateForLoadSync(player.id, db))()
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    const item = assets.getShopItemSync(4, id)
    for (const cost of item.costs) inventory.setPlayerItemSync(player.id, cost.id, Math.max(cost.amount * 10000, 10000))
    return { id: player.id, viewer, item }
}
function snapshot(player) {
    return Object.fromEntries(tables.map(({ name, owner }) => [name,
        db.prepare(`SELECT * FROM ${quote(name)} WHERE ${quote(owner)}=?`).all(player.id)
            .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))]))
}
function control(key, enabled) {
    const store = operations.contentOperations()
    store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Native activity product limits, exact synthetic HTTP scenario', actionOverrides: {
            visible: { enabled, endsAtMs: null, readiness: 'verified', evidence: 'Native activity product visibility; synthetic sales and acquisition navigation' },
            exchange: { enabled, endsAtMs: null, readiness: 'verified', evidence: 'Native col29/30/31; exact product and parent with retained purchase counts' }
        } }, Date.now())
}
function enable(id) {
    const row = operations.contentCatalog.rows.find(row => row.key === `event_item_shop:${id}`)
    assert.ok(row?.parentKey); control(row.parentKey, true); control(row.key, true)
    return row
}
const post = (player, url, body) => app.inject({ method: 'POST', url,
    payload: { viewer_id: player.viewer, api_count: 1, ...body } })
const buy = (player, id, number = 1) => post(player, '/shop/buy', { shop_type: 4, shop_item_id: id, number })
const bulk = (player, id, number) => post(player, '/shop/bulk_buy', { shop_type: 4, buy_item_list: { [id]: number } })
function success(result) { assert.equal(result.statusCode, 200, result.body); return result.json().data }
const state = (player, id) => quota.getShopQuotaStateSync(player.id, 4, id, assets.getShopItemSync(4, id), at)

before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    const options = { cutoverRealMs: anchor, legacyOffsetMs: 0, readiness: 'scenario-only',
        offlineGuard: { kind: 'approved-offline-file', databasePath: fs.realpathSync(db.name), allowedRoot: directory } }
    const plan = load('lib/time-cutover-rehearsal').planTimeCutoverRehearsalSync(db, options)
    load('lib/server-clock-state').activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: plan.digest })
    utils.installServerClockSnapshot(load('lib/server-clock-state').readServerClockStateSync(db).snapshot)
    utils.getServerDate = () => new Date(at)
    tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all()
        .map(({ name }) => ({ name, columns: db.prepare(`PRAGMA table_info(${quote(name)})`).all().map(row => row.name) }))
        .filter(row => row.name === 'players' || row.columns.includes('player_id'))
        .map(row => ({ name: row.name, owner: row.name === 'players' ? 'id' : 'player_id' }))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/shop').default, { prefix: '/shop' })
    await app.register(load('routes/api/howToGet').default, { prefix: '/how' }); await app.ready()
})
after(async () => {
    coordinator.runPersistenceTransaction = transaction; utils.getServerDate = getDate
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root); fs.rmSync(directory, { recursive: true })
})

test('all 8579 actual product getters separate native limits and preserve costs, rewards and public master bytes', () => {
    const digest = () => createHash('sha256').update(JSON.stringify(master.serverEventShops)).digest('hex')
    const before = digest()
    assert.equal(Object.keys(rules.products).length, 8579)
    for (const [key, rule] of Object.entries(rules.products)) {
        const id = Number(key.split(':')[1]), item = assets.getShopItemSync(4, id), native = rule.native
        const map = master.serverEventShopIdMap[id], raw = master.serverEventShops[map.eventType][map.eventId][id]
        assert.equal(item.stock, native.max_frequency ?? 0, key)
        assert.deepEqual(item.nativeStockLimits, { perRequest: native.buy_max_count, lifetime: native.max_frequency }, key)
        assert.equal(item.dailyStock, native.daily_stock ?? undefined, key)
        assert.equal(item.monthlyStock, undefined, key)
        assert.equal(item.kind1EquipmentOnlyPossessionOne, native.kind1_equipment_only_possession_one, key)
        for (const field of ['costs', 'rewards', 'userCost', 'availableFrom', 'availableUntil']) assert.deepEqual(item[field], raw[field], `${key}:${field}`)
    }
    assert.equal(digest(), before)
    for (let id = 9700121; id <= 9700129; id++) assert.equal(assets.getShopItemSync(4, id).nativeStockLimits, undefined, `uncatalogued ${id} remains unprojected`)
})

test('a native daily event product is available again at 05:00 while its lifetime purchase count keeps growing', async () => {
    const id = 10000; enable(id); const player = fixture(id)
    at = new Date('2026-10-20T20:59:59Z')
    assert.equal(state(player, id).remaining, 1); success(await buy(player, id))
    const before = snapshot(player); assert.equal((await buy(player, id)).statusCode, 400); assert.deepEqual(snapshot(player), before)
    at = new Date('2026-10-20T21:00:00Z')
    assert.equal(state(player, id).remaining, 1); success(await buy(player, id))
    assert.equal(state(player, id).total, 2); assert.equal(state(player, id).today, 1); assert.equal(state(player, id).remaining, 0)
})

test('an unlimited native product enforces the per-request maximum without turning it into a lifetime cap', async () => {
    const id = 10002259; enable(id); const player = fixture(id)
    assert.equal(player.item.nativeStockLimits.perRequest, 999); assert.equal(state(player, id).remaining, Infinity)
    const before = snapshot(player); assert.equal((await buy(player, id, 1000)).statusCode, 400); assert.deepEqual(snapshot(player), before)
    success(await buy(player, id, 999)); success(await buy(player, id, 1))
    assert.equal(state(player, id).total, 1000); assert.equal(state(player, id).remaining, Infinity)
})

test('finite cumulative stock includes old purchases, bulk caps to remaining, and publication never resets it', async () => {
    const id = 203001, row = enable(id), player = fixture(id)
    purchases.addPlayerShopPurchaseCountSync(player.id, id, 9)
    const before = snapshot(player); assert.equal((await buy(player, id, 2)).statusCode, 400); assert.deepEqual(snapshot(player), before)
    success(await bulk(player, id, 50)); assert.equal(state(player, id).total, 10)
    control(row.parentKey, false); control(row.parentKey, true)
    const after = snapshot(player); assert.equal((await buy(player, id)).statusCode, 400); assert.deepEqual(snapshot(player), after)
})

test('final transaction rechecks daily quota after another real HTTP purchase commits while queued', async () => {
    const id = 10000; enable(id); const player = fixture(id); let first = true
    coordinator.runPersistenceTransaction = async (context, fn, options) => {
        if (context.operation === 'purchase' && first) { first = false; success(await buy(player, id)) }
        return transaction(context, fn, options)
    }
    try { assert.equal((await buy(player, id)).statusCode, 400) } finally { coordinator.runPersistenceTransaction = transaction }
    assert.equal(state(player, id).total, 1); assert.equal(state(player, id).today, 1)
})

test('purchase-history SQL failure rolls daily quota, cost and rewards back atomically', async () => {
    const id = 10000; enable(id); const player = fixture(id), before = snapshot(player)
    db.exec(`CREATE TRIGGER fail_event_quota_history BEFORE INSERT ON players_shop_purchases WHEN NEW.player_id=${player.id} BEGIN SELECT RAISE(ABORT,'event quota history failure'); END`)
    try { assert.equal((await buy(player, id)).statusCode, 500); assert.deepEqual(snapshot(player), before) }
    finally { db.exec('DROP TRIGGER fail_event_quota_history') }
    success(await buy(player, id)); assert.equal(state(player, id).total, 1)
})

test('undated old purchases reserve the cutover day only, and native sales and acquisition rows share the next-day ledger', async () => {
    const id = 10000; enable(id); const player = fixture(id)
    purchases.addPlayerShopPurchaseCountSync(player.id, id, 12); at = new Date(anchor)
    assert.equal(state(player, id).migrationState, 'legacy-carry'); assert.equal(state(player, id).remaining, 0)
    const before = snapshot(player); assert.equal((await buy(player, id)).statusCode, 400); assert.deepEqual(snapshot(player), before)
    at = new Date('2026-10-20T21:00:00Z'); success(await bulk(player, id, 99)); assert.equal(state(player, id).total, 13)
    const listing = success(await post(player, '/shop/get_sales_list', { shop_types: [], event_list: [{ event_type: 0, event_ids: [100005] }], boss_coin_shop_category_ids: [], equipment_enhancement_category_ids: [] }))
    const sale = listing.sales_list.find(row => row.shop_item_id === id)
    assert.equal(sale.stock_quantity, 0); assert.equal(sale.today_purchase_num, 1); assert.equal(sale.total_purchase_num, 13)
    const acquisition = success(await post(player, '/how/get_list', { item_id: 4 })).shop_sales_list.find(row => row.shop_type === 4 && row.shop_item_id === id)
    assert.deepEqual(acquisition, sale)
})
