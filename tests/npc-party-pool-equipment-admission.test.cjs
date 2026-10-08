const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const { after, test } = require("node:test")

const projectTmp = path.join(__dirname, "..", "tmp")
fs.mkdirSync(projectTmp, { recursive: true })
const dataDir = fs.mkdtempSync(path.join(projectTmp, "npc-party-admission-"))
process.env.DATA_DIR = dataDir
process.env.GACHA_SEED_DIR = path.join(dataDir, "seeds")
fs.mkdirSync(process.env.GACHA_SEED_DIR)

const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerCharacterSync } = require("../out/data/domains/character")
const { insertPlayerEquipmentSync } = require("../out/data/domains/equipment")
const { updatePlayerPartySync } = require("../out/data/domains/party")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const { getDb } = require("../out/data/db")
const { PartyCategory } = require("../out/data/types")
const pool = require("../out/multi/npc/player-party-pool")

const account = insertAccountSync({
    appId: "npc-party-admission",
    idpAlias: "test",
    idpCode: "test",
    idpId: "npc-party-admission",
    status: "active",
})
const player = insertDefaultPlayerSync(account.id)
for (const id of [2, 3]) insertDefaultPlayerCharacterSync(player.id, id)
for (const id of [100013, 300101]) {
    insertPlayerEquipmentSync(player.id, id, {
        level: 5,
        enhancementLevel: 0,
        protection: false,
        stack: 1,
    })
}

function party(name, equipmentId, soulId) {
    return {
        name,
        characterIds: [1, 2, 3],
        unisonCharacterIds: [null, null, null],
        equipmentIds: [equipmentId, null, null],
        abilitySoulIds: [soulId, null, null],
        edited: true,
        options: { allowOtherPlayersToHealMe: true },
        category: PartyCategory.NORMAL,
        currentBattlePower: 20_000,
        beforeBattlePower: 20_000,
    }
}

updatePlayerPartySync(player.id, 1, party("invalid-fantasy", 100013, 100023))
pool.refreshPlayerNpcPartyPoolSync(true)

after(async () => {
    await pool.stopQuestNpcPartyPoolWorker()
    if (getDb().open) getDb().close()
    fs.rmSync(dataDir, { recursive: true, force: true })
    try { fs.rmdirSync(projectTmp) } catch {}
})

test("ordinary AI pool rejects a Fantasy-equipped party instead of stripping it", () => {
    const result = pool.getRandomPlayerNpcPartiesSync(player.id, 1, {
        questCategory: 2,
        questId: 1099001,
    })
    assert.deepEqual(result, [])
    const stored = getDb().prepare(`
        SELECT equipment_1, ability_soul_1
        FROM players_parties
        WHERE player_id = ? AND category = ? AND group_id = 1 AND slot = 1
    `).get(player.id, PartyCategory.NORMAL)
    assert.deepEqual(stored, { equipment_1: 100013, ability_soul_1: 100023 })
})

test("Fantasy AI pool may select the same complete party unchanged", () => {
    const result = pool.getRandomPlayerNpcPartiesSync(player.id, 1, {
        questCategory: 7,
        questId: 300098001,
    })
    assert.equal(result.length, 1)
    assert.equal(result[0].party.equipments[0][1].equipmentId, 100013)
    assert.deepEqual(result[0].party.abilitySoulIds[0], [0, 100023])
})

test("ordinary AI pool skips an invalid party and selects a legal alternative", () => {
    updatePlayerPartySync(player.id, 2, party("legal", 300101, 300201))
    pool.refreshPlayerNpcPartyPoolSync(true)
    const originalRandom = Math.random
    Math.random = () => 0.999999
    try {
        const result = pool.getRandomPlayerNpcPartiesSync(player.id, 1, {
            questCategory: 2,
            questId: 1099001,
        })
        assert.equal(result.length, 1)
        assert.equal(result[0].party.equipments[0][1].equipmentId, 300101)
        assert.deepEqual(result[0].party.abilitySoulIds[0], [0, 300201])
    } finally {
        Math.random = originalRandom
    }
})
