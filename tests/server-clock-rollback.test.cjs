'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
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
function fixture(t, markerTableExisted = true, filename = ':memory:') {
    const db = new Database(filename)
    t.after(() => { if (db.open) db.close() })
    db.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY,exp_pool INTEGER,exp_pooled_time,time_offset,vmoney INTEGER);
        CREATE TABLE players_active_quests(player_id INTEGER PRIMARY KEY,play_id TEXT,started_at_ms INTEGER,clock_version INTEGER);
        CREATE TABLE claimed(player_id INTEGER,claimed INTEGER);
        CREATE TABLE mission_facts(player_id INTEGER,counter INTEGER);
        CREATE TABLE gacha_rights(player_id INTEGER,points INTEGER,is_buy INTEGER);
        CREATE TABLE pass_rights(player_id INTEGER,is_buy INTEGER,reward_claimed INTEGER);
        CREATE TABLE stock(item_id INTEGER,count INTEGER);
        CREATE TABLE lookup_cache(cache_key TEXT,value TEXT);
        CREATE TABLE business_receipts(request_id TEXT PRIMARY KEY,response BLOB);
        CREATE TABLE time_cutover_rehearsal_ledger(plan_digest TEXT,plan_json TEXT,after_digest TEXT,status TEXT);
        CREATE TABLE other_ledger(n INTEGER); PRAGMA user_version=17; PRAGMA application_id=120;`)
    if (markerTableExisted) db.exec(`CREATE TABLE player_time_state(player_id INTEGER PRIMARY KEY,version INTEGER,
        cutover_real_ms INTEGER,day_anchor_ms INTEGER,week_anchor_ms INTEGER)`)
    const insertPlayer = db.prepare('INSERT INTO players VALUES(?,?,?,?,?)')
    const insertPlay = db.prepare('INSERT INTO players_active_quests VALUES(?,?,?,?)')
    for (let id = 1; id <= 151; id++) {
        insertPlayer.run(id, id * 123, new Date(cutoverRealMs + legacyOffsetMs - id * 1000).toISOString(), legacyOffsetMs, id * 99)
        if (id > 2) insertPlay.run(id, `old-play-${id}`, cutoverRealMs + legacyOffsetMs - id * 1000, 0)
        else if (markerTableExisted) db.prepare('INSERT INTO player_time_state VALUES(?,1,?,?,?)')
            .run(id, cutoverRealMs - 90000, cutoverRealMs - 80000, cutoverRealMs - 70000)
    }
    db.exec(`INSERT INTO claimed VALUES(1,1); INSERT INTO mission_facts VALUES(1,12);
        INSERT INTO gacha_rights VALUES(1,250,1); INSERT INTO pass_rights VALUES(1,1,7);
        INSERT INTO stock VALUES(1,999); INSERT INTO lookup_cache VALUES('effective','old');
        INSERT INTO business_receipts VALUES('old',x'0102');
        INSERT INTO time_cutover_rehearsal_ledger VALUES('old','old','old','rolled-back');
        INSERT INTO other_ledger VALUES(9007199254740992)`)
    return db
}
function activate(db, extra = {}) {
    const plan = rehearsal.planTimeCutoverRehearsalSync(db, { ...options, ...extra })
    const state = core.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: plan.digest, ...extra })
    return { state, plan, rollback: { expectedPlanDigest: state.planDigest } }
}
const receiptRows = db => db.prepare(`SELECT * FROM ${core.SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE}`).safeIntegers().all()
function refuseWithoutWrites(db, callback, expected = /refused|receipt|snapshot|schema|clock|digest|version|integer/i) {
    const before = core.getServerClockPersistentFingerprintSync(db)
    const receipt = receiptRows(db)
    assert.throws(callback, expected)
    assert.equal(core.getServerClockPersistentFingerprintSync(db), before)
    assert.deepEqual(receiptRows(db), receipt)
}

test('explicit rollback restores exact player fields/schema, 2 existing v1 and 149 old plays without changing the process clock', t => {
    for (const markers of [true, false]) {
        const db = fixture(t, markers)
        const before = core.getServerClockPersistentFingerprintSync(db)
        const plays = db.prepare('SELECT * FROM players_active_quests').safeIntegers().all()
        const anchors = markers ? db.prepare('SELECT * FROM player_time_state').safeIntegers().all() : null
        const processBefore = utils.getServerClockSnapshot()
        const { state, rollback } = activate(db)
        assert.deepEqual(utils.getServerClockSnapshot(), processBefore)
        assert.deepEqual(core.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: state.planDigest }), state)
        const after = core.getServerClockPersistentFingerprintSync(db)
        const result = core.rollbackRealServerClockOfflineSync(db, rollback)
        assert.deepEqual(result, { status: 'rolled-back', planDigest: state.planDigest, beforeFingerprint: before, afterFingerprint: after })
        assert.equal(core.getServerClockPersistentFingerprintSync(db), before)
        assert.equal(core.readServerClockStateSync(db), null)
        assert.deepEqual(db.prepare('SELECT * FROM players_active_quests').safeIntegers().all(), plays)
        assert.equal(plays.length, 149)
        if (markers) assert.deepEqual(db.prepare('SELECT * FROM player_time_state').safeIntegers().all(), anchors)
        else assert.equal(db.prepare("SELECT 1 FROM sqlite_master WHERE name='player_time_state'").get(), undefined)
        assert.deepEqual(utils.getServerClockSnapshot(), processBefore)
        const receipt = receiptRows(db)
        assert.equal(core.rollbackRealServerClockOfflineSync(db, rollback).status, 'already-rolled-back')
        assert.deepEqual(receiptRows(db), receipt)
    }
})

test('activation and rollback fault boundaries restore entire schema/data/receipt atomically', t => {
    for (const faultAt of ['after-player-migration', 'after-clock-state', 'after-activation-receipt']) {
        const db = fixture(t, false)
        const before = core.getServerClockPersistentFingerprintSync(db)
        assert.throws(() => activate(db, { faultAt }), /Injected/)
        assert.equal(core.getServerClockPersistentFingerprintSync(db), before)
        assert.equal(db.prepare('SELECT 1 FROM sqlite_master WHERE name=?').get(core.SERVER_CLOCK_ROLLBACK_RECEIPT_TABLE), undefined)
    }
    for (const faultAt of ['after-player-restore', 'after-clock-restore', 'after-rollback-receipt']) {
        const db = fixture(t, false)
        const { rollback } = activate(db)
        refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, { ...rollback, faultAt }), /Injected/)
        assert.ok(core.readServerClockStateSync(db))
        assert.equal(core.rollbackRealServerClockOfflineSync(db, rollback).status, 'rolled-back')
    }
})

test('every new business fact, entitlement, balance, receipt, stock, lookup, ledger, anchor or schema change refuses rollback and keeps progress', t => {
    const mutations = [
        'UPDATE players SET exp_pool=exp_pool+1 WHERE id=1', 'UPDATE players SET vmoney=vmoney-1 WHERE id=3',
        'UPDATE claimed SET claimed=2', 'INSERT INTO mission_facts VALUES(3,99)',
        'UPDATE gacha_rights SET points=500', 'UPDATE pass_rights SET reward_claimed=8',
        'UPDATE stock SET count=count-1', "UPDATE lookup_cache SET value='new'",
        "INSERT INTO business_receipts VALUES('new',x'0103')", 'UPDATE other_ledger SET n=9007199254740993',
        "UPDATE time_cutover_rehearsal_ledger SET status='applied'", 'DELETE FROM players_active_quests WHERE player_id=3',
        'UPDATE player_time_state SET day_anchor_ms=day_anchor_ms+1 WHERE player_id=1',
        'UPDATE players SET time_offset=1 WHERE id=3', 'ALTER TABLE stock ADD COLUMN updated INTEGER',
        'PRAGMA user_version=18', 'PRAGMA application_id=121',
        "INSERT INTO players VALUES(999,7,NULL,NULL,8)",
    ]
    for (const sql of mutations) {
        const db = fixture(t)
        const { rollback } = activate(db)
        db.exec(sql)
        refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, rollback), /persistent state changed after activation/)
    }
})

test('receipt integrity, schema/version, expected digest and missing old-phase4 receipt all fail closed', t => {
    for (const sql of ["UPDATE server_clock_rollback_receipt SET receipt_json='{}'", "UPDATE server_clock_rollback_receipt SET receipt_digest='bad'",
        "UPDATE server_clock_rollback_receipt SET status='rolled-back'", 'ALTER TABLE server_clock_rollback_receipt ADD COLUMN extension TEXT',
        'PRAGMA ignore_check_constraints=ON; UPDATE server_clock_rollback_receipt SET version=2',
        'CREATE TRIGGER altered_receipt AFTER UPDATE ON server_clock_rollback_receipt BEGIN SELECT 1; END']) {
        const db = fixture(t)
        const { rollback } = activate(db)
        db.exec(sql)
        refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, rollback))
    }
    const db = fixture(t)
    const { state, rollback } = activate(db)
    refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, { expectedPlanDigest: '0'.repeat(64) }), /digest mismatch/)
    db.exec('DROP TABLE server_clock_rollback_receipt')
    const before = core.getServerClockPersistentFingerprintSync(db)
    assert.deepEqual(core.readServerClockStateSync(db), state, 'old real state remains read-compatible')
    assert.throws(() => core.rollbackRealServerClockOfflineSync(db, rollback), /No clock rollback receipt/)
    assert.throws(() => core.activateRealServerClockOfflineSync(db, { ...options, expectedPlanDigest: state.planDigest }), /no valid rollback receipt/)
    assert.equal(core.getServerClockPersistentFingerprintSync(db), before)
})

test('raw unsafe INTEGER and BLOB time before images restore exactly and adjacent 64-bit facts differ', t => {
    const db = fixture(t, false)
    db.exec('UPDATE players SET exp_pooled_time=9007199254740993,time_offset=9007199254740993 WHERE id=3')
    db.prepare('UPDATE players SET exp_pooled_time=?,time_offset=? WHERE id=4').run(Buffer.from([1, 2, 3]), Buffer.from([4, 5]))
    const beforeFields = db.prepare('SELECT exp_pooled_time,time_offset FROM players WHERE id IN (3,4) ORDER BY id').safeIntegers().all()
    const old = core.getServerClockPersistentFingerprintSync(db)
    db.exec('UPDATE other_ledger SET n=9007199254740993')
    assert.notEqual(core.getServerClockPersistentFingerprintSync(db), old)
    db.exec('UPDATE other_ledger SET n=9007199254740992')
    const { rollback } = activate(db)
    core.rollbackRealServerClockOfflineSync(db, rollback)
    assert.equal(core.getServerClockPersistentFingerprintSync(db), old)
    assert.deepEqual(db.prepare('SELECT exp_pooled_time,time_offset FROM players WHERE id IN (3,4) ORDER BY id').safeIntegers().all(), beforeFields)
})

test('offline guard rejects attached and nested transactions before any write', t => {
    const db = fixture(t)
    const { rollback } = activate(db)
    db.exec("ATTACH DATABASE ':memory:' AS extra")
    refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, rollback), /Attached databases/)
    db.exec('DETACH DATABASE extra')
    assert.throws(() => db.transaction(() => core.rollbackRealServerClockOfflineSync(db, rollback))(), /outside a transaction/)
})

test('guarded task file can activate/rollback; missing guard, wrong file/root and readonly connections refuse', t => {
    const root = process.env.STARPOINT_CLOCK_TEST_ROOT || require('node:os').tmpdir()
    fs.mkdirSync(root, { recursive: true })
    const dir = fs.mkdtempSync(path.join(root, 'clock-rollback-'))
    const filename = path.join(dir, 'synthetic.sqlite')
    const db = fixture(t, true, filename)
    const offlineGuard = { kind: 'approved-offline-file', databasePath: filename, allowedRoot: dir }
    const { rollback } = activate(db, { offlineGuard })
    refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, rollback), /explicit approved offline path guard/)
    const other = path.join(dir, 'other.sqlite')
    fs.writeFileSync(other, '')
    refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, { ...rollback, offlineGuard: { ...offlineGuard, databasePath: other } }), /path mismatch/)
    fs.mkdirSync(path.join(dir, 'outside'))
    refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, { ...rollback, offlineGuard: { ...offlineGuard, allowedRoot: path.join(dir, 'outside') } }), /outside approved offline scope/)
    const readonly = new Database(filename, { readonly: true })
    try { assert.throws(() => core.rollbackRealServerClockOfflineSync(readonly, { ...rollback, offlineGuard }), /writable explicit database/) }
    finally { readonly.close() }
    assert.equal(core.rollbackRealServerClockOfflineSync(db, { ...rollback, offlineGuard }).status, 'rolled-back')
})

test('rollback-only trigger side effects refuse the full before image and transaction restores applied state', t => {
    const db = fixture(t)
    db.exec(`CREATE TRIGGER legacy_update AFTER UPDATE ON players WHEN NEW.time_offset != 0
        BEGIN UPDATE mission_facts SET counter=counter+1; END`)
    const { rollback } = activate(db)
    refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, rollback), /restore exact full persistent before image/)
    assert.ok(core.readServerClockStateSync(db))
})

test('temporary shadow tables cannot hide new persistent facts from the fingerprint or offline rollback', t => {
    const db = fixture(t)
    const { rollback } = activate(db)
    const before = core.getServerClockPersistentFingerprintSync(db)
    db.exec('CREATE TEMP TABLE mission_facts AS SELECT * FROM main.mission_facts; UPDATE main.mission_facts SET counter=1000')
    assert.notEqual(core.getServerClockPersistentFingerprintSync(db), before)
    refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, rollback), /Temporary shadow/)
})

test('persistent REAL infinities never collapse to NULL or each other in the full fingerprint', t => {
    const db = fixture(t)
    db.exec('CREATE TABLE real_facts(value REAL); INSERT INTO real_facts VALUES(NULL)')
    const nullDigest = core.getServerClockPersistentFingerprintSync(db)
    db.exec('UPDATE real_facts SET value=1e999')
    const positive = core.getServerClockPersistentFingerprintSync(db)
    assert.notEqual(positive, nullDigest)
    db.exec('UPDATE real_facts SET value=-1e999')
    assert.notEqual(core.getServerClockPersistentFingerprintSync(db), nullDigest)
    assert.notEqual(core.getServerClockPersistentFingerprintSync(db), positive)
})

test('new facts after a completed rollback refuse repeat rollback and never delete those facts', t => {
    const db = fixture(t)
    const { rollback } = activate(db)
    core.rollbackRealServerClockOfflineSync(db, rollback)
    db.exec('INSERT INTO mission_facts VALUES(99,1000)')
    refuseWithoutWrites(db, () => core.rollbackRealServerClockOfflineSync(db, rollback), /persistent state changed after rollback/)
})
