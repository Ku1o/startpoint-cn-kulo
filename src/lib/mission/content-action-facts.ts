import { incrementPlayerCategoryMissionSync } from "../../data/domains/mission"
import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "../../data/domains/player-operation-receipt"
import { runPersistenceTransactionSync } from "../persistence-coordinator"
import { contentMissionDecision } from "../content-operations"
import { getMissionMasterDefinitions, isMissionDefinitionEnabledAt } from "./master-data"
import { refreshCollectTargetMissionProgressSync } from "./collect-progress"

const CONDITIONS = Object.freeze({
    login: 0,
    mana_node_release: 7,
    over_limit: 9,
    character_story_finish: 21,
    equipment_awaken: 34,
    ability_soul_equip: 35,
    stamina_spend: 39,
    mana_spend: 46,
    profile_view: 88,
})
export type ContentActionFactKind = keyof typeof CONDITIONS
export interface ContentActionFact {
    kind: ContentActionFactKind
    /** Successful action delta. Stamina uses the existing server mission credit
     * (nominal cost on free entry), never an account lifetime total. */
    amount?: number
    nowMs?: number
    /** For an authoritative successful action that has a stable replay identity. */
    dedupeKey?: string
}
const absent = (value: unknown) => value === undefined || value === null || value === "" || value === "(None)"
const dayKey = (nowMs: number) => Math.floor((nowMs + 3 * 60 * 60 * 1000) / 86_400_000) // CN 05:00 business day

/** Called inside a successful action's transaction. Nested persistence transactions
 * retain the caller's rollback boundary. Closed events receive no new facts. */
export function recordContentActionFactsSync(playerId: number, fact: ContentActionFact): number[] {
    const nowMs = fact.nowMs ?? Date.now(), amount = fact.kind === "login" ? 1 : fact.amount ?? 1
    if (!Number.isSafeInteger(playerId) || playerId <= 0 || !Object.prototype.hasOwnProperty.call(CONDITIONS, fact.kind)
        || !Number.isSafeInteger(nowMs) || nowMs < 0 || !Number.isSafeInteger(amount) || amount < 0
        || (fact.dedupeKey !== undefined && (typeof fact.dedupeKey !== "string" || !fact.dedupeKey.length || fact.dedupeKey.length > 240)))
        throw new TypeError("Invalid successful content action fact")
    if (amount === 0) return []
    return runPersistenceTransactionSync({ domain: "mission", playerId, operation: "record_content_action_fact" }, () => {
        const actionKey = fact.dedupeKey === undefined ? undefined : `${fact.kind}:${fact.dedupeKey}`
        if (actionKey && getPlayerOperationReceiptSync(playerId, "content_action_fact", actionKey)) return []
        const changed: number[] = [], at = new Date(nowMs)
        const categories = fact.kind === "login" ? [4, 8] : fact.kind === "stamina_spend" ? [4, 6, 7] : [4]
        for (const definition of categories.flatMap(category => getMissionMasterDefinitions(category))) {
            const pattern = definition.category === 4 ? Number(definition.row[4]) : definition.patternType
            if (pattern !== CONDITIONS[fact.kind]
                || !isMissionDefinitionEnabledAt(definition, at, definition.eventId)) continue
            // Legacy passes retain their existing snapshot calculations. Explicit
            // operations control uses only facts collected while participation is on.
            if (definition.category !== 4
                && contentMissionDecision(definition.category, definition.missionId, "enter", nowMs) !== true) continue
            // All current missions of these nine kinds have no selectors or
            // prerequisite lock. Future variants require their own reviewed rule.
            // item_id can contain legacy residue for non-item patterns; it is
            // not an eligibility selector for any action handled here.
            if (definition.category === 4
                && [15, 16, 20, 21, 22, 23, 24, 25, 26].some(index => !absent(definition.row[index]))) continue
            const loginKey = `${definition.category}:${definition.missionId}:${dayKey(nowMs)}`
            if (fact.kind === "login" && getPlayerOperationReceiptSync(playerId, "content_mission_login", loginKey)) continue
            incrementPlayerCategoryMissionSync(playerId, definition.category, definition.missionId, amount)
            changed.push(definition.missionId)
            if (fact.kind === "login") insertPlayerOperationReceiptSync({ playerId, operation: "content_mission_login",
                requestKey: loginKey, response: { missionId: definition.missionId } }, nowMs)
        }
        changed.push(...refreshCollectTargetMissionProgressSync(playerId, at))
        if (actionKey) insertPlayerOperationReceiptSync({ playerId, operation: "content_action_fact", requestKey: actionKey,
            response: { missionIds: [...new Set(changed)] } }, nowMs)
        return [...new Set(changed)]
    })
}
