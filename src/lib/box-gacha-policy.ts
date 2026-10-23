import { contentCatalog } from "./content-operations"
import type { ContentCatalogRow } from "./content-operations-store"
import type { BoxGachaBox, BoxGachaBoxes } from "./types"
import type { PlayerBoxGachaDrawnReward } from "../data/types"

export interface BoxOperationRule {
    requiredBoxId: number | null
    resetKind: number
    resetLimit: number | null
    availableFrom: string
    availableUntil: string | null
    closeKind: number
}

export function getBoxOperationRules(row: ContentCatalogRow, boxes: BoxGachaBoxes): ReadonlyMap<number, BoxOperationRule> | null {
    const source = (row as ContentCatalogRow & { boxRules?: Record<string, BoxOperationRule> }).boxRules
    if (!source || Object.keys(source).length !== Object.keys(boxes).length) return null
    const rules = new Map<number, BoxOperationRule>()
    for (const [boxId, rewards] of Object.entries(boxes)) {
        const id = Number(boxId), rule = source[boxId]
        // The native optional timestamp serializes an unbounded box as (None).
        // Normalize only that explicit sentinel; malformed dates still fail closed.
        const availableUntil = rule?.availableUntil === "(None)" ? null : rule?.availableUntil
        if (!Number.isSafeInteger(id) || id <= 0 || !rule
            || ![0, 1, 2].includes(rule.resetKind) || ![0, 1, 2, 3].includes(rule.closeKind)
            || (rule.requiredBoxId !== null && (!Number.isSafeInteger(rule.requiredBoxId) || !boxes[rule.requiredBoxId] || rule.requiredBoxId === id))
            || (rule.resetLimit !== null && (!Number.isSafeInteger(rule.resetLimit) || rule.resetLimit < 0))
            || typeof rule.availableFrom !== "string" || (availableUntil !== null && typeof availableUntil !== "string")
            || !Number.isFinite(Date.parse(rule.availableFrom.replace(" ", "T") + "+08:00"))
            || (availableUntil !== null && !Number.isFinite(Date.parse(availableUntil.replace(" ", "T") + "+08:00")))
            || !Object.values(rewards).length
            || Object.values(rewards).some(reward => !Number.isSafeInteger(reward.available) || reward.available < 0
                || !Number.isSafeInteger(reward.count) || reward.count < 0 || ![0, 1, 2].includes(reward.tier))) return null
        rules.set(id, { ...rule, availableUntil })
    }
    return rules
}

export function getBoxOperationRule(gachaId: number, boxId: number, boxes: BoxGachaBoxes): BoxOperationRule | null {
    const row = contentCatalog.rows.find(row => row.key === `box_gacha:${gachaId}`)
    return row ? getBoxOperationRules(row, boxes)?.get(boxId) ?? null : null
}

function drawnRequiredRewards(rule: BoxOperationRule, rewards: BoxGachaBox, drawn: readonly PlayerBoxGachaDrawnReward[]): boolean {
    if (rule.closeKind === 0) return false
    const featureKind = 3 - rule.closeKind
    const facts = new Map(drawn.map(reward => [reward.id, reward.number]))
    return Object.entries(rewards).every(([id, reward]) => reward.tier !== featureKind
        || (facts.get(Number(id)) ?? 0) >= reward.available)
}

export function boxPolicyResetError(rule: BoxOperationRule, remaining: number, resetTimes: number,
    rewards: BoxGachaBox, drawn: readonly PlayerBoxGachaDrawnReward[]): string | null {
    if (rule.resetKind === 0) return "Box cannot be reset."
    if (rule.resetKind === 1 && !drawnRequiredRewards(rule, rewards, drawn)) return "Required box rewards have not all been drawn."
    if (rule.resetKind === 2 && remaining > 0) return "Box still has remaining rewards."
    if (rule.resetLimit !== null && resetTimes >= rule.resetLimit) return "Box reset limit reached."
    return null
}

export function boxPolicyCloseError(rule: BoxOperationRule, remaining: number,
    rewards: BoxGachaBox, drawn: readonly PlayerBoxGachaDrawnReward[]): string | null {
    if (rule.resetKind !== 0) return "Box cannot be closed."
    if (rule.closeKind === 0) return remaining > 0 ? "Box still has remaining rewards." : null
    return drawnRequiredRewards(rule, rewards, drawn) ? null : "Required box rewards have not all been drawn."
}
