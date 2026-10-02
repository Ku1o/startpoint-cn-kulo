// Local single-thread comparison of the r4/r5 game-request authentication paths.
// Measures authentication only, not game endpoints, network latency, or cloud capacity.
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os')
const { performance } = require('node:perf_hooks')
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-login-perf-'))
process.env.DATA_DIR = dataDir
require('ts-node/register/transpile-only')
const { getDb } = require('../src/data/db')
const auth = require('../src/lib/player-login')
const db = getDb()
auth.initializePlayerLogin()
const count = 10000, iterations = 30000, records = [], expires = Date.now() + 86400000
const legacyRecords = []
const account = db.prepare(`INSERT INTO accounts(app_id,first_login_time,idp_alias,idp_code,idp_id,reg_time,last_login_time,status,username,takeover_udid)
    VALUES('wf_cn',?,'','leiting','',?,?,'normal',?,?)`)
const credential = db.prepare('INSERT INTO player_login_credentials(account_id,password,created_at) VALUES(?,?,?)')
const viewer = db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)')
const session = db.prepare('INSERT INTO player_login_sessions(token,account_id,viewer_id,udid,expires_at) VALUES(?,?,?,?,?)')
db.transaction(() => {
    const now = new Date().toISOString()
    for (let i = 0; i < count; i++) {
        const token = (i + 1).toString(16).padStart(64, '0'), udid = token.slice(32)
        const id = Number(account.run(now, now, now, 'perf' + i, udid).lastInsertRowid)
        const uid = 200000000 + i
        credential.run(id, 'SyntheticOnly', Date.now()); viewer.run(String(uid), id, now)
        session.run(token, id, uid, udid, expires); records.push({ token, udid, viewer: String(uid), id })
    }
    for (let i = 0; i < count; i++) {
        const id = Number(account.run(now, now, now, 'legacy' + i, '').lastInsertRowid)
        const uid = 300000000 + i
        viewer.run(String(uid), id, now)
        legacyRecords.push({ viewer: String(uid), id })
    }
})()
function r4(record) {
    if (!/^[a-f0-9]{64}$/.test(record.token)) return false
    const s = db.prepare(`SELECT s.* FROM player_login_sessions s JOIN accounts a ON a.id=s.account_id
        WHERE s.token=? AND s.expires_at>? AND a.status='normal'`).get(record.token, Date.now())
    const a = db.prepare('SELECT account_id FROM sessions WHERE token=? AND type=2').get(record.viewer)
    const managed = a && db.prepare('SELECT 1 FROM player_login_credentials WHERE account_id=?').get(a.account_id)
    if (!s || !a || !managed || s.account_id !== a.account_id) return false
    const legacy = db.prepare(`SELECT a.takeover_udid FROM sessions s JOIN accounts a ON a.id=s.account_id
        WHERE s.token=? AND s.type=? LIMIT 1`).get(record.viewer, 2)
    return !legacy?.takeover_udid || legacy.takeover_udid === record.udid
}
function r5(record) {
    const s = auth.readPlayerLoginAccess(record.token, record.viewer)
    return !!s && s.request_account_id === s.account_id
}
function legacyOld(record) {
    const row = db.prepare('SELECT account_id FROM sessions WHERE token=? AND type=2').get(record.viewer)
    return row && !db.prepare('SELECT 1 FROM player_login_credentials WHERE account_id=?').get(row.account_id)
}
function legacyNew(record) {
    const access = auth.readPlayerLoginViewerAccess(record.viewer)
    return access && !access.managed
}
function run(fn, n, source = records) {
    const cpu = process.cpuUsage(), start = performance.now()
    for (let i = 0; i < n; i++) assert.ok(fn(source[(i * 7919) % source.length]))
    const elapsed = performance.now() - start, usage = process.cpuUsage(cpu)
    return { elapsed_ms: elapsed, cpu_ms: (usage.user + usage.system) / 1000, microseconds_per_check: elapsed * 1000 / n }
}
async function main() {
    run(r4, 2000); run(r5, 2000)
    run(legacyOld, 2000, legacyRecords); run(legacyNew, 2000, legacyRecords)
    const samples = []
    for (let round = 0; round < 5; round++) {
        const result = {}
        for (const version of round % 2 ? ['r5', 'r4'] : ['r4', 'r5']) result[version] = run(version === 'r4' ? r4 : r5, iterations)
        for (const version of round % 2 ? ['legacyNew', 'legacyOld'] : ['legacyOld', 'legacyNew']) {
            result[version] = run(
                version === 'legacyOld' ? legacyOld : legacyNew,
                iterations,
                legacyRecords,
            )
        }
        samples.push(result)
    }
    const median = version => samples.map(x => x[version].microseconds_per_check).sort((a,b) => a-b)[2]
    const report = {
        scope: 'Local single-thread game-request authentication only; no cloud capacity claim',
        node: process.version, cpu: os.cpus()[0].model, account_count: count, checks_per_sample: iterations, samples,
        r4_median_us: median('r4'), r5_median_us: median('r5'),
        reduction_percent: (1 - median('r5') / median('r4')) * 100,
        legacy_guard_old_median_us: median('legacyOld'),
        legacy_guard_new_median_us: median('legacyNew'),
        legacy_guard_reduction_percent: (1 - median('legacyNew') / median('legacyOld')) * 100,
        database_reads_per_authenticated_game_guard: { r4: 4, r5: 1 },
        username_query_plan: db.prepare("EXPLAIN QUERY PLAN SELECT id FROM accounts WHERE lower(username)=? AND username IS NOT NULL AND username<>''").all('perf9999'),
    }
    if (process.argv[2]) fs.writeFileSync(path.resolve(process.argv[2]), JSON.stringify(report, null, 2) + '\n')
    console.log(JSON.stringify({ accounts: count * 2, r4_us: report.r4_median_us, r5_us: report.r5_median_us,
        reduction_percent: report.reduction_percent, legacy_guard_old_us: report.legacy_guard_old_median_us,
        legacy_guard_new_us: report.legacy_guard_new_median_us,
        legacy_guard_reduction_percent: report.legacy_guard_reduction_percent }))
}
main().catch(error => { console.error(error); process.exitCode = 1 }).finally(async () => {
    await require('../src/multi/npc/player-party-pool').stopQuestNpcPartyPoolWorker()
    db.close()
    assert.ok(path.resolve(dataDir).startsWith(path.resolve(os.tmpdir()) + path.sep))
    fs.rmSync(dataDir, { recursive: true, force: true })
    setImmediate(() => process.exit(process.exitCode || 0))
})
