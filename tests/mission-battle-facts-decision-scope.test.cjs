const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const fs = require('node:fs')
const Sqlite = require('better-sqlite3')
const { compileFunction } = require('node:vm')

const now = Date.parse('2026-11-03T12:17:43Z')
const key = 'mission_regular:1'
const stateSql = 'SELECT value_json FROM content_operations_state WHERE content_key=?'

// Run the compiled battle entry with isolated fact producers, backed by the real
// store and SQLite. This keeps catalog size and control changes reproducible.
function fixture(out, memberCount = 4) {
    const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } =
        require(path.join(out, 'lib/content-operations-store'))
    const db = new Sqlite(':memory:')
    initializeContentOperationsSchema(db)
    const members = Array.from({ length: memberCount }, (_, index) => '1:' + (index + 1))
    const store = new ContentOperationsStore(db, {
        schemaVersion: 1, source: { assetVersion: 'fixture', manifestSha256: 'fixture' },
        baselineTimeMs: 0, baselineEvidence: 'fixture', resources: {}, missing: [], questMap: {},
        missionMap: Object.fromEntries(members.map(member => [member, key])),
        rows: [{ key, type: 'mission_regular', id: 1, name: 'fixture', source: 'fixture',
            originalStartMs: null, originalEndMs: null, originalExchangeEndMs: null,
            windowCandidate: false, browseCandidate: false }],
    }, () => CONTENT_ACTIONS, () => ({ digest: 'fixture', matchesCatalog: true }))
    store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'fixture', readiness: 'verified', evidence: 'fixture',
        flags: { visible: true, enter: true, claim: true, exchange: false },
        missionKeys: members, endsAtMs: null }, now)
    const original = db.prepare(stateSql).get(key).value_json
    const denied = JSON.stringify({ ...JSON.parse(original),
        flags: { visible: true, enter: false, claim: false, exchange: false } })
    const setState = db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?')
    db.exec('CREATE TABLE fixture_progress(value INTEGER NOT NULL); INSERT INTO fixture_progress VALUES(0)')
    const increment = db.prepare('UPDATE fixture_progress SET value=value+1')
    const readProgress = db.prepare('SELECT value FROM fixture_progress').pluck()
    const counts = { reads: 0, parses: 0 }
    function observeRun(callback) {
        const { cachedStatement } = require(path.join(out, 'lib/cached-statement'))
        const statement = cachedStatement(db, stateSql)
        const get = statement.get
        const parse = JSON.parse
        statement.get = function (...args) {
            counts.reads++
            return get.apply(this, args)
        }
        JSON.parse = function (value, ...args) {
            if (value === original || value === denied) counts.parses++
            return parse.call(this, value, ...args)
        }
        counts.reads = 0
        counts.parses = 0
        try { return callback() }
        finally { statement.get = get; JSON.parse = parse }
    }
    const decision = (member = members[0]) => store.scopedAllowed(key, 'mission', member, 'enter', now)
    let scenario
    const dependencies = {
        '../../data/domains/quest': { incrementPlayerQuestMultiClearSync() {} },
        '../../data/domains/mission_battle_facts': { recordMissionBattleResultSync() { increment.run() } },
        '../quest/finish/character-clear-tracker': { trackCharacterClears() {} },
        '../quest/finish/leader-powerflip-tracker': { trackLeaderPowerflip() {} },
        '../quest/finish/party-co-clear-tracker': { trackPartyCoClears: () => [] },
        '../quest/finish/powerflip-tracker': { trackPowerflip() {} },
        '../../utils': { getServerTime: () => now / 1000 },
        './event-battle-facts': { recordEventMissionBattleFacts: () => [] },
        './pass-battle-facts': { recordPassMissionBattleFacts: () => [], recordPassWeeklyEmotionFacts() {} },
        './active-conditional-battle-facts': { recordActiveMissionConditionalBattleFactsSync() {} },
        './active-loadout-battle-facts': { recordActiveMissionLoadoutBattleFactsSync() {} },
        './daily-battle-facts': {
            recordDailyMissionBattleFacts() {
                if (scenario?.change) {
                    assert.equal(decision(), true)
                    assert.equal(decision(), true)
                    setState.run(denied, key)
                    assert.equal(decision(), false)
                    assert.equal(decision(), false)
                    if (scenario.failure) throw scenario.failure
                    setState.run(original, key)
                    assert.equal(decision(), true)
                    return [1]
                }
                return members.filter(member => decision(member)).map(member => Number(member.slice(2)))
            },
        },
        './collect-battle-facts': { recordCollectMissionBattleFacts: () => [] },
        './computer-degree': {},
        './computer-event-safe': {},
        './degree-party-power': { recordDegreePartyPowerClearSync() {} },
        '../types': { QuestCategory: { RUSH_EVENT: 24 } },
        '../content-operations': { withContentOperationsDecisionScope: operation => store.withDecisionScope(operation) },
    }
    const filename = path.join(out, 'lib/mission/battle-facts.js')
    const exports = {}
    compileFunction(fs.readFileSync(filename, 'utf8'), ['require', 'exports'], { filename })(id => {
        assert.ok(Object.hasOwn(dependencies, id), 'Unexpected dependency ' + id)
        return dependencies[id]
    }, exports)
    const transact = db.transaction(() => exports.recordMissionBattleFacts({
        playerId: 1, questCategory: 24, questId: 1, questAccomplished: true, clearRank: 5,
    }, new Date(now)))
    return {
        run(options) { scenario = options; return transact() },
        counts, observeRun, decision, revision: () => store.revision(),
        progress: () => readProgress.get(), close: () => db.close(),
    }
}

module.exports = { fixture }

if (require.main === module) {
    const out = path.resolve(__dirname, '../out')
    test('battle fact decisions reuse a decode, retain fresh SQL, and release the success scope', t => {
        const f = fixture(out)
        t.after(f.close)
        f.observeRun(() => {
            assert.deepEqual(f.run().dailyMissionIds, [1, 2, 3, 4])
            assert.deepEqual(f.counts, { reads: 4, parses: 1 })
            assert.equal(f.decision(), true)
            assert.equal(f.decision(), true)
            assert.deepEqual(f.counts, { reads: 6, parses: 3 })
        })
        assert.equal(f.progress(), 1)
    })

    test('battle fact scope sees same-revision changes and is released after rollback', t => {
        const f = fixture(out)
        t.after(f.close)
        const revision = f.revision()
        const failure = new Error('fixture rollback')
        f.observeRun(() => {
            assert.deepEqual(f.run({ change: true }).dailyMissionIds, [1])
            assert.deepEqual(f.counts, { reads: 5, parses: 3 })
        })
        f.observeRun(() => {
            assert.throws(() => f.run({ change: true, failure }), error => error === failure)
            assert.deepEqual(f.counts, { reads: 4, parses: 2 })
            assert.equal(f.decision(), true)
            assert.equal(f.decision(), true)
            assert.deepEqual(f.counts, { reads: 6, parses: 4 })
        })
        assert.equal(f.revision(), revision)
        assert.equal(f.progress(), 1)
    })
}
