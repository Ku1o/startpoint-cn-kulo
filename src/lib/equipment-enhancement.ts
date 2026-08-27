export interface EquipmentEnhancementStage {
    shopItemId: number
    shopCategoryId: number
    groupId: number
    equipmentId: number
    stage: number
    maxLevel: number
}

export interface EquipmentEnhancementStageQuery {
    shopCategoryId: number
    groupId: number
    equipmentId: number
    currentLevel: number
}

export type EquipmentEnhancementPurchasePlan =
    | {
        ok: true
        newLevel: number
        chargedPurchaseAmount: number
        grantedLevelCount: number
    }
    | {
        ok: false
        message: string
    }

/**
 * Resolves the next purchasable row inside one enhancement category.
 *
 * Some equipment IDs occur in more than one category with overlapping group
 * and stage numbers, so category is part of the progression identity.
 */
export function findCurrentEquipmentEnhancementStage(
    stages: readonly EquipmentEnhancementStage[],
    query: EquipmentEnhancementStageQuery,
): EquipmentEnhancementStage | null {
    const candidates = stages
        .filter(stage => stage.shopCategoryId === query.shopCategoryId
            && stage.groupId === query.groupId
            && stage.equipmentId === query.equipmentId
            && stage.maxLevel > query.currentLevel
        )
        .sort((left, right) => left.maxLevel - right.maxLevel
            || left.stage - right.stage
            || left.shopItemId - right.shopItemId)

    return candidates[0] ?? null
}

/**
 * Plans one special-equipment enhancement purchase.
 *
 * The normal progression boundary is still enforced, while the private-server
 * benefit intentionally completes the current material stage for one unit of
 * its listed cost. Later material stages must still be purchased separately.
 */
export function planEquipmentEnhancementPurchase(
    currentLevel: number,
    requestedPurchaseAmount: number,
    stageMaxLevel: number,
    currentAwakeningLevel: number,
    requiredAwakeningLevel: number,
): EquipmentEnhancementPurchasePlan {
    if (!Number.isSafeInteger(requestedPurchaseAmount) || requestedPurchaseAmount <= 0) {
        return { ok: false, message: "Invalid enhancement purchase amount." }
    }
    if (
        !Number.isSafeInteger(currentLevel)
        || !Number.isSafeInteger(stageMaxLevel)
        || currentLevel < 0
        || stageMaxLevel <= currentLevel
        || requestedPurchaseAmount > stageMaxLevel - currentLevel
    ) {
        return { ok: false, message: "Enhancement purchase exceeds the current stage." }
    }
    if (currentAwakeningLevel < requiredAwakeningLevel) {
        return { ok: false, message: "Equipment awakening level is too low." }
    }

    return {
        ok: true,
        newLevel: stageMaxLevel,
        chargedPurchaseAmount: 1,
        grantedLevelCount: stageMaxLevel - currentLevel,
    }
}
