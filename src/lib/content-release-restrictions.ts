import policy from "../../assets/quest_shop_availability_cnmod.json"
import type { ContentOperationsSnapshot } from "./content-operations-store"

const quests = new Set<string>(policy.managedQuestKeys)
const shops = new Set<string>(policy.closedShopKeys)
if (policy.schemaVersion !== 1 || quests.size !== policy.expectedQuestCount
    || shops.size !== policy.expectedShopCount
    || policy.questFlags.visible !== false || policy.questFlags.enter !== false
    || policy.shopFlags.visible !== false || policy.shopFlags.exchange !== false
    || [...quests].some(key => !/^(2|26):\d+$/.test(key))
    || [...shops].some(key => !/^boss_coin_shop:\d+$/.test(key))) {
    throw new Error("Invalid restricted content availability policy")
}

/** Definitions and owned progress remain present; a new catalog cannot reopen these entries. */
export function isReleaseClosedQuest(category: number, questId: number): boolean {
    return quests.has(`${category}:${questId}`)
}

export function isReleaseClosedShop(type: string, shopId: number): boolean {
    return shops.has(`${type}:${shopId}`)
}

const CLOSED_QUEST_CONTROL_KEY = "closed_boss_quests:1"
const record = (value: unknown): value is Record<string, unknown> =>
    !!value && typeof value === "object" && !Array.isArray(value)
const stripClosedQuestKeys = (value: unknown): unknown =>
    Array.isArray(value) ? value.filter(key => !quests.has(String(key))) : value

function cloneDefaultPolicy(value: Record<string, unknown>): Record<string, unknown> {
    // The native policy is a shallow tree of string lists. Copying those lists
    // avoids structuredClone traversing roughly 80,000 immutable key strings.
    // Unknown shapes retain the original general clone contract.
    const actions = value.actions
    const fields = ["closed_keys", "qualified_rights_keys", "legacy_keys"]
    if (Object.keys(value).some(key => !["version", "explicit_actions_override_defaults", "actions"].includes(key))
        || value.version !== 1 || value.explicit_actions_override_defaults !== true || !record(actions)
        || Object.values(actions).some(scope => !record(scope) || Object.keys(scope).some(key => !fields.includes(key))
            || fields.some(field => !Array.isArray(scope[field]) || !(scope[field] as unknown[]).every(key => typeof key === "string")))) {
        return structuredClone(value)
    }
    return { ...value, actions: Object.fromEntries(Object.entries(actions).map(([action, scope]) => [action,
        Object.fromEntries(fields.map(field => [field, [...(scope as Record<string, string[]>)[field]]]))])) }
}

/** Read-only wire projection: existing native clients consume these generic quest scopes. */
export function projectReleaseClosedSnapshot(snapshot: ContentOperationsSnapshot): ContentOperationsSnapshot {
    const questKeys = [...quests]
    const closedAction = (scope: string[] | null = null) => ({
        enabled: false, ends_at_ms: null, quest_keys: scope, mission_keys: null,
    })
    const states: Array<Record<string, unknown>> = snapshot.states.filter(row => row.key !== CLOSED_QUEST_CONTROL_KEY).map(row => {
        const actions = record(row.actions) ? Object.fromEntries(Object.entries(row.actions).map(([action, value]) =>
            [action, record(value) ? { ...value, quest_keys: stripClosedQuestKeys(value.quest_keys) } : value])) : row.actions
        if (shops.has(String(row.key)) && record(actions)) {
            actions.visible = closedAction()
            actions.exchange = closedAction()
        }
        return { ...row, quest_keys: stripClosedQuestKeys(row.quest_keys), actions }
    })
    states.push({ key: CLOSED_QUEST_CONTROL_KEY, instance_id: CLOSED_QUEST_CONTROL_KEY + ":original",
        permanent: true, ends_at_ms: null, quest_keys: questKeys, mission_keys: null,
        visible: false, enter: false,
        actions: { visible: closedAction(questKeys), enter: closedAction(questKeys) } })
    const catalog: Array<Record<string, unknown>> = snapshot.catalog.filter(row => row.key !== CLOSED_QUEST_CONTROL_KEY)
        .map(row => ({ ...row, quest_keys: stripClosedQuestKeys(row.quest_keys) }))
    catalog.push({ key: CLOSED_QUEST_CONTROL_KEY, type: "closed_boss_quests", id: 1, entry: null,
        server_actions: ["visible", "enter"], client_actions: ["visible", "enter"], parent_key: null,
        quest_keys: questKeys, mission_keys: [] })
    const defaults = record(snapshot.default_policy) ? cloneDefaultPolicy(snapshot.default_policy) : undefined
    if (defaults && record(defaults.actions)) for (const action of ["visible", "exchange"]) {
        const scope = defaults.actions[action]
        if (!record(scope)) continue
        scope.closed_keys = [...new Set([...(Array.isArray(scope.closed_keys) ? scope.closed_keys : []), ...shops])]
        for (const field of ["qualified_rights_keys", "legacy_keys"]) if (Array.isArray(scope[field])) {
            scope[field] = (scope[field] as unknown[]).filter(key => !shops.has(String(key)))
        }
    }
    return { ...snapshot, states, catalog, ...(defaults ? { default_policy: defaults } : {}) }
}
