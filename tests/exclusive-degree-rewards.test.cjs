const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const crypto = require('node:crypto')

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-exclusive-degrees-'))
process.env.DATA_DIR = dataDir
process.env.GACHA_SEED_DIR = path.join(dataDir, 'isolated-seeds')
fs.mkdirSync(process.env.GACHA_SEED_DIR)

const { getDb } = require('../out/data/db')
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const { saveAccountDefaultPlayer } = require('../out/data/activeAccount')
const {
    getPlayerEquipmentSync,
    insertPlayerEquipmentSync,
    updatePlayerEquipmentSync,
} = require('../out/data/domains/equipment')
const { addPlayerShopPurchaseCountSync } = require('../out/data/domains/shopPurchase')
const { getPlayerDegreeIdsSync, hasPlayerDegreeSync } = require('../out/data/domains/degree')
const { grantAbyssShopDegreeRewardSync, isAbyssShopDegreeEligible } = require('../out/lib/abyss-shop-degree-reward')
const {
    EQUIPMENT_DEGREE_CATALOG,
    grantEquipmentDegreeRewardsSync,
    grantPracticeExclusiveDegreeRewardsSync,
    isEquipmentDegreeEnhancementComplete,
} = require('../out/lib/equipment-degree-rewards')
const { recordBattleMissionDimensions } = require('../out/lib/mission/battle-dimensions')
const { summarizeBattleStatistics } = require('../out/lib/mission/events')
const { QuestCategory, ShopType } = require('../out/lib/types')

const db = getDb()

function player(label = 'fixture') {
    const account = insertAccountSync({
        appId: 'wf_cn', idpAlias: '', idpCode: 'fixture', idpId: label, status: 'normal',
    })
    const saved = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, saved.id)
    return saved.id
}

function equipment(playerId, id, enhancementLevel) {
    const existing = getPlayerEquipmentSync(playerId, id)
    if (existing) updatePlayerEquipmentSync(playerId, id, { level: 1, enhancementLevel, protection: false, stack: 999 })
    else insertPlayerEquipmentSync(playerId, id, { level: 1, enhancementLevel, protection: false, stack: 999 })
}

function practice(playerId, overrides = {}) {
    return {
        type: 'battle_finish', playerId, questCategory: QuestCategory.PRACTICE, questId: 1,
        accomplished: true, mode: 'single', clearTimeMs: 180000,
        partyCharacterIds: [], unisonCharacterIds: [], statistics: summarizeBattleStatistics({}),
        ...overrides,
    }
}

test.after(() => {
    if (db.open) db.close()
    fs.rmSync(dataDir, { recursive: true, force: true })
})

test('the fused chain carries three definitions and an 18-member 1.4.109 archive', () => {
    const definitions = require('../assets/degree_exclusive.json')
    assert.deepEqual(Object.keys(definitions).map(Number), [9911001, 9911002, 9911003])
    const manifest = require('../assets/asset-patch/manifest.json')
    assert.equal(manifest.cdn_version, '1.4.109')
    const patch = manifest.patches.find(row => row.id === 'author-update-fusion-20260914')
    assert.ok(patch)
    assert.equal(patch.depends_on, '1.4.108')
    const receipt = patch.archive_integrity.find(row => row.name === patch.archive)
    assert.equal(receipt.members, 18)
    const archive = path.join(__dirname, '..', 'assets/asset-patch/active', patch.archive)
    const bytes = fs.readFileSync(archive)
    assert.equal(bytes.length, receipt.size)
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), receipt.sha256)
})

test('the shop achievement reads persisted ticket counters and ignores inventory or shop type', () => {
    assert.equal(isAbyssShopDegreeEligible(9998, 9999), false)
    assert.equal(isAbyssShopDegreeEligible(9999, 9999), true)
    const playerId = player('shop')
    addPlayerShopPurchaseCountSync(playerId, 9700116, 9999)
    addPlayerShopPurchaseCountSync(playerId, 9700117, 9998)
    assert.deepEqual(grantAbyssShopDegreeRewardSync(playerId), [])
    addPlayerShopPurchaseCountSync(playerId, 9700117, 1)
    assert.deepEqual(grantAbyssShopDegreeRewardSync(playerId), [9911001])
    assert.deepEqual(grantAbyssShopDegreeRewardSync(playerId), [])
    assert.equal(hasPlayerDegreeSync(playerId, 9911001), true)
})

test('the two equipment achievements require every exact enhancement_level and ignore level or stack', () => {
    const playerId = player('equipment')
    const all = [...EQUIPMENT_DEGREE_CATALOG[0].equipment_ids, 5900101]
    for (const id of all) equipment(playerId, id, 119)
    assert.equal(isEquipmentDegreeEnhancementComplete(119), false)
    assert.equal(isEquipmentDegreeEnhancementComplete(120), true)
    assert.deepEqual(grantEquipmentDegreeRewardsSync(playerId), [])
    for (const id of all) equipment(playerId, id, 120)
    assert.deepEqual(grantEquipmentDegreeRewardsSync(playerId), [9911002, 9911003])
    assert.deepEqual(grantEquipmentDegreeRewardsSync(playerId), [])
    assert.deepEqual(getPlayerDegreeIdsSync(playerId).filter(id => id >= 9911001), [9911002, 9911003])
})

test('a successful single-player practice backfills all three achievements for an old eligible player', () => {
    const playerId = player('practice')
    for (const id of EQUIPMENT_DEGREE_CATALOG[0].equipment_ids) equipment(playerId, id, 120)
    equipment(playerId, 5900101, 120)
    addPlayerShopPurchaseCountSync(playerId, 9700116, 9999)
    addPlayerShopPurchaseCountSync(playerId, 9700117, 9999)
    assert.deepEqual(grantPracticeExclusiveDegreeRewardsSync(practice(playerId)), [9911001, 9911002, 9911003])
    assert.deepEqual(grantPracticeExclusiveDegreeRewardsSync(practice(playerId)), [])
    assert.deepEqual(grantPracticeExclusiveDegreeRewardsSync(practice(playerId, { accomplished: false })), [])
    assert.deepEqual(grantPracticeExclusiveDegreeRewardsSync(practice(playerId, { mode: 'multi' })), [])
    assert.deepEqual(grantPracticeExclusiveDegreeRewardsSync(practice(playerId, { questCategory: QuestCategory.MAIN })), [])
})

test('the battle-dimension entry point performs the same practice backfill inside its transaction', () => {
    const playerId = player('battle-entry')
    for (const id of EQUIPMENT_DEGREE_CATALOG[0].equipment_ids) equipment(playerId, id, 120)
    equipment(playerId, 5900101, 120)
    addPlayerShopPurchaseCountSync(playerId, 9700116, 9999)
    addPlayerShopPurchaseCountSync(playerId, 9700117, 9999)
    recordBattleMissionDimensions(practice(playerId))
    assert.deepEqual(getPlayerDegreeIdsSync(playerId).filter(id => id >= 9911001), [9911001, 9911002, 9911003])
})
