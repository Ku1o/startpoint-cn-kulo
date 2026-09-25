const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mission-counter-noop-'))
process.env.DATA_DIR = directory
const { initializeDatabase } = require('../out/data')
initializeDatabase()
const db = require('../out/data/db').getDb()
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const counters = require('../out/lib/mission/counters')

test.after(() => {
    db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory, {recursive:true})
})

test('max/min counters skip unchanged writes while preserving the returned value', () => {
    const playerId = insertDefaultPlayerSync(insertAccountSync({
        appId:'wf_cn', idpAlias:'', idpCode:'counter', idpId:'noop', status:'normal',
    }).id).id
    const query = {dimension:'test.noop', scopeType:'lifetime', scopeKey:'all', qualifier:{mode:'single'}}
    assert.equal(counters.setMissionCounterMaxSync(playerId, query, 5), 5)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 1)
    const timestamp = db.prepare('SELECT updated_at FROM players_mission_counters WHERE player_id=?').get(playerId).updated_at
    assert.equal(counters.setMissionCounterMaxSync(playerId, query, 4), 5)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 0)
    assert.equal(db.prepare('SELECT updated_at FROM players_mission_counters WHERE player_id=?').get(playerId).updated_at, timestamp)
    assert.equal(counters.setMissionCounterMinSync(playerId, query, 9), 5)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 0)
    assert.equal(counters.setMissionCounterMinSync(playerId, query, 3), 3)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 1)
    assert.equal(counters.setMissionCounterMaxSync(playerId, query, 8), 8)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 1)

    const { migrateStorageLayout } = require('../out/lib/storage-layout')
    migrateStorageLayout(db)
    const compactPlayerId = insertDefaultPlayerSync(insertAccountSync({
        appId:'wf_cn', idpAlias:'', idpCode:'counter-compact', idpId:'noop-compact', status:'normal',
    }).id).id
    const compactQuery = {dimension:'test.noop.compact', scopeType:'lifetime', scopeKey:'all', qualifier:{mode:'single'}}
    assert.equal(counters.setMissionCounterMaxSync(compactPlayerId, compactQuery, 5), 5)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 1)
    assert.equal(counters.setMissionCounterMaxSync(compactPlayerId, compactQuery, 4), 5)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 0)
    assert.equal(counters.setMissionCounterMinSync(compactPlayerId, compactQuery, 9), 5)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 0)
    assert.equal(counters.setMissionCounterMinSync(compactPlayerId, compactQuery, 3), 3)
    assert.equal(db.prepare('SELECT changes() AS n').get().n, 1)
})
