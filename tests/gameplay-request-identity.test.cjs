'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const Sqlite = require('better-sqlite3'), path = require('node:path')
if (process.env.STARPOINT_TEST_COMPILED !== '1') require('ts-node/register/transpile-only')
const api = require(path.join(__dirname, '..', process.env.STARPOINT_TEST_COMPILED === '1' ? 'out' : 'src', 'lib/gameplay-request-identity'))
const now = 1792540800000, parent = 'a'.repeat(64)
function fixture(t) {
    const db = new Sqlite(':memory:'); t.after(() => db.close())
    db.exec(`CREATE TABLE accounts(id INTEGER PRIMARY KEY,status TEXT); INSERT INTO accounts VALUES(1,'normal'),(2,'normal');
        CREATE TABLE sessions(token TEXT PRIMARY KEY,account_id INTEGER,type INTEGER);
        INSERT INTO sessions VALUES('1001',1,2),('1002',2,2);
        CREATE TABLE player_login_sessions(token TEXT PRIMARY KEY,account_id INTEGER,viewer_id INTEGER,expires_at INTEGER);`)
    db.prepare('INSERT INTO player_login_sessions VALUES(?,1,1001,?)').run(parent, now + 10000)
    api.initializeGameplayRequestIdentitySchemaSync(db)
    const issue = (extra = {}) => db.transaction(() => api.issueGameplayLoginTokenSync(db, {
        accountId: 1, viewerId: 1001, udid: 'synthetic-device', parentToken: parent,
        expiresAt: now + 10000, nowMs: now, ...extra,
    }))()
    const read = (token, count = 1, viewer = 1001, account = 1, at = now) => api.readGameplayMutationIdentitySync(db, token,
        { viewer_id: viewer, api_count: count }, account, at)
    return { db, issue, read }
}

test('logical retries retain identity while a new signup cannot reuse old api_count identity', t => {
    const { issue, read } = fixture(t)
    const first = issue(), old = read(first)
    assert.equal(old.isCurrent, true)
    assert.deepEqual(read(first), old)
    assert.ok(!old.requestKey.includes(first), 'receipt keys contain a hash, never the credential')
    assert.notEqual(read(first, 2).requestKey, old.requestKey)
    const second = issue()
    assert.notEqual(second, first)
    assert.equal(read(first).isCurrent, false)
    assert.equal(read(first).requestKey, old.requestKey)
    assert.equal(read(second).isCurrent, true)
    assert.notEqual(read(second).requestKey, old.requestKey)
})

test('identity checks reject forged credentials, viewer/account mismatch, expiration and revoked parent login', t => {
    const { db, issue, read } = fixture(t)
    const token = issue()
    for (const invalid of [undefined, '', 'wrong', parent]) assert.equal(read(invalid), null)
    for (const count of [null, 0, -1, 1.5, '1']) assert.equal(read(token, count), null)
    assert.equal(api.readGameplayMutationIdentitySync(db, token, { viewer_id: 1001 }, 1, now), null)
    assert.equal(read(token, 1, 1002), null)
    assert.equal(read(token, 1, 1001, 2), null)
    assert.equal(read(token, 1, 1001, 1, now + 10000), null)
    db.prepare("UPDATE accounts SET status='blocked' WHERE id=1").run()
    assert.equal(read(token), null)
    db.prepare("UPDATE accounts SET status='normal' WHERE id=1").run()
    db.prepare('DELETE FROM player_login_sessions WHERE token=?').run(parent)
    assert.equal(read(token), null)
})

test('failed signup issuance cannot revoke the prior nonce or change web credentials', t => {
    const { db, issue, read } = fixture(t)
    const first = issue(), before = db.serialize()
    assert.throws(() => db.transaction(() => {
        api.issueGameplayLoginTokenSync(db, { accountId: 1, viewerId: 1001, udid: 'synthetic-device', parentToken: parent,
            expiresAt: now + 10000, nowMs: now })
        throw new Error('injected signup rollback')
    })(), /injected signup rollback/)
    assert.deepEqual(db.serialize(), before)
    assert.equal(read(first).isCurrent, true)
    assert.throws(() => issue({ accountId: 2 }), /viewer does not belong/)
    assert.throws(() => issue({ expiresAt: now + 10001 }), /parent credential is invalid/)
    assert.deepEqual(db.serialize(), before)
    assert.equal(db.prepare('SELECT token FROM player_login_sessions').get().token, parent)
})
