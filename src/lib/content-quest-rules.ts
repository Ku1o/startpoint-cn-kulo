import nativeRules from "../../assets/content_history_quest_rules.json"
import type { RawQuest } from "./types/quest"

const projectedFields = [
    "clearRewardId", "sPlusRewardId", "scoreRewardGroupId", "element", "fixedParty",
    "bRankTime", "aRankTime", "sRankTime", "sPlusRankTime",
    "rankPointReward", "characterExpReward", "manaReward", "poolExpReward",
] as const
type ProjectedField = typeof projectedFields[number]
interface NativeQuestRule {
    parentKey?: string
    kind: "Story" | "Battle" | "LoseBattle"
    fields: Partial<Record<ProjectedField, number | null>>
    currentOverlayPriorityFields: ProjectedField[]
    nativeEligibility?: { battle_stamina_cost?: unknown; daily_challenge_point_id?: unknown }
}
interface NativeQuestRules {
    schemaVersion: number
    units: Record<string, string>
    quests: Record<string, NativeQuestRule>
}
const rules = nativeRules as unknown as NativeQuestRules
const fieldNames = new Set<string>(projectedFields)
const optionalReferences = new Set<string>(["clearRewardId", "sPlusRewardId", "scoreRewardGroupId", "fixedParty"])

if (rules.schemaVersion !== 1 || !rules.quests || typeof rules.quests !== "object"
    || ["bRankTime", "aRankTime", "sRankTime", "sPlusRankTime"].some(key => rules.units?.[key] !== "milliseconds")) {
    throw new Error("Invalid native quest rules schema or time units")
}
for (const [key, rule] of Object.entries(rules.quests)) {
    if (!/^\d+:\d+$/.test(key) || !["Story", "Battle", "LoseBattle"].includes(rule.kind)
        || !rule.fields || typeof rule.fields !== "object" || !Array.isArray(rule.currentOverlayPriorityFields)
        || rule.currentOverlayPriorityFields.some(field => !fieldNames.has(field))) {
        throw new Error(`Invalid native quest rule: ${key}`)
    }
    for (const [field, value] of Object.entries(rule.fields)) {
        if (!fieldNames.has(field) || (value === null ? !optionalReferences.has(field)
            : !Number.isSafeInteger(value) || value < 0 || (field === "element" && value > 5))) {
            throw new Error(`Invalid native quest field: ${key}:${field}`)
        }
    }
}

/** Correct extracted numeric columns without changing the source table or any player state. */
export function applyContentQuestRules(category: number, questId: number | string, quest: RawQuest): RawQuest {
    // Core/CN-mod bosses and other nonprojected definitions retain their original path.
    if (category === 2) return quest
    const rule = rules.quests[`${category}:${questId}`]
    if (rule === undefined) return quest
    const corrected = { ...quest }
    for (const field of projectedFields) {
        if (!Object.prototype.hasOwnProperty.call(rule.fields, field)
            || rule.currentOverlayPriorityFields.includes(field)) continue
        const value = rule.fields[field]
        // Native None must remove an incorrectly extracted old reference, including zero-safe handling.
        if (value === null) delete corrected[field]
        else corrected[field] = value
    }
    return corrected
}

/** Native nominal stamina for projected quests. Existing CN-mod/core overrides
 * retain their original cost source, and this does not charge player stamina. */
export function getContentNativeStaminaCost(category: number, questId: number | string): number | null {
    if (category === 2) return null
    const rule = rules.quests[`${category}:${questId}`]
    if (!rule || rule.kind === "Story" || ["rush_event:700099", "rush_event:700100"].includes(rule.parentKey ?? "")) return null
    const raw = rule.nativeEligibility?.battle_stamina_cost
    if (typeof raw !== "number" && (typeof raw !== "string" || !/^\d+$/.test(raw))) return null
    const cost = Number(raw)
    if (!Number.isSafeInteger(cost) || cost < 0) throw new Error(`Invalid native stamina cost: ${category}:${questId}`)
    return cost
}

/** Keep native shared quota identity separate from reward-column projection.
 * None does not create a player entry or infer a replacement limit. */
export function getContentNativeDailyChallengePointId(category: number, questId: number | string): number | null {
    if (category === 2) return null
    const rule = rules.quests[`${category}:${questId}`]
    if (!rule || rule.kind === "Story") return null
    const raw = rule.nativeEligibility?.daily_challenge_point_id
    if (raw === undefined || raw === null || raw === "(None)") return null
    if ((typeof raw !== "number" && (typeof raw !== "string" || !/^[1-9]\d*$/.test(raw)))
        || !Number.isSafeInteger(Number(raw)) || Number(raw) <= 0) {
        throw new Error(`Invalid native daily challenge point identity: ${category}:${questId}`)
    }
    return Number(raw)
}
