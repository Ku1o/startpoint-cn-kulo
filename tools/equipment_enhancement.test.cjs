const test = require("node:test")
const assert = require("node:assert/strict")
const enhancementShop = require("../assets/equipment_enhancement_shop.json")

const {
    findCurrentEquipmentEnhancementStage,
    planEquipmentEnhancementPurchase,
} = require("../out/lib/equipment-enhancement")

test("enhancement purchase keeps the one-material stage benefit", () => {
    assert.deepEqual(planEquipmentEnhancementPurchase(1, 11, 12, 1, 1), {
        ok: true,
        newLevel: 12,
        chargedPurchaseAmount: 1,
        grantedLevelCount: 11,
    })
})

test("enhancement purchase rejects completed stages and unmet awakening", () => {
    assert.equal(planEquipmentEnhancementPurchase(12, 1, 12, 1, 1).ok, false)
    assert.equal(planEquipmentEnhancementPurchase(1, 1, 12, 0, 1).ok, false)
    assert.equal(planEquipmentEnhancementPurchase(1, 0, 12, 1, 1).ok, false)
})

test("current enhancement stage cannot be selected from another group or equipment", () => {
    const stages = [
        { shopItemId: 1001, shopCategoryId: 2, groupId: 1, equipmentId: 5010070, stage: 1, maxLevel: 1 },
        { shopItemId: 1003, shopCategoryId: 2, groupId: 1, equipmentId: 5010070, stage: 2, maxLevel: 12 },
        { shopItemId: 1002, shopCategoryId: 2, groupId: 2, equipmentId: 5020043, stage: 1, maxLevel: 1 },
    ]
    assert.equal(findCurrentEquipmentEnhancementStage(stages, {
        shopCategoryId: 2,
        groupId: 1,
        equipmentId: 5010070,
        currentLevel: 1,
    }).shopItemId, 1003)
    assert.equal(findCurrentEquipmentEnhancementStage(stages, {
        shopCategoryId: 2,
        groupId: 2,
        equipmentId: 5020043,
        currentLevel: 1,
    }), null)
})

test("new special weapons advance one level per requested purchase", () => {
    assert.deepEqual(planEquipmentEnhancementPurchase(0, 1, 69, 5, 5, "per_level"), {
        ok: true,
        newLevel: 1,
        chargedPurchaseAmount: 1,
        grantedLevelCount: 1,
    })
    assert.deepEqual(planEquipmentEnhancementPurchase(20, 5, 69, 5, 5, "per_level"), {
        ok: true,
        newLevel: 25,
        chargedPurchaseAmount: 5,
        grantedLevelCount: 5,
    })
    assert.equal(planEquipmentEnhancementPurchase(68, 2, 69, 5, 5, "per_level").ok, false)
})

test("grey abyss weapon rows add materials per level without enabling Death Bringer mode", () => {
    const rows = Object.values(enhancementShop).filter(row => row.equipmentId >= 8000101 && row.equipmentId <= 8000115)
    assert.equal(rows.length, 90)
    assert.equal(rows.filter(row => row.enhancementPurchaseMode === "per_level").length, 90)

    for (const row of rows) {
        const costs = Object.fromEntries(row.costs.map(cost => [cost.id, cost.amount]))
        if ([1, 3, 5].includes(row.stage)) {
            assert.equal(costs[2370098], 1)
            assert.equal(costs[row.equipmentId >= 8000113 ? 10000093 : {
                8000101: 10000114, 8000102: 10000114,
                8000103: 10000117, 8000104: 10000117,
                8000105: 10000120, 8000106: 10000120,
                8000107: 10000123, 8000108: 10000123,
                8000109: 10000126, 8000110: 10000126,
                8000111: 10000129, 8000112: 10000129,
            }[row.equipmentId]], 5)
        }
        if (row.stage === 2) {
            const gearId = row.equipmentId >= 8000113
                ? 10000095
                : 40401 + Math.floor((row.equipmentId - 8000101) / 2)
            assert.equal(costs[gearId], 10)
        }
        if (row.stage === 4) {
            const coreId = row.equipmentId >= 8000113
                ? 10000096
                : 40407 + Math.floor((row.equipmentId - 8000101) / 2)
            assert.equal(costs[coreId], 2)
        }
        if (row.stage === 6) assert.equal(costs[2370097], 3)
    }

    const deathRows = Object.values(enhancementShop).filter(row => row.equipmentId === 5900101)
    assert.equal(deathRows.length, 6)
    assert.equal(deathRows.some(row => row.enhancementPurchaseMode !== undefined), false)
})

test("each grey abyss weapon reaches level 120 for exactly 2000 abyss tokens", () => {
    for (let equipmentId = 8000101; equipmentId <= 8000115; equipmentId += 1) {
        const rows = Object.values(enhancementShop)
            .filter(row => row.equipmentId === equipmentId)
            .sort((left, right) => left.stage - right.stage)
        let previousLevel = 0
        let total = 0
        for (const row of rows) {
            const levelCount = row.enhancementMaxLevel - previousLevel
            const tokenCost = row.costs.find(cost => cost.id === 2370099)?.amount ?? 0
            total += levelCount * tokenCost
            previousLevel = row.enhancementMaxLevel
        }
        assert.equal(previousLevel, 120)
        assert.equal(total, 2000)
        assert.deepEqual(rows.map(row => row.costs.find(cost => cost.id === 2370099)?.amount), [16, 42, 16, 43, 16, 43])
    }
})
