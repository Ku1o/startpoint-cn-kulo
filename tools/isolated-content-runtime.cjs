'use strict'
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict')
const { spawnSync } = require('node:child_process'), { createHash } = require('node:crypto')
const { isMainThread, threadId } = require('node:worker_threads')
const repo = path.resolve(__dirname, '..'), load = name => require(path.join(repo, 'out', name))
const command = 'isolated.runtime.probe'
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex')
const inputNames = ['out/cn-server.js', 'out/utils.js', 'out/data/activeAccount.js', 'out/lib/server-clock-state.js', 'out/lib/content-operations.js', 'out/lib/content-operations-store.js', 'out/lib/content-operations-bootstrap.js', 'out/lib/persistence/writer-client.js', 'out/workers/sqlite-writer-worker.js', 'out/routes/cn/load.js', 'assets/content_catalog.json', 'assets/content_july_controls.json', 'assets/asset-patch/manifest.json']
inputNames.push('out/lib/content-discovery.js', 'assets/content_discovery.json')
inputNames.push('assets/content_history_definition_runtime.json')
inputNames.push('assets/content_native_identities_runtime.json')
inputNames.push('out/lib/content-july-reference.js', 'out/lib/content-operations-defaults.js', 'out/lib/box-gacha-policy.js',
    'out/lib/mission/pass-battle-facts.js')
inputNames.push('out/lib/shop-quota.js', 'out/lib/content-definition-evidence.js', 'out/lib/content-economy-operations.js', 'out/routes/web_api/content.js', 'out/routes/api/shop.js', 'out/routes/api/howToGet.js', 'out/routes/api/passCard.js', 'out/routes/api/specialExchange.js', 'out/routes/api/startDashExchange.js', 'out/data/domains/player.js', 'out/lib/persistence-coordinator.js', 'out/content/runtime/content-snapshot.js')
inputNames.push('out/lib/content-client-reload.js', 'out/routes/web_api/server.js', 'out/server.js',
    'out/routes/api/index.js', 'out/multi/state/SessionManager.js', 'out/lounge/state.js',
    'out/multi/coordinator/runtime-command-handlers.js', 'out/multi/coordinator/business-handlers.js')
inputNames.push('out/routes/api/raidEvent.js', 'out/routes/api/storyQuest.js', 'out/routes/api/questUnlock.js',
    'out/routes/api/singleBattleQuest.js', 'out/routes/api/gacha.js', 'out/multi/http/battle.js',
    'out/lib/mission/battle-facts.js')
inputNames.push('out/lib/content-presentation.js', 'assets/content_presentation.json', 'assets/content_thumbnails/index.json', 'web/dist/index.html')
inputNames.push('out/lib/content-history-bootstrap.js', 'out/lib/content-history-readiness.js',
    'out/lib/content-quest-rules.js', 'assets/content_history_quest_rules.json',
    'out/lib/stamina-cost.js',
    'out/lib/mission/content-action-facts.js', 'out/lib/mission/collect-progress.js',
    'out/lib/mission/collect-battle-facts.js', 'out/lib/mission/pass.js', 'out/lib/mission/rescue-battle-facts.js',
    'out/lib/raid-event-config.js', 'out/lib/raidEventGlobal.js', 'out/lib/ranking-event-rewards.js',
    'out/lib/activity-degree-rewards.js', 'out/lib/gacha-exec-plan.js', 'out/lib/gacha-rules.js',
    'out/routes/api/rankingEvent.js', 'out/routes/api/character.js', 'out/routes/api/character/mana.js',
    'out/routes/api/equipment.js', 'out/routes/api/party.js', 'out/routes/api/profile.js',
    'out/lib/quest/finish/multi-finish-transaction.js', 'out/multi/coordinator/five-boss-command-handlers.js',
    'out/multi/http/five-boss-battle.js', 'out/multi/five-boss/battle-runtime.js',
    'assets/content_history_readiness.json', 'assets/content_history_definition_evidence.json',
    'assets/raid_event_rules.json', 'assets/raid_event_overall_reward.json',
    'assets/raid_event_ranking_reward.json', 'assets/ranking_event_ranking_reward.json')
inputNames.push('out/lib/gameplay-request-identity.js', 'out/lib/player-login.js', 'out/routes/cn/tool.js',
    'out/data/domains/crazy_gacha.js', 'out/lib/crazy-gacha.js',
    'out/data/initializers/wdfpData.js', 'out/data/types.js', 'out/data/domains/gacha.js',
    'out/data/utils/player-data.js', 'out/data/utils/client-player-snapshot.js',
    'out/data/snapshots/player-snapshot.js', 'out/lib/quest/finish/challenge-point.js',
    'out/lib/quest/finish/single-finish-transaction.js', 'out/routes/api/multiSpecialExchange.js',
    'out/lib/mission/active-master-data.js', 'out/lib/mission/active-core.js',
    'out/lib/mission/active-reconciliation.js', 'out/lib/mission/rewards.js')
inputNames.push('out/lib/content-shop-rules.js', 'out/lib/types/shop.js', 'assets/content_history_shop_rules.json')
inputNames.push('out/lib/assets.js', 'out/lib/content-master.js', 'out/lib/shop-sales.js', 'out/lib/multi-special-exchange.js',
    'out/lib/time-cutover-rehearsal.js', 'out/lib/battle-clock-compatibility.js', 'out/data/index.js', 'out/data/db.js',
    'src/lib/assets.ts', 'src/lib/content-master.ts', 'src/lib/shop-sales.ts', 'src/lib/multi-special-exchange.ts',
    'src/lib/content-quest-rules.ts', 'src/lib/content-shop-rules.ts')
const inputs = () => {
    const adminAssets = fs.readdirSync(path.join(repo, 'web/dist/assets')).filter(name => /\.(?:js|css)$/.test(name)).sort().map(name => 'web/dist/assets/' + name)
    const thumbnails = JSON.parse(fs.readFileSync(path.join(repo, 'assets/content_thumbnails/index.json'), 'utf8'))
    const thumbnailAssets = Object.keys(thumbnails.images).sort().map(hash => {
        assert.match(hash, /^[a-f0-9]{64}$/)
        assert.equal(thumbnails.images[hash].file, hash + '.webp')
        return 'assets/content_thumbnails/' + hash + '.webp'
    })
    return Object.fromEntries([...inputNames, ...adminAssets, ...thumbnailAssets].map(name => [name, createHash('sha256').update(fs.readFileSync(path.join(repo, name))).digest('hex')]))
}
function business(db) { return Object.fromEntries(['players_category_missions', 'players_category_mission_stages', 'players_pass_cards', 'players_pass_card_rewards', 'players_items', 'players_active_quests', 'player_operation_receipts'].map(table => [table, db.prepare('SELECT * FROM ' + table + ' ORDER BY rowid').all()])) }
function probe() {
    const db = load('data/db').getDb(), utils = load('utils'), store = load('lib/content-operations').contentOperations()
    const battle = load('lib/battle-clock-compatibility'), realMs = utils.getRealServerDate().getTime()
    return { threadId, database: fs.realpathSync(db.name), clock: utils.getServerClockSnapshot(), nowMs: utils.getServerDate().getTime(), realMs, oldBattleOffsetMs: battle.getBattleClockDate(0).getTime() - realMs, newBattleOffsetMs: battle.getBattleClockDate(1).getTime() - realMs, revision: store.revision(), controls: db.prepare('SELECT count(*) n FROM content_operations_state').get().n, businessDigest: hash(business(db)) }
}
if (!isMainThread) load('lib/persistence/command-registry').registerWriterCommand(command, probe)
else if (process.argv.includes('--phase')) {
    phase(process.argv[process.argv.indexOf('--phase') + 1]).then(result => { console.log('ISOLATED_RESULT ' + JSON.stringify(result)); process.exit(0) }, error => { console.error(error); process.exit(1) })
} else if (require.main === module) {
    const resumeIndex = process.argv.indexOf('--resume')
    if (resumeIndex >= 0) {
        const directory = fs.realpathSync(process.argv[resumeIndex + 1])
        const env = JSON.parse(fs.readFileSync(path.join(directory, 'launch-env.json'), 'utf8'))
        assert.equal(fs.realpathSync(env.STARPOINT_ISOLATED_RUNTIME_ROOT), directory)
        startManual(directory, env)
    } else {
    const rootIndex = process.argv.indexOf('--root')
    if (rootIndex < 0) throw Error('Usage: node tools/isolated-content-runtime.cjs --root <dedicated external fixture root> [--serve]')
    if (process.argv.includes('--verify')) {
        const result = spawnSync(process.execPath, ['--test', path.join(repo, 'tests/isolated-content-runtime.test.cjs')], { cwd: repo, env: { ...process.env, STARPOINT_ISOLATED_RUNTIME_TEST_ROOT: path.resolve(process.argv[rootIndex + 1]) }, stdio: 'inherit', windowsHide: true })
        process.exit(result.status ?? 1)
    }
    const result = run({ root: process.argv[rootIndex + 1], serve: process.argv.includes('--serve') })
    console.log(JSON.stringify(result, null, 2))
    }
}
function run({ root, serve = false }) {
    root = path.resolve(root)
    let ancestor = root
    const missing = []
    while (!fs.existsSync(ancestor)) { missing.unshift(path.basename(ancestor)); const parent = path.dirname(ancestor); assert.notEqual(parent, ancestor); ancestor = parent }
    const physical = path.join(fs.realpathSync(ancestor), ...missing)
    const registered = spawnSync('git', ['worktree', 'list', '--porcelain'], { cwd: repo, encoding: 'utf8', windowsHide: true })
    assert.equal(registered.status, 0)
    for (const match of registered.stdout.matchAll(/^worktree (.+)$/gm)) {
        const relative = path.relative(fs.realpathSync(match[1].trim()), physical)
        assert.ok(relative.startsWith('..' + path.sep) || relative === '..' || path.isAbsolute(relative), 'Fixture must be outside every registered worktree')
    }
    fs.mkdirSync(physical, { recursive: true })
    const directory = fs.mkdtempSync(path.join(physical, 'run-'))
    for (const name of ['data', 'tmp', 'seeds', 'logs', 'config']) fs.mkdirSync(path.join(directory, name))
    // Existing content repositories intentionally resolve public master tables from cwd/assets.
    // Reuse the same worktree bytes; the child write guard resolves this alias and rejects writes.
    fs.symlinkSync(path.join(repo, 'assets'), path.join(directory, 'assets'), 'junction')
    fs.writeFileSync(path.join(directory, 'config', 'client-admission.json'), JSON.stringify({ enforce: false, updateMessage: 'Synthetic isolated runtime only', builds: [] }))
    fs.writeFileSync(path.join(directory, 'config', 'client-admission.keys.json'), '{}')
    fs.writeFileSync(path.join(directory, 'config', 'news.json'), JSON.stringify({ version: 1, popup: { enabled: false, news_id: null, mode: 'once_per_news', start_time: null, end_time: null }, news: [] }))
    // Deliberately inherit only OS/tool lookup variables, never real service overrides or secrets.
    const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|COMSPEC|PATHEXT|SYSTEMDRIVE|NUMBER_OF_PROCESSORS|PROCESSOR_ARCHITECTURE)$/i.test(key)))
    Object.assign(env, { STARPOINT_ISOLATED_RUNTIME_ROOT: directory, DATA_DIR: path.join(directory, 'data'), TMP: path.join(directory, 'tmp'), TEMP: path.join(directory, 'tmp'), TMPDIR: path.join(directory, 'tmp'), GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_LOG_DIR: path.join(directory, 'logs'), NEWS_CONFIG_PATH: path.join(directory, 'config', 'news.json'), CLIENT_ADMISSION_CONFIG: path.join(directory, 'config', 'client-admission.json'), CLIENT_ADMISSION_KEYS: path.join(directory, 'config', 'client-admission.keys.json'), CN_RUNTIME_IMPORT_ONLY: '1', CN_LISTEN_HOST: '127.0.0.1', CN_LISTEN_PORT: '0', SESSION_HOST: '127.0.0.1', SESSION_PORT: '0', MULTI_REALTIME_PROCESS: '0', CN_MULTICORE: '0', CN_RESPONSE_WORKERS: '0', CN_WRITER_THREAD: '0', GAME_ROUTINE_LOGS: 'off', GAME_VERBOSE_LOGS: 'false', ADMIN_PANEL_PASSWORD: 'synthetic-isolated-local-test', SQLITE_WRITER_EXTRA_COMMANDS: __filename, GRACEFUL_SHUTDOWN_TIMEOUT_MS: '5000' })
    env.CDN_DIR = path.join(repo, '.cdn')
    env.SQLITE_TMPDIR = path.join(directory, 'tmp')
    fs.writeFileSync(path.join(directory, 'launch-env.json'), JSON.stringify(env, null, 2))
    const results = []
    const inputIdentity = inputs()
    for (const name of ['uninitialized-defaults', 'seed', 'first-start', 'restart', 'listener-smoke']) {
        assert.deepEqual(inputs(), inputIdentity, 'Compiled runtime or plan changed during verification; wait for the coordinated build and retry a fresh run')
        const child = spawnSync(process.execPath, ['--require', path.join(__dirname, 'isolated-runtime-fs-guard.cjs'), __filename, '--phase', name], { cwd: directory, env, encoding: 'utf8', timeout: 90000, windowsHide: true, maxBuffer: 8 * 1024 * 1024 })
        fs.writeFileSync(path.join(directory, name + '.log'), child.stdout + child.stderr)
        assert.equal(child.status, 0, name + ': ' + child.stdout + child.stderr)
        const line = child.stdout.split(/\r?\n/).find(line => line.startsWith('ISOLATED_RESULT '))
        assert.ok(line, name + ': result missing'); results.push(JSON.parse(line.slice(16)))
    }
    assert.deepEqual(inputs(), inputIdentity, 'Runtime inputs changed before report')
    const audit = fs.readFileSync(path.join(directory, 'path-audit.jsonl'), 'utf8').trim().split(/\r?\n/).map(JSON.parse)
    assert.ok(audit.some(row => row.kind === 'sqlite-open' && row.threadId > 0), 'actual worker opens isolated DB')
    const report = { schema: 1, directory, repo, compiledEntry: path.join(repo, 'out/cn-server.js'), compiledEntrySha256: inputIdentity['out/cn-server.js'], inputIdentity, results, isolation: { allAuditedPathsConfined: true, interceptedOperations: audit.length, sqliteConnections: audit.filter(row => row.kind === 'sqlite-open'), realServiceTouched: false, config: 'generated synthetic admission; no real configs copied', listeners: 'inject plus auto-closed 127.0.0.1 port 0 smoke; no multiplayer transport', cdn: { requested: env.CDN_DIR, physical: fs.realpathSync(env.CDN_DIR), use: 'read-only use enforced by harness write guard; no filesystem ACL change', patchManifest: path.join(repo, 'assets/asset-patch/manifest.json') } }, manualCommand: `node "${__filename}" --resume "${directory}"` }
    fs.writeFileSync(path.join(directory, 'result.json'), JSON.stringify(report, null, 2) + '\n')
    fs.writeFileSync(path.join(physical, 'latest.json'), JSON.stringify({ directory, report: path.join(directory, 'result.json'), env }, null, 2) + '\n')
    if (serve) return startManual(directory, env)
    return report
}
async function phase(name) {
    const directory = process.env.STARPOINT_ISOLATED_RUNTIME_ROOT, db = load('data/db').getDb(), utils = load('utils')
    for (const forbidden of [path.join(repo, '.isolated-write-probe'), path.join(repo, '.cdn', '.isolated-write-probe'), path.join(directory, 'assets', '.isolated-write-probe')]) {
        assert.throws(() => fs.writeFileSync(forbidden, 'must not write'), /ISOLATED_WRITE_OUTSIDE_ROOT/)
        assert.equal(fs.existsSync(forbidden), false)
    }
    if (name === 'uninitialized-defaults') {
        const empty = new (require('better-sqlite3'))(':memory:')
        load('data/db').setDbOverride(empty)
        try {
            assert.equal(empty.prepare("SELECT 1 FROM sqlite_master WHERE name='content_operations_meta'").get(), undefined)
            const ops = load('lib/content-operations')
            const key = load('lib/content-operations-bootstrap').julyContentPlan.controls.find(row => row.key.startsWith('gacha:')).key
            assert.equal(ops.contentDecision('gacha', Number(key.split(':')[1]), 'enter', Date.now()), false)
            assert.equal(ops.contentQuestDecision(13, 999999999), false)
            assert.equal(ops.contentQuestDecision(2, 1001001), null)
            return { name, absentMetaSeasonalFirstDecisionDenied: true, ordinaryQuestFallbackPreserved: true, scenario: 'unmigrated override connection; normal application initialization separately covered' }
        } finally { load('data/db').setDbOverride(null); empty.close(); db.close() }
    }
    assert.equal(fs.realpathSync(path.dirname(db.name)), fs.realpathSync(process.env.DATA_DIR))
    const bootstrap = load('lib/content-operations-bootstrap'), store = load('lib/content-operations').contentOperations()
    const expectedFile = path.join(directory, 'expected.json'), guard = { kind: 'approved-offline-file', databasePath: fs.realpathSync(db.name), allowedRoot: directory }
    if (name === 'seed') {
        const now = Date.now(), offset = -420 * 86400000 - 12345, legacyNow = now + offset
        utils.setServerTimeOffset(offset)
        const players = load('data/domains/player'), accounts = load('data/domains/account'), ids = []
        utils.withServerClock(legacyNow, () => {
            for (let index = 0; index < 2; index++) {
                const account = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'isolated-runtime', idpId: 'synthetic-' + index, status: 'normal' })
                const p = players.insertDefaultPlayerSync(account.id); ids.push(p.id)
                players.updatePlayerSync({ id: p.id, expPool: 777 + index, timeOffset: index ? null : offset, expPooledTime: new Date(legacyNow - 30000), lastLoginTime: new Date(legacyNow), totalLoginDays: 19 })
                load('data/activeAccount').saveAccountDefaultPlayer(account.id, p.id)
                db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(880000000 + p.id), account.id, '2099-01-01T00:00:00Z')
                load('data/domains/mission').updatePlayerCategoryMissionSync(p.id, 6, 53, 11)
                load('data/domains/mission').updatePlayerCategoryMissionStageSync(p.id, 6, 1, 53, true)
                load('data/domains/item').setPlayerItemSync(p.id, 14040, 17)
                load('data/domains/pass-card').addPlayerPassCardPointSync(p.id, 15, 777)
                db.prepare('UPDATE players_pass_cards SET is_buy=1 WHERE player_id=? AND event_id=15').run(p.id)
                load('data/domains/pass-card').setPlayerPassCardRewardReceivedSync(p.id, 15, 841, true, true)
                load('data/domains/quest_active').insertPlayerActiveQuestSync(p.id, { playerId: p.id, playId: 'retained-old-' + index, questId: 1001001, category: 2, isMulti: false, isMultiHost: false, roomNumber: null, useBoostPoint: false, useBossBoostPoint: false, isAutoStartMode: false, continueCount: 0, startedAtMs: index ? null : legacyNow - 60000, partySlot: 1 })
                db.prepare('UPDATE players_active_quests SET clock_version=0 WHERE player_id=?').run(p.id)
                db.prepare('INSERT INTO player_operation_receipts VALUES(?,?,?,?,?)').run(p.id, 'synthetic.claim', 'already-paid', '{"paid":true}', now)
            }
        }, offset)
        const retained = business(db)
        const applied = bootstrap.applyJulyContentPlanOfflineSync(store, { expectedRevision: store.revision(), expectedCatalogDigest: store.digest, nowMs: now, offlineGuard: guard })
        assert.equal(applied.controls, bootstrap.julyContentPlan.controls.length)
        const options = { cutoverRealMs: now, legacyOffsetMs: offset, offlineGuard: guard }
        const plan = load('lib/time-cutover-rehearsal').planTimeCutoverRehearsalSync(db, options)
        load('lib/server-clock-state').activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: plan.digest, readiness: 'scenario-only' })
        assert.deepEqual(business(db), retained)
        const expected = { ids, controls: applied.controls, businessDigest: hash(retained) }
        fs.writeFileSync(expectedFile, JSON.stringify(expected))
        db.close()
        return { name, players: ids.length, controls: applied.controls, nonemptyRetainedProgress: true }
    }
    const expected = JSON.parse(fs.readFileSync(expectedFile, 'utf8'))
    // Import the actual compiled application: route graph, clock restore, authentication,
    // startup migration and all onClose hooks. No substitute Fastify registration.
    const app = load('cn-server').fastify
    await app.ready()
    const writer = load('lib/persistence/writer-client'), coordinator = load('lib/persistence-coordinator')
    try {
        const before = probe()
        assert.equal(before.clock.mode, 'real'); assert.equal(before.clock.businessOffsetMs, 0); assert.ok(Math.abs(before.nowMs - before.realMs) <= 5)
        assert.ok(Math.abs(before.oldBattleOffsetMs - before.clock.legacyBattleOffsetMs) <= 5); assert.ok(Math.abs(before.newBattleOffsetMs) <= 5)
        assert.equal(before.businessDigest, expected.businessDigest); assert.equal(before.controls, expected.controls)
        if (name === 'first-start') { expected.clock = before.clock; fs.writeFileSync(expectedFile, JSON.stringify(expected)) }
        else assert.deepEqual(before.clock, expected.clock)
        const unauthorized = await app.inject('/api/content/'); assert.equal(unauthorized.statusCode, 401)
        const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
        assert.equal(login.statusCode, 200, login.body)
        const cookie = login.headers['set-cookie'].split(';')[0]
        const admin = async (url, options = {}) => app.inject({ url, ...options, headers: { cookie } })
        const current = (await admin('/api/server/currentTime')).json()
        assert.equal(current.clockMode, 'real'); assert.equal(current.isCustom, false)
        assert.ok(Math.abs(current.servertime * 1000 - Date.now()) < 2000)
        assert.equal((await admin('/api/server/resetTime')).statusCode, 409)
        const listing = await admin('/api/content/?limit=200'); assert.equal(listing.statusCode, 200)
        // The technical closure check includes members explicitly; the daily admin view now lists parents only.
        const julyResponse = await admin('/api/content/?julyOnly=true&includeMembers=true&limit=200')
        assert.equal(julyResponse.statusCode, 200, julyResponse.body)
        const july = julyResponse.json(), reference = july.permanentReference
        assert.equal(reference.date, '2025-07-20'); assert.equal(reference.timeZone, 'UTC+08:00')
        assert.equal(reference.startMs, bootstrap.julyContentPlan.referenceStartMs)
        assert.equal(reference.endMsExclusive, bootstrap.julyContentPlan.referenceEndMsExclusive)
        const covers = row => !row.personalWindow && (row.originalStartMs === null || row.originalStartMs <= reference.startMs) && (row.originalEndMs === null || row.originalEndMs >= reference.endMsExclusive - 1000)
        assert.ok(july.rows.length > 0); assert.ok(july.rows.every(covers))
        assert.equal(july.total, load('lib/content-operations').contentCatalog.rows.filter(covers).length)
        assert.equal((await admin('/api/content/?julyOnly=invalid')).statusCode, 400)
        const row = bootstrap.julyContentPlan.controls.find(control => control.key.startsWith('gacha:') && control.actionOverrides.enter?.enabled)
        assert.ok(row, 'current plan supplies a controlled pool')
        const original = store.state(row.key)
        const change = enabled => admin('/api/content/' + encodeURIComponent(row.key), { method: 'PATCH', payload: { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic isolated close/reopen preservation check', actionOverrides: { enter: { enabled, endsAtMs: null, readiness: 'verified', evidence: 'Current reviewed plan synthetic lifecycle test' } } } })
        assert.equal((await change(false)).statusCode, 200)
        assert.equal(load('lib/content-operations').contentDecision('gacha', Number(row.key.split(':')[1]), 'enter', Date.now()), false)
        assert.equal(hash(business(db)), expected.businessDigest)
        assert.equal((await change(true)).statusCode, 200)
        assert.equal(store.state(row.key).instanceId, original.instanceId)
        const snapshotResponse = await app.inject({ method: 'POST', url: '/api/index.php/content_operations', payload: { viewer_id: 880000000 + expected.ids[0] } })
        assert.equal(snapshotResponse.statusCode, 200, snapshotResponse.body)
        const decoded = require('msgpackr').unpack(Buffer.from(snapshotResponse.body, 'base64'))
        assert.equal(decoded.data_headers.result_code, 1)
        assert.ok(decoded.data.content_operations)
        assert.ok(Math.abs(decoded.data_headers.servertime * 1000 - Date.now()) < 2000)
        const retained = await app.inject({ method: 'POST', url: '/api/index.php/Pass_card/get_retained_pass_cards', payload: { viewer_id: 880000000 + expected.ids[0] } })
        assert.equal(retained.statusCode, 200, retained.body)
        const cards = require('msgpackr').unpack(Buffer.from(retained.body, 'base64'))
        assert.equal(cards.data_headers.result_code, 1)
        assert.ok(cards.data.retained_pass_card_list.some(card => card.pass_card_id === 15 && card.point === 777 && card.is_buy))
        process.env.CN_WRITER_THREAD = '1'
        const workerIds = []
        for (let attempt = 0; attempt < 2; attempt++) {
            assert.equal(writer.startSqliteWriter(db.name), true); assert.equal(await writer.waitForSqliteWriterReady(30000), true)
            const result = await coordinator.runWriterCommand(command, {}, { domain: 'maintenance', operation: 'isolated_probe' }, () => { throw Error('Writer fallback forbidden') })
            assert.ok(result.threadId > 0); workerIds.push(result.threadId)
            assert.deepEqual(result.clock, before.clock); assert.equal(result.database, before.database)
            assert.ok(Math.abs(result.oldBattleOffsetMs - before.clock.legacyBattleOffsetMs) <= 5); assert.ok(Math.abs(result.newBattleOffsetMs) <= 5)
            assert.ok(Math.abs(result.nowMs - result.realMs) <= 5); assert.equal(result.controls, expected.controls)
            assert.equal(result.businessDigest, expected.businessDigest); assert.equal(result.revision, store.revision())
            await writer.stopSqliteWriter()
        }
        assert.notEqual(workerIds[0], workerIds[1])
        assert.equal(bootstrap.applyJulyContentPlanOfflineSync(store, { expectedRevision: store.revision(), expectedCatalogDigest: store.digest, nowMs: Date.now(), offlineGuard: guard }).applied, false)
        assert.equal(hash(business(db)), expected.businessDigest)
        assert.equal(db.pragma('quick_check', { simple: true }), 'ok')
        let listener
        if (name === 'listener-smoke') {
            await app.listen({ host: '127.0.0.1', port: 0 })
            const address = app.server.address()
            assert.equal(address.address, '127.0.0.1'); assert.ok(![8001, 8011].includes(address.port))
            const response = await fetch(`http://127.0.0.1:${address.port}/api/content/`)
            assert.equal(response.status, 401)
            listener = { host: address.address, port: address.port, actualHttpAuthentication: true, autoClosedInFinally: true }
        }
        return { name, routeGraph: 'actual out/cn-server.js', controls: expected.controls, clock: before.clock, adminAuthentication: true, managementCurrentTime: true, permanentReference: reference, julyRowsChecked: july.rows.length, julyTotal: july.total, julyWindowFilterIndependentOfLegacyCandidate: true, legacySetterRejected: true, closeReopenPreserved: true, publicSnapshot: true, retainedPaidPass: true, workerIds, workerClockEqual: true, legacyBattleCoordinatePreserved: true, restartPreserved: name === 'restart', businessDigest: expected.businessDigest, quickCheck: 'ok', listener, outsideWritesRejectedBeforeMutation: true }
    } finally { await writer.stopSqliteWriter(); await app.close(); if (db.open) db.close() }
}
function startManual(directory, env) {
    const result = spawnSync(process.execPath, ['--require', path.join(__dirname, 'isolated-runtime-fs-guard.cjs'), path.join(__dirname, 'isolated-content-runtime-serve.cjs')], { cwd: directory, env: { ...env, CN_RUNTIME_IMPORT_ONLY: '1' }, stdio: 'inherit', windowsHide: true })
    return { directory, exitCode: result.status }
}
module.exports = { run, inputs }
