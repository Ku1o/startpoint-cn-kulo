'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID, createHash } = require('node:crypto')
const { spawnSync } = require('node:child_process')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'gift-bond-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false',
    GAME_ROUTINE_LOGS: 'off', ADMIN_PANEL_PASSWORD: randomUUID() })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const players = load('data/domains/player'), inventory = load('data/domains/item'), gifts = load('lib/gift-codes')
const saves = load('data/snapshots/player-snapshot')
let app, db, cookie
function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'gift-test', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 790000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    return { id: player.id, viewer }
}
const post = (p, url, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: p.viewer, api_count: 1, ...body } })
const admin = (method, suffix = '/', payload, headers = { cookie }) => app.inject({ method, url: '/api/server/gifts' + suffix, payload, headers })
const ok = result => { assert.equal(result.statusCode, 200, result.body); return result.json() }
async function code(rewards = [{ type: 4, type_id: null, number: 10 }]) {
    const key = randomUUID().slice(0, 20)
    const created = ok(await admin('POST', '/', { code: key, note: 'isolated fixture', rewards }))
    ok(await admin('PATCH', '/' + created.id, { revision: 1, enabled: true }))
    return { id: created.id, key }
}
const receiptCount = (p, operation) => db.prepare('SELECT COUNT(*) AS n FROM player_operation_receipts WHERE player_id=? AND operation=?').get(p.id, operation).n
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(fs.realpathSync(path.dirname(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    load('lib/management-auth').installManagementAuth(app)
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/gift').default, { prefix: '/gift' })
    await app.register(load('routes/api/exchange').default, { prefix: '/exchange' })
    await app.register(load('routes/web_api/gift').default, { prefix: '/api/server/gifts' })
    await app.ready()
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    ok(login); cookie = login.headers['set-cookie'].split(';')[0]
})
after(async () => {
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root); fs.rmSync(directory, { recursive: true })
})

test('gift management requires login, validates content, defaults paused and detects stale toggles', async () => {
    assert.equal(gifts.isGiftEnabledSync(), false)
    for (const method of ['GET', 'POST', 'PATCH']) assert.equal((await admin(method, method === 'PATCH' ? '/1' : '/', method === 'GET' ? undefined : {}, {})).statusCode, 401)
    assert.equal((await admin('POST', '/', { code: 'bad', note: '', rewards: [{ type: 5, type_id: 999999999, number: 1 }] })).statusCode, 400)
    for (const code of ['A B', 'A\u00a0B', 'A\u3000B', 'A\u0001B'])
        assert.equal((await admin('POST', '/', { code, note: '', rewards: [{ type: 4, type_id: null, number: 1 }] })).statusCode, 400)
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM server_gift_codes').get().n, 0)
    const id = ok(await admin('POST', '/', { code: 'PAUSED', note: '', rewards: [{ type: 4, type_id: null, number: 10 }] })).id
    const p = fixture()
    assert.equal(ok(await post(p, '/gift/receive', { key: 'PAUSED' })).data.result_code, 6103)
    assert.equal(gifts.isGiftEnabledSync(), false)
    ok(await admin('PATCH', '/' + id, { revision: 1, enabled: true }))
    assert.equal(gifts.isGiftEnabledSync(), true)
    assert.equal((await admin('PATCH', '/' + id, { revision: 1, enabled: false })).statusCode, 409)
    assert.equal((await admin('POST', '/', { code: 'PAUSED', note: '', rewards: [{ type: 4, type_id: null, number: 1 }] })).statusCode, 400)
})

test('gift concurrent receive grants once, records history, projects final balances and isolates saves', async () => {
    const p = fixture(), second = fixture(), gift = await code([{ type: 4, type_id: null, number: 13 }, { type: 1, type_id: 100000, number: 3 }])
    const before = players.getPlayerSync(p.id).freeVmoney
    const results = await Promise.all([post(p, '/gift/receive', { key: gift.key }), post(p, '/gift/receive', { key: gift.key })])
    assert.deepEqual(results.map(result => ok(result).data.result_code).sort(), [1, 6104])
    assert.equal(players.getPlayerSync(p.id).freeVmoney, before + 13)
    assert.equal(inventory.getPlayerItemSync(p.id, 100000), 3)
    assert.equal(receiptCount(p, 'gift_code_redemption'), 1)
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_receive_history WHERE player_id=?').get(p.id).n, 2)
    assert.equal(ok(await post(second, '/gift/receive', { key: gift.key })).data.result_code, 1)
    assert.equal(ok(await admin('GET')).gifts.find(row => row.id === gift.id).redeemed_count, 2)
})

test('gift late ledger failure rolls back grants and history; capacity rejection leaves code unclaimed', async () => {
    const p = fixture(), gift = await code([{ type: 4, type_id: null, number: 19 }, { type: 1, type_id: 100000, number: 5 }])
    const before = saves.createPlayerSaveSnapshotV2Sync(p.id).data.tables
    db.exec(`CREATE TEMP TRIGGER fail_gift_receipt BEFORE INSERT ON player_operation_receipts WHEN NEW.operation='gift_code_redemption' BEGIN SELECT RAISE(ABORT,'gift fault'); END`)
    try { assert.equal((await post(p, '/gift/receive', { key: gift.key })).statusCode, 500) } finally { db.exec('DROP TRIGGER fail_gift_receipt') }
    assert.deepEqual(saves.createPlayerSaveSnapshotV2Sync(p.id).data.tables, before)
    assert.equal(receiptCount(p, 'gift_code_redemption'), 0)
    assert.equal(ok(await post(p, '/gift/receive', { key: gift.key })).data.result_code, 1)
    const full = fixture(), mana = await code([{ type: 8, type_id: null, number: 2 }])
    players.updatePlayerSync({ id: full.id, freeMana: load('lib/mana').getMaxManaSync(), paidMana: 0 })
    assert.equal((await post(full, '/gift/receive', { key: mana.key })).statusCode, 400)
    assert.equal(receiptCount(full, 'gift_code_redemption'), 0)
    players.updatePlayerSync({ id: full.id, freeMana: 0 })
    assert.equal(ok(await post(full, '/gift/receive', { key: mana.key })).data.result_code, 1)
})

test('gift invalid viewers and codes have no side effects; stopped codes remain stopped', async () => {
    const p = fixture(), gift = await code()
    assert.equal((await post(p, '/gift/receive', { viewer_id: p.viewer + 500000, key: gift.key })).statusCode, 400)
    assert.equal(ok(await post(p, '/gift/receive', { key: 'nonexistent' })).data.result_code, 6101)
    ok(await admin('PATCH', '/' + gift.id, { revision: 2, enabled: false }))
    assert.equal(ok(await post(p, '/gift/receive', { key: gift.key })).data.result_code, 6103)
    assert.equal(receiptCount(p, 'gift_code_redemption'), 0)
})

test('native bond catalog, balance, stock, repeated and concurrent requests are atomic', async () => {
    const p = fixture()
    const initial = ok(await post(p, '/exchange/get_bond_token_exchange_list')).data
    assert.deepEqual(initial, [{ equipment_id: 5010005, exchange_count: 0 }, { equipment_id: 5030005, exchange_count: 0 }])
    players.updatePlayerSync({ id: p.id, bondToken: 49 })
    assert.equal((await post(p, '/exchange/bond_token', { equipment_id: 5010005 })).statusCode, 400)
    players.updatePlayerSync({ id: p.id, bondToken: 100 })
    const results = await Promise.all([post(p, '/exchange/bond_token', { equipment_id: 5010005 }), post(p, '/exchange/bond_token', { equipment_id: 5010005 })])
    assert.deepEqual(results.map(result => result.statusCode).sort(), [200, 400])
    assert.equal(players.getPlayerSync(p.id).bondToken, 50)
    assert.equal(load('data/domains/equipment').getPlayerEquipmentSync(p.id, 5010005).stack, 0)
    assert.equal(ok(await post(p, '/exchange/get_bond_token_exchange_list')).data[0].exchange_count, 1)
    assert.equal((await post(p, '/exchange/bond_token', { equipment_id: 99999999 })).statusCode, 400)
    assert.equal((await post(p, '/exchange/bond_token', { equipment_id: 5010005.5 })).statusCode, 400)
})

test('bond receipt failure rolls back currency, equipment and quota', async () => {
    const p = fixture(); players.updatePlayerSync({ id: p.id, bondToken: 50 })
    const before = saves.createPlayerSaveSnapshotV2Sync(p.id).data.tables
    db.exec(`CREATE TEMP TRIGGER fail_bond_receipt BEFORE INSERT ON player_operation_receipts WHEN NEW.operation='bond_token_exchange' BEGIN SELECT RAISE(ABORT,'bond fault'); END`)
    try { assert.equal((await post(p, '/exchange/bond_token', { equipment_id: 5030005 })).statusCode, 500) } finally { db.exec('DROP TRIGGER fail_bond_receipt') }
    assert.deepEqual(saves.createPlayerSaveSnapshotV2Sync(p.id).data.tables, before)
    assert.equal(receiptCount(p, 'bond_token_exchange'), 0)
    assert.equal(ok(await post(p, '/exchange/bond_token', { equipment_id: 5030005 })).data.user_info.bond_token, 0)
})

test('old inventory import cannot reset gift or bond claims; new V2 transfers bond quota', async () => {
    const p = fixture(), target = fixture(), gift = await code()
    players.updatePlayerSync({ id: p.id, bondToken: 100 })
    const old = saves.createPlayerSaveSnapshotV2Sync(p.id)
    ok(await post(p, '/gift/receive', { key: gift.key })); ok(await post(p, '/exchange/bond_token', { equipment_id: 5030005 }))
    const earned = saves.createPlayerSaveSnapshotV2Sync(p.id)
    saves.restorePlayerSaveSnapshotV2Sync(earned, target.id)
    assert.equal(ok(await post(target, '/exchange/get_bond_token_exchange_list')).data[1].exchange_count, 1)
    saves.restorePlayerSaveSnapshotV2Sync(old, p.id)
    assert.equal(ok(await post(p, '/gift/receive', { key: gift.key })).data.result_code, 6104)
    assert.equal((await post(p, '/exchange/bond_token', { equipment_id: 5030005 })).statusCode, 400)
    assert.equal(players.getPlayerSync(p.id).bondToken, 100)
})

test('exact prior V2 schema imports and preserves new target progress; unknown tables fail before writes', () => {
    const p = fixture()
    db.prepare('INSERT INTO players_shop_campaign_lineups VALUES(?,?,?,?,?)').run(p.id, 4, 1, 1, Date.now())
    db.prepare('INSERT INTO players_bond_token_exchanges VALUES(?,?,?)').run(p.id, 5010005, 1)
    const archive = saves.createPlayerSaveSnapshotV2Sync(p.id)
    const newTables = new Set(['players_ex_boost_pending_draws', 'players_shop_campaign_lineups', 'players_bond_token_exchanges'])
    const oldTables = saves.PLAYER_SNAPSHOT_V2_TABLES.filter(table => !newTables.has(table))
    // Reconstruct the exact pre-extension SQL fingerprint, not a permissive bypass.
    archive.schemaFingerprint = createHash('sha256').update(JSON.stringify(oldTables.map(table => ({ table,
        columns: db.prepare(`PRAGMA table_info("${table}")`).all().map(column => ({ name: column.name, type: column.type,
            notnull: column.notnull, defaultValue: column.dflt_value, pk: column.pk })) })))).digest('hex')
    for (const table of newTables) delete archive.data.tables[table]
    archive.summary.includedTableCount = oldTables.length
    archive.summary.rowCount = Object.values(archive.data.tables).reduce((sum, table) => sum + table.rows.length, 0)
    saves.restorePlayerSaveSnapshotV2Sync(archive, p.id)
    assert.equal(db.prepare('SELECT exchange_count FROM players_bond_token_exchanges WHERE player_id=?').get(p.id).exchange_count, 1)
    assert.equal(db.prepare('SELECT lineup_id FROM players_shop_campaign_lineups WHERE player_id=?').get(p.id).lineup_id, 1)
    const before = saves.createPlayerSaveSnapshotV2Sync(p.id).data.tables
    archive.data.tables.unrecognized = { columns: [], rows: [] }
    assert.throws(() => saves.restorePlayerSaveSnapshotV2Sync(archive, p.id), /未知|完整/)
    assert.deepEqual(saves.createPlayerSaveSnapshotV2Sync(p.id).data.tables, before)
})

test('V1 replacement preserves nonempty new progress and redemption ledgers; late restore failure rolls back', async () => {
    const p = fixture(), gift = await code()
    players.updatePlayerSync({ id: p.id, bondToken: 50 })
    ok(await post(p, '/gift/receive', { key: gift.key }))
    ok(await post(p, '/exchange/bond_token', { equipment_id: 5010005 }))
    db.prepare('INSERT INTO players_shop_campaign_lineups VALUES(?,?,?,?,?)').run(p.id, 4, 1, 1, Date.now())
    const state = () => ({
        bond: db.prepare('SELECT * FROM players_bond_token_exchanges WHERE player_id=?').all(p.id),
        selection: db.prepare('SELECT * FROM players_shop_campaign_lineups WHERE player_id=?').all(p.id),
        receipts: db.prepare('SELECT * FROM player_operation_receipts WHERE player_id=? ORDER BY operation,request_key').all(p.id),
    })
    const expected = state()
    players.replacePlayerDataSync(load('data/utils/player-data').getMergedPlayerDataSync(p.id))
    assert.deepEqual(state(), expected)
    assert.equal(ok(await post(p, '/gift/receive', { key: gift.key })).data.result_code, 6104)
    const portable = saves.createPlayerSaveSnapshotV2Sync(p.id).data.tables
    db.exec(`CREATE TEMP TRIGGER fail_restored_bond BEFORE INSERT ON players_bond_token_exchanges BEGIN SELECT RAISE(ABORT,'restore fault'); END`)
    try { assert.throws(() => players.replacePlayerDataSync(load('data/utils/player-data').getMergedPlayerDataSync(p.id)), /restore fault/) }
    finally { db.exec('DROP TRIGGER fail_restored_bond') }
    assert.deepEqual(state(), expected)
    assert.deepEqual(saves.createPlayerSaveSnapshotV2Sync(p.id).data.tables, portable)
    assert.deepEqual(db.pragma('foreign_key_check'), [])
})

test('gift catalog, completed claims and bond quota survive a new process', async () => {
    const p = fixture(), gift = await code()
    players.updatePlayerSync({ id: p.id, bondToken: 50 })
    ok(await post(p, '/gift/receive', { key: gift.key }))
    ok(await post(p, '/exchange/bond_token', { equipment_id: 5030005 }))
    const sourceRoot = compiled ? 'out' : 'src'
    const script = `const assert=require('node:assert/strict');
        const db=require('./${sourceRoot}/data/db').getDb();
        const gifts=require('./${sourceRoot}/lib/gift-codes');
        assert.equal(gifts.isGiftEnabledSync(),true);
        assert.equal(db.transaction(()=>gifts.redeemGiftCodeWithinTransactionSync(${p.id},${JSON.stringify(gift.key)}))().result_code,6104);
        assert.equal(require('./${sourceRoot}/lib/bond-token-exchange').getBondTokenExchangeCountSync(${p.id},5030005),1);
        db.close();`
    const result = spawnSync(process.execPath, [...(compiled ? [] : ['-r', 'ts-node/register/transpile-only']), '-e', script],
        { cwd: path.resolve(__dirname, '..'), env: process.env, encoding: 'utf8', timeout: 30000 })
    assert.equal(result.status, 0, result.stderr + result.stdout)
})
