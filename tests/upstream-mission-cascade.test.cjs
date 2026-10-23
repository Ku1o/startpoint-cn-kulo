'use strict'
require('ts-node/register/transpile-only')
const { test, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'upstream-mission-cascade-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    CN_WRITER_THREAD: '0', GAME_ROUTINE_LOGS: 'off' })
const load = name => require(`../src/${name}`)
load('data').initializeDatabase()
const db = load('data/db').getDb()
assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '',
    idpCode: 'cascade-test', idpId: 'cascade-test', status: 'normal' })
const player = load('data/domains/player').insertDefaultPlayerSync(account.id)
const missions = load('data/domains/mission')
const items = load('data/domains/item')
const settle = load('lib/mission/settlement').settleMissionCategories
const mergeSettlementResults = load('lib/mission/settlement').mergeSettlementResults
after(async () => {
    await load('lib/seed-validator').default.close()
    if (db.open) db.close()
    fs.rmSync(directory, { recursive: true })
})

test('cascade response retains first-acquisition fields when a later round updates only the stack', () => {
    const empty = { missionInfo: [], itemList: {}, equipmentList: [], degreeIds: [], passCardPoints: {} }
    const first = { ...empty, characterList: [{ character_id: 111015, viewer_id: 42,
        entry_count: 1, join_time: '2026-01-01 00:00:00', bond_token_list: [{ mana_board_index: 1, status: 0 }], stack: 0 }],
        equipmentList: [{ equipment_id: 5010005, level: 1, enhancement_level: 0, stack: 0 }] }
    const next = { ...empty, characterList: [{ character_id: 111015, stack: 1 }],
        equipmentList: [{ equipment_id: 5010005, stack: 2 }] }
    const merged = mergeSettlementResults(first, next)
    assert.deepEqual(merged.characterList, [{ ...first.characterList[0], stack: 1 }])
    assert.deepEqual(merged.equipmentList, [{ ...first.equipmentList[0], stack: 2 }])
})

test('regular mission item reward settles the dependent title in one response and rolls back as one transaction', () => {
    // Native regular mission 33 pays 300 crafting stones at each of stages
    // 1..4. The title at 41000 requires 1000 lifetime acquired stones.
    missions.updatePlayerCategoryMissionSync(player.id, 1, 33, 15)
    missions.updatePlayerCategoryMissionSync(player.id, 1, 1, 100)
    const before = items.getPlayerItemSync(player.id, 100000) ?? 0
    db.exec(`CREATE TRIGGER deny_title_cascade BEFORE INSERT ON players_category_mission_stages
        WHEN NEW.category=5 AND NEW.mission_id=41000
        BEGIN SELECT RAISE(ABORT, 'cascade rollback'); END`)
    try {
        assert.throws(() => settle(player.id, [{ category: 1, missionIds: [33] }], new Date()), /cascade rollback/)
        assert.equal(items.getPlayerItemSync(player.id, 100000) ?? 0, before)
        assert.deepEqual(missions.getPlayerCategoryMissionsSync(player.id, 1)['33'].stages, [])
    } finally {
        db.exec('DROP TRIGGER deny_title_cascade')
    }
    const result = settle(player.id, [{ category: 1, missionIds: [33] }], new Date())
    assert.ok(result.missionInfo.some(row => row.mission_category_id === 1 && row.mission_id === 33))
    assert.ok(result.missionInfo.some(row => row.mission_category_id === 5 && row.mission_id === 41000))
    assert.ok(!result.missionInfo.some(row => row.mission_category_id === 1 && row.mission_id === 1),
        'an unrelated old completed regular mission must not be swept into a scoped reward chain')
    assert.equal(result.itemList['100000'], items.getPlayerItemSync(player.id, 100000))
    assert.ok((items.getPlayerItemSync(player.id, 100000) ?? 0) >= before + 1200)
    assert.ok(missions.getPlayerCategoryMissionsSync(player.id, 5)['41000'].stages['1'])
    assert.deepEqual(settle(player.id, [{ category: 1, missionIds: [33] }], new Date()).missionInfo, [])
})
