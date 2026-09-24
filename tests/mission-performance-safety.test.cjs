const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mission-performance-safety-'))
process.env.DATA_DIR = dir
const { getDb } = require('../out/data/db')
const db = getDb()
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const characters = require('../out/data/domains/character')
const master = require('../out/lib/mission/master-data')
const stages = require('../out/lib/mission/stages')
const { runMeasuredSingleTransaction } = require('../out/lib/sqlite-write-coordinator')
const { drainServerWorkPerformance } = require('../out/lib/server-work-performance')
const { getRaidQuestCounts } = require('../out/lib/raid-event-counts')
const { createPlayerSaveSnapshotV2Sync, assertPlayerSnapshotCoverageSync } = require('../out/data/snapshots/player-snapshot')
test.after(() => {
    db.close()
    assert.equal(path.dirname(fs.realpathSync(dir)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(dir, {recursive: true})
})

test('indexed mission definitions retain IDs, availability boundaries and caller-owned arrays', () => {
    for (const category of master.MISSION_CATEGORIES) {
        for (const definition of master.getMissionMasterDefinitions(category)) {
            assert.equal(master.getMissionMasterDefinition(category, definition.missionId), definition)
            assert.equal(master.isMissionDefinitionEnabledAt(definition, new Date('2026-09-24T00:00:00Z'), definition.eventId),
                master.isMissionDefinitionEnabledAt({...definition}, new Date('2026-09-24T00:00:00Z'), definition.eventId))
        }
        const original = stages.getMissionIdsByCategory(category)
        stages.getMissionIdsByCategory(category).pop()
        assert.deepEqual(stages.getMissionIdsByCategory(category), original)
        assert.equal(master.getMissionMasterDefinition(category, -999), undefined)
    }
    const definition = {category: 1, missionId: 1, pattern: 'x', row: [], enableStart: '2026-09-24 08:00:00'}
    const date = new Date('2026-09-24T00:00:00Z')
    assert.equal(master.isMissionDefinitionEnabledAt(definition, date), true)
    definition.enableStart = '2026-09-24 08:00:01'
    assert.equal(master.isMissionDefinitionEnabledAt(definition, date), false)
    assert.throws(() => master.getMissionMasterDefinition(999, 1), /unsupported/)
})

test('lightweight character facts equal full records and see reward writes and rollback', () => {
    const p = insertDefaultPlayerSync(insertAccountSync({appId: 'wf_cn', idpAlias: '', idpCode: 'perf', idpId: '', status: 'normal'}).id)
    const ids = Object.keys(require('../assets/character.json')).map(Number).slice(0, 30)
    for (const id of ids) if (!characters.playerOwnsCharacterSync(p.id, id)) characters.insertDefaultPlayerCharacterSync(p.id, id)
    const compare = () => assert.deepEqual(characters.getPlayerCharacterMissionFactsSync(p.id), Object.fromEntries(
        Object.entries(characters.getPlayerCharactersSync(p.id)).map(([id, c]) => [id,
            {exp: c.exp, evolutionLevel: c.evolutionLevel, overLimitStep: c.overLimitStep, bondTokenList: c.bondTokenList}]),
    ))
    compare()
    const before = characters.getPlayerCharacterMissionFactsSync(p.id)
    assert.throws(() => runMeasuredSingleTransaction(db, () => {
        db.prepare('UPDATE players_characters SET exp = exp + 10000, over_limit_step = over_limit_step + 1 WHERE player_id = ?').run(p.id)
        compare()
        assert.notDeepEqual(characters.getPlayerCharacterMissionFactsSync(p.id), before)
        throw Error('rollback')
    }), /rollback/)
    assert.deepEqual(characters.getPlayerCharacterMissionFactsSync(p.id), before)
    runMeasuredSingleTransaction(db, () => db.prepare('UPDATE players_characters SET exp = exp + 10000 WHERE player_id = ?').run(p.id))
    compare()
    const performance = drainServerWorkPerformance()
    assert.equal(performance['db.single.body'].n, 2)
    assert.equal(performance['db.single.commit'].n, 1)
    const beforeCache = createPlayerSaveSnapshotV2Sync(p.id)
    getRaidQuestCounts(db, 7)
    assertPlayerSnapshotCoverageSync()
    const afterCache = createPlayerSaveSnapshotV2Sync(p.id)
    assert.equal(afterCache.schemaFingerprint, beforeCache.schemaFingerprint)
    assert.ok(Object.keys(beforeCache.data.tables).length > 0)
    assert.deepEqual(afterCache.data.tables, beforeCache.data.tables)
})

test('batched party clears count each character once and preserve leader, multiplayer and rollback semantics', () => {
    const p = insertDefaultPlayerSync(insertAccountSync({appId: 'wf_cn', idpAlias: '', idpCode: 'batch', idpId: '', status: 'normal'}).id)
    const { trackCharacterClears } = require('../out/lib/quest/finish/character-clear-tracker')
    const { getPlayerCharacterClearSync } = require('../out/data/domains/character_clear')
    const party = {characters: [{id: 101}, {id: 102}, {id: 102}], unison_characters: [{id: 101}, null, {id: 103}]}
    db.transaction(() => trackCharacterClears({playerId: p.id, party, isMulti: true}))()
    db.transaction(() => trackCharacterClears({playerId: p.id, party, isMulti: false}))()
    assert.deepEqual(getPlayerCharacterClearSync(p.id, 101), {
        clear_count: 2, multi_count: 1, leader_clear_count: 2, leader_multi_count: 1, leader_power_flip_count: 0,
    })
    for (const id of [102, 103]) assert.deepEqual(getPlayerCharacterClearSync(p.id, id), {
        clear_count: 2, multi_count: 1, leader_clear_count: 0, leader_multi_count: 0, leader_power_flip_count: 0,
    })
    assert.throws(() => db.transaction(() => {trackCharacterClears({playerId: p.id, party, isMulti: true}); throw Error('rollback')})(), /rollback/)
    assert.equal(getPlayerCharacterClearSync(p.id, 101).clear_count, 2)
})
