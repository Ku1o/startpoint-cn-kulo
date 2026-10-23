'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
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
const taskRoot = path.resolve(process.env.SERVER_CLOCK_TEST_ROOT || path.join(require('node:os').tmpdir(), 'starpoint-clock-dispatch'))
const scenarios = ['absent-real-state', 'mismatched-real-state', 'matching-real-state', 'legacy-without-global']
if (process.argv[2] === '--dispatch-child') {
    Promise.resolve().then(() => verifyScenario(process.argv[3])).then(result => {
        console.log('DISPATCH_RESULT ' + JSON.stringify(result)); process.exit(0)
    }, error => { console.error(error); process.exit(1) })
} else {
    const test = require('node:test')
    for (const scenario of scenarios) test(`clock dispatch guards: ${scenario}`, { timeout: 45000 }, () => {
        fs.mkdirSync(taskRoot, { recursive: true })
        const directory = fs.mkdtempSync(path.join(taskRoot, `${scenario}-`))
        const child = spawnSync(process.execPath, [...process.execArgv, __filename, '--dispatch-child', scenario], {
            cwd: path.resolve(__dirname, '..'), windowsHide: true, timeout: 40000, encoding: 'utf8',
            env: { ...process.env, DATA_DIR: directory, TMP: directory, TEMP: directory, TMPDIR: directory,
                GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0' },
        })
        fs.writeFileSync(path.join(directory, 'process.log'), child.stdout + child.stderr)
        assert.equal(child.status, 0, child.stdout + child.stderr)
        const line = child.stdout.split(/\r?\n/).find(value => value.startsWith('DISPATCH_RESULT '))
        assert.ok(line, child.stdout + child.stderr)
        const result = JSON.parse(line.slice('DISPATCH_RESULT '.length))
        fs.writeFileSync(path.join(directory, 'verification.json'), JSON.stringify(result, null, 2) + '\n')
        console.log(line)
    })
}
async function verifyScenario(scenario) {
    assert.ok(scenarios.includes(scenario))
    const db = new Database(':memory:')
    load('data/db').setDbOverride(db)
    const core = load('lib/server-clock-state'), utils = load('utils'), persistence = load('lib/persistence-coordinator')
    const cutoverRealMs = Date.parse('2026-10-13T03:15:00Z'), legacyOffsetMs = -420 * 86400000
    db.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY,exp_pool INTEGER,exp_pooled_time,time_offset,free_mana INTEGER);
        CREATE TABLE progress(id INTEGER PRIMARY KEY,counter INTEGER);
        INSERT INTO progress VALUES(1,12);`)
    db.prepare('INSERT INTO players VALUES(1,?,?,?,99)').run(1234, new Date(cutoverRealMs + legacyOffsetMs - 5000).toISOString(), legacyOffsetMs)
    if (scenario !== 'legacy-without-global') {
        const options = { cutoverRealMs, legacyOffsetMs }
        const plan = load('lib/time-cutover-rehearsal').planTimeCutoverRehearsalSync(db, options)
        core.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: plan.digest, readiness: 'scenario-only' })
        core.restoreServerClockStateSync(db)
        if (scenario === 'absent-real-state') db.exec('DROP TABLE server_clock_state')
        if (scenario === 'mismatched-real-state') db.exec('UPDATE server_clock_state SET revision=revision+1')
    }
    const readMarkers = () => db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_time_state'").get()
        ? db.prepare('SELECT * FROM player_time_state ORDER BY player_id').all() : null
    const before = core.getServerClockPersistentFingerprintSync(db), markers = readMarkers(), snapshot = utils.getServerClockSnapshot()
    let executorCalls = 0, fallbackCalls = 0, backgroundCalls = 0
    persistence.configurePersistenceSqlExecutor(async (_context, statements) => {
        executorCalls++
        db.transaction(() => { for (const statement of statements) db.prepare(statement.sql).run(...statement.params) }).immediate()
    })
    const executor = () => persistence.runPersistenceSqlCommand({ domain: 'maintenance', operation: 'guard-raw-sql' },
        [{ sql: 'UPDATE progress SET counter=counter+1 WHERE id=?', params: [1] }], () => { fallbackCalls++ })
    const background = () => persistence.runBackgroundPersistenceTask({ domain: 'maintenance', operation: 'guard-background-no-prepare' },
        async prepared => {
            backgroundCalls++; assert.equal(prepared, undefined)
            assert.equal(db.inTransaction, false, 'short admission transaction must release its lock before asynchronous work')
            await Promise.resolve()
            db.prepare('UPDATE progress SET counter=counter+10 WHERE id=1').run()
        })
    try {
        const rejected = scenario === 'absent-real-state' || scenario === 'mismatched-real-state'
        if (rejected) {
            const expected = scenario === 'absent-real-state' ? /no committed global state/ : /differs from committed global state/
            await assert.rejects(executor(), expected)
            await assert.rejects(background(), expected)
            assert.equal(executorCalls, 0); assert.equal(backgroundCalls, 0); assert.equal(fallbackCalls, 0)
            assert.equal(core.getServerClockPersistentFingerprintSync(db), before)
            assert.deepEqual(readMarkers(), markers)
            assert.equal(db.prepare('SELECT counter FROM progress').get().counter, 12)
            assert.deepEqual(utils.getServerClockSnapshot(), snapshot)
            // A corrected DB match resumes both entry points; failed admission
            // must not leak the global queue, exclusive gate or SQLite lock.
            if (scenario === 'mismatched-real-state') {
                db.exec('UPDATE server_clock_state SET revision=revision-1')
                await executor(); await background()
                assert.equal(executorCalls, 1); assert.equal(backgroundCalls, 1)
                assert.equal(db.prepare('SELECT counter FROM progress').get().counter, 23)
                assert.deepEqual(readMarkers(), markers)
            }
        } else {
            await executor(); await background()
            assert.equal(executorCalls, 1); assert.equal(backgroundCalls, 1); assert.equal(fallbackCalls, 0)
            assert.equal(db.prepare('SELECT counter FROM progress').get().counter, 23)
            assert.deepEqual(readMarkers(), markers)
            assert.deepEqual(utils.getServerClockSnapshot(), snapshot)
            if (scenario === 'legacy-without-global') {
                assert.equal(snapshot.mode, 'legacy'); assert.equal(core.readServerClockStateSync(db), null); assert.equal(readMarkers(), null)
            }
        }
        assert.equal(db.inTransaction, false)
        return { scenario, rejectedBeforeDispatch: rejected, untouchedOnFailure: rejected, markerPreserved: true,
            mode: snapshot.mode, executorCalls, backgroundCalls, fallbackCalls, noLockAcrossBackgroundAwait: backgroundCalls > 0 ? true : null,
            rejectedCallbacks: rejected ? { executor: 0, background: 0, fallback: 0 } : null,
            resumedAfterCorrection: scenario === 'mismatched-real-state', beforeFingerprint: before,
            finalCounter: db.prepare('SELECT counter FROM progress').get().counter }
    } finally { persistence.configurePersistenceSqlExecutor(null); db.close() }
}
