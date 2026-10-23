'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { execFile } = require('node:child_process')
const { promisify } = require('node:util')
const root = path.resolve(process.env.STARPOINT_TEST_ENGINE || path.join(__dirname, '..'))
const load = name => require(path.join(root, 'out', name))
const scenarios = ['legacy-manual', 'real-manual', 'real-scheduled', 'corrupt-clock', 'real-rollback']

async function scenario(name) {
    const temporaryRoot = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
    fs.mkdirSync(temporaryRoot, { recursive: true })
    const directory = fs.mkdtempSync(path.join(temporaryRoot, 'leaderboard-clock-'))
    Object.assign(process.env, { DATA_DIR: directory, GACHA_SEED_DIR: path.join(directory, 'seeds'),
        TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory, CN_WRITER_THREAD: '0',
        GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
    const db = load('data/db').getDb()
    const accounts = load('data/domains/account'), players = load('data/domains/player')
    const background = load('lib/leaderboard/background-worker')
    const settlement = load('lib/leaderboard/settlement')
    const competitions = load('lib/leaderboard/competition')
    const availability = load('lib/leaderboard/availability')
    const clock = load('lib/server-clock-state')
    const key = 'rush:700099:1', ids = []
    try {
        assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
        for (let i = 0; i < 4; i++) {
            const account = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '',
                idpCode: 'leaderboard-clock-fixture', idpId: String(i), status: 'normal' })
            ids.push(players.insertDefaultPlayerSync(account.id).id)
        }
        const nowMs = Date.now()
        if (name !== 'legacy-manual') {
            const options = { cutoverRealMs: nowMs, legacyOffsetMs: null,
                offlineGuard: { kind: 'approved-offline-file', databasePath: fs.realpathSync(db.name), allowedRoot: temporaryRoot } }
            const plan = load('lib/time-cutover-rehearsal').planTimeCutoverRehearsalSync(db, options)
            clock.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: plan.digest,
                readiness: 'scenario-only' })
            clock.restoreServerClockStateSync(db)
            assert.equal(load('utils').getServerClockSnapshot().mode, 'real')
        }
        const season = competitions.getLeaderboardCompetitionSeasonSync(key, nowMs)
        availability.getLeaderboardAvailabilitySync(key, nowMs)
        const config = settlement.getLeaderboardSettlementConfigSync(key, nowMs)
        db.transaction(() => {
            for (const [index, playerId] of ids.entries()) {
                const run = db.prepare(`INSERT INTO leaderboard_runs
                    (competition_key,player_id,season,status,started_at_ms,finished_at_ms,
                     client_battle_ms,rounds_cleared,total_rounds,tracked_from_round)
                    VALUES (?,?,?,'completed',1,2,?,1,1,1)`).run(key, playerId, season, 1000 + index)
                db.prepare(`INSERT INTO leaderboard_run_rounds
                    (run_id,round_number,quest_id,client_battle_ms,server_elapsed_ms,started_at_ms,finished_at_ms)
                    VALUES (?,1,1,?,?,1,2)`).run(Number(run.lastInsertRowid), 1000 + index, 1000 + index)
            }
        })()
        const playerRows = () => db.prepare('SELECT * FROM players ORDER BY id').all()
        const initialPlayers = playerRows()
        const initialClock = name === 'legacy-manual' ? null : db.prepare('SELECT * FROM server_clock_state').get()
        const count = table => db.prepare(`SELECT COUNT(*) n FROM ${table}`).get().n
        const emptyAwards = () => {
            for (const table of ['leaderboard_settlements', 'leaderboard_settlement_results', 'players_mails']) {
                assert.equal(count(table), 0, table)
            }
        }
        const job = { competitionKey: key, source: 'clock-fixture', nowMs, scheduled: name === 'real-scheduled' }
        if (name === 'corrupt-clock') {
            // Exercise the actual worker's restore failure, without allowing a
            // parent's earlier clock assertion to mask this startup branch.
            db.prepare("UPDATE server_clock_state SET plan_digest='corrupt'").run()
            await assert.rejects(background.executeLeaderboardSettlementWorker({ ...job,
                databasePath: db.name, season }), /persisted clock/i)
            emptyAwards()
            assert.deepEqual(playerRows(), initialPlayers)
            assert.equal(db.prepare('SELECT plan_digest FROM server_clock_state').get().plan_digest, 'corrupt')
            return { name, rejectedBeforeAwards: true }
        }
        if (name === 'real-scheduled') {
            settlement.putLeaderboardSettlementConfigSync({ ...config, autoEnabled: true,
                freezeEnabled: true, settleAtMs: nowMs - 1, repeatIntervalMs: null, updatedAtMs: nowMs })
        }
        if (name === 'real-rollback') {
            const initialAvailability = db.prepare('SELECT * FROM leaderboard_availability WHERE competition_key=?').get(key)
            const unchangedInputs = () => ({
                config: db.prepare('SELECT * FROM leaderboard_settlement_configs WHERE competition_key=?').get(key),
                runs: db.prepare('SELECT * FROM leaderboard_runs ORDER BY id').all(),
                rounds: db.prepare('SELECT * FROM leaderboard_run_rounds ORDER BY run_id,round_number').all(),
            })
            const initialInputs = unchangedInputs()
            db.exec(`CREATE TRIGGER fixture_fail_clock_rank BEFORE INSERT ON leaderboard_settlement_results
                WHEN NEW.rank_number=2 BEGIN SELECT RAISE(ABORT,'clock fixture later reward failure'); END`)
            try {
                await assert.rejects(background.runLeaderboardSettlementInBackground(job), /clock fixture later reward failure/)
            } finally { db.exec('DROP TRIGGER fixture_fail_clock_rank') }
            emptyAwards()
            assert.deepEqual(playerRows(), initialPlayers)
            assert.deepEqual(db.prepare('SELECT * FROM leaderboard_availability WHERE competition_key=?').get(key), initialAvailability)
            assert.deepEqual(unchangedInputs(), initialInputs, 'failed settlement must preserve plans and recorded scores')
        }
        const outcome = await background.runLeaderboardSettlementInBackground(job)
        assert.equal(outcome?.ok, true)
        assert.equal(outcome.rankedPlayers, 4)
        assert.equal(outcome.rewardedPlayers, 4)
        assert.equal(count('leaderboard_settlements'), 1)
        const results = db.prepare(`SELECT player_id,rank_number,mail_ids_json,skip_reason
            FROM leaderboard_settlement_results ORDER BY rank_number`).all()
        assert.deepEqual(results.map(row => row.player_id), ids)
        const mailIds = results.flatMap(row => { assert.equal(row.skip_reason, null); return JSON.parse(row.mail_ids_json) })
        assert.ok(mailIds.length >= 4)
        assert.equal(new Set(mailIds).size, mailIds.length)
        assert.equal(count('players_mails'), mailIds.length)
        for (const result of results) for (const id of JSON.parse(result.mail_ids_json)) {
            const mail = db.prepare('SELECT player_id,receive_time FROM players_mails WHERE id=?').get(id)
            assert.equal(mail.player_id, result.player_id)
            assert.equal(mail.receive_time, '0000-00-00 00:00:00')
        }
        const beforeReplay = db.prepare('SELECT * FROM players_mails ORDER BY id').all()
        if (job.scheduled) {
            assert.equal(await background.runLeaderboardSettlementInBackground(job), null)
            assert.deepEqual(db.prepare(`SELECT auto_enabled,freeze_enabled,settle_at_ms
                FROM leaderboard_settlement_configs WHERE competition_key=?`).get(key),
            { auto_enabled: 0, freeze_enabled: 0, settle_at_ms: null })
        } else {
            const repeat = await background.runLeaderboardSettlementInBackground(job)
            assert.equal(repeat.settlementId, outcome.settlementId)
            assert.equal(repeat.reason, 'already-settled')
        }
        assert.deepEqual(db.prepare('SELECT * FROM players_mails ORDER BY id').all(), beforeReplay)
        assert.deepEqual(playerRows(), initialPlayers, 'unclaimed rewards must not change player balances or fields')
        if (initialClock) assert.deepEqual(db.prepare('SELECT * FROM server_clock_state').get(), initialClock)
        else assert.equal(clock.readServerClockStateSync(db), null, 'legacy settlement must not create clock state')
        return { name, ranked: 4, rewarded: 4, mailCount: mailIds.length, replayUnchanged: true }
    } finally {
        await load('lib/persistence-coordinator').drainPersistence()
        await load('lib/seed-validator').default.close()
        if (db.open) db.close()
        assert.equal(path.dirname(directory), temporaryRoot)
        fs.rmSync(directory, { recursive: true })
    }
}

if (process.argv[2] === '--child') {
    scenario(process.argv[3]).then(value => { console.log('RESULT ' + JSON.stringify(value)); process.exit(0) },
        error => { console.error(error); process.exit(1) })
} else {
    for (const name of scenarios) test(`leaderboard worker clock: ${name}`, { timeout: 120000 }, async () => {
        const { stdout } = await promisify(execFile)(process.execPath, [__filename, '--child', name],
            { windowsHide: true, timeout: 90000, maxBuffer: 2_000_000 })
        const result = stdout.split('\n').find(line => line.startsWith('RESULT '))
        assert.ok(result, stdout)
        console.log(result)
    })
}
