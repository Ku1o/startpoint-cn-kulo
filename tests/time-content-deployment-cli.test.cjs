'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const net = require('node:net')
const { randomInt } = require('node:crypto')
const { spawnSync } = require('node:child_process')
const Sqlite = require('better-sqlite3')

const root = path.resolve(__dirname, '..')
const command = path.join(root, 'scripts/time-content-deployment.cjs')
const maintenance = path.join(root, '.storage-maintenance')
const statePath = path.join(maintenance, 'time-content-state.json')
const cdn = process.env.STARPOINT_TEST_CDN_DIR || process.env.CDN_DIR // read-only native-definition fixture
const run = (args, env) => spawnSync(process.execPath, args, { cwd: root, env, encoding: 'utf8', windowsHide: true, timeout: 120000 })
const message = result => `${result.stdout}\n${result.stderr}`
const marker = db => db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('content_operations_deployment','content_box_exchange_deployment','server_clock_state') ORDER BY name").all().map(row => row.name)

async function freePort(excluded = new Set()) {
    for (let attempt = 0; attempt < 32; attempt++) {
        const port = randomInt(25000, 60001), server = net.createServer()
        if (excluded.has(port)) continue
        const available = await new Promise((resolve, reject) => {
            server.once('error', error => error.code === 'EADDRINUSE' || error.code === 'EACCES' ? resolve(false) : reject(error))
            server.listen(port, '127.0.0.1', () => resolve(true))
        })
        if (!available) continue
        await new Promise(resolve => server.close(resolve))
        return port
    }
    throw new Error('Could not reserve two high loopback ports after 32 attempts')
}
function createFixture(t, ports) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'time-content-cli-'))
    const data = path.join(directory, 'database'), log = path.join(directory, 'logs')
    fs.mkdirSync(data); fs.mkdirSync(log)
    const env = { ...process.env, DATA_DIR: data, CDN_DIR: cdn, CN_LOG_DIR: log,
        CN_LISTEN_PORT: String(ports[0]), SESSION_PORT: String(ports[1]), CN_WRITER_THREAD: '0' }
    const setup = run(['-e', `
        const { initializeDatabase } = require('./out/data');
        const { insertAccountSync } = require('./out/data/domains/account');
        const { insertDefaultPlayerSync } = require('./out/data/domains/player');
        const db = initializeDatabase();
        const ids = [];
        for (const name of ['source','target']) {
            const account = insertAccountSync({ appId:'wf_cn', idpAlias:'', idpCode:'fixture', idpId:'time-content-'+name, status:'normal' });
            ids.push(insertDefaultPlayerSync(account.id).id);
        }
        db.prepare('UPDATE players SET free_vmoney=13579 WHERE id=?').run(ids[0]);
        db.prepare('UPDATE players SET free_vmoney=24680 WHERE id=?').run(ids[1]);
        db.close(); console.log('FIXTURE_IDS='+JSON.stringify(ids));
    `], env)
    assert.equal(setup.status, 0, message(setup))
    const ids = JSON.parse(setup.stdout.match(/FIXTURE_IDS=(\[[^\]]+\])/)?.[1] || 'null')
    assert.equal(ids.length, 2)
    fs.writeFileSync(path.join(data, 'active_account.json'), JSON.stringify({ timeOffset: -38793700413 }))
    const dbFile = path.join(data, 'wdfp_data.db')
    t.after(() => { fs.rmSync(directory, { recursive: true, force: true }) })
    return { directory, data, dbFile, env, ids }
}
function cli(action, env) { return run([command, action, '--project', root], env) }
function assertNoLocks(data) {
    assert.equal(fs.existsSync(path.join(maintenance, 'active.lock')), false)
    assert.equal(fs.existsSync(path.join(data, 'storage-maintenance.lock')), false)
}

test('full deployment CLI: real database schema, save transfer, repeat choices, and fault rollback', async t => {
    if (!cdn || !path.isAbsolute(cdn) || !fs.statSync(cdn).isDirectory())
        throw new Error('Set STARPOINT_TEST_CDN_DIR to the existing read-only native CDN directory')
    if (fs.existsSync(statePath) || fs.existsSync(path.join(maintenance, 'active.lock')))
        throw new Error('Candidate maintenance state is already in use; run this test only when no rehearsal owns it')
    const ownedDatabases = new Set()
    t.after(() => {
        if (!fs.existsSync(statePath)) return
        const state = JSON.parse(fs.readFileSync(statePath, 'utf8'))
        if (!ownedDatabases.has(state.database)) return
        for (const file of [path.join(maintenance, 'active.lock'), path.join(path.dirname(state.database), 'storage-maintenance.lock')]) {
            if (!fs.existsSync(file)) continue
            const lock = JSON.parse(fs.readFileSync(file, 'utf8'))
            if (lock.runId === state.runId && lock.database === state.database) fs.unlinkSync(file)
        }
        fs.unlinkSync(statePath)
        try { fs.rmdirSync(maintenance) } catch {}
    })
    const firstPort = await freePort()
    const ports = [firstPort, await freePort(new Set([firstPort]))]
    const good = createFixture(t, ports)
    ownedDatabases.add(good.dbFile)
    const before = cli('preview', good.env)
    assert.equal(before.status, 0, message(before))
    assert.match(before.stdout, /"ready": false/)
    assert.match(before.stdout, /"canApply": true/)
    const applied = run(['-e', `
        const guard=require('./out/lib/deployment-maintenance-guard');
        const fingerprint=guard.getDeploymentDatabaseFingerprintSync;
        let committed=false;
        guard.getDeploymentDatabaseFingerprintSync=(...args)=>{
            if(committed)throw Error('Unexpected full database scan after COMMIT');
            return fingerprint(...args);
        };
        require('./scripts/time-content-deployment.cjs').apply({project:process.cwd(),checkpoint:point=>{
            if(point!=='after-commit')return;
            committed=true;
            const Sqlite=require('better-sqlite3'); let contender,locked=false;
            try {
                contender=new Sqlite(${JSON.stringify(good.dbFile)},{fileMustExist:true,timeout:50});
                contender.prepare('UPDATE players SET free_vmoney=free_vmoney+777 WHERE id=?').run(${good.ids[0]});
            } catch(error) {
                if(!['SQLITE_BUSY','SQLITE_LOCKED'].includes(error.code))throw error;
                locked=true;
            } finally {if(contender?.open)contender.close()}
            if(!locked)throw Error('Exclusive database lock was released before the apply receipt');
            console.log('EXCLUSIVE_LOCK_HELD_AFTER_COMMIT');
        }}).then(state=>console.log(JSON.stringify(state,null,2)))
            .catch(error=>{console.error(error.message);process.exitCode=1});
    `], good.env)
    assert.equal(applied.status, 0, message(applied))
    assert.match(applied.stdout, /"phase": "applied"/)
    assert.match(applied.stdout, /EXCLUSIVE_LOCK_HELD_AFTER_COMMIT/)
    assert.equal(cli('verify', good.env).status, 0)
    const released = cli('release', good.env)
    assert.equal(released.status, 0, message(released))
    assertNoLocks(good.data)
    const db = new Sqlite(good.dbFile)
    try {
        assert.deepEqual(marker(db), ['content_box_exchange_deployment', 'content_operations_deployment', 'server_clock_state'])
        assert.equal(db.prepare('SELECT free_vmoney FROM players WHERE id=?').get(good.ids[0]).free_vmoney, 13579)
        assert.equal(db.prepare('SELECT count(*) AS n FROM content_operations_state').get().n, 9599)
        const snapshots = require('../out/data/snapshots/player-snapshot')
        const source = snapshots.createPlayerSaveSnapshotV2Sync(good.ids[0], db)
        assert.equal(source.data.tables.players.rows.length, 1)
        assert.equal(source.data.tables.content_box_exchange_deployment, undefined)
        const serverMarker = db.prepare('SELECT * FROM content_box_exchange_deployment').get()
        snapshots.restorePlayerSaveSnapshotV2Sync(source, good.ids[1], {}, db)
        assert.deepEqual(db.prepare('SELECT * FROM content_box_exchange_deployment').get(), serverMarker)
        assert.equal(db.prepare('SELECT free_vmoney FROM players WHERE id=?').get(good.ids[1]).free_vmoney, 13579)
        const { createContentOperationsStore } = require('../out/lib/content-operations')
        const store = createContentOperationsStore(db)
        store.setPublished('gacha:1', { published: true, expectedRevision: store.revision(), catalogDigest: store.digest,
            reason: 'synthetic operator decision after deployment' }, Date.now())
        const revision = store.revision()
        db.close()
        const repeated = run(['-e', `
            require('./out/lib/deployment-maintenance-guard').getDeploymentDatabaseFingerprintSync=()=>{
                throw Error('Unexpected full database scan on already-ready deployment');
            };
            require('./scripts/time-content-deployment.cjs').apply({project:process.cwd()})
                .then(state=>console.log(JSON.stringify(state,null,2)))
                .catch(error=>{console.error(error.message);process.exitCode=1});
        `], good.env)
        assert.equal(repeated.status, 0, message(repeated))
        assert.match(repeated.stdout, /"phase": "already-ready"/)
        assert.equal(cli('verify', good.env).status, 0)
        const reopened = new Sqlite(good.dbFile, { readonly: true, fileMustExist: true })
        try {
            assert.equal(reopened.prepare('SELECT revision FROM content_operations_meta WHERE id=1').get().revision, revision)
            assert.equal(createContentOperationsStore(reopened).state('gacha:1').published, true)
            assert.equal(reopened.prepare('SELECT free_vmoney FROM players WHERE id=?').get(good.ids[1]).free_vmoney, 13579)
        } finally { reopened.close() }
    } finally { if (db.open) db.close() }
    // A second fully initialized database exercises injected failure after clock planning.
    if (fs.existsSync(statePath)) fs.unlinkSync(statePath)
    const failed = createFixture(t, ports)
    ownedDatabases.add(failed.dbFile)
    const crash = run(['-e', `
        const guard=require('./out/lib/deployment-maintenance-guard');
        const fingerprint=guard.getDeploymentDatabaseFingerprintSync;
        const clock=require('./out/lib/server-clock-state'), activate=clock.activateRealServerClockMaintenanceSync;
        let afterClock=false;
        guard.getDeploymentDatabaseFingerprintSync=(...args)=>{
            if(afterClock)throw Error('Forbidden diagnostic database scan masked the original failure');
            return fingerprint(...args);
        };
        clock.activateRealServerClockMaintenanceSync=(...args)=>{
            const result=activate(...args); afterClock=true; return result;
        };
        require('./scripts/time-content-deployment.cjs').apply({project:process.cwd(),faultAt:'after-clock'})
            .catch(error=>{console.error(error.message);process.exitCode=1});
    `], failed.env)
    assert.equal(crash.status, 1, message(crash))
    assert.match(message(crash), /Injected failure after clock/)
    assert.doesNotMatch(message(crash), /Forbidden diagnostic database scan/)
    const failedState = JSON.parse(fs.readFileSync(statePath, 'utf8'))
    assert.equal(failedState.phase, 'failed')
    assert.equal(failedState.failedAt, 'prepared')
    assert.equal(failedState.error, 'Injected failure after clock')
    assert.equal(Object.hasOwn(failedState, 'failureFingerprint'), false)
    for (const file of [path.join(maintenance, 'active.lock'), path.join(failed.data, 'storage-maintenance.lock')])
        assert.equal(fs.existsSync(file), true, 'Failure must retain both maintenance locks')
    const failedDb = new Sqlite(failed.dbFile, { readonly: true, fileMustExist: true })
    try {
        assert.deepEqual(marker(failedDb), [])
        assert.equal(failedDb.prepare('SELECT count(*) AS n FROM content_operations_state').get().n, 0)
        assert.equal(failedDb.prepare('SELECT free_vmoney FROM players WHERE id=?').get(failed.ids[0]).free_vmoney, 13579)
    } finally { failedDb.close() }
    const failureRelease = cli('release', failed.env)
    assert.equal(failureRelease.status, 0, message(failureRelease))
    assertNoLocks(failed.data)
    if (fs.existsSync(statePath)) fs.unlinkSync(statePath)
    try { fs.rmdirSync(maintenance) } catch {}
})
