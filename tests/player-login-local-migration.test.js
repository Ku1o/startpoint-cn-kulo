const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { performance } = require('node:perf_hooks')
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-local-migration-'))
process.env.DATA_DIR = dataDir
require('ts-node/register/transpile-only')
const { getDb } = require('../src/data/db')
const auth = require('../src/lib/player-login')
const { insertAccountSync, updateAccountSync } = require('../src/data/domains/account')
const { insertDefaultPlayerSync } = require('../src/data/domains/player')
const { insertDeviceBindingSync } = require('../src/data/domains/session')
const { saveAccountDefaultPlayer } = require('../src/data/activeAccount')
const routes = require('../src/routes/cn/playerLogin').default
const Fastify = require('fastify')
const db = getDb()
auth.initializePlayerLogin()
let checks = 0, sequence = 0
function check(value, name) { assert.ok(value, name); checks++ }
function legacy(udid = null) {
    const id = ++sequence
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'leiting', idpId: '', status: 'normal' })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    const viewer = 612345000 + id, device = 712345000000 + id
    insertDeviceBindingSync(device, account.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, new Date().toISOString())
    updateAccountSync({ id: account.id, takeoverUdid: udid, adminNote: '老账号备注：保留', takeoverPassword: 'LegacyPass7' })
    return { account, player, body: { viewer_id: viewer, device_id: device, udid: udid || 'old-local-udid-not-saved-on-server' } }
}
function preview(x) { return auth.previewLocalPlayerClaim(x.body || x) }
function rejected(p) { assert.throws(() => auth.bindPlayerLogin(p.proof, 'local_migrate_' + (++sequence), 'PlainPass7', true), auth.PlayerLoginError); checks++ }
async function main() {
    const a = legacy(), b = legacy()
    const initialCount = db.prepare('SELECT count(*) n FROM accounts').get().n
    const playerBefore = db.prepare('SELECT * FROM players WHERE id=?').get(a.player.id)
    const accountBefore = db.prepare('SELECT * FROM accounts WHERE id=?').get(a.account.id)
    check(preview({ viewer_id: a.body.viewer_id }).status === 'manual_required', 'public UID alone cannot claim')
    check(preview({ ...a.body, device_id: b.body.device_id }).status === 'manual_required', 'device must belong to same UID')
    for (const invalid of [null, true, {}, [], -1, 1.1, Number.MAX_SAFE_INTEGER + 1, 'bad']) {
        check(preview({ ...a.body, device_id: invalid }).status === 'manual_required', 'invalid device rejected')
    }
    check(preview({ ...a.body, viewer_id: 'not-a-uid' }).status === 'manual_required', 'invalid UID falls back')
    const p = preview(a)
    check(p.status === 'claimable' && p.profile.viewer_id === a.body.viewer_id, 'untransferred old device and UID preview exact save')
    assert.deepEqual(db.prepare('SELECT * FROM accounts WHERE id=?').get(a.account.id), accountBefore); checks++
    check(db.prepare('SELECT count(*) n FROM accounts').get().n === initialCount, 'discovery never creates accounts')
    const bound = auth.bindPlayerLogin(p.proof, 'local_migrate_a', 'PlainPass7', true)
    check(bound.profile.viewer_id === a.body.viewer_id && auth.playerAccountByViewer(a.body.viewer_id) === a.account.id, 'binding preserves account and UID')
    assert.deepEqual(db.prepare('SELECT * FROM players WHERE id=?').get(a.player.id), playerBefore); checks++
    check(db.prepare('SELECT admin_note FROM accounts WHERE id=?').get(a.account.id).admin_note === accountBefore.admin_note, 'admin note retained')
    check(db.prepare('SELECT account_id FROM device_bindings WHERE device_id=?').get(a.body.device_id).account_id === a.account.id, 'original binding retained as history')
    rejected(p)
    const managed = preview(a)
    assert.deepEqual(managed, { status: 'login_required' }); checks++
    check(!managed.proof && !managed.profile, 'already-bound saves expose neither proof nor username')
    const udid = 'verified-original-udid-0123456789'
    const transferred = legacy(udid)
    check(preview({ ...transferred.body, udid: 'wrong-udid-0123456789' }).status === 'manual_required', 'matching old device cannot override changed UDID')
    check(preview({ ...transferred.body, udid: 'unknown' }).status === 'manual_required', 'placeholder UDID never overrides transfer guard')
    const up = preview({ ...transferred.body, device_id: 0 })
    check(up.status === 'claimable', 'verified stored UDID recovers after device file is lost')
    updateAccountSync({ id: transferred.account.id, takeoverUdid: 'new-owner-udid-0123456789' })
    rejected(up)
    const removed = legacy(), rp = preview(removed)
    db.prepare('DELETE FROM device_bindings WHERE device_id=?').run(removed.body.device_id)
    rejected(rp)
    const moved = legacy(), mp = preview(moved)
    db.prepare('UPDATE sessions SET account_id=? WHERE token=? AND type=2').run(b.account.id, String(moved.body.viewer_id))
    rejected(mp)
    const changed = legacy(), cp = preview(changed)
    updateAccountSync({ id: changed.account.id, takeoverUdid: 'new-transfer-after-preview-012345' })
    rejected(cp)
    const banned = legacy(), bp = preview(banned)
    db.prepare("UPDATE accounts SET status='banned' WHERE id=?").run(banned.account.id)
    check(preview(banned).status === 'manual_required', 'banned account not offered')
    rejected(bp)
    const expired = legacy(), ep = preview(expired)
    db.prepare('UPDATE player_login_claims SET expires_at=? WHERE proof=?').run(Date.now() - 1, ep.proof)
    rejected(ep)
    const competing = legacy(), p1 = preview(competing), p2 = preview(competing)
    auth.bindPlayerLogin(p1.proof, 'local_migrate_compete', 'PlainPass7', true)
    rejected(p2)
    const duplicate = legacy(), dp = preview(duplicate)
    assert.throws(() => auth.bindPlayerLogin(dp.proof, 'local_migrate_a', 'PlainPass7', true), auth.PlayerLoginError)
    check(!auth.playerLoginManaged(duplicate.account.id), 'name collision rolls back without consuming old account')
    check(auth.bindPlayerLogin(dp.proof, 'local_migrate_retry', 'PlainPass7', true).profile.viewer_id === duplicate.body.viewer_id, 'same proof can retry after name collision')
    const app = Fastify({ logger: false })
    await app.register(routes)
    const http = legacy()
    const response = await app.inject({ method: 'POST', url: '/player-auth/local-claim-preview', payload: http.body })
    const data = response.json()
    check(data.ok && data.data.status === 'claimable', 'actual HTTP discovery route works')
    check(response.headers['cache-control'] === 'no-store' && response.body.length < 1024, 'small non-cacheable response')
    const result = (await app.inject({ method: 'POST', url: '/player-auth/bind', payload: { proof: data.data.proof, username: 'local_http', password: 'PlainPass7', remember: true } })).json()
    check(result.ok && result.data.profile.viewer_id === http.body.viewer_id, 'HTTP preview then bind retains UID')
    const beforeLimit = db.prepare('SELECT count(*) n FROM player_login_claims').get().n
    for (let i = 0; i < 31; i++) {
        const reply = (await app.inject({ method: 'POST', url: '/player-auth/local-claim-preview', remoteAddress: '192.0.2.14', payload: { viewer_id: 999999999, device_id: 1 } })).json()
        if (i === 30) check(reply.code === 'RATE_LIMITED', 'discovery rate limited')
    }
    check(db.prepare('SELECT count(*) n FROM player_login_claims').get().n === beforeLimit, 'failed discovery does not create proofs')
    await app.close()
    // Small local single-thread timing only, with 10k accounts to catch accidental account-table scans.
    db.transaction(() => {
        for (let i = 0; i < 10000; i++) insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'leiting', idpId: '', status: 'normal' })
    })()
    const perfFixture = legacy()
    const timings = []
    for (let i = 0; i < 500; i++) {
        const start = performance.now(); const discovered = preview(perfFixture); timings.push(performance.now() - start)
        assert.equal(discovered.status, 'claimable')
    }
    timings.sort((a, b) => a - b)
    check(db.pragma('integrity_check', { simple: true }) === 'ok', 'database integrity')
    check(db.pragma('foreign_key_check').length === 0, 'foreign keys intact')
    console.log(JSON.stringify({ checks, responseBytes: Buffer.byteLength(response.body), accounts: db.prepare('SELECT count(*) n FROM accounts').get().n,
        localDiscoveryMs: { samples: timings.length, median: timings[250], p95: timings[475] }, scope: 'local single-thread discovery; not a cloud capacity benchmark' }, null, 2))
}
main().catch(error => { console.error(error); process.exitCode = 1 }).finally(() => { db.close(); fs.rmSync(dataDir, { recursive: true, force: true }) })
