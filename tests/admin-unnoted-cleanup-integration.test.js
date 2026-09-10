const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-unnoted-cleanup-'))
process.env.DATA_DIR = dataDir
process.env.ADMIN_PANEL_PASSWORD = 'cleanup-fixture-admin'
require('ts-node/register/transpile-only')
const { getDb } = require('../src/data/db')
const { insertAccountSync, updateAccountSync } = require('../src/data/domains/account')
const { insertDefaultPlayerSync } = require('../src/data/domains/player')
const { insertDeviceBindingSync } = require('../src/data/domains/session')
const { saveAccountDefaultPlayer, setActivePlayerId, setSelectedAccountId, getActivePlayerId, getSelectedAccountId, getAccountDefaultPlayer } = require('../src/data/activeAccount')
const auth = require('../src/lib/player-login')
const { installManagementAuth } = require('../src/lib/management-auth')
const app = require('fastify')({ logger: false })
const db = getDb()
const disconnected = []
auth.initializePlayerLogin(viewerId => disconnected.push(viewerId))

function legacy(note, deviceId) {
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'leiting', idpId: '', status: 'normal' })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    updateAccountSync({ id: account.id, adminNote: note })
    if (deviceId) insertDeviceBindingSync(deviceId, account.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)')
        .run(String(500000 + account.id), account.id, '2099-01-01T00:00:00.000Z')
    return { accountId: account.id, playerId: player.id }
}

async function main() {
    const blankNotes = [null, '', '   ', '\t\r\n', '\u3000\u00a0', null]
    const eligible = blankNotes.map((note, i) => legacy(note, i % 2 ? 91000 + i : null))
    const noted = legacy('没有设备绑定也必须保留备注账号', null)
    const active = legacy(null, 92000)
    const bound = auth.registerPlayerLogin('cleanupbound', 'FixturePass10', true)
    const boundAccountId = db.prepare('SELECT id FROM accounts WHERE username=?').get('cleanupbound').id
    const boundPlayerId = db.prepare('SELECT id FROM players WHERE account_id=?').get(boundAccountId).id
    const extraSave = insertDefaultPlayerSync(boundAccountId)
    setActivePlayerId(boundPlayerId)
    setSelectedAccountId(active.accountId)
    const notedBound = auth.registerPlayerLogin('cleanupnoted', 'FixturePass10', true)
    const notedBoundId = auth.playerAccountByViewer(notedBound.profile.viewer_id)
    updateAccountSync({ id: notedBoundId, adminNote: '已备注绑定账号保留' })
    const usernameOnly = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'fixture', idpId: 'zero-save', status: 'normal' })
    updateAccountSync({ id: usernameOnly.id, username: 'zerounnoted' })
    const notedDuringCleanup = legacy(null, null)
    const bindCode = auth.createPlayerLoginCode(500000 + eligible[0].accountId, 'bind')
    auth.previewPlayerClaim({ code: bindCode.code })
    auth.createPlayerLoginCode(bound.profile.viewer_id, 'reset')
    const expectedDeleted = [...eligible.map(row => row.accountId), active.accountId, boundAccountId, usernameOnly.id].sort((a, b) => a - b)
    const expectedPlanned = [...expectedDeleted, notedDuringCleanup.accountId].sort((a, b) => a - b)
    const expectedDeletedSaves = eligible.length + 1 + 2
    const initialCount = db.prepare('SELECT COUNT(*) AS n FROM accounts').get().n
    installManagementAuth(app)
    await app.register(require('../src/routes/web_api/server').default, { prefix: '/api/server' })
    await app.ready()
    const post = (url, payload, headers = {}) => app.inject({ method: 'POST', url, payload, headers })
    assert.equal((await post('/api/server/deleteUnnotedAccounts', { confirm: 'DELETE_UNNOTED_ACCOUNTS' })).statusCode, 401)
    const login = await post('/admin-login', { password: process.env.ADMIN_PANEL_PASSWORD })
    const headers = { cookie: login.headers['set-cookie'].split(';')[0] }
    assert.equal((await post('/api/server/deleteUnnotedAccounts', {}, headers)).statusCode, 400)
    const list = (await app.inject({ url: '/api/server/accounts', headers })).json()
    const uiEligible = list.filter(account =>
        !(typeof account.note === 'string' && account.note.trim().length > 0)
    )
    assert.deepEqual(uiEligible.map(account => account.id).sort((a, b) => a - b), expectedPlanned)
    disconnected.length = 0

    const start = await post('/api/server/deleteUnnotedAccounts', { confirm: 'DELETE_UNNOTED_ACCOUNTS' }, headers)
    assert.equal(start.statusCode, 202)
    assert.equal(start.json().totalAccounts, expectedPlanned.length)
    // The worker is still preparing the plan. A note added after confirmation
    // must be rechecked in the eventual deletion transaction.
    updateAccountSync({ id: notedDuringCleanup.accountId, adminNote: '清理期间补备注保留' })
    let job = start.json()
    const deadline = Date.now() + 20000
    while (job.status === 'running' && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 100))
        job = (await app.inject({ url: '/api/server/deleteUnnotedAccounts/status', headers })).json()
    }
    assert.equal(job.status, 'completed', job.error || 'cleanup did not finish')
    assert.equal(job.deletedAccounts, expectedDeleted.length)
    assert.equal(job.deletedSaves, expectedDeletedSaves)
    assert.equal(job.processedAccounts, expectedPlanned.length)
    assert.equal(job.skippedActiveAccount, null)
    for (const accountId of expectedDeleted) {
        assert.equal(db.prepare('SELECT id FROM accounts WHERE id=?').get(accountId), undefined)
        assert.equal(db.prepare('SELECT id FROM players WHERE account_id=?').get(accountId), undefined)
        assert.equal(getAccountDefaultPlayer(accountId), null)
        for (const table of ['sessions', 'device_bindings', 'player_login_credentials', 'player_login_sessions', 'player_login_codes', 'player_login_claims']) {
            assert.equal(db.prepare(`SELECT COUNT(*) n FROM ${table} WHERE account_id=?`).get(accountId).n, 0, table)
        }
    }
    assert.equal(db.prepare('SELECT id FROM players WHERE id=?').get(extraSave.id), undefined)
    assert.equal(getActivePlayerId(), null)
    assert.equal(getSelectedAccountId(), null)
    for (const id of [noted.accountId, notedBoundId, notedDuringCleanup.accountId]) {
        assert.ok(db.prepare('SELECT id FROM accounts WHERE id=?').get(id))
    }
    assert.equal(auth.readPlayerLoginSession(bound.token), null, 'deleted bound session is invalid')
    assert.throws(() => auth.resumePlayerLogin(bound.token), auth.PlayerLoginError)
    assert.throws(() => auth.loginPlayer('cleanupbound', 'FixturePass10', true), auth.PlayerLoginError)
    assert.ok(disconnected.includes(bound.profile.viewer_id), 'deleted bound account transports are disconnected')
    assert.ok(disconnected.includes(500000 + active.accountId), 'deleted selected legacy account transports are disconnected')
    assert.ok(!disconnected.includes(notedBound.profile.viewer_id))
    assert.ok(auth.readPlayerLoginSession(notedBound.token), 'noted bound session remains usable')
    assert.equal(db.prepare('SELECT admin_note FROM accounts WHERE id=?').get(noted.accountId).admin_note, '没有设备绑定也必须保留备注账号')

    const backupDir = path.join(dataDir, 'admin-backups', path.basename(job.backup))
    const backupDb = new (require('better-sqlite3'))(path.join(backupDir, 'wdfp_data.db'), { readonly: true })
    try {
        assert.equal(backupDb.prepare('SELECT COUNT(*) AS n FROM accounts').get().n, initialCount)
        assert.ok(backupDb.prepare('SELECT account_id FROM player_login_credentials WHERE account_id=?').get(boundAccountId))
        assert.ok(backupDb.prepare('SELECT account_id FROM player_login_codes WHERE account_id=?').get(boundAccountId))
        assert.ok(backupDb.prepare('SELECT id FROM players WHERE id=?').get(extraSave.id))
    } finally { backupDb.close() }
    const result = JSON.parse(fs.readFileSync(path.join(backupDir, 'cleanup-result.json'), 'utf8'))
    assert.deepEqual(result.deletedAccountIds.sort((a, b) => a - b), expectedDeleted)
    const empty = await post('/api/server/deleteUnnotedAccounts', { confirm: 'DELETE_UNNOTED_ACCOUNTS' }, headers)
    assert.equal(empty.statusCode, 200)
    assert.equal(empty.json().deletedAccounts, 0)
    assert.equal(empty.json().backup, null)
    assert.equal(db.pragma('integrity_check', { simple: true }), 'ok')
    assert.deepEqual(db.pragma('foreign_key_check'), [])
    console.log(`PASS cleanup HTTP + Worker: ${expectedDeleted.length} unnoted accounts / ${expectedDeletedSaves} saves deleted, including bound, selected, zero-save and Unicode-whitespace notes; noted/newly-noted accounts preserved; credentials revoked; backup verified; empty retry returns 0.`)
}

main().catch(error => { console.error(error); process.exitCode = 1 }).finally(async () => {
    await app.close()
    await require('../src/multi/npc/player-party-pool').stopQuestNpcPartyPoolWorker()
    db.close()
    const resolved = path.resolve(dataDir)
    assert.ok(resolved.startsWith(path.resolve(os.tmpdir()) + path.sep))
    assert.ok(path.basename(resolved).startsWith('starpoint-unnoted-cleanup-'))
    fs.rmSync(resolved, { recursive: true, force: true })
    setImmediate(() => process.exit(process.exitCode || 0))
})
