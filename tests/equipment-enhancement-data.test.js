const test = require("node:test")
const assert = require("node:assert/strict")
const crypto = require("node:crypto")

const shop = require("../assets/equipment_enhancement_shop.json")

const TARGET_EQUIPMENT_IDS = new Set([5010070, 5020043])
const EXPECTED_CAPS = [1, 12, 23, 34, 45, 56, 69, 70, 77, 84, 91, 98, 99]
const UNRELATED_ROWS_SHA256 = "234da37cb06a3b2a778b713ac7b31abdcc9e5e9ca7b8cbdf40972323f41541a3"

test("only Liberator and Terminator gain the new 13-stage shop rows", () => {
    assert.equal(Object.keys(shop).length, 311)

    for (const equipmentId of TARGET_EQUIPMENT_IDS) {
        const rows = Object.entries(shop)
            .filter(([, row]) => row.equipmentId === equipmentId)
            .sort((left, right) => left[1].stage - right[1].stage)
        assert.equal(rows.length, 13)
        assert.deepEqual(rows.map(([, row]) => row.stage), Array.from({ length: 13 }, (_, i) => i + 1))
        assert.deepEqual(rows.map(([, row]) => row.enhancementMaxLevel), EXPECTED_CAPS)
        assert.ok(rows.every(([, row]) => (
            row.costs.length === 1
            && row.costs[0].id === 40313
            && row.costs[0].amount === 1
        )))
    }

    const unrelatedRows = Object.fromEntries(
        Object.entries(shop).filter(([, row]) => !TARGET_EQUIPMENT_IDS.has(row.equipmentId))
    )
    const digest = crypto.createHash("sha256")
        .update(JSON.stringify(unrelatedRows))
        .digest("hex")
    assert.equal(Object.keys(unrelatedRows).length, 285)
    assert.equal(digest, UNRELATED_ROWS_SHA256)
})
