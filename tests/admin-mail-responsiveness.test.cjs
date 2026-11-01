'use strict'
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')

const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'admin-mail-yield-'))
Object.assign(process.env, { DATA_DIR: directory, GACHA_SEED_DIR: path.join(directory, 'seeds'),
    CN_WRITER_THREAD: '0', MULTI_REALTIME_PROCESS: '0', GAME_ROUTINE_LOGS: 'off' })
const load = name => require(path.resolve(__dirname, '../out', name))
const db = load('data/db').getDb()
const accounts = load('data/domains/account'), players = load('data/domains/player')
const shutdown = load('lib/shutdown-state')
let app, targets, other
const count = subject => db.prepare('SELECT COUNT(*) AS n FROM players_mails WHERE subject=?').get(subject).n
const send = payload => app.inject({ method: 'POST', url: '/mail/send',
    headers: { accept: 'application/json' }, payload: { type: '4', number: '1', ...payload } })

before(async () => {
    const defaults = load('data/utils').getDefaultPlayerData()
    db.transaction(() => {
        const account = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'mail-yield', idpId: 'batch', status: 'normal' })
        targets = Array.from({ length: 4700 }, () => players.insertPlayerSync(account.id, defaults))
        const account2 = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'mail-yield', idpId: 'other', status: 'normal' })
        other = { accountId: account2.id, id: players.insertPlayerSync(account2.id, defaults) }
    })()
    app = require('fastify')({ logger: false })
    load('lib/persistence-http-errors').installPersistenceHttpErrors(app)
    await app.register(load('routes/web_api/mail').default, { prefix: '/mail' })
    app.get('/probe', async () => ({ mails: count('bulk-yield') }))
    await app.ready()
})
after(async () => {
    await app?.close()
    await shutdown.drainServerWork()
    if (db.open) db.close()
    fs.rmSync(directory, { recursive: true, force: true })
})

test('4700-recipient broadcast handles other requests before the batch completes', async () => {
    let probing = true, intermediate = false, probes = 0
    const pump = async () => {
        while (probing) {
            await new Promise(resolve => setImmediate(resolve))
            if (!probing) break
            const response = await app.inject({ method: 'GET', url: '/probe' })
            probes++
            if (response.json().mails > 0 && response.json().mails < 4701) intermediate = true
        }
    }
    const observed = pump()
    let response
    try { response = await send({ subject: 'bulk-yield' }) }
    finally { probing = false; await observed }
    assert.equal(response.statusCode, 200, response.body)
    assert.deepEqual(response.json(), { ok: true, sent: 4701 })
    assert.equal(count('bulk-yield'), 4701)
    assert.equal(db.prepare('SELECT COUNT(DISTINCT player_id) AS n FROM players_mails WHERE subject=?').get('bulk-yield').n, 4701)
    assert.equal(intermediate, true, `other HTTP requests must progress during mail delivery; probes=${probes}`)
})

test('targeted mail keeps recipient scope and an individual failure does not suppress later recipients', async () => {
    const targeted = await send({ subject: 'targeted', playerId: String(other.id) })
    assert.deepEqual(targeted.json(), { ok: true, sent: 1 })
    assert.equal(count('targeted'), 1)
    assert.equal(db.prepare('SELECT player_id FROM players_mails WHERE subject=?').get('targeted').player_id, other.id)
    db.exec(`CREATE TRIGGER fixture_reject_mail BEFORE INSERT ON players_mails
        WHEN NEW.subject='partial' AND NEW.player_id=${targets[2]}
        BEGIN SELECT RAISE(ABORT, 'fixture invalid recipient'); END`)
    try {
        const result = await send({ subject: 'partial' })
        assert.equal(result.statusCode, 200, result.body)
        assert.deepEqual(result.json(), { ok: true, sent: 4700 })
        assert.equal(count('partial'), 4700)
        assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_mails WHERE subject=? AND player_id=?').get('partial', other.id).n, 1)
    } finally { db.exec('DROP TRIGGER fixture_reject_mail') }
    const invalid = await send({ subject: 'invalid', number: '-1' })
    assert.equal(invalid.statusCode, 400)
    assert.equal(count('invalid'), 0)
})

test('an accepted batch finishes during shutdown while a new batch is rejected', async () => {
    let closing = false, drained = false, earlyDrain = false
    const stop = new Promise(resolve => {
        const check = () => {
            if (count('accepted-close') > 0) {
                closing = true
                shutdown.beginServerShutdown()
                void shutdown.drainServerWork().then(() => {
                    drained = true
                    earlyDrain = count('accepted-close') !== 4701
                    resolve()
                })
            } else setImmediate(check)
        }
        setImmediate(check)
    })
    const accepted = await send({ subject: 'accepted-close' })
    await stop
    assert.equal(closing, true)
    assert.equal(drained, true)
    assert.equal(earlyDrain, false, 'drain must include the entire accepted broadcast')
    assert.equal(accepted.statusCode, 200, accepted.body)
    assert.deepEqual(accepted.json(), { ok: true, sent: 4701 })
    const refused = await send({ subject: 'after-close' })
    assert.equal(refused.statusCode, 503, refused.body)
    assert.equal(count('after-close'), 0)
    assert.equal(db.pragma('quick_check', { simple: true }), 'ok')
})
