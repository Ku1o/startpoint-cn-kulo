'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), { createHash, randomUUID } = require('node:crypto')
const Database = require('better-sqlite3')
const { spawnSync } = require('node:child_process')
const out = process.env.STARPOINT_TEST_OUT_DIR
if (!out) {
    const ts = require('typescript')
    require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2016, esModuleInterop: true, resolveJsonModule: true },
    }).outputText, filename)
}
const load = name => require(out ? path.join(out, `${name}.js`) : path.resolve(__dirname, `../src/${name}.ts`))
const guardCore = load('lib/deployment-maintenance-guard'), core = load('lib/server-clock-state'), rehearsal = load('lib/time-cutover-rehearsal'), utils = load('utils')
const options = { cutoverRealMs: Date.parse('2026-10-24T01:00:00Z'), legacyOffsetMs: -420 * 86400000 }
const fingerprint = guardCore.getDeploymentDatabaseFingerprintSync
function fixture(t) {
    const parent = process.env.SERVER_CLOCK_TEST_ROOT || os.tmpdir()
    fs.mkdirSync(parent, { recursive: true })
    const directory = fs.mkdtempSync(path.join(parent, 'clock-maintenance-'))
    const data = path.join(directory, '.database'); fs.mkdirSync(data)
    const db = new Database(path.join(data, 'synthetic.db'), { timeout: 30 })
    db.pragma('journal_mode=WAL')
    db.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY, exp_pool INTEGER, exp_pooled_time, time_offset, vmoney INTEGER);
        CREATE TABLE players_active_quests(player_id INTEGER PRIMARY KEY,play_id TEXT,started_at_ms INTEGER,clock_version INTEGER);
        CREATE TABLE progress(player_id INTEGER, claimed INTEGER, balance INTEGER);
        CREATE TABLE player_time_state(player_id INTEGER PRIMARY KEY REFERENCES players(id),version INTEGER,cutover_real_ms INTEGER,day_anchor_ms INTEGER,week_anchor_ms INTEGER);
        CREATE TABLE other_ledger(value INTEGER);
        INSERT INTO other_ledger VALUES(9007199254740993);
        INSERT INTO progress VALUES(1,7,123),(2,8,456);
        INSERT INTO players VALUES(1,777,NULL,NULL,99),(2,888,NULL,NULL,88),(3,999,'old existing',91,77);
        INSERT INTO player_time_state VALUES(3,1,1750000000000,1750000000000,1750000000000)`)
    db.prepare('UPDATE players SET exp_pooled_time=?,time_offset=? WHERE id=1').run(new Date(options.cutoverRealMs + options.legacyOffsetMs - 60000).toISOString(), options.legacyOffsetMs)
    db.prepare('INSERT INTO players_active_quests VALUES(1,?,?,0)').run('retained-legacy-play', options.cutoverRealMs + options.legacyOffsetMs - 30000)
    db.prepare('INSERT INTO players_active_quests VALUES(2,?,?,1)').run('retained-real-play', options.cutoverRealMs - 30000)
    t.after(() => { if (db.open) db.close() })
    return { db, directory }
}
async function backup(db, directory) {
    const file = path.join(directory, `backup-${randomUUID()}.db`)
    await db.backup(file)
    return { kind: 'approved-stopped-database', databasePath: fs.realpathSync(db.name), backupPath: fs.realpathSync(file),
        expectedDatabaseFingerprint: fingerprint(db), expectedBackupSha256: createHash('sha256').update(fs.readFileSync(file)).digest('hex') }
}
function apply(db, context, extra = {}) {
    const plan = core.planRealServerClockMaintenanceSync(db, options, context)
    const state = core.activateRealServerClockMaintenanceSync(db, { ...options, expectedPlanDigest: plan.digest, ...extra }, context)
    return { state, plan }
}
function noWrites(db, operation, pattern) {
    const before = fingerprint(db)
    assert.throws(operation, pattern)
    assert.equal(fingerprint(db), before)
}

test('explicit backed-up maintenance atomically initializes content then clock, preserving nonempty rights and old plays', async t => {
    const { db, directory } = fixture(t), approval = await backup(db, directory)
    const beforeProcessClock = utils.getServerClockSnapshot(), progress = db.prepare('SELECT * FROM progress').all()
    const plays = db.prepare('SELECT * FROM players_active_quests').all(), marker = db.prepare('SELECT * FROM player_time_state').get()
    const result = guardCore.withDeploymentMaintenanceTransactionSync(db, approval, context => {
        assert.equal(db.inTransaction, true)
        db.exec("CREATE TABLE content_state(key TEXT PRIMARY KEY,enabled INTEGER); INSERT INTO content_state VALUES('preserved-season',1)")
        return apply(db, context)
    })
    assert.equal(result.state.readiness, 'maintenance-approved')
    assert.deepEqual(core.readServerClockStateSync(db), result.state)
    assert.deepEqual(utils.getServerClockSnapshot(), beforeProcessClock, 'migration never changes the running process clock')
    assert.deepEqual(db.prepare('SELECT * FROM progress').all(), progress)
    assert.deepEqual(db.prepare('SELECT * FROM players_active_quests').all(), plays)
    assert.deepEqual(db.prepare('SELECT * FROM player_time_state WHERE player_id=3').get(), marker)
    assert.deepEqual(db.prepare('SELECT exp_pool,vmoney FROM players WHERE id=1').get(), { exp_pool: 777, vmoney: 99 })
    assert.equal(db.prepare('SELECT exp_pooled_time FROM players WHERE id=1').get().exp_pooled_time, new Date(options.cutoverRealMs - 60000).toISOString())
    assert.equal(db.prepare('SELECT exp_pooled_time FROM players WHERE id=2').get().exp_pooled_time, new Date(options.cutoverRealMs).toISOString())
    assert.equal(db.prepare('SELECT value FROM other_ledger').safeIntegers().get().value, 9007199254740993n)
    const repeatApproval = await backup(db, directory), beforeRepeat = fingerprint(db)
    guardCore.withDeploymentMaintenanceTransactionSync(db, repeatApproval, context => {
        assert.deepEqual(core.activateRealServerClockMaintenanceSync(db, { ...options, expectedPlanDigest: result.plan.digest }, context), result.state)
    })
    assert.equal(fingerprint(db), beforeRepeat)
    noWrites(db, () => core.activateRealServerClockOfflineSync(db, { ...options, readiness: 'scenario-only', expectedPlanDigest: result.plan.digest,
        offlineGuard: { kind: 'approved-offline-file', databasePath: db.name, allowedRoot: directory } }), /outside approved offline scope/)
})

test('every activation fault and a late content-stage error roll back both stages and all receipts', async t => {
    for (const faultAt of ['after-player-migration', 'after-clock-state', 'after-activation-receipt', 'after-both-stages']) {
        const { db, directory } = fixture(t), approval = await backup(db, directory)
        noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, approval, context => {
            db.exec('CREATE TABLE content_state(value INTEGER); INSERT INTO content_state VALUES(10)')
            apply(db, context, { faultAt })
            if (faultAt === 'after-both-stages') throw Error('Injected final content-stage failure')
        }), /Injected/)
        assert.equal(core.readServerClockStateSync(db), null)
        assert.equal(db.prepare("SELECT 1 FROM sqlite_master WHERE name='content_state'").get(), undefined)
    }
})

test('backup/hash/state/path mismatches, attached DBs and temp shadows cannot begin maintenance', async t => {
    const { db, directory } = fixture(t), approval = await backup(db, directory)
    for (const patch of [{ expectedBackupSha256: '0'.repeat(64) }, { expectedDatabaseFingerprint: '0'.repeat(64) },
        { databasePath: approval.backupPath }, { backupPath: db.name }, { databasePath: 'relative.db' }]) {
        noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, { ...approval, ...patch }, () => assert.fail('must not run')))
    }
    db.exec("ATTACH ':memory:' AS other")
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, approval, () => assert.fail('must not run')), /attached/)
    db.exec('DETACH other; CREATE TEMP TABLE players(id INTEGER)')
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, approval, () => assert.fail('must not run')), /shadows/)
    db.exec('DROP TABLE temp.players; UPDATE progress SET balance=balance+1 WHERE player_id=1')
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, approval, () => assert.fail('must not run')), /target changed before exclusive lock/)
})

test('maintenance scans the target once and only after taking the exclusive transaction', async t => {
    const { db, directory } = fixture(t), approval = await backup(db, directory)
    const prepare = db.prepare, scans = []
    db.prepare = function (sql, ...args) {
        if (sql.startsWith('SELECT type,name,tbl_name,sql FROM main.sqlite_master')) scans.push(this.inTransaction)
        return prepare.call(this, sql, ...args)
    }
    try {
        guardCore.withDeploymentMaintenanceTransactionSync(db, approval, context => {
            guardCore.assertDeploymentMaintenanceContextSync(db, context)
        })
        assert.deepEqual(scans, [true], 'the target must be read once under its write lock')
    } finally { db.prepare = prepare }
})

test('WAL contents require a standalone SQLite backup and a hard-link/alias cannot authorize a target', async t => {
    const { db, directory } = fixture(t), approval = await backup(db, directory)
    fs.writeFileSync(approval.backupPath + '-wal', 'nonempty journal state is not covered by the backup hash')
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, approval, () => assert.fail('must not run')), /standalone/)
    fs.unlinkSync(approval.backupPath + '-wal')
    const aliasDirectory = path.join(directory, 'alias')
    fs.symlinkSync(path.dirname(db.name), aliasDirectory, process.platform === 'win32' ? 'junction' : 'dir')
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, { ...approval, databasePath: path.join(aliasDirectory, path.basename(db.name)) }, () => {}), /aliased/)
    const link = path.join(directory, 'hardlink.db'); fs.linkSync(db.name, link)
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, approval, () => {}), /hard-linked/)
    fs.unlinkSync(link)
})

test('opaque stage context rejects fabricated, foreign, expired and outside-transaction uses; planner rejects a stale post-content plan', async t => {
    const { db, directory } = fixture(t), approval = await backup(db, directory)
    noWrites(db, () => core.planRealServerClockMaintenanceSync(db, options, { kind: 'deployment-maintenance-transaction' }), /context required/)
    const other = new Database(':memory:'); t.after(() => other.close())
    let captured
    guardCore.withDeploymentMaintenanceTransactionSync(db, approval, context => {
        captured = context
        assert.throws(() => guardCore.assertDeploymentMaintenanceContextSync(other, context), /context required/)
    })
    noWrites(db, () => db.transaction(() => core.planRealServerClockMaintenanceSync(db, options, captured))(), /context required/)
    const next = await backup(db, directory)
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, next, context => {
        const plan = core.planRealServerClockMaintenanceSync(db, options, context)
        db.exec('UPDATE progress SET claimed=claimed+1 WHERE player_id=1')
        core.activateRealServerClockMaintenanceSync(db, { ...options, expectedPlanDigest: plan.digest }, context)
    }), /plan digest mismatch/)
})

test('concurrent SQLite writer prevents maintenance; no stage executes without the exclusive lock', async t => {
    const { db, directory } = fixture(t), approval = await backup(db, directory)
    const competing = new Database(db.name, { timeout: 30 }); t.after(() => competing.close())
    competing.exec('BEGIN IMMEDIATE')
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, approval, () => assert.fail('must not run')), /locked/)
    competing.exec('ROLLBACK')
    guardCore.withDeploymentMaintenanceTransactionSync(db, approval, context => apply(db, context))
})

test('safe rollback reverses only untouched activation; new progress and rollback faults preserve all facts', async t => {
    const { db, directory } = fixture(t), approval = await backup(db, directory)
    const before = core.getServerClockPersistentFingerprintSync(db)
    const { plan } = guardCore.withDeploymentMaintenanceTransactionSync(db, approval, context => apply(db, context))
    for (const faultAt of ['after-player-restore', 'after-clock-restore', 'after-rollback-receipt']) {
        const rollbackApproval = await backup(db, directory)
        noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, rollbackApproval, context => {
            core.rollbackRealServerClockMaintenanceSync(db, { expectedPlanDigest: plan.digest, faultAt }, context)
        }), /Injected/)
    }
    db.exec('UPDATE progress SET balance=balance+1 WHERE player_id=1')
    const changedApproval = await backup(db, directory)
    noWrites(db, () => guardCore.withDeploymentMaintenanceTransactionSync(db, changedApproval, context => {
        core.rollbackRealServerClockMaintenanceSync(db, { expectedPlanDigest: plan.digest }, context)
    }), /persistent state changed/)
    db.exec('UPDATE progress SET balance=balance-1 WHERE player_id=1')
    const rollbackApproval = await backup(db, directory)
    assert.equal(guardCore.withDeploymentMaintenanceTransactionSync(db, rollbackApproval, context => {
        return core.rollbackRealServerClockMaintenanceSync(db, { expectedPlanDigest: plan.digest }, context)
    }).status, 'rolled-back')
    assert.equal(core.getServerClockPersistentFingerprintSync(db), before)
    const repeatApproval = await backup(db, directory)
    assert.equal(guardCore.withDeploymentMaintenanceTransactionSync(db, repeatApproval, context => {
        return core.rollbackRealServerClockMaintenanceSync(db, { expectedPlanDigest: plan.digest }, context)
    }).status, 'already-rolled-back')
})

test('maintenance reads old scenario states without promoting them and fingerprints adjacent SQLite INTEGER facts exactly', async t => {
    const db = new Database(':memory:'); t.after(() => db.close())
    db.exec('CREATE TABLE players(id INTEGER PRIMARY KEY,exp_pool INTEGER,exp_pooled_time,time_offset); INSERT INTO players VALUES(1,7,NULL,NULL)')
    const plan = rehearsal.planTimeCutoverRehearsalSync(db, options)
    const state = core.activateRealServerClockOfflineSync(db, { ...options, readiness: 'scenario-only', expectedPlanDigest: plan.digest })
    assert.equal(core.readServerClockStateSync(db).readiness, 'scenario-only')
    assert.deepEqual(core.readServerClockStateSync(db), state)
    const { db: file } = fixture(t), first = fingerprint(file)
    file.exec('UPDATE other_ledger SET value=9007199254740992')
    assert.notEqual(fingerprint(file), first)
})

test('abrupt process exit before outer commit recovers the exact original WAL state; committed maintenance restores in a fresh process', async t => {
    const { db, directory } = fixture(t), approval = await backup(db, directory), before = fingerprint(db)
    const modulePath = name => out ? path.join(out, `${name}.js`) : path.resolve(__dirname, `../src/${name}.ts`)
    const prelude = `${out ? '' : "require('ts-node/register/transpile-only');"}
        const Database=require('better-sqlite3'), assert=require('node:assert/strict');
        const core=require(${JSON.stringify(modulePath('lib/server-clock-state'))});
        const guard=require(${JSON.stringify(modulePath('lib/deployment-maintenance-guard'))});`
    const crashed = spawnSync(process.execPath, ['-e', prelude + `
        const db=new Database(${JSON.stringify(db.name)});
        guard.withDeploymentMaintenanceTransactionSync(db,${JSON.stringify(approval)},context=>{
            db.exec('CREATE TABLE crashed_content(value INTEGER); INSERT INTO crashed_content VALUES(9)');
            const options=${JSON.stringify(options)};
            const plan=core.planRealServerClockMaintenanceSync(db,options,context);
            core.activateRealServerClockMaintenanceSync(db,{...options,expectedPlanDigest:plan.digest},context);
            process.exit(13);
        });`], { cwd: path.resolve(__dirname, '..'), env: { ...process.env, DATA_DIR: directory }, encoding: 'utf8', windowsHide: true, timeout: 30000 })
    assert.equal(crashed.status, 13, crashed.stdout + crashed.stderr)
    assert.equal(fingerprint(db), before)
    assert.equal(db.pragma('quick_check', { simple: true }), 'ok')
    const current = await backup(db, directory)
    const { state } = guardCore.withDeploymentMaintenanceTransactionSync(db, current, context => apply(db, context))
    const restored = spawnSync(process.execPath, ['-e', prelude + `
        const utils=require(${JSON.stringify(modulePath('utils'))});
        const db=new Database(${JSON.stringify(db.name)},{readonly:true,fileMustExist:true});
        const actual=core.restoreServerClockStateSync(db);
        assert.deepEqual(actual,${JSON.stringify(state)});
        assert.equal(utils.getServerClockSnapshot().mode,'real');
        assert.equal(utils.getConfiguredBusinessTimeOffset(),0);
        assert.equal(utils.getLegacyTimeOffset(),${options.legacyOffsetMs});
        assert.ok(Math.abs(utils.getServerDate().getTime()-Date.now())<2000);
        db.close();`], { cwd: path.resolve(__dirname, '..'), env: { ...process.env, DATA_DIR: directory }, encoding: 'utf8', windowsHide: true, timeout: 30000 })
    assert.equal(restored.status, 0, restored.stdout + restored.stderr)
})
