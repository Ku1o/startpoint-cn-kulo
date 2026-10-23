'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto'), { spawnSync } = require('node:child_process')
const root = path.resolve(os.tmpdir()), directory = fs.mkdtempSync(path.join(root, 'economy-fixes-'))
Object.assign(process.env, { DATA_DIR: directory, GACHA_SEED_DIR: path.join(directory, 'seeds'),
    CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const players = load('data/domains/player'), items = load('data/domains/item')
const characters = load('data/domains/character'), equipment = load('data/domains/equipment')
const pending = load('data/domains/ex-boost-pending'), identities = load('lib/gameplay-request-identity')
const mails = load('data/domains/mail'), saves = load('data/snapshots/player-snapshot')
const characterId = 111015, equipmentId = 5010005, materialId = 10001
let db, app
function fixture(material = 20) {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'economy-test', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 890000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    const nonce = db.transaction(() => identities.issueGameplayLoginTokenSync(db, {
        accountId: account.id, viewerId: viewer, udid: 'economy-' + viewer, expiresAt: Date.now() + 86400000,
    }))()
    load('lib/character').givePlayerCharacterSync(player.id, characterId)
    characters.updatePlayerCharacterSync(player.id, characterId, { overLimitStep: 4 })
    items.setPlayerItemSync(player.id, materialId, material)
    return { id: player.id, accountId: account.id, viewer, nonce, count: 0 }
}
const post = (p, route, body = {}, count = ++p.count) => app.inject({ method: 'POST', url: route,
    headers: { login_token: p.nonce }, payload: { viewer_id: p.viewer, api_count: count, ...body } })
const draw = (p, count, first = false) => post(p, '/ex/' + (first ? 'first_draw' : 'draw'),
    { character_id: characterId, cost_item_id: materialId }, count)
const select = (p, confirm, count) => post(p, '/ex/select', { is_confirm: confirm }, count)
function ok(response) { assert.equal(response.statusCode, 200, response.body); return response.json().data }
const amount = p => items.getPlayerItemSync(p.id, materialId)
function mail(p, type, id, number) {
    return mails.insertMailSync(p.id, { reason_id: 1, subject: 'fixture', description: 'fixture', type, type_id: id, number,
        receive_time: '0000-00-00 00:00:00', create_time: '2026-01-01 00:00:00', reward_period_limited: 0, reward_limit_time: null })
}
function ownEquipment(p, stack = 3, protection = false) {
    equipment.insertPlayerEquipmentSync(p.id, equipmentId, { level: 1, enhancementLevel: 0, stack, protection })
}
const soldItem = p => load('lib/equipment-dissolve').calculateDissolveRewards(equipmentId, 1)
const stock = p => equipment.getPlayerEquipmentSync(p.id, equipmentId).stack
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    load('data/initializers/ex-boost-pending').initializeExBoostPendingSchema(db)
    identities.initializeGameplayRequestIdentitySchemaSync(db)
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, payload, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof payload === 'object' ? JSON.stringify(payload) : payload))
    await app.register(load('routes/api/exBoost').default, { prefix: '/ex' })
    await app.register(load('routes/api/mail').default, { prefix: '/mail' })
    await app.register(load('routes/api/sell').default, { prefix: '/equipment' })
    await app.ready()
})
after(async () => {
    await app?.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root)
    fs.rmSync(directory, { recursive: true })
})

test('EX concurrent retries persist one paid result, reject conflicting identities, and recover after restart', async () => {
    const p = fixture(20)
    const results = await Promise.all([draw(p, 1), draw(p, 1), draw(p, 2)])
    const wires = results.map(ok)
    assert.deepEqual(wires[0].draw_result, wires[1].draw_result)
    assert.deepEqual(wires[0].draw_result, wires[2].draw_result)
    assert.equal(amount(p), 15)
    const saved = pending.getPendingExBoostDrawSync(p.id)
    const conflict = await post(p, '/ex/draw', { character_id: characterId, cost_item_id: 10002 }, 1)
    assert.equal(conflict.statusCode, 400)
    assert.equal(amount(p), 15)
    const script = `${compiled ? '' : "require('ts-node/register/transpile-only');"}
        const db=require('./${compiled ? 'out' : 'src'}/data/db').getDb();
        const draw=require('./${compiled ? 'out' : 'src'}/data/domains/ex-boost-pending').getPendingExBoostDrawSync(${p.id});
        if(draw.drawId!==${JSON.stringify(saved.drawId)})process.exit(2);db.close();process.exit(0);`
    const child = spawnSync(process.execPath, ['-e', script], { cwd: path.resolve(__dirname, '..'), env: process.env, encoding: 'utf8', timeout: 45000 })
    assert.equal(child.status, 0, child.stderr)
    assert.equal(pending.getPendingExBoostDrawSync(p.id).drawId, saved.drawId)
})

test('EX draw and select failures roll back cost, ability, pending and durable receipts', async () => {
    const p = fixture(20)
    db.exec(`CREATE TRIGGER fail_ex_pending BEFORE INSERT ON players_ex_boost_pending_draws BEGIN SELECT RAISE(ABORT,'pending failure'); END`)
    try { assert.equal((await draw(p, 1)).statusCode, 500) } finally { db.exec('DROP TRIGGER fail_ex_pending') }
    assert.equal(amount(p), 20); assert.equal(pending.getPendingExBoostDrawSync(p.id), null)
    assert.equal(db.prepare("SELECT COUNT(*) n FROM player_operation_receipts WHERE player_id=? AND operation='ex_boost_draw'").get(p.id).n, 0)
    ok(await draw(p, 1)); const saved = pending.getPendingExBoostDrawSync(p.id)
    const before = characters.getPlayerCharacterSync(p.id, characterId).exBoost
    db.exec(`CREATE TRIGGER fail_ex_delete BEFORE DELETE ON players_ex_boost_pending_draws BEGIN SELECT RAISE(ABORT,'delete failure'); END`)
    try { assert.equal((await select(p, true, 2)).statusCode, 500) } finally { db.exec('DROP TRIGGER fail_ex_delete') }
    assert.deepEqual(characters.getPlayerCharacterSync(p.id, characterId).exBoost, before)
    assert.equal(pending.getPendingExBoostDrawSync(p.id).drawId, saved.drawId)
    assert.equal(db.prepare("SELECT COUNT(*) n FROM player_operation_receipts WHERE player_id=? AND operation='ex_boost_completion'").get(p.id).n, 0)
    ok(await select(p, true, 2)); ok(await select(p, true, 2))
    assert.equal(pending.getPendingExBoostDrawSync(p.id), null); assert.equal(amount(p), 15)
    assert.equal((await draw(p, 1)).statusCode, 400)
    assert.equal(amount(p), 15)
})

test('EX first draw retries are free, discard is durable, and late select cannot clear a newer pending draw', async () => {
    const p = fixture(30)
    ok(await draw(p, 1, true)); ok(await draw(p, 1, true)); ok(await draw(p, 2, true))
    assert.equal(amount(p), 25)
    ok(await draw(p, 3)); const original = pending.getPendingExBoostDrawSync(p.id)
    ok(await select(p, false, 4)); ok(await select(p, false, 4))
    ok(await draw(p, 5)); const next = pending.getPendingExBoostDrawSync(p.id)
    assert.notEqual(original.drawId, next.drawId)
    ok(await select(p, false, 4))
    assert.equal(pending.getPendingExBoostDrawSync(p.id).drawId, next.drawId)
    assert.equal(amount(p), 15)
})

test('EX superseded login may replay an accepted request but cannot start a new mutation', async () => {
    const p = fixture(20), oldNonce = p.nonce
    ok(await draw(p, 1))
    const newNonce = db.transaction(() => identities.issueGameplayLoginTokenSync(db, {
        accountId: p.accountId, viewerId: p.viewer, udid: 'economy-' + p.viewer, expiresAt: Date.now() + 86400000,
    }))()
    ok(await draw(p, 1))
    assert.equal((await select(p, true, 2)).statusCode, 400)
    assert.equal(amount(p), 15)
    p.nonce = newNonce
    ok(await select(p, true, 1))
    p.nonce = oldNonce
    assert.equal((await draw(p, 1)).statusCode, 400)
    assert.equal(amount(p), 15)
})

test('EX receipt publication failure rolls pending and material back', async () => {
    const p = fixture(20)
    db.exec(`CREATE TRIGGER fail_ex_receipt BEFORE INSERT ON player_operation_receipts
        WHEN NEW.operation='ex_boost_draw' BEGIN SELECT RAISE(ABORT,'receipt failure'); END`)
    try { assert.equal((await draw(p, 1)).statusCode, 500) } finally { db.exec('DROP TRIGGER fail_ex_receipt') }
    assert.equal(amount(p), 20); assert.equal(pending.getPendingExBoostDrawSync(p.id), null)
})

test('EX actual deferred-FK COMMIT failure rolls material, pending and receipts back', async () => {
    const p = fixture(20), coordinator = load('lib/persistence-coordinator')
    const original = coordinator.runPersistenceTransaction
    db.exec('CREATE TABLE ex_commit_guard (player_id INTEGER REFERENCES players(id) DEFERRABLE INITIALLY DEFERRED)')
    coordinator.runPersistenceTransaction = (context, callback, options) => original(context, () => {
        const result = callback()
        if (context.operation === 'ex_boost_draw') db.prepare('INSERT INTO ex_commit_guard(player_id) VALUES(-1234567)').run()
        return result
    }, options)
    try { assert.equal((await draw(p, 1)).statusCode, 500) } finally {
        coordinator.runPersistenceTransaction = original
        db.exec('DROP TABLE ex_commit_guard')
    }
    assert.equal(amount(p), 20); assert.equal(pending.getPendingExBoostDrawSync(p.id), null)
    assert.equal(db.prepare("SELECT COUNT(*) n FROM player_operation_receipts WHERE player_id=? AND operation='ex_boost_draw'").get(p.id).n, 0)
})

test('EX portable pending round trips; importing a completed old draw cannot reactivate it on this server', async () => {
    const p = fixture(20)
    ok(await draw(p, 1))
    const saved = pending.getPendingExBoostDrawSync(p.id)
    const archive = saves.createPlayerSaveSnapshotV2Sync(p.id)
    assert.ok(archive.data.tables.players_ex_boost_pending_draws)
    const target = fixture(20)
    saves.restorePlayerSaveSnapshotV2Sync(archive, target.id)
    assert.equal(pending.getPendingExBoostDrawSync(target.id).drawId, saved.drawId)
    ok(await select(p, true, 2))
    const committed = characters.getPlayerCharacterSync(p.id, characterId).exBoost
    saves.restorePlayerSaveSnapshotV2Sync(archive, p.id)
    assert.equal((await select(p, true, 3)).statusCode, 400)
    assert.equal(pending.getPendingExBoostDrawSync(p.id), null)
    // Import may restore portable character state, but selecting the old paid UUID never reapplies it.
    assert.equal(db.prepare("SELECT COUNT(*) n FROM player_operation_receipts WHERE player_id=? AND operation='ex_boost_completion'").get(p.id).n, 1)
    assert.ok(committed)
})

test('EX archive rejects malformed pending contents before changing the destination', async () => {
    const source = fixture(20), target = fixture(7)
    ok(await draw(source, 1))
    const archive = saves.createPlayerSaveSnapshotV2Sync(source.id)
    const table = archive.data.tables.players_ex_boost_pending_draws
    for (const [column, value] of [['ability_id_list', '{broken'], ['status_id', 999999], ['cost_item_count', 999999]]) {
        const bad = JSON.parse(JSON.stringify(archive))
        bad.data.tables.players_ex_boost_pending_draws.rows[0][table.columns.indexOf(column)] = value
        const before = saves.createPlayerSaveSnapshotV2Sync(target.id)
        assert.throws(() => saves.restorePlayerSaveSnapshotV2Sync(bad, target.id))
        assert.deepEqual(saves.createPlayerSaveSnapshotV2Sync(target.id).data, before.data)
    }
})

test('character mail grants every copy with standard duplicate compensation and safe retry', async () => {
    const p = fixture(), before = characters.getPlayerCharacterSync(p.id, characterId)
    const id = mail(p, mails.MailType.CHARACTER, characterId, 3)
    const response = ok(await post(p, '/mail/receive', { mail_id: id, request_id: randomUUID() }))
    const after = characters.getPlayerCharacterSync(p.id, characterId)
    assert.equal(after.stack, before.stack + 3)
    assert.equal(after.entryCount, before.entryCount)
    assert.equal(response.character_list[0].stack, after.stack)
    assert.ok(Object.keys(response.item_list).length > 0)
    const beforeRetry = after.stack
    await post(p, '/mail/receive', { mail_id: id })
    assert.equal(characters.getPlayerCharacterSync(p.id, characterId).stack, beforeRetry)
    const fresh = fixture(), newId = 111009
    assert.equal(characters.getPlayerCharacterSync(fresh.id, newId), null)
    ok(await post(fresh, '/mail/receive', { mail_id: mail(fresh, mails.MailType.CHARACTER, newId, 3) }))
    assert.equal(characters.getPlayerCharacterSync(fresh.id, newId).stack, 2)
})

test('empty and malformed mail cannot mint assets; late compensation failure restores receipt and mail state', async () => {
    const p = fixture(), absent = 111009
    const empty = mail(p, mails.MailType.CHARACTER, absent, 0)
    ok(await post(p, '/mail/receive', { mail_id: empty }))
    assert.equal(characters.getPlayerCharacterSync(p.id, absent), null)
    for (const [kind, count] of [[mails.MailType.CHARACTER, -1], [99999, 1]]) {
        const id = mail(p, kind, characterId, count)
        assert.equal((await post(p, '/mail/receive', { mail_id: id })).statusCode, 400)
        assert.equal(db.prepare('SELECT receive_time FROM players_mails WHERE id=?').get(id).receive_time, '0000-00-00 00:00:00')
    }
    const id = mail(p, mails.MailType.CHARACTER, characterId, 2)
    const before = characters.getPlayerCharacterSync(p.id, characterId).stack
    db.exec(`CREATE TRIGGER fail_mail_history BEFORE INSERT ON players_receive_history BEGIN SELECT RAISE(ABORT,'history failure'); END`)
    try { assert.equal((await post(p, '/mail/receive', { mail_id: id })).statusCode, 500) } finally { db.exec('DROP TRIGGER fail_mail_history') }
    assert.equal(characters.getPlayerCharacterSync(p.id, characterId).stack, before)
    assert.equal(db.prepare('SELECT receive_time FROM players_mails WHERE id=?').get(id).receive_time, '0000-00-00 00:00:00')
})

test('zero-count title mail grants ownership, retries idempotently, and rolls back after a late failure', async () => {
    const p = fixture(), degreeId = 54500, degree = load('data/domains/degree')
    assert.equal(degree.hasPlayerDegreeSync(p.id, degreeId), false)
    const first = mail(p, mails.MailType.DEGREE, degreeId, 0), requestId = randomUUID()
    const response = ok(await post(p, '/mail/receive', { mail_id: first, request_id: requestId }))
    assert.equal(degree.hasPlayerDegreeSync(p.id, degreeId), true)
    assert.deepEqual(response.degree_list, [{ viewer_id: p.viewer, degree_id: degreeId }])
    ok(await post(p, '/mail/receive', { mail_id: first, request_id: requestId }))
    const another = mail(p, mails.MailType.DEGREE, degreeId, 0)
    ok(await post(p, '/mail/receive', { mail_id: another }))
    assert.equal(db.prepare('SELECT COUNT(*) n FROM players_degrees WHERE player_id=? AND degree_id=?').get(p.id, degreeId).n, 1)
    const other = fixture(), failed = mail(other, mails.MailType.DEGREE, degreeId, 0)
    db.exec(`CREATE TRIGGER fail_title_mail_history BEFORE INSERT ON players_receive_history BEGIN SELECT RAISE(ABORT,'title history failure'); END`)
    try { assert.equal((await post(other, '/mail/receive', { mail_id: failed })).statusCode, 500) }
    finally { db.exec('DROP TRIGGER fail_title_mail_history') }
    assert.equal(degree.hasPlayerDegreeSync(other.id, degreeId), false)
    assert.equal(db.prepare('SELECT receive_time FROM players_mails WHERE id=?').get(failed).receive_time, '0000-00-00 00:00:00')
})

test('all three equipment sales reject protected inventory without rewards', async () => {
    for (const [route, body] of [['sell_equipment', { equipment_list: [{ equipment_id: equipmentId }] }],
        ['sell_stack', { equipment_list: [{ equipment_id: equipmentId, number: 1 }] }], ['bulk_sell_stack', { equipment_ids: [equipmentId] }]]) {
        const p = fixture(); ownEquipment(p, 3, true)
        const before = items.getPlayerItemsSync(p.id)
        assert.equal((await post(p, '/equipment/' + route, body)).statusCode, 400)
        assert.equal(stock(p), 3); assert.deepEqual(items.getPlayerItemsSync(p.id), before)
    }
})

test('single sale consumes one duplicate, bulk all duplicates, and empty replay never grants', async () => {
    const p = fixture(); ownEquipment(p, 3)
    const unit = soldItem(p), craft = load('lib/assets').getConfigSync().craft_point_item_id || 100000
    const initial = items.getPlayerItemSync(p.id, craft) ?? 0
    ok(await post(p, '/equipment/sell_equipment', { equipment_list: [{ equipment_id: equipmentId }] }))
    assert.equal(stock(p), 2); assert.equal(items.getPlayerItemSync(p.id, craft), initial + unit.craftPoints)
    ok(await post(p, '/equipment/bulk_sell_stack', { equipment_ids: [equipmentId, equipmentId] }))
    assert.equal(stock(p), 0); assert.equal(items.getPlayerItemSync(p.id, craft), initial + 3 * unit.craftPoints)
    assert.equal((await post(p, '/equipment/sell_equipment', { equipment_list: [{ equipment_id: equipmentId }] })).statusCode, 400)
    ok(await post(p, '/equipment/bulk_sell_stack', { equipment_ids: [equipmentId] }))
    assert.equal(items.getPlayerItemSync(p.id, craft), initial + 3 * unit.craftPoints)
    assert.ok(equipment.getPlayerEquipmentSync(p.id, equipmentId))
})

test('equipment reward failure rolls the consumed duplicate back; partial duplicate IDs share one budget', async () => {
    const p = fixture(); ownEquipment(p, 3)
    db.exec(`CREATE TRIGGER fail_sale_reward BEFORE INSERT ON players_items BEGIN SELECT RAISE(ABORT,'sale failure'); END`)
    try { assert.equal((await post(p, '/equipment/sell_equipment', { equipment_list: [{ equipment_id: equipmentId }] })).statusCode, 500) }
    finally { db.exec('DROP TRIGGER fail_sale_reward') }
    assert.equal(stock(p), 3)
    assert.equal((await post(p, '/equipment/sell_stack', { equipment_list: [{ equipment_id: equipmentId, number: 2 }, { equipment_id: equipmentId, number: 2 }] })).statusCode, 400)
    assert.equal(stock(p), 3)
    ok(await post(p, '/equipment/sell_stack', { equipment_list: [{ equipment_id: equipmentId, number: 1 }, { equipment_id: equipmentId, number: 2 }] }))
    assert.equal(stock(p), 0)
})
