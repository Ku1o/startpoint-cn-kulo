'use strict'
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { test, after } = require('node:test'), assert = require('node:assert/strict')
const { createHash, randomUUID } = require('node:crypto')
const { spawnSync } = require('node:child_process')
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'water-gerald-ex30-'))
Object.assign(process.env, { DATA_DIR: directory, CN_WRITER_THREAD: '0', MULTI_REALTIME_PROCESS: '0',
    MULTI_REALTIME_OWNER_CHILD: '0', GAME_ROUTINE_LOGS: 'off', GAME_VERBOSE_LOGS: 'false',
    GACHA_SEED_DIR: path.join(directory, 'seeds') })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const db = load('data/db').getDb()
assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
const players = load('data/domains/player'), characters = load('data/domains/character')
const claims = load('data/domains/water-gerald-claim'), snapshots = load('data/snapshots/player-snapshot')
const grant = load('lib/quest/finish/water-gerald-reward').grantWaterGeraldEx30Sync
const settle = load('lib/quest/finish/single-finish-transaction').settleSingleQuestFinishInTransaction
const merged = load('data/utils/player-data').getMergedPlayerDataSync
const CHAR = 129989
function player() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '',
        idpCode: 'water-gerald', idpId: randomUUID(), status: 'normal' })
    return players.insertDefaultPlayerSync(account.id)
}
function input(p, extra = {}) {
    return { playerId: p.id, questCategory: 24, questId: 700100030, questAccomplished: true,
        questData: { rushEventId: 700100, rushEventFolderId: 1, rushEventRound: 30 }, ...extra }
}
function owned(p) { return characters.getPlayerCharacterSync(p.id, CHAR) }
function count(p) { return claims.getWaterGeraldClaimsSync(p.id).length }
function finish(p, accomplished = true, extra = {}) {
    const playId = randomUUID(), questId = 700100030, category = 24
    const party = { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
        equipments: [null, null, null], ability_soul_ids: [null, null, null] }
    const activeQuestData = { playerId: p.id, playId, questId, category, continueCount: 0, startedAtMs: Date.now() - 60000,
        useBoostPoint: false, useBossBoostPoint: false, isMulti: false, isAutoStartMode: false, clockVersion: 1 }
    load('data/domains/quest_active').insertPlayerActiveQuestSync(p.id, activeQuestData)
    const args = { ...input(p), viewerId: 870000000 + p.id,
        questData: { ...load('lib/assets').getQuestFromCategorySync(category, questId),
            characterExpReward: 0, poolExpReward: 0, manaReward: 0, rankPointReward: 0,
            clearReward: undefined, sPlusReward: undefined, scoreRewardGroup: null },
        activeQuestData, body: { quest_id: questId, category, play_id: playId, score: 1, elapsed_time_ms: 60000,
            continue_count: 0, add_mana: 0, is_accomplished: accomplished, statistics: { party, max_combo_count: 0 } },
        clearTime: 60000, clearRank: 5, questAccomplished: accomplished, battleFactsAccomplished: accomplished,
        fiveBossSoloQuest: false, registered: true, scoreAttackBorderTiers: [], manaObtained: 0,
        displayMode15ManaAsFieldDrop: false, finishCacheKey: playId, receiptPlayId: playId, ...extra }
    return { args, run: () => db.transaction(() => settle(args))() }
}
function oldV2(snapshot, omitBusiness = false) {
    const copy = structuredClone(snapshot), omitted = new Set(['players_water_gerald_claims'])
    if (omitBusiness) for (const table of ['players_ex_boost_pending_draws', 'players_shop_campaign_lineups', 'players_bond_token_exchanges']) omitted.add(table)
    const tables = snapshots.PLAYER_SNAPSHOT_V2_TABLES.filter(table => !omitted.has(table))
    copy.schemaFingerprint = createHash('sha256').update(JSON.stringify(tables.map(table => ({ table,
        columns: db.prepare(`PRAGMA table_info("${table}")`).all().map(column => ({ name: column.name, type: column.type,
            notnull: column.notnull, defaultValue: column.dflt_value, pk: column.pk })) })))).digest('hex')
    for (const table of omitted) delete copy.data.tables[table]
    copy.summary.includedTableCount = tables.length
    copy.summary.rowCount = Object.values(copy.data.tables).reduce((sum, table) => sum + table.rows.length, 0)
    return copy
}
after(async () => {
    await load('lib/seed-validator').default.close()
    if (db.open) db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory, { recursive: true })
})

test('successful newly settled EX30 grants once for new and previously cleared players', () => {
    for (const old of [false, true]) {
        const p = player()
        if (old) load('data/domains/quest').insertPlayerQuestProgressSync(p.id, 24, {
            questId: 700100030, finished: true, bestElapsedTimeMs: 123, highScore: 999, clearRank: 5, leaderCharacterId: 1 })
        assert.equal(count(p), 0, 'history does not seed entitlement')
        const first = finish(p), result = first.run().response.data
        assert.equal(count(p), 1)
        const character = owned(p)
        assert.equal(character.exp, 0); assert.equal(character.overLimitStep, 0); assert.equal(character.evolutionLevel, 0)
        assert.equal(character.stack, 0)
        assert.ok(result.character_list.some(row => row.character_id === CHAR))
        assert.ok(result.joined_character_id_list.includes(CHAR))
        assert.ok(result.rush_event.rush_battle_reward_list.some(row => row.kind === 5 && row.kind_id === CHAR && row.number === 1))
        assert.deepEqual(db.transaction(() => settle(first.args))().response.data, result, 'same play replays')
        const next = finish(p).run().response.data
        assert.equal(count(p), 1); assert.equal(owned(p).stack, 0)
        assert.ok(!next.rush_event.rush_battle_reward_list.some(row => row.kind_id === CHAR))
        if (old) {
            const progress = load('data/domains/quest').getPlayerSingleQuestProgressSync(p.id, 24, 700100030)
            assert.equal(progress.bestElapsedTimeMs, 123); assert.equal(progress.highScore, 999)
        }
    }
})

test('failure, exit and nonmatching category/event/folder/round cannot claim', () => {
    const p = player()
    finish(p, false).run()
    assert.equal(count(p), 0); assert.equal(owned(p), null)
    for (const extra of [{ questAccomplished: false }, { questCategory: 1 }, { questId: 700100029 },
        { questData: { rushEventId: 700099, rushEventFolderId: 1, rushEventRound: 30 } },
        { questData: { rushEventId: 700100, rushEventFolderId: 2, rushEventRound: 30 } },
        { questData: { rushEventId: 700100, rushEventFolderId: 1, rushEventRound: 0 } }]) {
        assert.equal(grant(input(p, extra)), null)
    }
    assert.equal(count(p), 0)
    assert.ok(grant(input(p))); assert.equal(count(p), 1)
})

test('owned characters receive only ordinary duplicate handling, without level or breakthrough changes', () => {
    const p = player()
    load('lib/character').givePlayerCharacterSync(p.id, CHAR)
    characters.updatePlayerCharacterSync(p.id, CHAR, { exp: 1234, overLimitStep: 2, evolutionLevel: 1 })
    const before = owned(p)
    assert.ok(grant(input(p)))
    const after = owned(p)
    assert.equal(after.exp, before.exp); assert.equal(after.overLimitStep, before.overLimitStep)
    assert.equal(after.evolutionLevel, before.evolutionLevel); assert.equal(after.stack, before.stack + 1)
    assert.equal(grant(input(p)), null); assert.equal(owned(p).stack, after.stack)
})

test('character-write or later settlement failure rolls back claim, inventory and active-play consumption', () => {
    const p = player()
    db.exec(`CREATE TEMP TRIGGER reject_water_gerald BEFORE INSERT ON players_characters
        WHEN NEW.id=${CHAR} BEGIN SELECT RAISE(ABORT,'water-character-fault'); END`)
    const battle = finish(p)
    try { assert.throws(battle.run, /water-character-fault/) } finally { db.exec('DROP TRIGGER reject_water_gerald') }
    assert.equal(count(p), 0); assert.equal(owned(p), null)
    assert.ok(load('data/domains/quest_active').getPlayerActiveQuestSync(p.id))
    db.exec(`CREATE TEMP TRIGGER reject_water_receipt BEFORE INSERT ON battle_settlement_ledger
        WHEN NEW.player_id=${p.id} BEGIN SELECT RAISE(ABORT,'water-late-fault'); END`)
    try { assert.throws(battle.run, /water-late-fault/) } finally { db.exec('DROP TRIGGER reject_water_receipt') }
    assert.equal(count(p), 0); assert.equal(owned(p), null)
    assert.ok(load('data/domains/quest_active').getPlayerActiveQuestSync(p.id))
    battle.run(); assert.equal(count(p), 1)
})

test('V2 carries claims to another account and all old/empty archive forms preserve destination claims', () => {
    const source = player(), target = player(), empty = snapshots.createPlayerSaveSnapshotV2Sync(source.id)
    const old = oldV2(empty), older = oldV2(empty, true)
    grant(input(source))
    const archive = snapshots.createPlayerSaveSnapshotV2Sync(source.id)
    assert.equal(archive.data.tables.players_water_gerald_claims.rows.length, 1)
    snapshots.restorePlayerSaveSnapshotV2Sync(archive, target.id)
    assert.equal(count(target), 1); assert.equal(grant(input(target)), null)
    for (const prior of [empty, old, older]) {
        const before = snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables
        assert.throws(() => snapshots.restorePlayerSaveSnapshotV2Sync(prior, target.id), /水杰.*存档/)
        assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables, before)
        assert.ok(owned(target), 'a rejected pre-claim archive cannot delete the awarded character')
        assert.equal(count(target), 1); assert.equal(grant(input(target)), null)
    }
    const fresh = player()
    snapshots.restorePlayerSaveSnapshotV2Sync(old, fresh.id)
    assert.equal(count(fresh), 0); assert.ok(grant(input(fresh)), 'old history alone does not claim reward')
})

test('V1 carries portable claims, preserves target on absent/empty field, and malformed import is atomic', () => {
    const source = player(), target = player()
    grant(input(source))
    const exported = merged(source.id)
    assert.equal(exported.waterGeraldClaims.length, 1)
    const transfer = () => { const value = merged(source.id); value.player.id = target.id; return value }
    players.replacePlayerDataSync(transfer())
    assert.equal(count(target), 1); assert.equal(grant(input(target)), null)
    for (const legacy of [true, false]) {
        const value = transfer()
        if (legacy) delete value.waterGeraldClaims
        else value.waterGeraldClaims = []
        players.replacePlayerDataSync(value)
        assert.equal(count(target), 1); assert.equal(grant(input(target)), null)
    }
    const before = snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables
    const invalid = transfer(); invalid.waterGeraldClaims = [{ claimedAt: -1 }]
    assert.throws(() => players.replacePlayerDataSync(invalid), /permanent water Gerald/)
    assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables, before)
})

test('V1 and V2 preserve character entitlement across source/target claim and character-presence combinations', () => {
    for (const format of ['v1', 'v2']) for (const targetClaimed of [false, true]) {
        for (const sourceClaimed of [false, true]) for (const hasCharacter of [false, true]) {
            const source = player(), target = player()
            if (sourceClaimed) grant(input(source))
            else if (hasCharacter) load('lib/character').givePlayerCharacterSync(source.id, CHAR)
            if (targetClaimed) {
                grant(input(target))
                characters.updatePlayerCharacterSync(target.id, CHAR, { exp: 9999, overLimitStep: 4, stack: 7 })
            }
            if (owned(source)) {
                characters.updatePlayerCharacterSync(source.id, CHAR, { exp: 1234, overLimitStep: 2,
                    evolutionLevel: 1, stack: 3 })
                characters.insertPlayerCharacterManaNodesSync(source.id, CHAR, [259978201])
                characters.updatePlayerCharacterManaNodeAwakeLevelSync(source.id, CHAR, 259978201, 1)
            }
            let archive = format === 'v1' ? merged(source.id) : snapshots.createPlayerSaveSnapshotV2Sync(source.id)
            if (format === 'v1') {
                archive.player.id = target.id
                if (!hasCharacter) delete archive.characterList[String(CHAR)]
            } else if (!hasCharacter) {
                const table = archive.data.tables.players_characters
                table.rows = table.rows.filter(row => row[table.columns.indexOf('id')] !== CHAR)
                archive.summary.rowCount = Object.values(archive.data.tables).reduce((sum, row) => sum + row.rows.length, 0)
            }
            const importArchive = () => format === 'v1' ? players.replacePlayerDataSync(archive)
                : snapshots.restorePlayerSaveSnapshotV2Sync(archive, target.id)
            const before = snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables
            if (!hasCharacter && (sourceClaimed || targetClaimed)) {
                assert.throws(importArchive, /水杰.*存档/, `${format} cannot strand a spent entitlement`)
                assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables, before)
                if (targetClaimed) assert.ok(owned(target))
                continue
            }
            importArchive()
            assert.equal(count(target), Number(sourceClaimed || targetClaimed))
            if (hasCharacter) {
                const actual = owned(target)
                // Character-containing archives follow ordinary replacement semantics,
                // including restoring older lower progression rather than mixing owners.
                assert.equal(actual.exp, 1234); assert.equal(actual.overLimitStep, 2)
                assert.equal(actual.evolutionLevel, 1); assert.equal(actual.stack, 3)
                const nodes = characters.getPlayerCharactersManaNodesSync(target.id)
                assert.deepEqual(nodes[CHAR], [259978201])
                assert.equal(characters.getPlayerCharactersManaNodeAwakeLevelsSync(target.id)[CHAR][259978201], 1)
            } else assert.equal(owned(target), null)
            if (sourceClaimed || targetClaimed) {
                const beforeCharacter = owned(target)
                assert.equal(grant(input(target)), null)
                assert.deepEqual(owned(target), beforeCharacter, 'import/replay does not add another duplicate')
            } else {
                assert.ok(grant(input(target)))
                assert.equal(owned(target).stack, hasCharacter ? 4 : 0, 'only a new successful entitlement grants one ordinary copy')
            }
        }
    }
})

test('pre-claim V1 archives with absent or empty claim metadata cannot remove an awarded water Gerald', () => {
    const source = player(), target = player(), beforeClaimArchive = merged(source.id)
    grant(input(target))
    for (const absent of [true, false]) {
        const archive = structuredClone(beforeClaimArchive); archive.player.id = target.id
        if (absent) delete archive.waterGeraldClaims
        else archive.waterGeraldClaims = []
        const before = snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables
        assert.throws(() => players.replacePlayerDataSync(archive), /水杰.*存档/)
        assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables, before)
        assert.ok(owned(target)); assert.equal(count(target), 1); assert.equal(grant(input(target)), null)
    }
})

test('late V1/V2 claim import failures roll back all imported player data', () => {
    const source = player(), target = player()
    grant(input(source)); grant(input(target))
    const before = snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables
    const archive = snapshots.createPlayerSaveSnapshotV2Sync(source.id)
    const v1 = merged(source.id); v1.player.id = target.id
    db.exec(`CREATE TEMP TRIGGER reject_import_claim BEFORE INSERT ON players_water_gerald_claims
        WHEN NEW.player_id=${target.id} BEGIN SELECT RAISE(ABORT,'water-import-fault'); END`)
    try {
        assert.throws(() => snapshots.restorePlayerSaveSnapshotV2Sync(archive, target.id), /water-import-fault/)
        assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables, before)
        assert.throws(() => players.replacePlayerDataSync(v1), /water-import-fault/)
        assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables, before)
    } finally { db.exec('DROP TRIGGER reject_import_claim') }
})

test('claimed progress survives a fresh process and malformed V2 claim state is rejected before writes', () => {
    const p = player(); grant(input(p))
    const child = spawnSync(process.execPath, ['-e', `
        ${compiled ? '' : "require('ts-node/register/transpile-only');"}
        const root='./${compiled ? 'out' : 'src'}';
        const claims=require(root+'/data/domains/water-gerald-claim');
        const grant=require(root+'/lib/quest/finish/water-gerald-reward').grantWaterGeraldEx30Sync;
        require('node:assert/strict').equal(claims.getWaterGeraldClaimsSync(${p.id}).length,1);
        require('node:assert/strict').equal(grant(${JSON.stringify(input(p))}),null);
        require(root+'/lib/seed-validator').default.close().then(()=>require(root+'/data/db').getDb().close());
    `], { cwd: path.resolve(__dirname, '..'), env: process.env, encoding: 'utf8', timeout: 30000, windowsHide: true })
    assert.equal(child.error, undefined); assert.equal(child.status, 0, child.stderr + child.stdout)
    const target = player(), before = snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables
    for (const mutation of [
        archive => { delete archive.data.tables.players_water_gerald_claims },
        archive => { const table = archive.data.tables.players_water_gerald_claims; table.rows[0][table.columns.indexOf('claimed_at')] = -1 },
    ]) {
        const archive = snapshots.createPlayerSaveSnapshotV2Sync(p.id); mutation(archive)
        assert.throws(() => snapshots.restorePlayerSaveSnapshotV2Sync(archive, target.id))
        assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(target.id).data.tables, before)
    }
})
