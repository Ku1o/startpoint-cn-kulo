const test = require("node:test")
const assert = require("node:assert/strict")

const adventEventQuests = require("../assets/advent_event_quest.json")
const {
    RESCUE_GOLD_FRAGMENT_ITEM_ID,
    RESCUE_PURPLE_FRAGMENT_ITEM_ID,
    RESCUE_SILVER_FRAGMENT_ITEM_ID,
    getEligibleRescueFragmentReward,
    getRescueFragmentReward,
} = require("../out/multi/rescue-fragment-reward")
const { SessionManager } = require("../out/multi/state/SessionManager")

test("CN AdventEvent categories 7 and 8 share the complete rescue fragment schedule", () => {
    const battleQuestIds = Object.entries(adventEventQuests)
        .filter(([rawQuestId, quest]) => Number.isSafeInteger(Number(rawQuestId))
            && quest.rankPointReward !== undefined)
        .map(([rawQuestId]) => Number(rawQuestId))

    assert.ok(battleQuestIds.length > 0)
    for (const questId of battleQuestIds) {
        const category7Reward = getRescueFragmentReward(7, questId)
        assert.notEqual(category7Reward, null, `category 7 quest ${questId}`)
        assert.deepEqual(category7Reward, getRescueFragmentReward(8, questId))
    }
})

test("Fantasy stages use the pinned silver, gold and purple rescue tiers", () => {
    assert.deepEqual(getRescueFragmentReward(7, 300098001), {
        type: 0,
        id: RESCUE_SILVER_FRAGMENT_ITEM_ID,
        count: 10,
    })
    assert.deepEqual(getRescueFragmentReward(7, 300098002), {
        type: 0,
        id: RESCUE_GOLD_FRAGMENT_ITEM_ID,
        count: 10,
    })
    assert.deepEqual(getRescueFragmentReward(7, 300098003), {
        type: 0,
        id: RESCUE_PURPLE_FRAGMENT_ITEM_ID,
        count: 10,
    })
})

test("only a successful fragment-eligible rescue receives a fragment reward", () => {
    assert.equal(getEligibleRescueFragmentReward(7, 300098001, false, true), null)
    assert.equal(getEligibleRescueFragmentReward(7, 300098001, true, false), null)
    assert.equal(getEligibleRescueFragmentReward(7, 999999999, true, true), null)
    assert.deepEqual(getEligibleRescueFragmentReward(7, 300098001, true, true), {
        type: 0,
        id: RESCUE_SILVER_FRAGMENT_ITEM_ID,
        count: 10,
    })
})

test("Fantasy helpers and bell rescues keep separate fragment eligibility", () => {
    const manager = new SessionManager()
    const roomNumber = "fragment-eligibility"

    manager.markRescueGuest(roomNumber, 101, false, false)
    manager.markRescueGuest(roomNumber, 102, false, true)

    assert.equal(manager.isRescueGuest(roomNumber, 101), true)
    assert.equal(manager.isRescueFragmentEligibleGuest(roomNumber, 101), false)
    assert.equal(manager.isRescueGuest(roomNumber, 102), true)
    assert.equal(manager.isRescueFragmentEligibleGuest(roomNumber, 102), true)

    manager.clearRescueGuestStateForRoom(roomNumber)
    assert.equal(manager.isRescueFragmentEligibleGuest(roomNumber, 102), false)
})
