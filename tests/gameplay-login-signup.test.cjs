'use strict'
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-native-signup-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const auth = load('lib/player-login'), identity = load('lib/gameplay-request-identity')
let db, app
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    auth.initializePlayerLogin()
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/cn/tool').default)
    await app.ready()
})
after(async () => {
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root)
    fs.rmSync(directory, { recursive: true })
})
const signup = token => app.inject({ method: 'POST', url: '/signup', headers: { 'x-sp-session': token, login_token: token }, payload: {} })

test('legacy device signup returns a trusted native nonce without creating player login credentials', async () => {
    const payload = { device_id: 88776655, channelNo: 'synthetic', first_viewer_id: 0 }
    const first = await app.inject({ method: 'POST', url: '/signup', headers: { udid: 'synthetic-legacy-device' }, payload })
    assert.equal(first.statusCode, 200)
    const data = first.json(), viewer = data.data_headers.viewer_id
    const account = auth.playerAccountByViewer(viewer), token = data.data.login_token
    assert.match(token, /^[a-f0-9]{64}$/)
    assert.equal(auth.playerLoginManaged(account), false)
    assert.equal(identity.readGameplayMutationIdentitySync(db, token, { viewer_id: viewer, api_count: 1 }, account).isCurrent, true)
    const count = db.prepare('SELECT COUNT(*) AS n FROM accounts').get().n
    const second = await app.inject({ method: 'POST', url: '/signup', headers: { udid: 'synthetic-legacy-device', login_token: token }, payload })
    assert.equal(second.statusCode, 200)
    assert.equal(second.json().data_headers.viewer_id, viewer)
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM accounts').get().n, count)
    assert.equal(identity.readGameplayMutationIdentitySync(db, token, { viewer_id: viewer, api_count: 1 }, account).isCurrent, false)
})

test('actual signup rotates native request generation, preserves web login and accepts nonce on the next signup', async () => {
    const registered = auth.registerPlayerLogin('native_signup_fixture', 'SyntheticPass9', true)
    const web = registered.token, viewer = registered.profile.viewer_id
    const firstResponse = await signup(web)
    assert.equal(firstResponse.statusCode, 200)
    const first = firstResponse.json().data.login_token
    assert.match(first, /^[a-f0-9]{64}$/)
    assert.notEqual(first, web)
    assert.equal(auth.readPlayerLoginSession(web).token, web)
    assert.equal(auth.readPlayerLoginSession(first).token, web)
    const initialAccess = auth.readPlayerLoginAccess(first, viewer)
    assert.equal(initialAccess.account_id, initialAccess.request_account_id)
    const secondResponse = await signup(first)
    assert.equal(secondResponse.statusCode, 200)
    const second = secondResponse.json().data.login_token
    assert.notEqual(second, first)
    assert.equal(auth.readPlayerLoginAccess(first, viewer), null, 'old game generation cannot authorize new mutations')
    assert.equal(auth.readPlayerLoginSession(first).token, web, 'an old in-flight signup can recover through its still-valid web credential')
    assert.equal(auth.readPlayerLoginAccess(second, viewer).account_id, initialAccess.account_id)
    assert.equal(identity.readGameplayMutationIdentitySync(db, first, { viewer_id: viewer, api_count: 1 }, initialAccess.account_id).isCurrent, false)
    assert.equal(identity.readGameplayMutationIdentitySync(db, second, { viewer_id: viewer, api_count: 1 }, initialAccess.account_id).isCurrent, true)
    assert.equal(auth.readPlayerLoginSession(web).token, web)
    auth.logoutPlayer(second)
    assert.equal(auth.readPlayerLoginSession(web), null)
    assert.equal(identity.readGameplayMutationIdentitySync(db, second, { viewer_id: viewer, api_count: 1 }, initialAccess.account_id), null)
})

test('failed actual signup token issuance rolls back nonce rotation and preserves the prior login', async () => {
    const registered = auth.registerPlayerLogin('native_rollback_fixture', 'SyntheticPass9', true)
    const response = await signup(registered.token), token = response.json().data.login_token
    db.exec("CREATE TRIGGER fail_native_nonce BEFORE INSERT ON gameplay_login_sessions BEGIN SELECT RAISE(ABORT,'synthetic nonce failure'); END")
    try {
        const failed = await signup(token)
        assert.equal(failed.statusCode, 500)
        assert.ok(auth.readPlayerLoginAccess(token, registered.profile.viewer_id))
        assert.ok(auth.readPlayerLoginSession(registered.token))
    } finally { db.exec('DROP TRIGGER fail_native_nonce') }
})
