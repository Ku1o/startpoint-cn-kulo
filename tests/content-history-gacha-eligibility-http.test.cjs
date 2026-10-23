'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), { randomUUID } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-gacha-eligibility-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const operations = load('lib/content-operations'), assets = load('lib/assets')
const players = load('data/domains/player'), gachas = load('data/domains/gacha'), items = load('data/domains/item')
const coordinator = load('lib/persistence-coordinator'), transaction = coordinator.runPersistenceTransaction
const native = operations.contentCatalog.rows.filter(row => row.type === 'gacha')
const onceIds = native.filter(row => assets.getGachaSync(row.id)?.pageKind === 1).map(row => row.id)
const ticketIds = native.filter(row => [2, 3, 4].includes(assets.getGachaSync(row.id)?.pageKind)).map(row => row.id)
let db, app
function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'history-gacha-eligibility', idpId: randomUUID(), status: 'normal' })
    const p = players.insertDefaultPlayerSync(account.id), viewer = 897000000 + p.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, p.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    players.updatePlayerSync({ id: p.id, freeVmoney: 100000, vmoney: 50000 })
    return { id: p.id, viewer }
}
function control(id, enabled) {
    const store = operations.contentOperations(), review = { readiness: 'verified', evidence: 'Original native page and immutable configured payment rules; synthetic HTTP regression', endsAtMs: null }
    store.update(`gacha:${id}`, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Historical account-first and exact ticket qualification regression',
        actionOverrides: { visible: { ...review, enabled: true }, enter: { ...review, enabled } } }, Date.now())
}
const draw = (p, id, payment, type, count = 1) => app.inject({ method: 'POST', url: '/gacha/exec',
    payload: { viewer_id: p.viewer, gacha_id: id, payment_type: payment, type, number_of_exec: count, api_count: 1 } })
function response(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
const snapshot = p => load('data/snapshots/player-snapshot').createPlayerSaveSnapshotV2Sync(p.id, db).data.tables
const ticketRule = id => {
    const gacha = assets.getGachaSync(id), multi = gacha.pageKind !== 3 && !!gacha.tenTicketItemId
    return { itemId: multi ? gacha.tenTicketItemId : gacha.onceTicketItemId, type: multi ? 4 : 3, pulls: multi ? 10 : 1 }
}
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    assert.equal(onceIds.length, 20); assert.equal(ticketIds.length, 22)
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/gacha').default, { prefix: '/gacha' }); await app.ready()
})
after(async () => {
    coordinator.runPersistenceTransaction = transaction
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root); fs.rmSync(directory, { recursive: true })
})

test('all twenty account-limited native pools reject paid-single and crossed payment types without consuming first-time qualification', async () => {
    const p = fixture()
    for (const id of onceIds) {
        control(id, true)
        const before = snapshot(p)
        for (const [payment, type] of [[2, 2], [2, 8], [2, 5], [1, 1], [1, 8], [4, 2]]) {
            assert.equal((await draw(p, id, payment, type)).statusCode, 400, `${id}/${payment}/${type}`)
        }
        assert.deepEqual(snapshot(p), before, `pool${id} preserves wallet, inventory and missing account-first row`)
        assert.equal(gachas.getPlayerGachaInfoSync(p.id, id), null)
    }
})

test('account-limited page contract remains exactly ten even when a ticket execution is presented', () => {
    const original = assets.getGachaSync(onceIds[0])
    const plan = load('lib/gacha-exec-plan').buildGachaExecPlan
    const input = { gacha: { ...original, onceTicketItemId: 999003, tenTicketItemId: 999001 },
        paymentType: 3, execType: 3, numberOfExec: 1, playerFunds: { freeVmoney: 10000, paidVmoney: 10000 },
        playerGachaData: { isAccountFirst: true, isDailyFirst: true }, getTicketCount: () => 10 }
    assert.equal(plan(input).ok, false, 'a single ticket cannot replace the original account ten-pull')
    assert.equal(plan({ ...input, execType: 4, numberOfExec: 2 }).ok, false, 'one account-first execution cannot expand into twenty draws')
})

test('all twenty original account ten-pulls charge their configured cost once and reopening preserves spent qualification', async () => {
    const p = fixture()
    for (const id of onceIds) {
        control(id, true)
        const gacha = assets.getGachaSync(id), before = players.getPlayerSync(p.id)
        const result = response(await draw(p, id, 1, 2))
        assert.equal(result.data.draw.length, 10, `pool${id}`)
        assert.equal(players.getPlayerSync(p.id).freeVmoney, before.freeVmoney - (gacha.tenTimesPerAccountCost ?? gacha.multiCost))
        assert.equal(players.getPlayerSync(p.id).vmoney, before.vmoney)
        assert.equal(gachas.getPlayerGachaInfoSync(p.id, id).isAccountFirst, false)
        const saved = snapshot(p), instance = operations.contentOperations().state(`gacha:${id}`).instanceId
        control(id, false); control(id, true)
        assert.equal(operations.contentOperations().state(`gacha:${id}`).instanceId, instance)
        assert.equal((await draw(p, id, 1, 2)).statusCode, 400)
        assert.deepEqual(snapshot(p), saved)
    }
})

test('all twenty-two native ticket pools require their exact owned ticket, reject coins and wildcards and never issue tickets on opening', async () => {
    const p = fixture()
    items.setPlayerItemSync(p.id, 999001, 10); items.setPlayerItemSync(p.id, 999003, 10)
    for (const id of ticketIds) {
        const rule = ticketRule(id); assert.ok(Number.isSafeInteger(rule.itemId))
        const before = snapshot(p); control(id, true)
        assert.deepEqual(snapshot(p), before, `opening${id} cannot grant any player qualification or ticket`)
        for (const [payment, type] of [[1, 1], [1, 2], [2, 5], [4, 7], [4, 8], [3, 9], [3, 10], [3, rule.type]]) {
            assert.equal((await draw(p, id, payment, type)).statusCode, 400, `${id}/${payment}/${type}`)
        }
        assert.deepEqual(snapshot(p), before)
        items.setPlayerItemSync(p.id, rule.itemId, 2)
        const wallet = players.getPlayerSync(p.id)
        for (const remaining of [1, 0]) {
            const result = response(await draw(p, id, 3, rule.type))
            assert.equal((result.data.draw ?? result.data.draw_equipment).length, rule.pulls)
            assert.equal(items.getPlayerItemSync(p.id, rule.itemId), remaining)
            assert.equal(players.getPlayerSync(p.id).freeVmoney, wallet.freeVmoney)
            assert.equal(players.getPlayerSync(p.id).vmoney, wallet.vmoney)
        }
        const spent = snapshot(p); control(id, false); control(id, true)
        assert.equal((await draw(p, id, 3, rule.type)).statusCode, 400)
        assert.deepEqual(snapshot(p), spent)
    }
})

test('final draw transaction rechecks account-first, exact ticket stock and the operator switch after preview', async () => {
    for (const mode of ['account', 'ticket', 'closed']) {
        const p = fixture(), id = mode === 'account' ? onceIds[0] : ticketIds[0], rule = mode === 'account' ? null : ticketRule(id)
        control(id, true)
        if (rule) items.setPlayerItemSync(p.id, rule.itemId, 1)
        let atWrite, injected = false
        coordinator.runPersistenceTransaction = async (context, callback, options) => {
            if (!injected && context.operation === 'draw') {
                injected = true
                if (mode === 'account') gachas.insertPlayerGachaInfoSync(p.id, { gachaId: id, isAccountFirst: false, isDailyFirst: true, gachaExchangePoint: 7 })
                else if (mode === 'ticket') items.setPlayerItemSync(p.id, rule.itemId, 0)
                else control(id, false)
                atWrite = snapshot(p)
            }
            return transaction(context, callback, options)
        }
        try {
            assert.equal((await draw(p, id, rule ? 3 : 1, rule?.type ?? 2)).statusCode, 400, mode)
            assert.equal(injected, true, mode); assert.deepEqual(snapshot(p), atWrite, mode)
        } finally { coordinator.runPersistenceTransaction = transaction }
    }
})
