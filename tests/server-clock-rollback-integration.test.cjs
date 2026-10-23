'use strict'
// The production writer loads this module as extra commands. Worker imports
// register handlers only, and never invoke node:test or synthesize databases.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { isMainThread, threadId } = require('node:worker_threads')
const sourceRoot = path.resolve(process.env.SERVER_CLOCK_TEST_SOURCE || path.resolve(__dirname, '..'))
const taskRoot = path.resolve(process.env.SERVER_CLOCK_TEST_ROOT || path.join(require('node:os').tmpdir(), 'starpoint-clock-rollback'))
const out = process.env.STARPOINT_TEST_OUT_DIR
if (!out) throw new Error('Rollback writer integration requires STARPOINT_TEST_OUT_DIR for the current isolated build')
const load = name => require(path.join(out, name))
const legacyOffset = -420 * 86400000 - 12345
const command = name => `clock.rollback.integration.${name}`
function probe() {
    const clock = load('utils'), battle = load('lib/battle-clock-compatibility'), real = clock.getRealServerDate().getTime()
    return { thread: isMainThread ? 'main' : 'worker', threadId, snapshot: clock.getServerClockSnapshot(),
        real, now: clock.getServerDate().getTime(), offset: clock.getTimeOffset(),
        oldBattle: battle.getBattleClockDate(0).getTime(), newBattle: battle.getBattleClockDate(1).getTime(),
        transaction: load('data/db').getDb().inTransaction }
}
function registerCommands() {
    const { registerWriterCommand } = load('lib/persistence/command-registry')
    registerWriterCommand(command('probe'), probe)
    registerWriterCommand(command('slow'), args => {
        fs.writeFileSync(args.signal, 'entered')
        const until = Date.now() + 150
        while (Date.now() < until) { /* genuine writer transaction held for drain */ }
        return probe()
    })
    registerWriterCommand(command('new-progress'), args => {
        const db = load('data/db').getDb()
        db.prepare('UPDATE players SET free_mana=free_mana+7,exp_pool=exp_pool+11 WHERE id=?').run(args.playerId)
        db.prepare('UPDATE rollback_business_facts SET counter=counter+1 WHERE id=1').run()
        db.prepare('INSERT INTO rollback_business_receipts(request_id,response) VALUES(?,?)').run(args.requestId, 'paid-once')
        return { ...probe(), requestId: args.requestId }
    })
}
if (!isMainThread) registerCommands()
else if (process.argv[2] === '--rollback-child') {
    Promise.resolve().then(() => runScenario(process.argv[3])).then(result => {
        console.log('ROLLBACK_RESULT ' + JSON.stringify(result)); process.exit(0)
    }, error => { console.error(error); process.exit(1) })
} else {
    const test = require('node:test')
    for (const scenario of ['drain-rollback-restart', 'stale-real-writer', 'new-progress-refusal']) {
        test(`offline rollback genuine process/writer: ${scenario}`, { timeout: 120000 }, () => {
            fs.mkdirSync(taskRoot, { recursive: true })
            const directory = fs.mkdtempSync(path.join(taskRoot, `${scenario}-`))
            const result = childProcess(scenario, directory)
            fs.writeFileSync(path.join(directory, 'process.log'), result.stdout + result.stderr)
            assert.equal(result.status, 0, result.stdout + result.stderr)
            const value = readResult(result)
            fs.writeFileSync(path.join(directory, 'verification.json'), JSON.stringify(value, null, 2) + '\n')
            console.log('ROLLBACK_RESULT ' + JSON.stringify(value))
        })
    }
}
function childProcess(scenario, directory, extra = {}) {
    return spawnSync(process.execPath, ['--preserve-symlinks', '--preserve-symlinks-main', __filename, '--rollback-child', scenario], {
        cwd: sourceRoot, windowsHide: true, timeout: 100000, encoding: 'utf8', maxBuffer: 2000000,
        env: { ...process.env, DATA_DIR: directory, TMP: directory, TEMP: directory, TMPDIR: directory,
            GACHA_SEED_DIR: path.join(directory, 'seeds'), SERVER_CLOCK_TEST_SOURCE: sourceRoot,
            SERVER_CLOCK_TEST_ROOT: taskRoot, STARPOINT_TEST_OUT_DIR: out, CN_WRITER_THREAD: '0',
            SQLITE_WRITER_EXTRA_COMMANDS: __filename, GAME_ROUTINE_LOGS: 'off', ...extra },
    })
}
function readResult(result) {
    const text = result.stdout.split(/\r?\n/).find(line => line.startsWith('ROLLBACK_RESULT '))
    assert.ok(text, result.stdout + result.stderr)
    return JSON.parse(text.slice('ROLLBACK_RESULT '.length))
}
const receipt = db => db.prepare('SELECT * FROM server_clock_rollback_receipt').all()
const digest = db => load('lib/server-clock-state').getServerClockPersistentFingerprintSync(db)
function registrations(db) {
    return { markers: db.prepare('SELECT * FROM player_time_state WHERE player_id IN (1,2) ORDER BY player_id').all(),
        oldPlays: db.prepare('SELECT * FROM players_active_quests ORDER BY player_id').all() }
}
function seed(db, clock) {
    const players = load('data/domains/player'), accounts = load('data/domains/account'), realMs = Date.now()
    clock.setServerTimeOffset(legacyOffset)
    load('data/activeAccount').saveTimeOffset(legacyOffset)
    clock.withServerClock(realMs + legacyOffset, () => {
        for (let index = 0; index < 151; index++) {
            const account = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'offline-rollback', idpId: `fixture-${index}`, status: 'normal' })
            const player = players.insertDefaultPlayerSync(account.id)
            assert.equal(player.id, index + 1)
            players.updatePlayerSync({ id: player.id, expPool: 1234 + index, freeMana: 9876 + index, timeOffset: legacyOffset,
                expPooledTime: new Date(realMs + legacyOffset - index * 1000), lastLoginTime: new Date(realMs + legacyOffset), totalLoginDays: 27 })
            if (index >= 2) {
                load('data/domains/quest_active').insertPlayerActiveQuestSync(player.id, { playerId: player.id,
                    playId: `preserved-old-${index}`, questId: 1001001, category: 2, isMulti: false, isMultiHost: false,
                    roomNumber: null, useBoostPoint: false, useBossBoostPoint: false, isAutoStartMode: false,
                    continueCount: 0, startedAtMs: realMs + legacyOffset - 60000, partySlot: 1 })
                db.prepare('UPDATE players_active_quests SET clock_version=0 WHERE player_id=?').run(player.id)
            }
        }
    }, legacyOffset)
    db.exec(`CREATE TABLE player_time_state(player_id INTEGER PRIMARY KEY REFERENCES players(id),version INTEGER NOT NULL,
        cutover_real_ms INTEGER NOT NULL,day_anchor_ms INTEGER NOT NULL,week_anchor_ms INTEGER NOT NULL);
        CREATE TABLE rollback_business_facts(id INTEGER PRIMARY KEY,counter INTEGER NOT NULL);
        CREATE TABLE rollback_business_receipts(request_id TEXT PRIMARY KEY,response TEXT NOT NULL);
        INSERT INTO rollback_business_facts VALUES(1,12); INSERT INTO rollback_business_receipts VALUES('prior','old');`)
    for (const id of [1, 2]) {
        db.prepare('INSERT INTO player_time_state VALUES(?,1,?,?,?)').run(id, realMs - 90000, realMs - 80000, realMs - 70000)
        players.updatePlayerSync({ id, timeOffset: 0, expPooledTime: new Date(realMs - 5000) })
    }
    assert.equal(registrations(db).oldPlays.length, 149)
    return { realMs, registrations: registrations(db), originalJson: fs.readFileSync(path.join(process.env.DATA_DIR, 'active_account.json')) }
}
function activate(db, fixture, extra = {}) {
    const offlineGuard = { kind: 'approved-offline-file', databasePath: fs.realpathSync(db.name), allowedRoot: taskRoot }
    const options = { cutoverRealMs: fixture.realMs, legacyOffsetMs: legacyOffset, offlineGuard }
    const plan = load('lib/time-cutover-rehearsal').planTimeCutoverRehearsalSync(db, options)
    load('lib/server-clock-state').activateRealServerClockOfflineSync(db, { ...options, readiness: 'scenario-only', expectedPlanDigest: plan.digest, ...extra })
    return { expectedPlanDigest: plan.digest, offlineGuard }
}
function assertProbe(value, expected) {
    assert.equal(value.thread, 'worker'); assert.ok(value.threadId > 0); assert.equal(value.transaction, true)
    assert.deepEqual(value.snapshot, expected)
    assert.ok(Math.abs(value.now - value.real - (expected.businessOffsetMs ?? 0)) <= 30)
    assert.equal(value.offset, expected.businessOffsetMs ?? 0)
    assert.ok(Math.abs(value.oldBattle - value.real - (expected.legacyBattleOffsetMs ?? 0)) <= 30)
    assert.ok(Math.abs(value.newBattle - value.real) <= 30)
}
async function startWriter(db) {
    const writer = load('lib/persistence/writer-client')
    process.env.CN_WRITER_THREAD = '1'; process.env.SQLITE_WRITER_MAX_IN_FLIGHT = '16'
    process.env.SQLITE_GROUP_COMMIT_WINDOW_MS = '0'; process.env.SQLITE_WRITER_COMMAND_TIMEOUT_MS = '0'
    process.env.SQLITE_WRITER_BUSY_TIMEOUT_MS = '0'
    assert.equal(writer.startSqliteWriter(db.name), true)
    assert.equal(await writer.waitForSqliteWriterReady(30000), true)
    return writer
}
function run(name, args = {}, playerId) {
    return load('lib/persistence-coordinator').runWriterCommand(command(name), args,
        { domain: 'maintenance', operation: command(name), ...(playerId === undefined ? {} : { playerId }) })
}
async function waitForSignal(file) {
    const deadline = Date.now() + 10000
    while (!fs.existsSync(file)) {
        assert.ok(Date.now() < deadline, 'real writer slow command did not enter')
        await new Promise(resolve => setTimeout(resolve, 5))
    }
}
async function runScenario(scenario) {
    const clock = load('utils'), core = load('lib/server-clock-state')
    let db, writer
    try {
        if (scenario === 'fresh-legacy') {
            db = new (require('better-sqlite3'))(process.env.CLOCK_DATABASE)
            load('data/db').setDbOverride(db)
            const before = digest(db), registered = registrations(db), originalJson = fs.readFileSync(path.join(process.env.DATA_DIR, 'active_account.json'))
            load('data/activeAccount').restoreTimeOffset(db)
            const expected = clock.getServerClockSnapshot()
            assert.equal(expected.mode, 'legacy'); assert.equal(expected.businessOffsetMs, legacyOffset)
            assert.equal(expected.legacyBattleOffsetMs, legacyOffset); assert.equal(core.readServerClockStateSync(db), null)
            assert.equal(core.assertServerClockMatchesDatabaseSync(db), null)
            writer = await startWriter(db)
            const first = await run('probe'); assertProbe(first, expected)
            await writer.stopSqliteWriter(); assert.equal(writer.sqliteWriterQueueDepth(), 0)
            writer = await startWriter(db)
            const restarted = await run('probe'); assertProbe(restarted, expected)
            assert.notEqual(restarted.threadId, first.threadId)
            await writer.stopSqliteWriter()
            assert.equal(digest(db), before); assert.deepEqual(registrations(db), registered)
            assert.deepEqual(fs.readFileSync(path.join(process.env.DATA_DIR, 'active_account.json')), originalJson)
            return { scenario, mode: expected.mode, legacySnapshot: expected, firstThreadId: first.threadId,
                restartedThreadId: restarted.threadId, existingV1: registered.markers.length, oldPlays: registered.oldPlays.length,
                writerRestart: 'explicit-stop-and-start', clock0Offset: legacyOffset, clock1Offset: 0,
                fingerprint: before, unchangedFingerprint: true, unchangedLegacyJson: true }
        }
        db = load('data/db').getDb()
        assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(process.env.DATA_DIR))
        const fixture = seed(db, clock), before = digest(db), rollback = activate(db, fixture)
        load('data/activeAccount').restoreTimeOffset(db)
        const expected = clock.getServerClockSnapshot(), activated = digest(db)
        writer = await startWriter(db)
        const initial = await run('probe'); assertProbe(initial, expected)
        assert.equal(initial.now - initial.real, 0)
        if (scenario === 'new-progress-refusal') {
            const oldMana = db.prepare('SELECT free_mana,exp_pool FROM players WHERE id=3').get()
            const faultBefore = digest(db), faultReceipt = receipt(db)
            // stop+drain before any offline rollback operation, including failure injection
            await writer.stopSqliteWriter()
            assert.throws(() => core.rollbackRealServerClockOfflineSync(db, { ...rollback, faultAt: 'after-rollback-receipt' }), /Injected/)
            assert.equal(digest(db), faultBefore); assert.deepEqual(receipt(db), faultReceipt)
            writer = await startWriter(db)
            const paid = await run('new-progress', { playerId: 3, requestId: 'new-paid' }, 3); assertProbe(paid, expected)
            await writer.stopSqliteWriter()
            const newFacts = digest(db), newReceipt = receipt(db)
            assert.throws(() => core.rollbackRealServerClockOfflineSync(db, rollback), /persistent state changed after activation/)
            assert.equal(digest(db), newFacts); assert.deepEqual(receipt(db), newReceipt)
            assert.deepEqual(db.prepare('SELECT free_mana,exp_pool FROM players WHERE id=3').get(), { free_mana: oldMana.free_mana + 7, exp_pool: oldMana.exp_pool + 11 })
            assert.equal(db.prepare('SELECT counter FROM rollback_business_facts WHERE id=1').get().counter, 13)
            assert.equal(db.prepare("SELECT count(*) n FROM rollback_business_receipts WHERE request_id='new-paid'").get().n, 1)
            assert.deepEqual(registrations(db), fixture.registrations)
            return { scenario, actualWriterPaid: true, receiptFaultRolledBack: true, newProgressRollbackRefused: true,
                beforeFingerprint: before, activatedFingerprint: activated, newFactsFingerprint: newFacts,
                existingV1: 2, oldPlays: 149, preservedMana: 7, preservedExpPool: 11, newReceipts: 1 }
        }
        if (scenario === 'drain-rollback-restart') {
            const signal = path.join(process.env.DATA_DIR, 'writer-slow.signal')
            const pending = run('slow', { signal })
            await waitForSignal(signal)
            assert.equal(writer.sqliteWriterQueueDepth(), 1)
            const stopping = writer.stopSqliteWriter()
            assertProbe(await pending, expected)
            await stopping
            assert.equal(writer.sqliteWriterQueueDepth(), 0); assert.equal(writer.isSqliteWriterReady(), false)
            assert.equal(digest(db), activated, 'drained read-only commands add no persistent progress')
        }
        // The stale-writer scenario deliberately leaves an idle synthetic worker
        // alive solely to verify rejection after a separate offline reversal.
        // This fault scenario is not the permitted stop/drain operating procedure.
        const result = core.rollbackRealServerClockOfflineSync(db, rollback)
        assert.equal(result.status, 'rolled-back'); assert.equal(digest(db), before)
        assert.deepEqual(clock.getServerClockSnapshot(), expected, 'offline rollback cannot reset the real runtime')
        const receiptAfter = receipt(db), persistence = load('lib/persistence-coordinator')
        assert.throws(() => persistence.runPersistenceTransactionSync({ domain: 'maintenance', operation: 'rollback-global-sync' },
            () => db.exec('UPDATE rollback_business_facts SET counter=1000')), /no committed global state/)
        await assert.rejects(persistence.runPersistenceTransaction({ domain: 'maintenance', operation: 'rollback-global-async' },
            () => db.exec('UPDATE rollback_business_facts SET counter=1000')), /no committed global state/)
        if (scenario === 'stale-real-writer') {
            await assert.rejects(writer.executeSqliteWriterCommand({ name: command('new-progress'), args: { playerId: 3, requestId: 'forbidden' },
                meta: { domain: 'maintenance', operation: 'no-player-global' } }), /no committed global state/)
            await assert.rejects(run('new-progress', { playerId: 3, requestId: 'forbidden-player' }, 3), /no committed global state/)
            await writer.stopSqliteWriter()
        }
        assert.equal(digest(db), before); assert.deepEqual(receipt(db), receiptAfter)
        assert.deepEqual(registrations(db), fixture.registrations)
        assert.deepEqual(fs.readFileSync(path.join(process.env.DATA_DIR, 'active_account.json')), fixture.originalJson)
        const child = childProcess('fresh-legacy', process.env.DATA_DIR, { CLOCK_DATABASE: db.name })
        fs.writeFileSync(path.join(process.env.DATA_DIR, 'fresh-process.log'), child.stdout + child.stderr)
        assert.equal(child.status, 0, child.stdout + child.stderr)
        const fresh = readResult(child)
        assert.equal(digest(db), before); assert.deepEqual(registrations(db), fixture.registrations)
        assert.equal(db.pragma('quick_check', { simple: true }), 'ok'); assert.deepEqual(db.pragma('foreign_key_check'), [])
        return { scenario, beforeFingerprint: before, activatedFingerprint: activated, rolledBackFingerprint: digest(db),
            originalRealSnapshot: expected, oldRealMainSyncRejected: true, oldRealMainAsyncRejected: true,
            idleStaleWriterRejected: scenario === 'stale-real-writer', drainCompletedBeforeRollback: scenario === 'drain-rollback-restart',
            oldPlays: 149, existingV1: 2, fresh, quickCheck: 'ok', productionCutover: 'no_go' }
    } finally { if (writer) await writer.stopSqliteWriter(); if (db?.open) db.close() }
}
