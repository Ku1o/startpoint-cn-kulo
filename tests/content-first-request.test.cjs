'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const Sqlite = require('better-sqlite3')
const { setDbOverride } = require('../out/data/db')
const operations = require('../out/lib/content-operations')
const duringOriginalWindow = Date.parse('2025-07-20T04:00:00Z')

function uninitialized(t) {
    const db = new Sqlite(':memory:')
    db.exec('CREATE TABLE preserved(player_id INTEGER,progress INTEGER,claimed INTEGER); INSERT INTO preserved VALUES(19,11,1)')
    setDbOverride(db)
    assert.equal(db.prepare("SELECT name FROM sqlite_master WHERE name='content_operations_meta'").get(), undefined)
    t.after(() => { setDbOverride(null); db.close() })
    return db
}

test('first seasonal draw guard cannot fall through to calendar before the first snapshot', t => {
    const db = uninitialized(t)
    assert.equal(operations.contentDecision('gacha', 1704, 'enter', duringOriginalWindow), false)
    assert.equal(db.prepare('SELECT revision FROM content_operations_meta WHERE id=1').get().revision, 0)
    assert.deepEqual(db.prepare('SELECT * FROM preserved').all(), [{ player_id: 19, progress: 11, claimed: 1 }])
    assert.equal(operations.contentDecision('gacha', 1704, 'exchange', duringOriginalWindow), true)
    assert.equal(operations.contentQuestDecision(1, 1000001, duringOriginalWindow), null)
})

test('first mapped event quest guard applies closed defaults without prewarming the store', t => {
    uninitialized(t)
    assert.equal(operations.contentQuestDecision(13, 1017, duringOriginalWindow), false)
})

test('first mapped seasonal mission guard closes new facts and preserves independent claim qualification', t => {
    uninitialized(t)
    assert.equal(operations.contentMissionDecision(6, 53, 'enter', duringOriginalWindow), false)
    assert.equal(operations.contentMissionDecision(6, 53, 'claim', duringOriginalWindow), true)
})
