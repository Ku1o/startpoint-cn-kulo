require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const dataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "mana-limit-"))
const previousDataDirectory = process.env.DATA_DIR
process.env.DATA_DIR = dataDirectory

const moduleRoot = process.env.MANA_LIMIT_USE_OUT === "1" ? "../out" : "../src"
const moduleExtension = process.env.MANA_LIMIT_USE_OUT === "1" ? ".js" : ".ts"
const { getDb } = require(`${moduleRoot}/data/db${moduleExtension}`)
const { insertAccountSync } = require(`${moduleRoot}/data/domains/account${moduleExtension}`)
const {
  getPlayerSync,
  insertDefaultPlayerSync,
  updatePlayerSync,
} = require(`${moduleRoot}/data/domains/player${moduleExtension}`)
const {
  getPlayerItemSync,
  setPlayerItemSync,
} = require(`${moduleRoot}/data/domains/item${moduleExtension}`)
const {
  OFFICIAL_MAX_MANA,
  calculateFreeManaGrant,
  getMaxManaSync,
} = require(`${moduleRoot}/lib/mana${moduleExtension}`)
const { sellItemSync } = require(`${moduleRoot}/lib/item-sell${moduleExtension}`)
const { givePlayerRewardsSync } = require(`${moduleRoot}/lib/quest${moduleExtension}`)
const { MissionRewardGranter } = require(`${moduleRoot}/lib/mission/grants${moduleExtension}`)
const { RewardType } = require(`${moduleRoot}/lib/types${moduleExtension}`)

const db = getDb()

function cleanup() {
  if (db.open) db.close()
  fs.rmSync(dataDirectory, { recursive: true, force: true })
  if (previousDataDirectory === undefined) delete process.env.DATA_DIR
  else process.env.DATA_DIR = previousDataDirectory
}

process.once("exit", cleanup)

try {
  assert.equal(OFFICIAL_MAX_MANA, 999999999)
  assert.equal(getMaxManaSync(), OFFICIAL_MAX_MANA)
  assert.deepEqual(
    calculateFreeManaGrant({ freeMana: 999999990, paidMana: 5 }, 10),
    { freeMana: 999999994, creditedMana: 4 },
  )

  const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "mana-limit-test",
    idpId: "mana-limit-test",
    status: "normal",
  })
  const playerId = insertDefaultPlayerSync(account.id).id
  const saleItemId = 1

  // The previous eight-digit cap incorrectly rejected this valid sale.
  setPlayerItemSync(playerId, saleItemId, 3)
  updatePlayerSync({ id: playerId, freeMana: 100000000, paidMana: 2000 })
  const aboveOldCap = sellItemSync(playerId, saleItemId, 1)
  assert.equal(aboveOldCap.ok, true)
  assert.equal(aboveOldCap.freeMana, 100000005)
  assert.equal(getPlayerSync(playerId).paidMana, 2000)

  // Free and paid Mana share one cap. Hitting the cap exactly is allowed.
  setPlayerItemSync(playerId, saleItemId, 2)
  updatePlayerSync({ id: playerId, freeMana: 999999990, paidMana: 4 })
  const exactBoundary = sellItemSync(playerId, saleItemId, 1)
  assert.equal(exactBoundary.ok, true)
  assert.equal(exactBoundary.freeMana, 999999995)
  assert.equal(getPlayerSync(playerId).freeMana + getPlayerSync(playerId).paidMana, OFFICIAL_MAX_MANA)

  // Paid Mana must participate in overflow validation, with no partial write.
  setPlayerItemSync(playerId, saleItemId, 1)
  updatePlayerSync({ id: playerId, freeMana: 999999990, paidMana: 5 })
  const overflow = sellItemSync(playerId, saleItemId, 1)
  assert.equal(overflow.ok, false)
  assert.equal(overflow.errorCode, 2102)
  assert.equal(getPlayerItemSync(playerId, saleItemId), 1)
  assert.equal(getPlayerSync(playerId).freeMana, 999999990)

  // Reward grants mirror the client: only the portion below the shared cap is credited.
  updatePlayerSync({
    id: playerId,
    freeMana: 999999990,
    paidMana: 5,
    totalManaObtained: 0,
  })
  const rewardResult = givePlayerRewardsSync(playerId, [
    { type: RewardType.MANA, count: 10 },
  ])
  const rewardedPlayer = getPlayerSync(playerId)
  assert.equal(rewardResult.user_info.free_mana, 4)
  assert.equal(rewardedPlayer.freeMana, 999999994)
  assert.equal(rewardedPlayer.freeMana + rewardedPlayer.paidMana, OFFICIAL_MAX_MANA)
  assert.equal(rewardedPlayer.totalManaObtained, 10)

  updatePlayerSync({
    id: playerId,
    freeMana: 999999990,
    paidMana: 5,
    totalManaObtained: 0,
  })
  const missionGranter = new MissionRewardGranter(playerId, getPlayerSync(playerId))
  missionGranter.grant([{ kind: 3, amount: 10 }])
  missionGranter.persistPlayer()
  const missionRewardedPlayer = getPlayerSync(playerId)
  assert.equal(missionRewardedPlayer.freeMana, 999999994)
  assert.equal(missionRewardedPlayer.freeMana + missionRewardedPlayer.paidMana, OFFICIAL_MAX_MANA)
  assert.equal(missionRewardedPlayer.totalManaObtained, 10)

  console.log("mana limit tests passed")
} finally {
  cleanup()
  process.removeListener("exit", cleanup)
}
