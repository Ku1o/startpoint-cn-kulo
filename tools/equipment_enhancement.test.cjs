const test = require("node:test")
const assert = require("node:assert/strict")

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
