'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict'), fs = require('node:fs'), crypto = require('node:crypto')
const ts = require('typescript'), Sqlite = require('better-sqlite3')
const original = require.extensions['.ts']
require.extensions['.ts'] = (mod, filename) => mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText, filename)
let library, Store
try {
    library = require('../src/lib/reported-content-repair.ts')
    Store = require('../src/lib/content-operations-store.ts')
} finally { if (original) require.extensions['.ts'] = original; else delete require.extensions['.ts'] }
const now = Date.parse('2026-10-31T06:00:00Z'), sha = x => crypto.createHash('sha256').update(x).digest('hex')
const keys = ['boss_coin_shop:990099002', 'boss_coin_shop:990099032', 'boss_coin_shop:990099033', 'gacha:990005',
    'tower_dungeon_event:1', 'challenge_dungeon_event:1', 'gacha:42']
function fixture(t) {
    const db = new Sqlite(':memory:'); t.after(() => db.close()); Store.initializeContentOperationsSchema(db)
    db.exec(`CREATE TABLE retained_player_progress(id INTEGER PRIMARY KEY,payload TEXT);
        INSERT INTO retained_player_progress VALUES(1,'purchases,stock,gacha-points,old-first-clears,claimed-rewards,active-play');
        CREATE TABLE town_presentation_state(id INTEGER PRIMARY KEY,value_json TEXT);
        INSERT INTO town_presentation_state VALUES(1,'manual town unchanged');`)
    const questMap = Object.fromEntries([
        ...Array.from({ length: 480 }, (_, index) => [`20:${1001 + index}`, 'tower_dungeon_event:1']),
        ...Array.from({ length: 40 }, (_, index) => [`13:${1001 + index}`, 'challenge_dungeon_event:1']),
    ])
    const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: sha('synthetic') },
        baselineTimeMs: 1, baselineEvidence: 'synthetic', missing: [], resources: {}, questMap,
        rows: keys.map(key => ({ key, type: key.split(':')[0], id: Number(key.split(':')[1]), name: key,
            originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: 3,
            windowCandidate: true, browseCandidate: true, source: 'synthetic' })) }
    const store = new Store.ContentOperationsStore(db, catalog, () => Store.CONTENT_ACTIONS,
        row => ({ digest: sha(row.key), matchesCatalog: true }))
    const open = { enabled: true, endsAtMs: null, readiness: 'verified', evidence: 'synthetic original review' }
    store.update('gacha:990005', { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'synthetic original publication',
        actionOverrides: { visible: open, enter: open, exchange: { ...open, enabled: false } } }, now)
    store.update('gacha:42', { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'synthetic unrelated operator choice',
        actionOverrides: { visible: { ...open, enabled: false } } }, now)
    // Represents already deployed history expansion; new update guards must reject creating it again.
    for (const key of ['tower_dungeon_event:1', 'challenge_dungeon_event:1']) {
        const row = { key, instanceId: key + ':original', readiness: 'unverified', evidence: '',
            flags: { visible: false, enter: false, claim: false, exchange: false }, endsAtMs: null,
            revision: store.revision(), catalogDigest: store.digest, contentDigest: store.contentDigests.get(key), controlled: true,
            actionOverrides: { visible: { ...open, catalogDigest: store.digest, contentDigest: store.contentDigests.get(key) },
                enter: { ...open, catalogDigest: store.digest, contentDigest: store.contentDigests.get(key),
                    questKeys: Object.keys(questMap).filter(member => questMap[member] === key) } } }
        db.prepare('INSERT INTO content_operations_state VALUES(?,?)').run(key, JSON.stringify(row))
    }
    const snapshot = () => JSON.stringify({ state: db.prepare('SELECT * FROM content_operations_state ORDER BY content_key').all(),
        meta: db.prepare('SELECT * FROM content_operations_meta').all(), audit: db.prepare('SELECT * FROM content_operations_audit ORDER BY revision').all() })
    const apply = plan => library.applyReportedContentRepairOfflineSync(store, plan, { expectedPlanDigest: plan.digest, nowMs: now })
    return { db, store, snapshot, apply }
}
test('six exact control corrections preserve player progress, instance IDs, town and unrelated decisions', t => {
    const f = fixture(t), before = f.snapshot(), player = f.db.prepare('SELECT * FROM retained_player_progress').all()
    const town = f.db.prepare('SELECT * FROM town_presentation_state').all(), unrelated = f.store.state('gacha:42')
    const plan = library.buildReportedContentRepairPlanSync(f.store, now)
    assert.equal(f.snapshot(), before, 'preview must not write')
    assert.equal(plan.changes.length, 6)
    assert.equal(f.apply(plan).updatedKeys.length, 6)
    for (const key of keys.slice(0, 4)) assert.equal(f.store.allowed(key, 'exchange', now), true)
    const tower = f.store.state('tower_dungeon_event:1')
    assert.equal(tower.instanceId, 'tower_dungeon_event:1:original')
    assert.deepEqual(tower.actionOverrides.enter.questKeys, Array.from({ length: 10 }, (_, i) => `20:${1381 + i}`))
    assert.deepEqual(tower.actionOverrides.visible.questKeys, tower.actionOverrides.enter.questKeys)
    assert.equal(f.store.state('challenge_dungeon_event:1').actionOverrides.enter.questKeys.length, 22)
    assert.equal(f.store.scopedAllowed('challenge_dungeon_event:1', 'quest', '13:1020', 'visible', now), false)
    assert.equal(f.store.scopedAllowed('challenge_dungeon_event:1', 'quest', '13:1038', 'enter', now), true)
    assert.deepEqual(f.db.prepare('SELECT * FROM retained_player_progress').all(), player)
    assert.deepEqual(f.db.prepare('SELECT * FROM town_presentation_state').all(), town)
    assert.deepEqual(f.store.state('gacha:42'), unrelated)
    const next = library.buildReportedContentRepairPlanSync(f.store, now + 1)
    assert.equal(next.changes.length, 0)
    assert.equal(f.apply(next).applied, false)
})
test('stale revision, tampered patch and changed source identity reject before any writes', t => {
    const f = fixture(t), plan = library.buildReportedContentRepairPlanSync(f.store, now)
    const edited = structuredClone(plan); edited.changes[0].actionOverrides.exchange.enabled = false
    let before = f.snapshot(); assert.throws(() => f.apply(edited), /计划或运营状态/); assert.equal(f.snapshot(), before)
    f.db.prepare('UPDATE content_operations_meta SET revision=revision+1').run()
    before = f.snapshot(); assert.throws(() => f.apply(plan), /计划或运营状态/); assert.equal(f.snapshot(), before)
    const current = library.buildReportedContentRepairPlanSync(f.store, now)
    const originalDigest = f.store.contentDigests.get('boss_coin_shop:990099033')
    f.store.contentDigests.set('boss_coin_shop:990099033', sha('new authoritative product definition'))
    assert.throws(() => f.apply(current), /计划或运营状态/); assert.equal(f.snapshot(), before)
    f.store.contentDigests.set('boss_coin_shop:990099033', originalDigest)
    f.store.rows.delete('boss_coin_shop:990099033')
    assert.throws(() => f.apply(current), /缺少原内容/); assert.equal(f.snapshot(), before)
})
test('late failure rolls all preceding corrections and audit rows back', t => {
    const f = fixture(t), plan = library.buildReportedContentRepairPlanSync(f.store, now), before = f.snapshot()
    f.db.exec(`CREATE TRIGGER reject_last_repair BEFORE UPDATE ON content_operations_state
        WHEN NEW.content_key='challenge_dungeon_event:1' BEGIN SELECT RAISE(ABORT,'synthetic late failure'); END`)
    assert.throws(() => f.apply(plan), /synthetic late failure/)
    assert.equal(f.snapshot(), before)
})
test('an explicit publication close requires review instead of silently reopening content', t => {
    const f = fixture(t), state = f.store.state('gacha:990005'); state.published = false
    f.db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(state), state.key)
    const before = f.snapshot()
    assert.throws(() => library.buildReportedContentRepairPlanSync(f.store, now), /运营关闭/)
    assert.equal(f.snapshot(), before)
})
test('expired, blocked and stale action identities cannot be reapproved by a repair', t => {
    for (const mutate of [
        action => { action.endsAtMs = now - 1 },
        action => { action.readiness = 'blocked' },
        action => { action.contentDigest = sha('changed definition') },
        action => { action.catalogDigest = sha('changed catalog') },
        action => { action.enabled = false },
    ]) {
        const f = fixture(t), state = f.store.state('tower_dungeon_event:1')
        mutate(state.actionOverrides.enter)
        f.db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(state), state.key)
        const before = f.snapshot()
        assert.throws(() => library.buildReportedContentRepairPlanSync(f.store, now), /审核|核对|身份/)
        assert.equal(f.snapshot(), before)
    }
})
test('offline CLI rejects a registered source-worktree target before opening it', () => {
    const path = require('node:path'), { spawnSync } = require('node:child_process')
    const directory = fs.mkdtempSync(path.join(process.env.TEMP || path.join(__dirname, '../tmp'), 'protected-repair-'))
    const database = path.join(directory, 'untouched.db'), payload = Buffer.from('must not be opened as a database')
    fs.writeFileSync(database, payload)
    const result = spawnSync(process.execPath, [path.join(__dirname, '../tools/repair-reported-content.cjs'),
        '--database', database, '--allowed-root', directory, '--plan', path.join(directory, 'plan.json')],
        { encoding: 'utf8', windowsHide: true, timeout: 10000 })
    assert.notEqual(result.status, 0)
    assert.match(result.stderr, /Protected source\/worktree database/)
    assert.deepEqual(fs.readFileSync(database), payload)
    assert.equal(fs.existsSync(path.join(directory, 'plan.json')), false)
    assert.equal(fs.existsSync(database + '-wal'), false)
})
