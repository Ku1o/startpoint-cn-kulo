'use strict'
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')
const temporaryRoot = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
const directory = fs.mkdtempSync(path.join(temporaryRoot, 'mission-claim-short-circuit-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const load = name => require('../out/' + name)
const players = load('data/domains/player')
const missions = load('data/domains/mission')
const operations = load('lib/content-operations')
const { ContentOperationsStore, CONTENT_ACTIONS } = load('lib/content-operations-store')
const { settleMissionCategoriesWithProgress } = load('lib/mission/settlement')
const { getComputer } = load('lib/mission/registry')
let db

before(() => {
    load('data').initializeDatabase()
    db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    assert.equal(load('lib/mission/master-data').getMissionMasterDefinition(1, 1).pattern, 'max_combo')
    const reward = load('lib/mission/rewards').getCategoryMissionRewardStageDefinition(1, 1, 1)
    assert.equal(reward.targetProgress, 10)
    assert.deepEqual(reward.rewards, [{ kind: 0, amount: 5 }])
})
after(async () => {
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(temporaryRoot))
    fs.rmSync(directory, { recursive: true })
})

function fixture(t, enter, claim, combo = 0, savedProgress = 0) {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '',
        idpCode: 'mission-claim-short-circuit', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id)
    players.updatePlayerSync({ id: player.id, maxComboAchieved: combo })
    if (savedProgress > 0) missions.updatePlayerCategoryMissionSync(player.id, 1, 1, savedProgress)
    const catalog = { schemaVersion: 1, source: { assetVersion: 'fixture', manifestSha256: 'fixture' },
        baselineTimeMs: 0, baselineEvidence: 'fixture', resources: {}, missing: [], questMap: {},
        missionMap: { '1:1': 'mission_regular:1' }, rows: [{ key: 'mission_regular:1', type: 'mission_regular',
            id: 1, name: 'max combo fixture', source: 'fixture', originalStartMs: null, originalEndMs: null,
            originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false }] }
    const store = new ContentOperationsStore(db, catalog, () => CONTENT_ACTIONS,
        () => ({ digest: 'fixture', matchesCatalog: true }))
    const control = (allowEnter, allowClaim) => store.update('mission_regular:1', {
        expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'isolated claim decision verification',
        readiness: 'verified', evidence: 'fixture definition and scoped rights',
        flags: { visible: allowEnter, enter: allowEnter, claim: allowClaim, exchange: false },
        missionKeys: ['1:1'], endsAtMs: null,
    }, Date.now())
    control(enter, claim)
    const checks = { enter: 0, claim: 0 }, stateReads = { enter: 0, claim: 0 }
    let activeAction
    const prepare = db.prepare.bind(db)
    t.mock.method(db, 'prepare', sql => {
        if (activeAction && sql === 'SELECT value_json FROM content_operations_state WHERE content_key=?') stateReads[activeAction]++
        return prepare(sql)
    })
    // Only substitute ownership for this one native mission. The decision still
    // uses real SQLite controls, strict decoding, action readiness and scopes.
    const originalDecision = operations.contentMissionDecision
    t.mock.method(operations, 'contentMissionDecision', (category, missionId, action, nowMs = Date.now()) => {
        if (category !== 1 || missionId !== 1) return originalDecision(category, missionId, action, nowMs)
        checks[action]++
        const previous = activeAction
        activeAction = action
        try { return store.scopedAllowed('mission_regular:1', 'mission', '1:1', action, nowMs) }
        finally { activeAction = previous }
    })
    const settle = () => settleMissionCategoriesWithProgress(player.id, [{ category: 1, missionIds: [1] }], new Date())
    const progress = () => missions.getPlayerCategoryMissionsSync(player.id, 1)['1']
    const balance = () => players.getPlayerSync(player.id).freeVmoney
    const saved = () => ({ player: players.getPlayerSync(player.id),
        missions: missions.getPlayerCategoryMissionsSync(player.id, 1) })
    return { player, control, checks, stateReads, settle, progress, balance, saved }
}

test('an open mission below its first reward updates progress without any preliminary claim SQL', t => {
    const f = fixture(t, true, true, 5)
    const balance = f.balance()
    const result = f.settle()
    assert.equal(f.progress().progress, 5)
    assert.deepEqual(result.evaluatedProgress, [{ category: 1, missionId: 1, progress: 5 }])
    assert.deepEqual(result.settlement.missionInfo, [])
    assert.equal(f.balance(), balance)
    assert.ok(f.stateReads.enter > 0, 'permission instrumentation must observe actual state SELECTs')
    assert.equal(f.checks.claim, 0)
    assert.equal(f.stateReads.claim, 0)
})

test('enter permission without claim permission updates progress but the final claim SQL refuses rewards', t => {
    const f = fixture(t, true, false, 10)
    const balance = f.balance()
    const result = f.settle()
    assert.equal(f.progress().progress, 10)
    assert.deepEqual(result.settlement.missionInfo, [])
    assert.equal(f.balance(), balance)
    assert.equal(f.checks.claim, 1, 'the remaining check belongs to the one pending reward stage')
    assert.equal(f.stateReads.claim, 1)
    assert.deepEqual(f.progress().stages, [])
})

test('claim-only missions retain old progress and grant each old stage exactly once', t => {
    const f = fixture(t, false, true, 500, 10)
    const balance = f.balance()
    const first = f.settle()
    assert.equal(f.progress().progress, 10, 'closed entry cannot inherit current combo facts')
    assert.equal(first.settlement.missionInfo.filter(row => row.mission_category_id === 1 && row.mission_id === 1).length, 1)
    assert.equal(f.balance(), balance + 5)
    assert.equal(f.progress().stages['1'], true)
    assert.ok(f.stateReads.claim > 0)
    assert.deepEqual(f.settle().settlement.missionInfo, [])
    assert.equal(f.balance(), balance + 5)
})

test('closed entry and claim leave mission progress, receipts and wallet unchanged', t => {
    const f = fixture(t, false, false, 500, 10)
    const before = f.saved()
    const result = f.settle()
    assert.deepEqual(result.evaluatedProgress, [])
    assert.deepEqual(result.settlement.missionInfo, [])
    assert.deepEqual(f.saved(), before)
    assert.equal(f.checks.claim, 1)
})

test('claim permission revoked after real computation is re-read before granting', t => {
    const f = fixture(t, true, true, 10)
    const computer = getComputer(1), compute = computer.compute
    let computed = 0
    t.mock.method(computer, 'compute', function (missionId, context, progress) {
        const value = compute.call(this, missionId, context, progress)
        if (missionId === 1) { computed++; f.control(true, false) }
        return value
    })
    const balance = f.balance(), result = f.settle()
    assert.equal(computed, 1)
    assert.equal(f.progress().progress, 10)
    assert.equal(f.stateReads.claim, 1, 'final authorization must still read the newly revoked state')
    assert.deepEqual(result.settlement.missionInfo, [])
    assert.equal(f.balance(), balance)
})

test('reward and progress writes still roll back together in the caller transaction', t => {
    const f = fixture(t, true, true, 10)
    const before = f.saved()
    assert.throws(() => db.transaction(() => {
        const result = f.settle()
        assert.ok(result.settlement.missionInfo.some(row => row.mission_category_id === 1 && row.mission_id === 1))
        assert.equal(f.balance(), before.player.freeVmoney + 5)
        throw new Error('isolated claim rollback')
    })(), /isolated claim rollback/)
    assert.deepEqual(f.saved(), before)
})
