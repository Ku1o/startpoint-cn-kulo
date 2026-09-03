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

export type EquipmentEnhancementPurchaseMode = "stage_benefit" | "per_level"

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
 * Legacy rows retain the existing stage-benefit behavior. Newly-added special
 * weapons opt into `per_level`, where the requested amount advances exactly
 * that many levels and the caller charges the row's materials per level.
 */
export function planEquipmentEnhancementPurchase(
    currentLevel: number,
    requestedPurchaseAmount: number,
    stageMaxLevel: number,
    currentAwakeningLevel: number,
    requiredAwakeningLevel: number,
    mode: EquipmentEnhancementPurchaseMode = "stage_benefit",
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

    if (mode === "per_level") {
        return {
            ok: true,
            newLevel: currentLevel + requestedPurchaseAmount,
            chargedPurchaseAmount: requestedPurchaseAmount,
            grantedLevelCount: requestedPurchaseAmount,
        }
    }

    return {
        ok: true,
        newLevel: stageMaxLevel,
        chargedPurchaseAmount: 1,
        grantedLevelCount: stageMaxLevel - currentLevel,
    }
}
