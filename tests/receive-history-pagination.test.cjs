'use strict'
const fs = require('node:fs'), path = require('node:path'), os = require('node:os')
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
require('ts-node/register/transpile-only')
const root = fs.mkdtempSync(path.join(process.env.TEMP || os.tmpdir(), 'receive-history-pages-'))
Object.assign(process.env, { DATA_DIR: root, GACHA_SEED_DIR: path.join(root, 'seeds'), CN_WRITER_THREAD: '0' })
const load = name => require(path.join(__dirname, '..', 'src', name))
let app, db, viewer, playerId
before(async () => {
    load('data').initializeDatabase()
    db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(root))
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'history-test', idpId: 'pagination', status: 'normal' })
    const player = load('data/domains/player').insertDefaultPlayerSync(account.id)
    playerId = player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    viewer = 876000000 + player.id
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    const insert = db.prepare('INSERT INTO players_receive_history(player_id,type,type_id,number,reason_id,create_time) VALUES(?,1,NULL,?,0,?)')
    const now = new Date().toISOString().replace('T', ' ').slice(0, 19)
    db.transaction(() => {
        for (let number = 1; number <= 537; number++) insert.run(player.id, number, now)
        insert.run(player.id, 999999, '2000-01-01 00:00:00')
        const other = load('data/domains/player').insertDefaultPlayerSync(account.id)
        insert.run(other.id, 888888, now)
    })()
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/history').default, { prefix: '/history' })
    await app.ready()
})
after(async () => {
    await app?.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    // The isolated-check runner owns removal of this task's temporary directory.
})
const post = page => app.inject({ method: 'POST', url: '/history/receive', payload: { viewer_id: viewer, ...(page === undefined ? {} : { page }) } })
const data = response => { assert.equal(response.statusCode, 200, response.body); return response.json().data }
test('100-item pages cover the 500 newest records once, preserving the seven-day and owner filters', async () => {
    const numbers = []
    for (let page = 1; page <= 5; page++) {
        const result = data(await post(page))
        assert.equal(result.total_count, 500)
        assert.equal(result.history.length, 100)
        numbers.push(...result.history.map(row => row.number))
    }
    assert.deepEqual(numbers, Array.from({ length: 500 }, (_, i) => 537 - i))
    assert.equal(new Set(numbers).size, 500)
    assert.deepEqual(data(await post(6)), { history: [], total_count: 500 })
    assert.deepEqual(data(await post(Number.MAX_SAFE_INTEGER)), { history: [], total_count: 500 })
})
test('an omitted page keeps first-page compatibility and repeated reads do not remove history', async () => {
    assert.deepEqual(data(await post()), data(await post(1)))
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_receive_history').get().n, 539)
})
test('a short final page retains the total and invalid page values are rejected', async () => {
    db.prepare('DELETE FROM players_receive_history WHERE number BETWEEN 1 AND 400').run()
    const last = data(await post(2))
    assert.equal(last.total_count, 137)
    assert.equal(last.history.length, 37)
    assert.equal(last.history[0].number, 437)
    assert.equal(last.history.at(-1).number, 401)
    for (const page of [0, -1, 1.5, '2', null, Number.MAX_SAFE_INTEGER + 1]) assert.equal((await post(page)).statusCode, 400)
    assert.deepEqual(data(await post(3)), { history: [], total_count: 137 })
})
test('history still requires an authenticated viewer', async () => {
    assert.equal((await app.inject({ method: 'POST', url: '/history/receive', payload: { viewer_id: 123456789, page: 1 } })).statusCode, 400)
})
test('an empty history has a stable empty page and leaves the other player untouched', async () => {
    db.prepare('DELETE FROM players_receive_history WHERE player_id=?').run(playerId)
    assert.deepEqual(data(await post(1)), { history: [], total_count: 0 })
    assert.deepEqual(data(await post(99)), { history: [], total_count: 0 })
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_receive_history').get().n, 1)
})
