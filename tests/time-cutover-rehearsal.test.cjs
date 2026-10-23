'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const Database = require('better-sqlite3')
// Standalone core has no application imports. Transpile only this file when no compiled test root is supplied.
function loadCore() {
    if (process.env.STARPOINT_TEST_OUT_DIR) return require(path.join(process.env.STARPOINT_TEST_OUT_DIR, 'lib/time-cutover-rehearsal.js'))
    const source = path.resolve(__dirname, '../src/lib/time-cutover-rehearsal.ts')
    const output = require('typescript').transpileModule(fs.readFileSync(source, 'utf8'), {
        compilerOptions: { module: require('typescript').ModuleKind.CommonJS, target: require('typescript').ScriptTarget.ES2016 },
    }).outputText
    const loaded = new Module(source, module)
    loaded.filename = source
    loaded.paths = module.paths
    loaded._compile(output, source)
    return loaded.exports
}
const core = loadCore()
const cutoverRealMs = Date.parse('2026-10-13T03:15:00Z')
const legacyOffsetMs = -420 * 86400_000
const options = { cutoverRealMs, legacyOffsetMs }
function fixture(t) {
    const db = new Database(':memory:')
    t.after(() => db.close())
    db.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY,exp_pool INTEGER,exp_pooled_time, time_offset,
        vmoney INTEGER,last_login_time TEXT,total_login_days INTEGER);
        CREATE TABLE players_active_quests(player_id INTEGER PRIMARY KEY,play_id TEXT,started_at_ms INTEGER,clock_version INTEGER);
        CREATE TABLE progress(player_id INTEGER,claimed INTEGER,counter INTEGER);
        CREATE TABLE actual_operations(request_id TEXT PRIMARY KEY,occurred_at_ms INTEGER);`)
    db.prepare('INSERT INTO players VALUES(?,?,?,?,?,?,?)').run(1, 12345, new Date(cutoverRealMs + legacyOffsetMs - 30_000).toISOString(), legacyOffsetMs, 9200, '2024-08-14T12:00:00Z', 42)
    db.prepare('INSERT INTO players VALUES(?,?,?,?,?,?,?)').run(2, 5678, '2024-08-14T12:00:00Z', null, 900, '2024-08-14T12:00:00Z', 9)
    db.prepare('INSERT INTO players_active_quests VALUES(?,?,?,?)').run(1, 'legacy-play', cutoverRealMs + legacyOffsetMs - 12_000, 0)
    db.prepare('INSERT INTO players_active_quests VALUES(?,?,?,?)').run(2, 'real-play', cutoverRealMs - 12_000, 1)
    db.exec('INSERT INTO progress VALUES(1,1,300),(2,1,12)')
    return db
}
function apply(db, extra = {}) {
    const plan = core.planTimeCutoverRehearsalSync(db, options)
    const result = core.applyTimeCutoverRehearsalSync(db, { ...options, expectedPlanDigest: plan.digest, ...extra })
    return { plan, result }
}
test('preview is read-only; exact EXP provenance is shifted with every balance and play preserved', t => {
    const db = fixture(t)
    const before = core.getTimeCutoverDatabaseDigestSync(db)
    const plays = db.prepare('SELECT * FROM players_active_quests').all()
    const plan = core.planTimeCutoverRehearsalSync(db, options)
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), before)
    assert.equal(plan.players[0].basis, 'saved-offset')
    assert.equal(plan.players[1].basis, 'unknown')
    assert.equal(plan.players[0].after.exp_pooled_time, new Date(cutoverRealMs - 30_000).toISOString())
    assert.equal(plan.players[1].after.exp_pooled_time, new Date(cutoverRealMs).toISOString())
    assert.equal(plan.diagnostics.some(x => x.code === 'unknown-exp-basis' && x.playerId === 2), true)
    core.applyTimeCutoverRehearsalSync(db, { ...options, expectedPlanDigest: plan.digest })
    assert.deepEqual(db.prepare('SELECT id,exp_pool,vmoney,total_login_days,last_login_time FROM players ORDER BY id').all(), [
        { id: 1, exp_pool: 12345, vmoney: 9200, total_login_days: 42, last_login_time: '2024-08-14T12:00:00Z' },
        { id: 2, exp_pool: 5678, vmoney: 900, total_login_days: 9, last_login_time: '2024-08-14T12:00:00Z' },
    ])
    assert.deepEqual(db.prepare('SELECT * FROM players_active_quests').all(), plays)
    assert.deepEqual(db.prepare('SELECT * FROM progress').all(), [{ player_id: 1, claimed: 1, counter: 300 }, { player_id: 2, claimed: 1, counter: 12 }])
    for (const state of db.prepare('SELECT * FROM player_time_state').all()) {
        assert.equal(state.day_anchor_ms, cutoverRealMs)
        assert.equal(state.week_anchor_ms, cutoverRealMs)
    }
    assert.equal(db.prepare("SELECT 1 FROM sqlite_master WHERE name='server_time_migration_config'").get(), undefined)
})
test('existing v1 marker and its player checkpoint remain byte-for-byte untouched', t => {
    const db = fixture(t)
    db.exec('CREATE TABLE player_time_state(player_id INTEGER PRIMARY KEY,version INTEGER,cutover_real_ms INTEGER,day_anchor_ms INTEGER,week_anchor_ms INTEGER)')
    db.prepare('INSERT INTO player_time_state VALUES(?,1,?,?,?)').run(1, cutoverRealMs - 300000, cutoverRealMs - 200000, cutoverRealMs - 100000)
    const state = db.prepare('SELECT * FROM player_time_state WHERE player_id=1').get()
    const player = db.prepare('SELECT * FROM players WHERE id=1').get()
    const { plan } = apply(db)
    assert.equal(plan.players[0].basis, 'existing-v1')
    assert.deepEqual(db.prepare('SELECT * FROM player_time_state WHERE player_id=1').get(), state)
    assert.deepEqual(db.prepare('SELECT * FROM players WHERE id=1').get(), player)
    core.rollbackTimeCutoverRehearsalSync(db, { expectedPlanDigest: plan.digest })
    assert.deepEqual(db.prepare('SELECT * FROM player_time_state').all(), [state])
})
test('same digest is idempotent, including after new real operations; new plan cannot displace active ledger', t => {
    const db = fixture(t)
    const { plan } = apply(db)
    db.prepare('INSERT INTO actual_operations VALUES(?,?)').run('new-operation', cutoverRealMs + 1)
    const state = core.getTimeCutoverDatabaseDigestSync(db)
    assert.equal(core.applyTimeCutoverRehearsalSync(db, { ...options, expectedPlanDigest: plan.digest }).status, 'already-applied')
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), state)
    assert.throws(() => core.applyTimeCutoverRehearsalSync(db, { ...options, expectedPlanDigest: 'a'.repeat(64) }), /already applied/)
    assert.throws(() => core.applyTimeCutoverRehearsalSync(db, { ...options, cutoverRealMs: cutoverRealMs + 1, expectedPlanDigest: plan.digest }), /options mismatch/)
})
test('plan race with progress, options or schema rejects without writes', t => {
    const db = fixture(t)
    const plan = core.planTimeCutoverRehearsalSync(db, options)
    db.exec('UPDATE progress SET counter=counter+1 WHERE player_id=1')
    const before = core.getTimeCutoverDatabaseDigestSync(db)
    assert.throws(() => core.applyTimeCutoverRehearsalSync(db, { ...options, expectedPlanDigest: plan.digest }), /Plan digest mismatch/)
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), before)
    const next = core.planTimeCutoverRehearsalSync(db, options)
    assert.throws(() => core.applyTimeCutoverRehearsalSync(db, { ...options, legacyOffsetMs: null, expectedPlanDigest: next.digest }), /Plan digest mismatch/)
    db.exec('CREATE INDEX progress_counter ON progress(counter)')
    assert.throws(() => core.applyTimeCutoverRehearsalSync(db, { ...options, expectedPlanDigest: next.digest }), /Plan digest mismatch/)
})
for (const faultAt of ['after-schema', 'after-player-update', 'before-ledger', 'after-ledger']) {
    test(`apply failure at ${faultAt} rolls back data, schema and ledger atomically`, t => {
        const db = fixture(t)
        const before = core.getTimeCutoverDatabaseDigestSync(db)
        assert.throws(() => apply(db, { faultAt }), /Injected cutover failure/)
        assert.equal(core.getTimeCutoverDatabaseDigestSync(db), before)
        assert.equal(db.prepare('SELECT 1 FROM sqlite_master WHERE name=?').get(core.TIME_CUTOVER_REHEARSAL_LEDGER), undefined)
    })
}
test('explicit rollback restores exact original data/schema; repeat rollback and apply are safe', t => {
    const db = fixture(t)
    const before = core.getTimeCutoverDatabaseDigestSync(db)
    const { plan } = apply(db)
    const after = core.getTimeCutoverDatabaseDigestSync(db)
    assert.throws(() => core.rollbackTimeCutoverRehearsalSync(db, { expectedPlanDigest: plan.digest, faultAt: 'after-player-restore' }), /Injected/)
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), after)
    assert.equal(core.rollbackTimeCutoverRehearsalSync(db, { expectedPlanDigest: plan.digest }).status, 'rolled-back')
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), before)
    assert.equal(core.rollbackTimeCutoverRehearsalSync(db, { expectedPlanDigest: plan.digest }).status, 'already-rolled-back')
    assert.equal(core.applyTimeCutoverRehearsalSync(db, { ...options, expectedPlanDigest: plan.digest }).status, 'applied')
})
for (const mutation of ["UPDATE players SET exp_pool=exp_pool+1 WHERE id=1", "UPDATE progress SET claimed=0 WHERE player_id=2", "INSERT INTO actual_operations VALUES('after',1)", 'UPDATE player_time_state SET day_anchor_ms=day_anchor_ms+1']) {
    test(`rollback refuses later durable state: ${mutation}`, t => {
        const db = fixture(t)
        const { plan } = apply(db)
        db.exec(mutation)
        const before = core.getTimeCutoverDatabaseDigestSync(db)
        assert.throws(() => core.rollbackTimeCutoverRehearsalSync(db, { expectedPlanDigest: plan.digest }), /Rollback refused/)
        assert.equal(core.getTimeCutoverDatabaseDigestSync(db), before)
    })
}
test('invalid marker and unsupported EXP input remain bounded and cannot grant balances', t => {
    const db = fixture(t)
    db.exec("UPDATE players SET exp_pooled_time='ambiguous timezone',time_offset=0 WHERE id=1")
    const plan = core.planTimeCutoverRehearsalSync(db, options)
    assert.equal(plan.players[0].basis, 'unknown')
    assert.equal(plan.players[0].after.exp_pooled_time, new Date(cutoverRealMs).toISOString())
    db.exec('CREATE TABLE player_time_state(player_id INTEGER PRIMARY KEY,version INTEGER,cutover_real_ms INTEGER,day_anchor_ms INTEGER,week_anchor_ms INTEGER); INSERT INTO player_time_state VALUES(1,2,1,1,1)')
    const before = core.getTimeCutoverDatabaseDigestSync(db)
    assert.throws(() => core.planTimeCutoverRehearsalSync(db, options), /Unsupported or invalid/)
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), before)
})
test('corrupt ledger cannot restore arbitrary checkpoints', t => {
    const db = fixture(t)
    const { plan } = apply(db)
    const altered = { ...plan, cutoverRealMs: 1 }
    db.prepare(`UPDATE ${core.TIME_CUTOVER_REHEARSAL_LEDGER} SET plan_json=?`).run(JSON.stringify(altered))
    assert.throws(() => core.rollbackTimeCutoverRehearsalSync(db, { expectedPlanDigest: plan.digest }), /Corrupt rehearsal receipt/)
})
test('attached databases and caller-owned transactions are rejected', t => {
    const db = fixture(t)
    db.exec("ATTACH ':memory:' AS other")
    assert.throws(() => core.planTimeCutoverRehearsalSync(db, options), /Attached/)
    db.exec('DETACH other')
    db.transaction(() => assert.throws(() => core.planTimeCutoverRehearsalSync(db, options), /outside a transaction/))()
})
test('unexpected business trigger changes during apply cause a complete atomic rollback', t => {
    const db = fixture(t)
    db.exec('CREATE TRIGGER unsafe_clock_update AFTER UPDATE OF time_offset ON players BEGIN UPDATE progress SET counter=counter+100 WHERE player_id=NEW.id; END')
    const before = core.getTimeCutoverDatabaseDigestSync(db)
    assert.throws(() => apply(db), /unrelated persistent state changed/)
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), before)
})
test('cross-player trigger cannot replace an earlier planned checkpoint', t => {
    const db = fixture(t)
    db.exec("CREATE TRIGGER cross_player_clock AFTER UPDATE OF time_offset ON players WHEN NEW.id=2 BEGIN UPDATE players SET exp_pooled_time='2026-10-13T00:00:00Z' WHERE id=1; END")
    const before = core.getTimeCutoverDatabaseDigestSync(db)
    assert.throws(() => apply(db), /exact planned fields/)
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), before)
})
test('rollback detects adjacent persisted SQLite integers above 2^53 without precision loss', t => {
    const db = fixture(t)
    db.exec('CREATE TABLE large_progress(counter INTEGER NOT NULL)')
    db.prepare('INSERT INTO large_progress VALUES(?)').run(9007199254740992n)
    const { plan } = apply(db)
    const afterApply = core.getTimeCutoverDatabaseDigestSync(db)
    db.exec('UPDATE large_progress SET counter=counter+1')
    assert.equal(db.prepare('SELECT counter FROM large_progress').safeIntegers().get().counter, 9007199254740993n)
    const advanced = core.getTimeCutoverDatabaseDigestSync(db)
    assert.notEqual(advanced, afterApply)
    assert.throws(() => core.rollbackTimeCutoverRehearsalSync(db, { expectedPlanDigest: plan.digest }), /Rollback refused/)
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db), advanced)
    assert.equal(db.prepare('SELECT counter FROM large_progress').safeIntegers().get().counter, 9007199254740993n)
})

// The fake connection exposes path metadata only, so rejection never opens a
// real database or creates scratch files inside a registered checkout.
test('offline file guard rejects the current registered worktree and its junction alias', t => {
    const root = path.resolve(__dirname, '..')
    const file = path.join(root, 'package.json')
    const connection = { open:true, readonly:false, inTransaction:false, name:file,
        prepare:sql => sql.includes('sqlite_temp_master') ? {get:()=>undefined} : {all:()=>[{name:'main',file}]}  }
    const guard = {kind:'approved-offline-file',databasePath:file,allowedRoot:root}
    assert.throws(()=>core.assertTimeCutoverOfflineDatabaseSync(connection,guard),/Protected database location/)
    const temp = fs.mkdtempSync(path.join(require('node:os').tmpdir(),'clock-guard-'))
    const alias = path.join(temp,'checkout-alias')
    fs.symlinkSync(root,alias,process.platform==='win32'?'junction':'dir')
    t.after(()=>{fs.unlinkSync(alias);fs.rmdirSync(temp)})
    const aliased = path.join(alias,'package.json')
    connection.name=aliased
    assert.throws(()=>core.assertTimeCutoverOfflineDatabaseSync(connection,
        {...guard,databasePath:aliased,allowedRoot:alias}),/Protected database location/)
})

test('temporary table shadows refuse preview and apply before modifying persistent players', t => {
    const db=fixture(t)
    const before=core.getTimeCutoverDatabaseDigestSync(db)
    const plan=core.planTimeCutoverRehearsalSync(db,options)
    db.exec('CREATE TEMP TABLE players AS SELECT * FROM main.players')
    assert.throws(()=>core.planTimeCutoverRehearsalSync(db,options),/Temporary shadow/)
    assert.throws(()=>core.applyTimeCutoverRehearsalSync(db,{...options,expectedPlanDigest:plan.digest}),/Temporary shadow/)
    db.exec('DROP TABLE temp.players')
    assert.equal(core.getTimeCutoverDatabaseDigestSync(db),before)
})
