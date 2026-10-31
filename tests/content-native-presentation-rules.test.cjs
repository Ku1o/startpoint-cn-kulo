'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict'), path = require('node:path')
const Sqlite = require('better-sqlite3')
if (!process.env.STARPOINT_TEST_OUT_DIR) require('ts-node/register/transpile-only')
const base = process.env.STARPOINT_TEST_OUT_DIR || path.join(__dirname, '../src')
const { nativePresentationScopeError } = require(path.join(base, 'lib/content-native-presentation-rules'))
const { ContentOperationsStore, initializeContentOperationsSchema } = require(path.join(base, 'lib/content-operations-store'))
const keys = (category, first, count) => Array.from({ length: count }, (_, index) => `${category}:${first + index}`)
const tower = { key: 'tower_dungeon_event:1', type: 'tower_dungeon_event', id: 1 }
const challenge = { key: 'challenge_dungeon_event:1', type: 'challenge_dungeon_event', id: 1 }
const cycle = keys(20, 1381, 10), common = keys(13, 1001, 19), currentBeast = [...common, ...keys(13, 1038, 3)]
const action = (questKeys, enabled = true) => ({ enabled, questKeys, endsAtMs: null, readiness: 'verified', evidence: 'Native one-period page contract' })
const control = (shown, playable = shown) => ({ flags: { visible: false, enter: false },
    actionOverrides: { visible: action(shown), enter: action(playable) } })
const check = (row, shown, playable = shown) => nativePresentationScopeError(row, control(shown, playable))

test('tower rejects the reported 480-period union and missing, null, duplicate or incomplete scopes', () => {
    for (const scope of [keys(20, 1001, 480), undefined, null, [], cycle.slice(1), [...cycle.slice(1), cycle[1]],
        keys(20, 1382, 10), [...cycle.slice(0, 9), '20:1400']])
        assert.match(check(tower, scope), /精确关卡范围|同一期完整的10个/)
})
test('tower accepts one complete period in any order and rejects different visible/enter periods', () => {
    assert.equal(check(tower, [...cycle].reverse(), cycle), null)
    assert.equal(check(tower, keys(20, 1001, 10)), null)
    assert.match(check(tower, cycle, keys(20, 1391, 10)), /显示和参与必须选择同一期/)
    assert.match(check(tower, [...cycle.slice(0, 9), '13:1390']), /同一期完整/)
})
test('suspension and disabled participation retain old scopes; other event policies are unchanged', () => {
    const hidden = control(keys(20, 1001, 480)); hidden.actionOverrides.visible.enabled = false
    assert.equal(nativePresentationScopeError(tower, hidden), null)
    const browseOnly = control(cycle, keys(20, 1001, 480)); browseOnly.actionOverrides.enter.enabled = false
    assert.equal(nativePresentationScopeError(tower, browseOnly), null)
    assert.equal(check({ key: 'story_event:1', type: 'story_event', id: 1 }, null), null)
    assert.equal(check({ key: 'challenge_dungeon_event:2', type: 'challenge_dungeon_event', id: 2 }, null), null)
    assert.equal(nativePresentationScopeError(tower, { ...control(null), controlled: false }), null)
})
test('beast keeps common quests and accepts any single historical period, but rejects the reported all40 union', () => {
    assert.equal(check(challenge, currentBeast), null)
    assert.equal(check(challenge, [...common, ...keys(13, 1020, 3)]), null)
    assert.equal(check(challenge, common), null)
    assert.match(check(challenge, keys(13, 1001, 40)), /不能同时开放多期/)
    assert.match(check(challenge, [...common, '13:1020', '13:1038']), /不能同时开放多期/)
    assert.match(check(challenge, currentBeast, [...common, ...keys(13, 1020, 3)]), /必须包含在同一显示范围/)
    assert.match(check(challenge, null), /精确关卡范围/)
})

function fixture(t) {
    const db = new Sqlite(':memory:'); t.after(() => db.close()); initializeContentOperationsSchema(db)
    db.exec("CREATE TABLE preserved_progress(section INTEGER,quest_id INTEGER,finished INTEGER,claimed INTEGER); INSERT INTO preserved_progress VALUES(13,1020,1,1),(20,1001,1,1)")
    const rows = [tower, challenge].map(row => ({ ...row, name: row.key, originalStartMs: null, originalEndMs: null,
        originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false, source: 'native presentation fixture' }))
    const questMap = Object.fromEntries([...keys(20, 1001, 480).map(key => [key, tower.key]), ...keys(13, 1001, 40).map(key => [key, challenge.key])])
    const catalog = { schemaVersion: 1, source: { assetVersion: 'fixture', manifestSha256: 'fixture' }, baselineTimeMs: 0,
        baselineEvidence: 'fixture', rows, questMap, missing: [], resources: {} }
    const store = new ContentOperationsStore(db, catalog, () => ['visible', 'enter', 'exchange'], () => ({ digest: 'fixture', matchesCatalog: true }))
    const update = (key, actionOverrides) => store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Native presentation regression', actionOverrides }, 1793404800000)
    return { db, store, update }
}
test('actual store atomically rejects invalid scopes and mismatches, without state/audit/player writes', t => {
    const f = fixture(t)
    for (const [row, scope] of [[tower, keys(20, 1001, 480)], [challenge, keys(13, 1001, 40)]]) {
        assert.throws(() => f.update(row.key, control(scope).actionOverrides), /同一期完整|不能同时开放多期/)
        assert.equal(f.store.revision(), 0); assert.equal(f.store.state(row.key), null)
    }
    const before = f.update(tower.key, control(cycle).actionOverrides), revision = f.store.revision()
    assert.throws(() => f.update(tower.key, { enter: action(keys(20, 1391, 10)) }), /显示和参与必须选择同一期/)
    assert.equal(f.store.revision(), revision); assert.deepEqual(f.store.state(tower.key), before)
    assert.equal(f.db.prepare('SELECT COUNT(*) n FROM content_operations_audit').get().n, 1)
    assert.deepEqual(f.db.prepare('SELECT * FROM preserved_progress').all(), [
        { section: 13, quest_id: 1020, finished: 1, claimed: 1 }, { section: 20, quest_id: 1001, finished: 1, claimed: 1 }])
})
test('actual store repairs both scopes in one update while preserving legacy instance, other actions and progress', t => {
    const f = fixture(t), initial = f.update(tower.key, { ...control(cycle).actionOverrides, exchange: action(undefined) })
    const legacy = { ...initial, published: false, actionOverrides: { ...initial.actionOverrides,
        visible: { ...initial.actionOverrides.visible, questKeys: keys(20, 1001, 480) },
        enter: { ...initial.actionOverrides.enter, questKeys: keys(20, 1001, 480) } } }
    f.db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(legacy), tower.key)
    f.update(tower.key, { exchange: { ...action(undefined), evidence: 'independent exchange update' } })
    const before = f.store.state(tower.key), progress = f.db.prepare('SELECT * FROM preserved_progress').all()
    const repaired = f.update(tower.key, control(cycle).actionOverrides)
    assert.equal(repaired.instanceId, before.instanceId); assert.equal(repaired.published, false)
    assert.deepEqual(repaired.actionOverrides.exchange, before.actionOverrides.exchange)
    assert.deepEqual(f.db.prepare('SELECT * FROM preserved_progress').all(), progress)
    assert.deepEqual(repaired.actionOverrides.visible.questKeys, cycle)
    assert.deepEqual(repaired.actionOverrides.enter.questKeys, cycle)
    f.update(challenge.key, control(currentBeast).actionOverrides)
})
test('legacy invalid scopes may be suspended, but cannot be republished until repaired', t => {
    const f = fixture(t), initial = f.update(tower.key, control(cycle).actionOverrides)
    const legacy = { ...initial, actionOverrides: { ...initial.actionOverrides,
        visible: { ...initial.actionOverrides.visible, questKeys: null },
        enter: { ...initial.actionOverrides.enter, questKeys: keys(20, 1001, 480) } } }
    f.db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(JSON.stringify(legacy), tower.key)
    const publish = published => f.store.setPublished(tower.key, { expectedRevision: f.store.revision(), catalogDigest: f.store.digest,
        reason: 'Native presentation publication regression', published }, 1793404800000)
    assert.equal(publish(false).published, false)
    const revision = f.store.revision()
    assert.throws(() => publish(true), /精确关卡范围/)
    assert.equal(f.store.revision(), revision); assert.equal(f.store.state(tower.key).published, false)
    f.update(tower.key, control(cycle).actionOverrides)
    assert.equal(publish(true).published, true)
})
