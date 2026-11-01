'use strict'
if (process.env.STARPOINT_TEST_COMPILED !== '1') require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const Sqlite = require('better-sqlite3')
const root = '../' + (process.env.STARPOINT_TEST_COMPILED === '1' ? 'out' : 'src') + '/lib/'
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require(root + 'content-operations-store')
const now = Date.parse('2026-11-01T00:00:00Z')
const key = 'mission_regular:1'
const stateSql = 'SELECT value_json FROM content_operations_state WHERE content_key=?'
const revisionSql = 'SELECT revision FROM content_operations_meta WHERE id=1'

function fixture(t, options = {}) {
    const db = options.db || new Sqlite(':memory:')
    if (!options.db) {
        initializeContentOperationsSchema(db)
        t.after(() => db.close())
    }
    const observation = options.observation || observe(t, db)
    const catalog = { schemaVersion: 1, source: { assetVersion: 'fixture', manifestSha256: 'fixture' },
        baselineTimeMs: 0, baselineEvidence: 'fixture', resources: {}, missing: [], questMap: {},
        missionMap: { '1:1': key, '1:2': key }, rows: [{ key, type: 'mission_regular', id: 1,
            name: 'decision fixture', source: 'fixture', originalStartMs: null, originalEndMs: null,
            originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false }],
        ...options.catalog }
    const store = new ContentOperationsStore(db, catalog, () => CONTENT_ACTIONS,
        () => ({ digest: 'fixture', matchesCatalog: true }))
    if (!options.db) store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'isolated decision cache verification', readiness: 'verified', evidence: 'fixture',
        flags: { visible: true, enter: true, claim: true, exchange: false },
        missionKeys: ['1:1'], endsAtMs: null }, now)
    const getRaw = () => db.prepare('SELECT value_json FROM content_operations_state WHERE content_key = ?').get(key)?.value_json
    const putRaw = raw => db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(raw, key)
    const raw = getRaw()
    observation.watch(raw)
    Object.assign(observation.counts, { stateGet: 0, revisionGet: 0, decode: 0 })
    const decision = (action = 'enter', time = now, member = '1:1') => store.scopedAllowed(key, 'mission', member, action, time)
    return { db, store, raw, getRaw, putRaw, decision, catalog, observation }
}

// Count work at observable boundaries, without reading the implementation's cache.
// Cached statements must be wrapped once: subsequent prepare calls may return them.
function observe(t, db) {
    const counts = { statePrepare: 0, stateGet: 0, revisionPrepare: 0, revisionGet: 0, decode: 0 }
    const observed = new WeakSet(), raws = new Set()
    const prepare = db.prepare.bind(db), parse = JSON.parse
    t.mock.method(db, 'prepare', sql => {
        const statement = prepare(sql)
        const label = sql === stateSql ? 'state' : sql === revisionSql ? 'revision' : null
        if (label) {
            counts[label + 'Prepare']++
            if (!observed.has(statement)) {
                observed.add(statement)
                const get = statement.get
                t.mock.method(statement, 'get', function (...args) {
                    counts[label + 'Get']++
                    return get.apply(this, args)
                })
            }
        }
        return statement
    })
    t.mock.method(JSON, 'parse', function (value, ...args) {
        if (raws.has(value)) counts.decode++
        return parse.call(this, value, ...args)
    })
    return { counts, watch: raw => raws.add(raw) }
}

test('each decision executes fresh SQL while only unchanged decoded controls are reused inside one scope', t => {
    const f = fixture(t), { counts } = f.observation
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        assert.equal(f.decision('claim'), true)
        assert.equal(f.store.allowed(key, 'enter', now), true)
        assert.equal(counts.stateGet, 3, 'every authority lookup must execute SQLite get')
        assert.equal(counts.statePrepare, 1, 'the fixed query must compile once')
        assert.equal(counts.decode, 1, 'same persisted JSON needs only one validation in this scope')
    })
    assert.equal(f.decision('claim'), true)
    assert.equal(counts.stateGet, 4, 'final claim outside evaluation must read again')
    assert.equal(counts.decode, 2, 'finished evaluation cannot supply a later claim decode')
    assert.equal(counts.statePrepare, 1)
    for (let i = 0; i < 3; i++) assert.equal(f.store.revision(), 1)
    assert.equal(counts.revisionGet, 3)
    assert.equal(counts.revisionPrepare, 1)
})

test('same-scope state changes are visible even without advancing the operation revision', t => {
    const f = fixture(t), { counts, watch } = f.observation
    const denied = JSON.stringify({ ...JSON.parse(f.raw), flags: { visible: true, enter: false, claim: false, exchange: false } })
    watch(denied)
    counts.decode = 0
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        f.putRaw(denied)
        assert.equal(f.decision(), false)
        f.putRaw(f.raw)
        assert.equal(f.decision(), true)
        assert.equal(f.store.revision(), 1)
        assert.equal(counts.stateGet, 3)
        assert.equal(counts.decode, 3, 'A to B to A must not retain an obsolete same-key entry')
    })
})

test('deleting and restoring a row cannot retain a previous authorization', t => {
    const f = fixture(t)
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        f.db.prepare('DELETE FROM content_operations_state WHERE content_key=?').run(key)
        assert.notEqual(f.decision(), true)
        f.db.prepare('INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?)').run(key, f.raw)
        assert.equal(f.decision(), true)
    })
})

test('malformed JSON, invalid shapes and foreign mission scope fail closed until the raw state is repaired', t => {
    const f = fixture(t)
    const original = JSON.parse(f.raw)
    const invalid = ['{broken', '{}', JSON.stringify({ ...original, missionKeys: ['1:999'] }),
        JSON.stringify({ ...original, flags: { ...original.flags, claim: 'true' } })]
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        for (const raw of invalid) {
            f.putRaw(raw)
            assert.equal(f.decision(), false)
            assert.equal(f.decision('claim'), false)
            assert.equal(f.store.state(key).integrityError, 'invalid_persisted_state')
            f.putRaw(f.raw)
            assert.equal(f.decision(), true)
        }
    })
})

test('savepoint rollback restores the authority read within an existing decision scope', t => {
    const f = fixture(t)
    const denied = JSON.stringify({ ...JSON.parse(f.raw), flags: { visible: true, enter: false, claim: false, exchange: false } })
    f.db.transaction(() => f.store.withDecisionScope(() => {
        assert.equal(f.decision('claim'), true)
        assert.throws(() => f.db.transaction(() => {
            f.putRaw(denied)
            assert.equal(f.decision('claim'), false)
            throw new Error('isolated control rollback')
        })(), /isolated control rollback/)
        assert.equal(f.decision('claim'), true)
        assert.equal(f.getRaw(), f.raw)
    }))()
})

test('public state remains mutable and independently decoded without exposing private authority objects', t => {
    const f = fixture(t)
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        const first = f.store.state(key), second = f.store.state(key)
        assert.notEqual(first, second)
        assert.notEqual(first.flags, second.flags)
        assert.notEqual(first.missionKeys, second.missionKeys)
        first.flags.enter = false
        first.missionKeys.push('1:2')
        assert.equal(second.flags.enter, true)
        assert.deepEqual(second.missionKeys, ['1:1'])
        assert.equal(f.decision(), true)
        assert.equal(f.decision('enter', now, '1:2'), false)
    })
})

test('public nested action overrides cannot mutate a privately reused decision', t => {
    const f = fixture(t), original = JSON.parse(f.raw)
    f.putRaw(JSON.stringify({ ...original, actionOverrides: { enter: {
        enabled: true, endsAtMs: null, readiness: 'verified', evidence: 'nested override fixture',
        missionKeys: ['1:1'], catalogDigest: original.catalogDigest, contentDigest: original.contentDigest,
    } } }))
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        const first = f.store.state(key), second = f.store.state(key)
        assert.notEqual(first.actionOverrides.enter, second.actionOverrides.enter)
        assert.notEqual(first.actionOverrides.enter.missionKeys, second.actionOverrides.enter.missionKeys)
        first.actionOverrides.enter.enabled = false
        first.actionOverrides.enter.missionKeys.push('1:2')
        assert.equal(second.actionOverrides.enter.enabled, true)
        assert.deepEqual(second.actionOverrides.enter.missionKeys, ['1:1'])
        assert.equal(f.decision(), true)
        assert.equal(f.decision('enter', now, '1:2'), false)
    })
})

test('identical controls are validated against each store and each database independently', t => {
    const a = fixture(t), b = fixture(t)
    const narrowed = fixture(t, { db: a.db, observation: a.observation, catalog: { missionMap: { '1:2': key } } })
    const denied = JSON.stringify({ ...JSON.parse(b.raw), flags: { visible: false, enter: false, claim: false, exchange: false } })
    b.putRaw(denied)
    a.store.withDecisionScope(() => {
        assert.equal(a.decision(), true)
        narrowed.store.withDecisionScope(() => assert.equal(narrowed.decision(), false))
        b.store.withDecisionScope(() => assert.equal(b.decision(), false))
        assert.equal(a.decision(), true)
    })
})

test('deadlines and mission membership are evaluated on every lookup of an unchanged raw state', t => {
    const f = fixture(t)
    const deadline = now + 1000
    f.putRaw(JSON.stringify({ ...JSON.parse(f.raw), endsAtMs: deadline }))
    f.store.withDecisionScope(() => {
        assert.equal(f.decision('claim', deadline - 1), true)
        assert.equal(f.decision('claim', deadline), true)
        assert.equal(f.decision('claim', deadline + 1), false)
        assert.equal(f.decision('claim', deadline - 1), true, 'a time reversal must be evaluated anew')
        assert.equal(f.decision('claim', now, '1:2'), false)
    })
})

test('nested scopes are independent and restore the outer decode only for the current raw state', t => {
    const f = fixture(t), { counts } = f.observation
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        f.store.withDecisionScope(() => {
            assert.equal(f.decision(), true)
            assert.equal(f.decision(), true)
            assert.equal(counts.decode, 2)
        })
        assert.equal(f.decision(), true)
        assert.equal(counts.decode, 2, 'nested scope must restore its parent')
    })
    assert.equal(f.decision(), true)
    assert.equal(counts.decode, 3)
    assert.equal(counts.stateGet, 5)
})

test('an inner failure restores the outer scope without restoring stale authorization', t => {
    const f = fixture(t)
    const denied = JSON.stringify({ ...JSON.parse(f.raw), flags: { visible: true, enter: false, claim: false, exchange: false } })
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        assert.throws(() => f.store.withDecisionScope(() => {
            f.putRaw(denied)
            assert.equal(f.decision(), false)
            throw new Error('isolated inner scope failure')
        }), /isolated inner scope failure/)
        assert.equal(f.decision(), false, 'resuming an outer scope must still read current raw state')
        f.putRaw(f.raw)
        assert.equal(f.decision(), true)
    })
})

test('throwing and asynchronous continuations cannot retain a finished synchronous scope', async t => {
    const f = fixture(t), { counts } = f.observation
    assert.throws(() => f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        throw new Error('isolated scope failure')
    }), /isolated scope failure/)
    assert.equal(f.decision(), true)
    assert.equal(counts.decode, 2)
    const continuation = f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        return Promise.resolve().then(() => {
            assert.equal(f.decision('claim'), true)
            assert.equal(f.decision('claim'), true)
        })
    })
    await continuation
    assert.equal(counts.decode, 5, 'each post-scope query must decode independently')
})

test('an oversized persisted control keeps fresh authorization without retaining its decoded object', t => {
    const f = fixture(t), { counts, watch } = f.observation
    const large = JSON.stringify({ ...JSON.parse(f.raw), evidence: 'x'.repeat(3 * 1024 * 1024) })
    f.putRaw(large)
    watch(large)
    counts.decode = 0
    f.store.withDecisionScope(() => {
        assert.equal(f.decision(), true)
        assert.equal(f.decision(), true)
        assert.equal(counts.stateGet, 2)
        assert.equal(counts.decode, 2, 'oversized raw must remain correct through the uncached path')
        f.putRaw(f.raw)
        assert.equal(f.decision(), true)
        assert.equal(f.decision(), true)
        assert.equal(counts.decode, 3, 'a normal replacement should still fit after the oversized row')
    })
})

test('more than one thousand distinct controls remain authoritative after the scope reaches its entry budget', t => {
    const rows = Array.from({ length: 1025 }, (_, index) => ({ key: `mission_regular:${index + 1}`,
        type: 'mission_regular', id: index + 1, name: 'bounded decision fixture', source: 'fixture',
        originalStartMs: null, originalEndMs: null, originalExchangeEndMs: null,
        windowCandidate: false, browseCandidate: false }))
    const missionMap = Object.fromEntries(rows.map(row => [`1:${row.id}`, row.key]))
    const f = fixture(t, { catalog: { rows, missionMap } }), original = JSON.parse(f.raw)
    const insert = f.db.prepare('INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?)')
    for (const row of rows.slice(1)) {
        const raw = JSON.stringify({ ...original, key: row.key, instanceId: `${row.key}:original`,
            contentDigest: f.store.contentDigests.get(row.key), missionKeys: [`1:${row.id}`] })
        f.observation.watch(raw)
        insert.run(row.key, raw)
    }
    f.observation.counts.decode = 0
    f.store.withDecisionScope(() => {
        for (let pass = 0; pass < 2; pass++) {
            for (const row of rows) assert.equal(f.store.scopedAllowed(row.key, 'mission', `1:${row.id}`, 'enter', now), true)
        }
        assert.equal(f.observation.counts.stateGet, 2050)
        assert.equal(f.observation.counts.decode, 1026, 'overflow still validates freshly without changing any decision')
    })
})

test('linked box decisions re-read both the parent and box when either control changes inside the scope', t => {
    const f = fixture(t), parentKey = 'active_mission_event:2', boxKey = 'box_gacha:3'
    const rows = [[parentKey, 'active_mission_event', 2], [boxKey, 'box_gacha', 3]].map(([key, type, id]) => ({
        key, type, id, name: 'linked decision fixture', source: 'fixture', originalStartMs: null,
        originalEndMs: null, originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false,
    }))
    const store = new ContentOperationsStore(f.db, { ...f.catalog, rows: [...f.catalog.rows, ...rows] },
        () => CONTENT_ACTIONS, () => ({ digest: 'fixture', matchesCatalog: true }),
        undefined, undefined, undefined, undefined,
        { available: true, associations: [{ parentKey, boxKey, relationshipMatches: true }] })
    const insert = f.db.prepare('INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?)')
    const write = f.db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?')
    const controls = rows.map(row => ({ ...JSON.parse(f.raw), key: row.key, instanceId: `${row.key}:original`,
        catalogDigest: store.digest, contentDigest: store.contentDigests.get(row.key), missionKeys: null,
        flags: { visible: true, enter: true, claim: true, exchange: true } }))
    for (const state of controls) insert.run(state.key, JSON.stringify(state))
    store.withDecisionScope(() => {
        assert.equal(store.allowed(boxKey, 'claim', now), true)
        write.run(JSON.stringify({ ...controls[0], flags: { ...controls[0].flags, enter: false } }), parentKey)
        assert.equal(store.allowed(boxKey, 'claim', now), false)
        write.run(JSON.stringify(controls[0]), parentKey)
        assert.equal(store.allowed(boxKey, 'claim', now), true)
        write.run(JSON.stringify({ ...controls[1], flags: { ...controls[1].flags, visible: false } }), boxKey)
        assert.equal(store.allowed(boxKey, 'claim', now), false)
        write.run(JSON.stringify(controls[1]), boxKey)
        assert.equal(store.allowed(boxKey, 'claim', now), true)
        write.run(JSON.stringify({ ...controls[0], endsAtMs: now + 1 }), parentKey)
        assert.equal(store.allowed(boxKey, 'claim', now + 1), true)
        assert.equal(store.allowed(boxKey, 'claim', now + 2), false)
    })
})
