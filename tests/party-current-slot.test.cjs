const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-party-slot-test-"))
process.env.DATA_DIR = temporaryDataDir

const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, getPlayerSync } = require("../out/data/domains/player")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const {
  findValidNormalPartySlotSync,
  isValidNormalPartySlotSync,
} = require("../out/data/domains/party")
const { getPlayerActiveQuestSync, insertPlayerActiveQuestSync } = require("../out/data/domains/quest_active")
const { PartyCategory } = require("../out/data/types")
const { QuestCategory } = require("../out/lib/types")
const { PartySlotValidator } = require("../out/lib/validate/party-slot")
const { usesNormalCurrentPartySlot } = require("../out/lib/party-current-slot")

function createPlayer() {
  const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "party-slot-test",
    idpId: "",
    status: "normal",
  })
  const player = insertDefaultPlayerSync(account.id)
  saveAccountDefaultPlayer(account.id, player.id)
  return player.id
}

test("invalid normal pointer falls back without changing independent event parties", () => {
  const playerId = createPlayer()
  const db = getDb()
  db.prepare(`UPDATE players_parties SET character_id_1 = NULL
    WHERE player_id = ? AND category = ? AND group_id = 1 AND slot = 1`)
    .run(playerId, PartyCategory.NORMAL)
  db.prepare(`INSERT INTO players_party_groups (id, color_id, player_id, category)
    VALUES (1, 15, ?, ?)`)
    .run(playerId, PartyCategory.FANTASY)
  db.prepare(`INSERT INTO players_parties (
    slot, name, character_id_1, character_id_2, character_id_3,
    unison_character_1, unison_character_2, unison_character_3,
    equipment_1, equipment_2, equipment_3,
    ability_soul_1, ability_soul_2, ability_soul_3, edited,
    player_id, group_id, category, current_battle_power, before_battle_power
  ) VALUES (1, 'Fantasy', 1, NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL, NULL, 1, ?, 1, ?, 0, 0)`)
    .run(playerId, PartyCategory.FANTASY)
  db.prepare("UPDATE players SET party_slot = 1 WHERE id = ?").run(playerId)

  assert.equal(isValidNormalPartySlotSync(playerId, 1), false)
  assert.equal(findValidNormalPartySlotSync(playerId, 1), 2)
  const beforeEventLeader = db.prepare(`SELECT character_id_1 FROM players_parties
    WHERE player_id = ? AND category = ? AND group_id = 1 AND slot = 1`)
    .get(playerId, PartyCategory.FANTASY).character_id_1

  const player = getPlayerSync(playerId)
  assert.equal(PartySlotValidator.validate(playerId, { player }), 1)
  assert.equal(getPlayerSync(playerId).partySlot, 2)
  assert.equal(db.prepare(`SELECT character_id_1 FROM players_parties
    WHERE player_id = ? AND category = ? AND group_id = 1 AND slot = 1`)
    .get(playerId, PartyCategory.FANTASY).character_id_1, beforeEventLeader)
})

test("active quest recovery preserves the selected event party", () => {
  const playerId = createPlayer()
  insertPlayerActiveQuestSync(playerId, {
    playerId,
    playId: "event-party-recovery",
    questId: 700098001,
    category: 30,
    useBossBoostPoint: false,
    useBoostPoint: false,
    isAutoStartMode: false,
    isMulti: false,
    isMultiHost: false,
    roomNumber: null,
    entryItemId: null,
    eventId: 700098,
    continueCount: 0,
    startedAtMs: Date.now(),
    partySlot: 81,
  })
  assert.equal(getPlayerActiveQuestSync(playerId).partySlot, 81)
})

test("event categories do not update the normal current-party pointer", () => {
  assert.equal(usesNormalCurrentPartySlot(1), true)
  assert.equal(usesNormalCurrentPartySlot(QuestCategory.CARNIVAL_EVENT), false)
  assert.equal(usesNormalCurrentPartySlot(QuestCategory.RAID_EVENT), false)
  assert.equal(usesNormalCurrentPartySlot(QuestCategory.RUSH_EVENT), false)
})
