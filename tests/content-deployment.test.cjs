'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { createHash } = require('node:crypto')
const Sqlite = require('better-sqlite3')
if (!process.env.STARPOINT_TEST_OUT_DIR) require('ts-node/register/transpile-only')
const base = process.env.STARPOINT_TEST_OUT_DIR || path.join(__dirname, '../src')
process.env.CDN_DIR = process.env.CDN_DIR || 'F:/codex/startpoint-cn-private-clean/.cdn'
const { initializeContentOperationsSchema } = require(path.join(base, 'lib/content-operations-store'))
const { createContentOperationsStore } = require(path.join(base, 'lib/content-operations'))
const { getDeploymentDatabaseFingerprintSync, withDeploymentMaintenanceTransactionSync } = require(path.join(base, 'lib/deployment-maintenance-guard'))
const { inspectContentDeploymentSync, applyContentDeploymentMaintenanceSync } = require(path.join(base, 'lib/content-deployment'))
const { julyContentPlan, applyJulyContentPlanOfflineSync } = require(path.join(base, 'lib/content-operations-bootstrap'))
const { completeExistingHistoryReviewsOfflineSync, prepareReviewedHistoryOfflineSync } = require(path.join(base, 'lib/content-history-bootstrap'))
const reviewed = require('../assets/content_deployment_review_plan.json')
const boxReview = require('../assets/content_box_exchange_review.json')
const presentation = require('../assets/content_presentation.json')
const shaFile = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex')
async function fixture(t) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'content-deployment-'))
    const target = path.join(directory, 'target.db'), backup = path.join(directory, 'backup.db')
    const db = new Sqlite(target)
    t.after(() => { db.close(); fs.rmSync(directory, { recursive: true, force: true }) })
    initializeContentOperationsSchema(db)
    db.exec("CREATE TABLE player_fact(id INTEGER PRIMARY KEY, earned INTEGER, claimed INTEGER); INSERT INTO player_fact VALUES(1,9,1)")
    const store = createContentOperationsStore(db)
    await db.backup(backup)
    const guard = { kind: 'approved-stopped-database', databasePath: target, backupPath: backup,
        expectedDatabaseFingerprint: getDeploymentDatabaseFingerprintSync(db), expectedBackupSha256: shaFile(backup) }
    return { db, store, guard }
}
async function legacyFixture(t) {
    const result = await fixture(t), { db, store, guard } = result
    const nowMs = Date.parse('2027-05-01T00:00:00Z')
    withDeploymentMaintenanceTransactionSync(db, guard, context => {
        applyJulyContentPlanOfflineSync(store, { expectedRevision: store.revision(), expectedCatalogDigest: store.digest,
            nowMs, maintenanceContext: context })
        completeExistingHistoryReviewsOfflineSync(store, reviewed.stage2,
            { expectedRevision: store.revision(), nowMs, maintenanceContext: context })
        prepareReviewedHistoryOfflineSync(store, reviewed.stage3,
            { expectedRevision: store.revision(), nowMs, maintenanceContext: context })
        db.exec(`CREATE TABLE content_operations_deployment (
            id INTEGER PRIMARY KEY CHECK(id=1), plan_digest TEXT NOT NULL, catalog_digest TEXT NOT NULL, applied_at_ms INTEGER NOT NULL)`)
        db.prepare('INSERT INTO content_operations_deployment VALUES(1,?,?,?)').run(reviewed.digest, store.digest, nowMs)
    })
    await db.backup(guard.backupPath)
    return { ...result, guard: { ...guard, expectedDatabaseFingerprint: getDeploymentDatabaseFingerprintSync(db),
        expectedBackupSha256: shaFile(guard.backupPath) } }
}

test('reviewed content deployment covers UI parents and preserves operator edits on repeat', async t => {
    const { db, store, guard } = await fixture(t)
    const initial = inspectContentDeploymentSync(store)
    assert.equal(initial.ready, false)
    assert.equal(initial.canApply, true)
    assert.equal(initial.counts.phase, 'initial')
    assert.equal(initial.counts.catalogParents, 1020)
    assert.equal(initial.counts.targetParentControls, 1018)
    const result = withDeploymentMaintenanceTransactionSync(db, guard, context =>
        applyContentDeploymentMaintenanceSync(store, context, { nowMs: Date.parse('2027-05-01T00:00:00Z') }))
    assert.equal(result.applied, true)
    assert.equal(result.counts.presentControlStates, 9599)
    assert.equal(result.counts.presentParentControls, 1018)
    assert.equal(result.counts.boxExchangeTarget, 48)
    assert.equal(result.counts.boxExchangeReady, true)
    assert.equal(db.prepare("SELECT count(*) AS n FROM content_box_exchange_deployment").get().n, 1)
    assert.equal(store.allowed('raid_event:7', 'exchange', Date.now()), true)
    assert.equal(store.state('world_story_event:100407').published, false)
    assert.equal(store.state('world_story_event:100407').actionOverrides.exchange.enabled, true)
    assert.deepEqual(result.counts.unsupportedParentKeys, ['collect_item_event:5', 'collect_item_event:80003'])
    assert.deepEqual(db.prepare('SELECT * FROM player_fact').get(), { id: 1, earned: 9, claimed: 1 })
    const calls = new Map(), readState = store.state
    store.state = function (key) {
        calls.set(key, (calls.get(key) || 0) + 1)
        return readState.call(this, key)
    }
    try {
        const inspection = inspectContentDeploymentSync(store)
        assert.equal(inspection.ready, true)
        assert.equal(inspection.counts.presentControlStates, 9599)
        assert.equal(inspection.counts.presentParentControls, 1018)
    } finally { store.state = readState }
    const boxParents = new Set(boxReview.rows.map(row => row.parentKey))
    for (const key of Object.keys(presentation.rows)) {
        if (result.counts.unsupportedParentKeys.includes(key)) continue
        assert.equal(calls.get(key), boxParents.has(key) ? 2 : 1, `parent state read count: ${key}`)
    }
    assert.equal([...calls.values()].reduce((sum, count) => sum + count, 0), 9599 + boxReview.rows.length,
        'the box supplement reads its parent separately from the one full identity pass')
    const original = store.state('gacha:1')
    store.setPublished('gacha:1', { published: true, expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'synthetic operator choice kept after deployment' }, Date.parse('2027-05-02T00:00:00Z'))
    const revision = store.revision()
    await db.backup(guard.backupPath)
    const repeatGuard = { ...guard, expectedDatabaseFingerprint: getDeploymentDatabaseFingerprintSync(db),
        expectedBackupSha256: shaFile(guard.backupPath) }
    const repeated = withDeploymentMaintenanceTransactionSync(db, repeatGuard, context =>
        applyContentDeploymentMaintenanceSync(store, context, { nowMs: Date.parse('2028-05-01T00:00:00Z') }))
    assert.equal(repeated.applied, false)
    assert.equal(repeated.revision, revision)
    assert.equal(store.state('gacha:1').published, true)
    assert.notEqual(store.state('gacha:1').published, original.published)
    const raw = db.prepare('SELECT value_json FROM content_operations_state WHERE content_key=?').get('gacha:1').value_json
    const saved = JSON.parse(raw)
    const write = value => db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(value), 'gacha:1')
    write({ ...saved, contentDigest: '0'.repeat(64) })
    assert.equal(inspectContentDeploymentSync(store).ready, false, 'root definition identity must be current')
    write({ ...saved, actionOverrides: { ...saved.actionOverrides,
        visible: { ...saved.actionOverrides.visible, contentDigest: '0'.repeat(64) } } })
    assert.equal(inspectContentDeploymentSync(store).ready, false, 'action-scoped definition identity must be current')
    write(saved)
    const runtime = store.runtimeDefinitions.get('gacha:1')
    store.runtimeDefinitions.set('gacha:1', { ...runtime, matchesCatalog: false })
    assert.equal(inspectContentDeploymentSync(store).ready, false, 'native runtime definition mismatch must not verify')
    store.runtimeDefinitions.set('gacha:1', runtime)
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run('{bad-json', 'gacha:1')
    const corrupted = inspectContentDeploymentSync(store)
    assert.equal(corrupted.ready, false)
    assert.equal(corrupted.canApply, false)
    assert.equal(corrupted.counts.presentControlStates, 9598)
    assert.equal(corrupted.counts.presentParentControls, 1017)
    assert.match(corrupted.reasons.join(';'), /状态缺失、损坏或定义身份失配/)
    write(saved)
    db.prepare('DELETE FROM content_operations_state WHERE content_key=?').run('gacha:1')
    const damaged = inspectContentDeploymentSync(store)
    assert.equal(damaged.ready, false)
    assert.equal(damaged.canApply, false)
    assert.equal(damaged.counts.presentControlStates, 9598)
    assert.equal(damaged.counts.missingParentControls, 1)
    assert.match(damaged.reasons.join(';'), /父项状态缺失/)
})

test('failure after July initialization rolls back every content stage and marker', async t => {
    const { db, store, guard } = await fixture(t)
    const update = store.update.bind(store)
    store.update = function (key, request, nowMs) {
        if (key === 'gacha:1') throw new Error('synthetic injected failure')
        return update(key, request, nowMs)
    }
    assert.throws(() => withDeploymentMaintenanceTransactionSync(db, guard, context =>
        applyContentDeploymentMaintenanceSync(store, context, { nowMs: Date.parse('2027-05-01T00:00:00Z') })),
    /synthetic injected failure/)
    assert.equal(store.revision(), 0)
    assert.equal(db.prepare('SELECT count(*) n FROM content_operations_state').get().n, 0)
    assert.equal(db.prepare("SELECT count(*) n FROM sqlite_master WHERE type='table' AND name IN ('content_operations_deployment','content_operations_initialization')").get().n, 0)
    assert.deepEqual(db.prepare('SELECT * FROM player_fact').get(), { id: 1, earned: 9, claimed: 1 })
})

test('a previously deployed source receives the exact box-window supplement atomically and never reopens an operator closure', async t => {
    const { db, store, guard } = await legacyFixture(t)
    const pending = inspectContentDeploymentSync(store)
    assert.equal(pending.ready, false)
    assert.equal(pending.canApply, true)
    assert.equal(pending.counts.phase, 'applied')
    assert.equal(pending.counts.boxExchangeReady, false)
    assert.equal(store.allowed('raid_event:7', 'exchange', Date.now()), false)
    const revision = store.revision(), first = store.state('raid_event:1')
    const beforePairs = new Map(boxReview.rows.flatMap(row => [[row.parentKey, store.state(row.parentKey)],
        [row.boxKey, store.state(row.boxKey)]]))
    const update = store.update.bind(store); let supplementWrites = 0
    store.update = function (key, request, nowMs) {
        if (request.reason === '核查原生奖励箱页兑换窗口；不新增活动商店商品资格' && ++supplementWrites === 2)
            throw new Error('synthetic second box-window write failure')
        return update(key, request, nowMs)
    }
    try {
        assert.throws(() => withDeploymentMaintenanceTransactionSync(db, guard, context =>
            applyContentDeploymentMaintenanceSync(store, context, { nowMs: Date.now() })), /synthetic second box-window/)
    } finally { store.update = update }
    assert.equal(store.revision(), revision)
    assert.deepEqual(store.state('raid_event:1'), first)
    assert.equal(db.prepare("SELECT count(*) AS n FROM sqlite_master WHERE name='content_box_exchange_deployment'").get().n, 0)
    const applied = withDeploymentMaintenanceTransactionSync(db, guard, context =>
        applyContentDeploymentMaintenanceSync(store, context, { nowMs: Date.now() }))
    assert.equal(applied.applied, true)
    assert.equal(applied.counts.boxExchangeReady, true)
    assert.equal(store.allowed('raid_event:7', 'exchange', Date.now()), true)
    assert.equal(store.state('world_story_event:100407').published, false)
    const unchangedExceptExchange = state => {
        const value = JSON.parse(JSON.stringify(state))
        delete value.revision; delete value.actionOverrides.exchange
        return value
    }
    for (const row of boxReview.rows) {
        assert.deepEqual(unchangedExceptExchange(store.state(row.parentKey)),
            unchangedExceptExchange(beforePairs.get(row.parentKey)), row.parentKey)
        assert.deepEqual(store.state(row.boxKey), beforePairs.get(row.boxKey), row.boxKey)
        assert.equal(store.state(row.parentKey).actionOverrides.exchange.enabled, true, row.parentKey)
        if (row.origin === 'stage3') {
            assert.equal(store.allowed(row.parentKey, 'visible', Date.now()), false, row.parentKey)
            assert.equal(store.allowed(row.boxKey, 'enter', Date.now()), false, row.boxKey)
        }
    }
    const raid = store.snapshot(Date.now()).states.find(row => row.key === 'raid_event:7')
    assert.equal(raid.exchange, true)
    assert.equal(raid.actions.exchange.enabled, true)
    const key = 'raid_event:7', previous = store.state(key).actionOverrides.exchange
    store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'synthetic operator closes box-page exchange', actionOverrides: { exchange: {
            enabled: false, endsAtMs: previous.endsAtMs, readiness: 'blocked',
            evidence: 'Synthetic operator fault review after completed supplement' } } }, Date.now())
    const afterClosure = store.state(key), closedRevision = store.revision()
    assert.equal(store.allowed(key, 'exchange', Date.now()), false)
    await db.backup(guard.backupPath)
    const repeatGuard = { ...guard, expectedDatabaseFingerprint: getDeploymentDatabaseFingerprintSync(db),
        expectedBackupSha256: shaFile(guard.backupPath) }
    const repeated = withDeploymentMaintenanceTransactionSync(db, repeatGuard, context =>
        applyContentDeploymentMaintenanceSync(store, context, { nowMs: Date.now() }))
    assert.equal(repeated.applied, false)
    assert.equal(store.revision(), closedRevision)
    assert.deepEqual(store.state(key), afterClosure)
    const raw = db.prepare('SELECT value_json FROM content_operations_state WHERE content_key=?').get(key).value_json
    const missing = JSON.parse(raw)
    delete missing.actionOverrides.exchange
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(missing), key)
    const broken = inspectContentDeploymentSync(store)
    assert.equal(broken.ready, false)
    assert.equal(broken.canApply, false)
    assert.match(broken.reasons.join(';'), /raid_event:7.*兑换动作缺失/)
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(raw, key)
})

test('an explicit same-value false after bootstrap is not mistaken for the unreviewed placeholder', async t => {
    const { db, store, guard } = await legacyFixture(t)
    const key = 'world_story_event:100407', review = store.state(key).actionOverrides.exchange
    store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'synthetic explicit operator false retaining old text', actionOverrides: { exchange: {
            enabled: false, endsAtMs: review.endsAtMs, readiness: review.readiness, evidence: review.evidence } } }, Date.now())
    const inspection = inspectContentDeploymentSync(store)
    assert.equal(inspection.ready, false)
    assert.equal(inspection.canApply, false)
    assert.match(inspection.reasons.join(';'), /world_story_event:100407.*审计链/)
    const sibling = boxReview.rows.find(row => row.parentKey === 'raid_event:1')
    const boxClaim = store.state(sibling.boxKey).actionOverrides.claim
    store.update(sibling.boxKey, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'synthetic box-side review edit with unchanged value', actionOverrides: { claim: {
            enabled: boxClaim.enabled, endsAtMs: boxClaim.endsAtMs, readiness: boxClaim.readiness,
            evidence: boxClaim.evidence } } }, Date.now())
    const boxInspection = inspectContentDeploymentSync(store)
    assert.match(boxInspection.reasons.join(';'), /raid_event:1.*审计链/)
    const afterEditsRevision = store.revision()
    await db.backup(guard.backupPath)
    const attemptGuard = { ...guard, expectedDatabaseFingerprint: getDeploymentDatabaseFingerprintSync(db),
        expectedBackupSha256: shaFile(guard.backupPath) }
    assert.throws(() => withDeploymentMaintenanceTransactionSync(db, attemptGuard, context =>
        applyContentDeploymentMaintenanceSync(store, context, { nowMs: Date.now() })), /审计链/)
    assert.equal(store.revision(), afterEditsRevision)
    assert.equal(db.prepare("SELECT count(*) AS n FROM sqlite_master WHERE name='content_box_exchange_deployment'").get().n, 0)
})
