const test = require("node:test")
const assert = require("node:assert/strict")
const crypto = require("node:crypto")

const shop = require("../assets/equipment_enhancement_shop.json")
const { resolveEquipmentEnhancementPurchaseMode } = require("../out/lib/equipment-enhancement")

const TARGET_EQUIPMENT_IDS = new Set([5010070, 5020043])
const EXPECTED_CAPS = [1, 12, 23, 34, 45, 56, 69, 70, 77, 84, 91, 98, 99]
// Deathbringer's six approved per-level rows are covered by the Five Boss
// integration suite. The remaining 279 legacy rows retain their recipes;
// explicit official purchase-mode tags are excluded from the legacy digest.
const DEATHBRINGER_ID = 5900101
const UNRELATED_ROWS_SHA256 = "774565cf4776cdb9c0c367999084ebbaa4263d808038147abd40456e36b47c5f"

test("Liberator and Terminator retain their 13-stage rows alongside the approved Deathbringer recipe", () => {
    const legacyRows = Object.entries(shop).filter(([, row]) => row.shopCategoryId <= 5)
    assert.equal(legacyRows.length, 311)

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
        legacyRows.filter(([, row]) => (
            !TARGET_EQUIPMENT_IDS.has(row.equipmentId) && row.equipmentId !== DEATHBRINGER_ID
        )).map(([id, row]) => {
            const legacyRecipe = { ...row }
            if (row.shopCategoryId <= 4) delete legacyRecipe.enhancementPurchaseMode
            return [id, legacyRecipe]
        })
    )
    const digest = crypto.createHash("sha256")
        .update(JSON.stringify(unrelatedRows))
        .digest("hex")
    assert.equal(Object.keys(unrelatedRows).length, 279)
    assert.equal(digest, UNRELATED_ROWS_SHA256)
})

test("stage benefit is explicit and restricted to the four official enhancement categories", () => {
    for (const row of Object.values(shop)) {
        const official = row.shopCategoryId >= 1 && row.shopCategoryId <= 4
        assert.equal(row.enhancementPurchaseMode, official ? "stage_benefit" : "per_level")
        assert.equal(
            resolveEquipmentEnhancementPurchaseMode(row.shopCategoryId, row.enhancementPurchaseMode),
            official ? "stage_benefit" : "per_level",
        )
    }
    for (const category of [5, 6, 7]) {
        assert.equal(resolveEquipmentEnhancementPurchaseMode(category, "stage_benefit"), "per_level")
    }
    assert.equal(resolveEquipmentEnhancementPurchaseMode(1), "per_level")
})

test("cursed, Paradox and bond additions retain their authored per-level stage boundaries", () => {
    const ordinaryCaps = [69, 70, 98, 99, 119, 120]
    const cursedIds = Array.from({ length: 29 }, (_, index) => 5910101 + index)
    const bondIds = [5010005, 5020024, 5020041, 5030005, 5040022, 5050026, 5060044, 5070027]
    const groups = [
        { category: 6, equipmentIds: cursedIds, caps: ordinaryCaps },
        { category: 6, equipmentIds: [5920001], caps: [...ordinaryCaps, 159, 160, 199, 200] },
        { category: 7, equipmentIds: bondIds, caps: ordinaryCaps },
    ]
    assert.equal(Object.values(shop).filter(row => row.shopCategoryId === 6).length, 184)
    assert.equal(Object.values(shop).filter(row => row.shopCategoryId === 7).length, 48)
    for (const group of groups) {
        for (const equipmentId of group.equipmentIds) {
            const rows = Object.values(shop)
                .filter(row => row.shopCategoryId === group.category && row.equipmentId === equipmentId)
                .sort((left, right) => left.stage - right.stage)
            assert.deepEqual(rows.map(row => row.stage), group.caps.map((_, index) => index + 1))
            assert.deepEqual(rows.map(row => row.enhancementMaxLevel), group.caps)
            assert.ok(rows.every(row => row.enhancementPurchaseMode === "per_level"))
            assert.ok(rows.every(row => row.costs.length > 0 && row.costs.every(cost => (
                Number.isSafeInteger(cost.id) && cost.id > 0
                && Number.isSafeInteger(cost.amount) && cost.amount > 0
            ))))
        }
    }
})
