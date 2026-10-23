'use strict'
// SERIAL ONLY: this suite owns the candidate checkout's .storage-maintenance
// journal while every player DB/config/log is synthesized outside the checkout.
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net')
const { randomInt, createHash } = require('node:crypto'), { spawnSync } = require('node:child_process')
const Sqlite = require('better-sqlite3')
const root = path.resolve(__dirname, '..'), command = path.join(root, 'scripts/time-content-deployment.cjs')
const maintenance = path.join(root, '.storage-maintenance'), journal = path.join(maintenance, 'time-content-state.json')
const cdn = process.env.STARPOINT_TEST_CDN_DIR || process.env.CDN_DIR
const crashExit = 73, json = file => JSON.parse(fs.readFileSync(file, 'utf8'))
const text = result => `${result.stdout}\n${result.stderr}`
const shaFile = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex')
const fingerprint = require('../out/lib/deployment-maintenance-guard').getDeploymentDatabaseFingerprintSync
function run(args, env) {
    return spawnSync(process.execPath, args, { cwd: root, env, encoding: 'utf8', windowsHide: true,
        timeout: 120000, maxBuffer: 4 * 1024 * 1024 })
}
const cli = (action, env) => run([command, action, '--project', root], env)
function successful(result) { assert.equal(result.status, 0, text(result)); return result }
function currentFingerprint(fixture) {
    const db = new Sqlite(fixture.database, { readonly: true, fileMustExist: true })
    try { return fingerprint(db) } finally { db.close() }
}
function locks(fixture) { return [path.join(maintenance, 'active.lock'), path.join(fixture.data, 'storage-maintenance.lock')] }
function assertLocks(fixture, expected) { for (const file of locks(fixture)) assert.equal(fs.existsSync(file), expected, file) }
function assertApplyRemainsLocked(fixture) {
    const saved = fs.readFileSync(journal)
    const refused = cli('apply', fixture.env)
    assert.equal(refused.status, 1, text(refused))
    assert.match(text(refused), /EEXIST|file already exists/i)
    assert.deepEqual(fs.readFileSync(journal), saved, 'A new apply must not replace the interrupted durable intent')
    assertLocks(fixture, true)
}
async function freePort(excluded = new Set()) {
    for (let attempt = 0; attempt < 32; attempt++) {
        const port = randomInt(25000, 60001)
        if (excluded.has(port)) continue
        const server = net.createServer()
        const available = await new Promise((resolve, reject) => {
            server.once('error', error => ['EADDRINUSE', 'EACCES'].includes(error.code) ? resolve(false) : reject(error))
            server.listen(port, '127.0.0.1', () => resolve(true))
        })
        if (!available) continue
        await new Promise(resolve => server.close(resolve))
        return port
    }
    throw Error('No free high loopback test port after 32 attempts')
}
function createFixture(ports) {
    const parent = fs.realpathSync(process.env.STARPOINT_DEPLOYMENT_TEST_ROOT || os.tmpdir())
    const directory = fs.mkdtempSync(path.join(parent, 'time-content-recovery-'))
    const data = path.join(directory, 'database'), logs = path.join(directory, 'logs')
    fs.mkdirSync(data); fs.mkdirSync(logs)
    const env = { ...process.env, DATA_DIR: data, CDN_DIR: cdn, CN_LOG_DIR: logs,
        TMP: directory, TEMP: directory, TMPDIR: directory, SQLITE_TMPDIR: directory,
        GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_LISTEN_PORT: String(ports[0]), SESSION_PORT: String(ports[1]),
        CN_WRITER_THREAD: '0', CN_MULTICORE: '0', CN_RESPONSE_WORKERS: '0', MULTI_REALTIME_PROCESS: '0' }
    const setup = run(['-e', `
        const db=require('./out/data').initializeDatabase();
        const account=require('./out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'recovery-fixture',idpId:'synthetic-player',status:'normal'});
        const player=require('./out/data/domains/player').insertDefaultPlayerSync(account.id);
        db.prepare('UPDATE players SET free_vmoney=13579,exp_pool=24680 WHERE id=?').run(player.id);
        console.log('RECOVERY_PLAYER='+player.id); db.close();
    `], env)
    successful(setup)
    const playerId = Number(setup.stdout.match(/RECOVERY_PLAYER=(\d+)/)?.[1])
    assert.ok(Number.isSafeInteger(playerId) && playerId > 0)
    fs.writeFileSync(path.join(data, 'active_account.json'), JSON.stringify({ timeOffset: -38793700413 }))
    return { parent, directory, data, env, playerId, database: fs.realpathSync(path.join(data, 'wdfp_data.db')) }
}
function crashAt(action, point, fixture) {
    const result = run(['-e', `
        const api=require('./scripts/time-content-deployment.cjs');
        api[${JSON.stringify(action)}]({project:process.cwd(),checkpoint:point=>{
            if(point===${JSON.stringify(point)}){
                process.stderr.write('REAL_PROCESS_EXIT_AT='+point+'\\n'); process.exit(${crashExit});
            }
        }}).then(()=>{throw Error('Checkpoint was not reached')}).catch(error=>{console.error(error);process.exitCode=1});
    `], fixture.env)
    assert.equal(result.status, crashExit, text(result))
    assert.match(result.stderr, new RegExp('REAL_PROCESS_EXIT_AT=' + point))
    return result
}
function assertMoney(fixture, expected = 13579) {
    const db = new Sqlite(fixture.database, { readonly: true, fileMustExist: true })
    try {
        assert.equal(db.prepare('SELECT free_vmoney FROM players WHERE id=?').get(fixture.playerId).free_vmoney, expected)
        assert.equal(db.prepare('SELECT exp_pool FROM players WHERE id=?').get(fixture.playerId).exp_pool, 24680)
        assert.equal(db.pragma('quick_check', { simple: true }), 'ok')
    } finally { db.close() }
}
function removeOwnJournal(fixture) {
    if (!fs.existsSync(journal)) return
    const state = json(journal)
    assert.equal(state.database, fixture.database, 'Never clean another run journal')
    for (const file of locks(fixture)) if (fs.existsSync(file)) {
        const lock = json(file)
        assert.equal(lock.runId, state.runId); assert.equal(lock.database, fixture.database)
        fs.unlinkSync(file)
    }
    fs.unlinkSync(journal)
    try { fs.rmdirSync(maintenance) } catch {}
}
async function withFixture(ports, execute) {
    assert.equal(fs.existsSync(journal), false, 'Another run owns the candidate journal; do not run suites in parallel')
    assert.equal(fs.existsSync(path.join(maintenance, 'active.lock')), false)
    const fixture = createFixture(ports)
    let passed = false
    try { await execute(fixture); passed = true } finally {
        // Retain unique failed synthetic inputs, but clear only our own candidate
        // lock files so a failed subtest cannot poison the next independent run.
        if (!passed && fs.existsSync(journal) && json(journal).database === fixture.database)
            fs.copyFileSync(journal, path.join(fixture.directory, 'failed-journal.json'))
        removeOwnJournal(fixture)
        if (passed) {
            assert.equal(path.dirname(fixture.directory), fixture.parent)
            fs.rmSync(fixture.directory, { recursive: true, force: true })
        } else console.error('FAILED_RECOVERY_FIXTURE=' + fixture.directory)
    }
}

test('deployment recovery uses genuine process exits and protects backups, frozen inputs and subsequent player facts', { timeout: 360000, concurrency: false }, async t => {
    assert.ok(cdn && path.isAbsolute(cdn) && fs.statSync(cdn).isDirectory(), 'Set STARPOINT_TEST_CDN_DIR to the existing read-only native CDN directory')
    assert.equal(fs.existsSync(journal), false, 'Run this suite after time-content-deployment-cli and all candidate maintenance has finished')
    assert.equal(fs.existsSync(path.join(maintenance, 'active.lock')), false)
    const one = await freePort(), ports = [one, await freePort(new Set([one]))]

    await t.test('committing intent survives a real process exit before COMMIT and recovers the exact pre-migration database', async () => withFixture(ports, async fixture => {
        const before = currentFingerprint(fixture)
        crashAt('apply', 'before-commit', fixture)
        const state = json(journal)
        assert.equal(state.phase, 'committing')
        assert.equal(state.beforeFingerprint, before)
        assert.match(state.afterFingerprint, /^[a-f0-9]{64}$/)
        assert.notEqual(state.afterFingerprint, before)
        assert.equal(currentFingerprint(fixture), before, 'SQLite must roll back actual uncommitted content+clock writes')
        assertLocks(fixture, true); assertMoney(fixture)
        assertApplyRemainsLocked(fixture)
        successful(cli('recover', fixture.env))
        const recovered = json(journal)
        assert.equal(recovered.phase, 'rolled-back')
        assert.equal(recovered.beforeFingerprint, state.beforeFingerprint)
        assert.equal(recovered.afterFingerprint, state.afterFingerprint, 'Recovery must retain the actual pre-COMMIT durable intent')
        assert.equal(currentFingerprint(fixture), before)
        successful(cli('release', fixture.env))
        assertLocks(fixture, false)
    }))

    await t.test('COMMIT followed by a real process exit before applied journal recovers committed state without replaying writes', async () => withFixture(ports, async fixture => {
        crashAt('apply', 'after-commit', fixture)
        const state = json(journal)
        assert.equal(state.phase, 'committing')
        const committed = currentFingerprint(fixture)
        assert.equal(committed, state.afterFingerprint)
        assert.notEqual(committed, state.beforeFingerprint)
        assertLocks(fixture, true); assertMoney(fixture)
        assertApplyRemainsLocked(fixture)
        successful(cli('recover', fixture.env))
        const recovered = json(journal)
        assert.equal(recovered.phase, 'applied')
        assert.equal(recovered.beforeFingerprint, state.beforeFingerprint)
        assert.equal(recovered.afterFingerprint, state.afterFingerprint, 'Recovery must use the fingerprint persisted before the real COMMIT')
        assert.equal(currentFingerprint(fixture), committed)
        successful(cli('verify', fixture.env))
        successful(cli('release', fixture.env))
        assertLocks(fixture, false)
        const repeated = successful(cli('apply', fixture.env))
        assert.match(repeated.stdout, /"phase": "already-ready"/)
        assert.equal(currentFingerprint(fixture), committed, 'Repeat must not replay migration or overwrite choices/progress')
        assertLocks(fixture, false)
    }))

    await t.test('release interrupted after deleting one lock resumes safely and permits repeated release', async () => withFixture(ports, async fixture => {
        successful(cli('apply', fixture.env))
        const applied = currentFingerprint(fixture)
        crashAt('release', 'after-release-first-lock', fixture)
        assert.equal(json(journal).phase, 'released')
        assert.equal(fs.existsSync(locks(fixture)[0]), false)
        assert.equal(fs.existsSync(locks(fixture)[1]), true)
        successful(cli('release', fixture.env))
        assertLocks(fixture, false)
        successful(cli('release', fixture.env))
        assertLocks(fixture, false)
        assert.equal(currentFingerprint(fixture), applied)
    }))

    await t.test('after-commit recovery refuses a changed backup or input read; subsequent real player progress prevents rollback', async () => withFixture(ports, async fixture => {
        crashAt('apply', 'after-commit', fixture)
        const state = json(journal), committed = currentFingerprint(fixture), frozenJournal = fs.readFileSync(journal)
        const backupBytes = fs.readFileSync(state.backup), tampered = Buffer.from(backupBytes)
        tampered[0] ^= 1
        fs.writeFileSync(state.backup, tampered)
        try {
            const refused = cli('recover', fixture.env)
            assert.equal(refused.status, 1, text(refused)); assert.match(text(refused), /备份|变化/)
            assert.equal(currentFingerprint(fixture), committed)
            assert.deepEqual(fs.readFileSync(journal), frozenJournal)
            assertLocks(fixture, true)
        } finally { fs.writeFileSync(state.backup, backupBytes) }
        assert.equal(shaFile(state.backup), state.backupSha256)
        const inputPath = path.join(root, 'assets/content_discovery_runtime.json'), originalInputSha = shaFile(inputPath)
        // Simulate changed raw input bytes for this one recovery process only.
        // Added JSON whitespace preserves semantics; no source/resource is written,
        // no receipt phase/fingerprint is forged, and the actual recover API runs.
        const inputRefusal = run(['-e', `
            const fs=require('node:fs'),path=require('node:path');
            const api=require('./scripts/time-content-deployment.cjs');
            if(!api.inspect({project:process.cwd()}).ready)throw Error('Committed fixture must be ready before input drift');
            const original=fs.readFileSync, target=${JSON.stringify(inputPath)};
            fs.readFileSync=function(file,...args){
                const value=original.call(this,file,...args);
                if(typeof file==='string'&&path.resolve(file)===target)
                    return typeof value==='string'?value+'\\n':Buffer.concat([value,Buffer.from('\\n')]);
                return value;
            };
            api.recover({project:process.cwd()}).then(()=>{throw Error('Changed input was accepted')})
                .catch(error=>{console.error(error.message);process.exitCode=1});
        `], fixture.env)
        assert.equal(inputRefusal.status, 1, text(inputRefusal))
        assert.match(text(inputRefusal), /输入|索引|变化|不匹配/)
        assert.equal(shaFile(inputPath), originalInputSha, 'The actual source asset remains unchanged')
        assert.equal(currentFingerprint(fixture), committed)
        assert.deepEqual(fs.readFileSync(journal), frozenJournal)
        assertLocks(fixture, true)
        successful(cli('recover', fixture.env))
        const db = new Sqlite(fixture.database, { fileMustExist: true })
        try { db.prepare('UPDATE players SET free_vmoney=free_vmoney+1 WHERE id=?').run(fixture.playerId) } finally { db.close() }
        const newProgress = currentFingerprint(fixture), refused = cli('rollback', fixture.env)
        assert.equal(refused.status, 1, text(refused)); assert.match(text(refused), /新的数据|玩家进度/)
        assert.equal(currentFingerprint(fixture), newProgress)
        assertMoney(fixture, 13580); assertLocks(fixture, true)
        successful(cli('release', fixture.env))
        assertMoney(fixture, 13580); assertLocks(fixture, false)
    }))
})
