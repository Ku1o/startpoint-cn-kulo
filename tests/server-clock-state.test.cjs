'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { spawnSync } = require('node:child_process')
const Database = require('better-sqlite3')
const out = process.env.STARPOINT_TEST_OUT_DIR
if (!out) {
    const ts = require('typescript')
    require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2016, esModuleInterop: true, resolveJsonModule: true },
    }).outputText, filename)
}
const load = name => require(out ? path.join(out, `${name}.js`) : path.resolve(__dirname, `../src/${name}.ts`))
const core = load('lib/server-clock-state')
const rehearsal = load('lib/time-cutover-rehearsal')
const utils = load('utils')
const cutoverRealMs = Date.parse('2026-10-13T03:15:00Z')
const legacyOffsetMs = -420 * 86400_000
const options = { cutoverRealMs, legacyOffsetMs, readiness: 'scenario-only' }
function fixture(t, filename = ':memory:') {
    const db = new Database(filename)
    t.after(() => { if (db.open) db.close() })
    db.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY,exp_pool INTEGER,exp_pooled_time,time_offset,
        vmoney INTEGER,last_login_time TEXT,total_login_days INTEGER);
        CREATE TABLE players_active_quests(player_id INTEGER PRIMARY KEY,play_id TEXT,started_at_ms INTEGER,clock_version INTEGER);
        CREATE TABLE progress(player_id INTEGER,claimed INTEGER,counter INTEGER);`)
    db.prepare('INSERT INTO players VALUES(?,?,?,?,?,?,?)').run(1, 12345, new Date(cutoverRealMs + legacyOffsetMs - 30000).toISOString(), legacyOffsetMs, 9200, '2024-08-14T12:00:00Z', 42)
    db.prepare('INSERT INTO players VALUES(?,?,?,?,?,?,?)').run(2, 5678, '2024-08-14T12:00:00Z', null, 900, '2024-08-14T12:00:00Z', 9)
    db.prepare('INSERT INTO players_active_quests VALUES(?,?,?,?)').run(1, 'legacy-play', cutoverRealMs + legacyOffsetMs - 12000, 0)
    db.prepare('INSERT INTO players_active_quests VALUES(?,?,?,?)').run(2, 'real-play', cutoverRealMs - 12000, 1)
    db.exec('INSERT INTO progress VALUES(1,1,300),(2,1,12)')
    return db
}
function activate(db, extra = {}) {
    const plan = rehearsal.planTimeCutoverRehearsalSync(db, { ...options, ...extra })
    return core.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: plan.digest, ...extra })
}
function child(t, payload) {
    const root = process.env.STARPOINT_CLOCK_TEST_ROOT || os.tmpdir()
    fs.mkdirSync(root, { recursive: true })
    const dir = fs.mkdtempSync(path.join(root, 'clock-state-'))
    const result = spawnSync(process.execPath, [...process.execArgv, __filename, '--clock-state-child', JSON.stringify(payload)], {
        cwd: process.cwd(), env: { ...process.env, DATA_DIR: dir, STARPOINT_CLOCK_TEST_CHILD: '1' }, encoding: 'utf8',
    })
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
    // Preserve the bounded synthetic artifacts in the task scratch root for review.
    return dir
}
function verifyLazyMigration(t) {
    const db = fixture(t)
    activate(db)
    assert.throws(() => db.transaction(() => core.ensurePlayerClockStateForLoadSync(1, db))(), /differs from committed/)
    core.restoreServerClockStateSync(db)
    db.prepare('INSERT INTO players VALUES(?,?,?,?,?,?,?)').run(3, 777, new Date(cutoverRealMs + legacyOffsetMs - 123000).toISOString(), legacyOffsetMs, 6, '2024-01-01', 20)
    db.prepare('INSERT INTO players VALUES(?,?,?,?,?,?,?)').run(4, 888, null, null, 7, '2024-01-01', 30)
    assert.throws(() => core.ensurePlayerClockStateForLoadSync(3, db), /existing load transaction/)
    db.transaction(() => {
        const old = db.prepare('SELECT * FROM player_time_state WHERE player_id=1').get()
        core.ensurePlayerClockStateForLoadSync(1, db)
        assert.deepEqual(db.prepare('SELECT * FROM player_time_state WHERE player_id=1').get(), old)
        for (const id of [3, 4]) {
            const state = core.ensurePlayerClockStateForLoadSync(id, db)
            assert.equal(state.cutoverRealMs, cutoverRealMs)
            assert.equal(state.dayAnchorMs, cutoverRealMs)
            assert.equal(state.weekAnchorMs, cutoverRealMs)
        }
    })()
    assert.equal(db.prepare('SELECT exp_pooled_time FROM players WHERE id=3').get().exp_pooled_time, new Date(cutoverRealMs - 123000).toISOString())
    assert.equal(db.prepare('SELECT exp_pooled_time FROM players WHERE id=4').get().exp_pooled_time, new Date(cutoverRealMs).toISOString())
    assert.deepEqual(db.prepare('SELECT exp_pool,vmoney,total_login_days FROM players WHERE id=3').get(), { exp_pool: 777, vmoney: 6, total_login_days: 20 })
    db.prepare('INSERT INTO players VALUES(?,?,?,?,?,?,?)').run(5, 1, null, null, 2, 'old', 3)
    const before = rehearsal.getTimeCutoverDatabaseDigestSync(db)
    assert.throws(() => db.transaction(() => { core.ensurePlayerClockStateForLoadSync(5, db); throw Error('load rollback') })(), /load rollback/)
    assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(db), before)
    const empty = new Database(':memory:')
    assert.throws(() => core.ensurePlayerClockStateForLoadSync(1, empty), /no committed global/)
    empty.close()
    db.close()
}
function verifyDefaultDegreesTrigger(mode) {
    const db = fixture({ after() {} })
    activate(db)
    core.restoreServerClockStateSync(db)
    db.exec(`ALTER TABLE players ADD COLUMN degree_id INTEGER NOT NULL DEFAULT 0;
        CREATE TABLE players_degrees(player_id INTEGER NOT NULL,degree_id INTEGER NOT NULL,acquired_at INTEGER NOT NULL,
            PRIMARY KEY(player_id,degree_id),FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE)`)
    // Exercise the actual initialized SQL, including SQLite's stored canonical
    // CREATE TRIGGER (IF NOT EXISTS is removed by SQLite itself).
    const initializer = fs.readFileSync(path.resolve(__dirname, '../src/data/initializers/wdfpData.ts'), 'utf8')
    const start = initializer.indexOf('CREATE TRIGGER IF NOT EXISTS trg_players_default_degrees')
    assert.ok(start >= 0)
    const end = initializer.indexOf('`).run();', start)
    assert.ok(end > start)
    let sql = initializer.slice(start, end)
    if (mode === 'same-name-update') sql = sql.replace('AFTER INSERT ON players', 'AFTER UPDATE ON players')
    if (mode === 'same-name-body') sql = sql.replace('WHERE NEW.degree_id > 0;', 'WHERE NEW.degree_id > 0; UPDATE players SET exp_pool=exp_pool+1 WHERE id=NEW.id;')
    db.exec(sql)
    db.prepare('INSERT INTO players(id,exp_pool,exp_pooled_time,time_offset,vmoney,last_login_time,total_login_days,degree_id) VALUES(?,?,?,?,?,?,?,?)')
        .run(3, 777, new Date(cutoverRealMs + legacyOffsetMs - 123000).toISOString(), legacyOffsetMs, 6, '2024-01-01', 20, 7)
    if (mode === 'other-update') db.exec('CREATE TRIGGER other_player_update AFTER UPDATE ON players BEGIN UPDATE players SET exp_pool=0 WHERE id=NEW.id; END')
    if (mode === 'marker-insert') db.exec('CREATE TRIGGER marker_extra AFTER INSERT ON player_time_state BEGIN UPDATE players SET vmoney=0 WHERE id=NEW.player_id; END')
    const degrees = db.prepare('SELECT * FROM players_degrees ORDER BY player_id,degree_id').all()
    const player = db.prepare('SELECT exp_pool,vmoney,last_login_time,total_login_days,degree_id FROM players WHERE id=3').get()
    if (mode === 'original') {
        assert.deepEqual(degrees, [{ player_id: 3, degree_id: 1, acquired_at: 0 }, { player_id: 3, degree_id: 7, acquired_at: 0 }])
        db.transaction(() => core.ensurePlayerClockStateForLoadSync(3, db))()
        assert.equal(db.prepare('SELECT exp_pooled_time FROM players WHERE id=3').get().exp_pooled_time, new Date(cutoverRealMs - 123000).toISOString())
        assert.equal(db.prepare('SELECT time_offset FROM players WHERE id=3').get().time_offset, 0)
    } else {
        const before = rehearsal.getTimeCutoverDatabaseDigestSync(db)
        assert.throws(() => db.transaction(() => core.ensurePlayerClockStateForLoadSync(3, db))(), /triggers are forbidden/)
        assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(db), before)
    }
    assert.deepEqual(db.prepare('SELECT * FROM players_degrees ORDER BY player_id,degree_id').all(), degrees)
    assert.deepEqual(db.prepare('SELECT exp_pool,vmoney,last_login_time,total_login_days,degree_id FROM players WHERE id=3').get(), player)
    db.close()
}

if (process.argv.includes('--clock-state-child')) {
    const payload = JSON.parse(process.argv[process.argv.indexOf('--clock-state-child') + 1])
    if (payload.kind === 'restore') {
        const db = new Database(payload.file, { readonly: true })
        const file = path.join(process.env.DATA_DIR, 'active_account.json')
        fs.writeFileSync(file, JSON.stringify({ timeOffset: null, activePlayerId: 9, defaultPlayers: { 7: 9 } }))
        const before = fs.readFileSync(file)
        for (let i = 0; i < 10; i++) utils.setServerTimeOffset(i)
        load('data/activeAccount').restoreTimeOffset(db)
        assert.deepEqual(utils.getServerClockSnapshot(), payload.snapshot)
        assert.equal(utils.getConfiguredBusinessTimeOffset(), 0)
        assert.equal(utils.getLegacyTimeOffset(), payload.snapshot.legacyBattleOffsetMs)
        assert.ok(Math.abs(utils.getServerDate().getTime() - Date.now()) < 100)
        assert.ok(Math.abs(load('lib/battle-clock-compatibility').getBattleClockDate(0).getTime() - Date.now()
            - (payload.snapshot.legacyBattleOffsetMs ?? 0)) < 100)
        utils.withServerClock(cutoverRealMs + 123, () => {
            assert.equal(utils.getTimeOffset(), 123)
            assert.equal(utils.getConfiguredBusinessTimeOffset(), 0)
            assert.equal(utils.getLegacyTimeOffset(), payload.snapshot.legacyBattleOffsetMs)
        }, 123)
        for (const action of [() => utils.setServerTime(null), () => utils.setServerTimeOffset(null),
            () => load('data/activeAccount').saveTimeOffset(1)]) assert.throws(action, /rejects virtual-time reset/)
        assert.deepEqual(fs.readFileSync(file), before)
        db.close()
    } else if (payload.kind === 'legacy-null') {
        const db = new Database(':memory:')
        fs.writeFileSync(path.join(process.env.DATA_DIR, 'active_account.json'), JSON.stringify({ timeOffset: null }))
        load('data/activeAccount').restoreTimeOffset(db)
        assert.equal(utils.getServerClockSnapshot().mode, 'legacy')
        assert.ok(Math.abs(utils.getServerDate().getTime() - Date.parse('2024-08-14T12:00:00Z')) < 100)
        assert.equal(core.readServerClockStateSync(db), null)
        db.close()
    } else if (payload.kind === 'lazy') {
        verifyLazyMigration({ after() {} })
    } else if (payload.kind === 'degrees-trigger') {
        verifyDefaultDegreesTrigger(payload.mode)
    } else if (payload.kind === 'corrupt-startup') {
        const db = new Database(payload.file, { readonly: true })
        const before = utils.getServerClockSnapshot()
        assert.throws(() => load('data/activeAccount').restoreTimeOffset(db), /clock/i)
        assert.deepEqual(utils.getServerClockSnapshot(), before)
        assert.equal(fs.existsSync(path.join(process.env.DATA_DIR, 'active_account.json')), false)
        db.close()
    }
} else {
test('atomic activation preserves balances/progress, registrations and existing v1 anchors', t => {
    const db = fixture(t)
    db.exec('CREATE TABLE player_time_state(player_id INTEGER PRIMARY KEY,version INTEGER,cutover_real_ms INTEGER,day_anchor_ms INTEGER,week_anchor_ms INTEGER)')
    db.prepare('INSERT INTO player_time_state VALUES(?,1,?,?,?)').run(1, cutoverRealMs - 300000, cutoverRealMs - 200000, cutoverRealMs - 100000)
    const player = db.prepare('SELECT * FROM players WHERE id=1').get()
    const anchors = db.prepare('SELECT * FROM player_time_state WHERE player_id=1').get()
    const plays = db.prepare('SELECT * FROM players_active_quests').all()
    const progress = db.prepare('SELECT * FROM progress').all()
    const beforeProcess = utils.getServerClockSnapshot()
    const committed = activate(db)
    assert.equal(committed.readiness, 'scenario-only')
    assert.equal(committed.snapshot.businessOffsetMs, 0)
    assert.equal(committed.snapshot.legacyBattleOffsetMs, legacyOffsetMs)
    assert.deepEqual(utils.getServerClockSnapshot(), beforeProcess, 'offline activation never installs process state')
    assert.deepEqual(db.prepare('SELECT * FROM players WHERE id=1').get(), player)
    assert.deepEqual(db.prepare('SELECT * FROM player_time_state WHERE player_id=1').get(), anchors)
    assert.deepEqual(db.prepare('SELECT * FROM players_active_quests').all(), plays)
    assert.deepEqual(db.prepare('SELECT * FROM progress').all(), progress)
    assert.deepEqual(db.prepare('SELECT exp_pool,vmoney,total_login_days FROM players WHERE id=2').get(), { exp_pool: 5678, vmoney: 900, total_login_days: 9 })
    assert.equal(db.prepare('SELECT exp_pooled_time FROM players WHERE id=2').get().exp_pooled_time, new Date(cutoverRealMs).toISOString())
    db.exec('INSERT INTO progress VALUES(3,1,999)')
    const afterProgress = rehearsal.getTimeCutoverDatabaseDigestSync(db)
    assert.deepEqual(core.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: committed.planDigest }), committed)
    assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(db), afterProgress)
    assert.throws(() => core.activateRealServerClockOfflineSync(db, { ...options, cutoverRealMs: cutoverRealMs + 1, expectedPlanDigest: committed.planDigest }), /conflict/)
})

test('both activation fault boundaries roll back original schema and data', t => {
    for (const faultAt of ['after-player-migration', 'after-clock-state']) {
        const db = fixture(t)
        const before = rehearsal.getTimeCutoverDatabaseDigestSync(db)
        assert.throws(() => activate(db, { faultAt }), /Injected/)
        assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(db), before)
        assert.equal(core.readServerClockStateSync(db), null)
        assert.equal(db.prepare("SELECT 1 FROM sqlite_master WHERE name='player_time_state'").get(), undefined)
    }
})

test('player-trigger mutations of unrelated progress refuse activation and roll back', t => {
    const db = fixture(t)
    db.exec('CREATE TRIGGER player_progress AFTER UPDATE ON players BEGIN UPDATE progress SET counter=counter+1; END')
    const before = rehearsal.getTimeCutoverDatabaseDigestSync(db)
    assert.throws(() => activate(db), /unrelated persistent state/)
    assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(db), before)
})

test('later player trigger cannot change an earlier planned target field', t => {
    const db = fixture(t)
    db.exec("CREATE TRIGGER player_cross_clock AFTER UPDATE ON players WHEN NEW.id=2 BEGIN UPDATE players SET exp_pooled_time='2024-01-01T00:00:00Z' WHERE id=1; END")
    const before = rehearsal.getTimeCutoverDatabaseDigestSync(db)
    assert.throws(() => activate(db), /fields did not match plan/)
    assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(db), before)
})

test('invalid offsets/epochs/digests and production-ready activation are rejected before writes', t => {
    const db = fixture(t)
    const plan = rehearsal.planTimeCutoverRehearsalSync(db, options)
    for (const extra of [{ legacyOffsetMs: NaN }, { legacyOffsetMs: 1.5 }, { cutoverRealMs: -1 },
        { cutoverRealMs: Number.MAX_SAFE_INTEGER }, { legacyOffsetMs: 8640000000000000 },
        { expectedPlanDigest: 'bad' }, { readiness: 'production-ready' }]) {
        const before = rehearsal.getTimeCutoverDatabaseDigestSync(db)
        assert.throws(() => core.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: plan.digest, ...extra }))
        assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(db), before)
    }
    db.exec('UPDATE progress SET counter=counter+1')
    assert.throws(() => core.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: plan.digest }), /digest mismatch/)
})

test('persisted schema/row/version/revision/cutover/unsafe integers fail closed without partial install', t => {
    const mutations = ["DELETE FROM server_clock_state", "UPDATE server_clock_state SET revision=0", "UPDATE server_clock_state SET cutover_real_ms=-1",
        "UPDATE server_clock_state SET week_anchor_ms=cutover_real_ms-1", "UPDATE server_clock_state SET revision=9007199254740993",
        "UPDATE server_clock_state SET legacy_battle_offset_ms=1.5", "UPDATE server_clock_state SET legacy_battle_offset_ms=8640000000000000",
        "ALTER TABLE server_clock_state ADD COLUMN extra INTEGER",
        "CREATE TRIGGER clock_trigger AFTER UPDATE ON server_clock_state BEGIN SELECT 1; END",
        "PRAGMA ignore_check_constraints=ON; UPDATE server_clock_state SET version=2",
        "PRAGMA ignore_check_constraints=ON; UPDATE server_clock_state SET readiness='production-ready'"]
    for (const sql of mutations) {
        const db = fixture(t)
        activate(db)
        db.exec(sql)
        const before = utils.getServerClockSnapshot()
        assert.throws(() => core.restoreServerClockStateSync(db), /clock/i)
        assert.deepEqual(utils.getServerClockSnapshot(), before)
    }
})

test('lazy migration requires load transaction, uses global anchors and preserves existing v1', t => {
    child(t, { kind: 'lazy' })
})

test('official INSERT-only default degrees trigger allows lazy migration without changing degrees or balances', t => {
    child(t, { kind: 'degrees-trigger', mode: 'original' })
})

test('same-name UPDATE/extra-body and other UPDATE/marker INSERT triggers fail closed before lazy writes', t => {
    for (const mode of ['same-name-update', 'same-name-body', 'other-update', 'marker-insert']) {
        child(t, { kind: 'degrees-trigger', mode })
    }
})

test('no global state keeps legacy null/marker behavior and does not create schema', t => {
    const db = fixture(t)
    const before = rehearsal.getTimeCutoverDatabaseDigestSync(db)
    assert.equal(core.readServerClockStateSync(db), null)
    assert.equal(core.restoreServerClockStateSync(db), null)
    assert.equal(core.ensurePlayerClockStateForLoadSync(1, db), null)
    assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(db), before)
    child(t, { kind: 'legacy-null' })
})

test('fresh process real restore overrides null legacy file and holds independent legacy offset, including null', t => {
    const root = process.env.STARPOINT_CLOCK_TEST_ROOT || os.tmpdir()
    fs.mkdirSync(root, { recursive: true })
    for (const offset of [legacyOffsetMs, null]) {
        const dir = fs.mkdtempSync(path.join(root, 'clock-restart-'))
        const file = path.join(dir, 'synthetic.sqlite')
        const db = fixture(t, file)
        const offlineGuard = { kind: 'approved-offline-file', databasePath: file, allowedRoot: dir }
        const state = activate(db, { legacyOffsetMs: offset, offlineGuard })
        const digest = rehearsal.getTimeCutoverDatabaseDigestSync(db)
        db.close()
        child(t, { kind: 'restore', file, snapshot: state.snapshot })
        const reopened = new Database(file)
        assert.equal(rehearsal.getTimeCutoverDatabaseDigestSync(reopened), digest, 'startup is read-only')
        reopened.exec('UPDATE server_clock_state SET revision=0')
        reopened.close()
        child(t, { kind: 'corrupt-startup', file })
    }
})

test('strict complete snapshot validation never publishes partial state; configured offset ignores ALS', () => {
    utils.setServerTimeOffset(500)
    let oldUpdates = 0, fullUpdates = 0
    const removeOld = utils.onServerTimeOffsetChanged(() => oldUpdates++)
    const removeFull = utils.onServerClockSnapshotChanged(() => fullUpdates++)
    const before = utils.getServerClockSnapshot()
    for (const patch of [{ version: 2 }, { revision: 1.5 }, { mode: 'real' }, { businessOffsetMs: NaN }, { unexpected: true }]) {
        assert.throws(() => utils.installServerClockSnapshot({ ...before, ...patch }))
        assert.deepEqual(utils.getServerClockSnapshot(), before)
    }
    assert.equal(oldUpdates, 0)
    assert.equal(fullUpdates, 0)
    utils.withServerClock(cutoverRealMs + 123, () => {
        assert.equal(utils.getTimeOffset(), 123)
        assert.equal(utils.getConfiguredBusinessTimeOffset(), 500)
        assert.equal(utils.getLegacyTimeOffset(), 500)
    }, 123)
    utils.setServerTimeOffset(null)
    assert.equal(oldUpdates, 1)
    assert.equal(fullUpdates, 1)
    removeOld(); removeFull()
})
}
