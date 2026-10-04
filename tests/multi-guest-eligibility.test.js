const test = require("node:test")
const assert = require("node:assert/strict")

const { canJoinMultiGuestQuestSync } = require("../out/multi/guest-eligibility")
const requirements = require("../assets/multi_guest_entry_requirements.json")
const playerRankTable = require("../assets/cdndata/player_rank_full.json")

function player(rankPoint) {
    return { rankPoint }
}

test("unknown guest quests remain eligible without invented restrictions", () => {
    const result = canJoinMultiGuestQuestSync(1, 2, 9999999, player(0), {
        hasFinishedQuest: () => false,
    })
    assert.deepEqual(result, { allowed: true, reason: "eligible" })
})

test("five-boss guests require rank 130 before the ticket check", () => {
    let reads = 0
    const getItemCount = () => { reads++; return 1 }
    const rank130Threshold = Number(playerRankTable["130"][0][1])
    const denied = canJoinMultiGuestQuestSync(1, 2, 1099001, player(rank130Threshold - 1), {
        getItemCount,
    })
    assert.deepEqual(denied, {
        allowed: false,
        reason: "player_rank",
        minimumPlayerRank: 130,
        playerRank: 129,
    })
    assert.equal(reads, 0)
    assert.deepEqual(
        canJoinMultiGuestQuestSync(1, 2, 1099001, player(rank130Threshold), {
            getItemCount,
        }),
        { allowed: true, reason: "eligible" },
    )
    assert.equal(reads, 1)
})

test("rank-130 five-boss guests require a ticket but the gate never consumes it", () => {
    let tickets = 0
    let reads = 0
    const rank130Threshold = Number(playerRankTable["130"][0][1])
    const dependencies = {
        getItemCount: (_playerId, itemId) => {
            assert.equal(itemId, 10000143)
            reads++
            return tickets
        },
    }
    const denied = canJoinMultiGuestQuestSync(
        1,
        2,
        1099001,
        player(rank130Threshold),
        dependencies,
    )
    assert.deepEqual(denied, {
        allowed: false,
        reason: "five_boss_ticket",
        minimumPlayerRank: 130,
        playerRank: 130,
        requiredItemId: 10000143,
        currentItemCount: 0,
    })
    tickets = 1
    assert.deepEqual(
        canJoinMultiGuestQuestSync(1, 2, 1099001, player(rank130Threshold), dependencies),
        { allowed: true, reason: "eligible" },
    )
    assert.equal(tickets, 1)
    assert.equal(reads, 2)
})

test("hard-multi guests require client-master player rank 120", () => {
    const result = canJoinMultiGuestQuestSync(1, 26, 1001001, player(0), {
        hasFinishedQuest: () => true,
    })
    assert.equal(result.allowed, false)
    assert.equal(result.reason, "player_rank")
    assert.equal(result.minimumPlayerRank, 120)
    assert.equal(result.playerRank, 1)
})

test("hard-multi guests require the exact linked prerequisite quest", () => {
    const checked = []
    const missing = canJoinMultiGuestQuestSync(1, 26, 1001001, player(Number.MAX_SAFE_INTEGER), {
        hasFinishedQuest: (_playerId, category, questId) => {
            checked.push({ category, questId })
            return false
        },
    })
    assert.equal(missing.allowed, false)
    assert.equal(missing.reason, "prerequisite_quest")
    assert.deepEqual(checked, [{ category: 2, questId: 1061004 }])

    const allowed = canJoinMultiGuestQuestSync(1, 26, 1001001, player(Number.MAX_SAFE_INTEGER), {
        hasFinishedQuest: (_playerId, category, questId) =>
            category === 2 && questId === 1061004,
    })
    assert.equal(allowed.allowed, true)
    assert.equal(allowed.minimumPlayerRank, 120)
})

test("collaboration hard-multi guests use the linked advent prerequisite", () => {
    const result = canJoinMultiGuestQuestSync(1, 26, 100001001, player(Number.MAX_SAFE_INTEGER), {
        hasFinishedQuest: (_playerId, category, questId) =>
            category === 8 && questId === 200064004,
    })
    assert.equal(result.allowed, true)
    assert.deepEqual(result.requiredQuestCategories, [7, 8])
    assert.equal(result.requiredQuestId, 200064004)
})

test("every audited guest rule accepts only its exact prerequisite", () => {
    assert.equal(Object.keys(requirements.rules).length, 12)
    for (const [key, rule] of Object.entries(requirements.rules)) {
        const [category, questId] = key.split(":").map(Number)
        const result = canJoinMultiGuestQuestSync(
            1,
            category,
            questId,
            player(Number.MAX_SAFE_INTEGER),
            {
                hasFinishedQuest: (_playerId, checkedCategory, checkedQuestId) =>
                    rule.required_quest_categories.includes(checkedCategory)
                    && checkedQuestId === rule.required_quest_id,
            },
        )
        assert.equal(result.allowed, true, key)
        assert.equal(result.minimumPlayerRank, rule.minimum_player_rank, key)
    }
})
