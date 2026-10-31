import { createHash } from "node:crypto"
import { ContentOperationError, ContentOperationsStore, type ContentActionOverride } from "./content-operations-store"
import { assertTimeCutoverOfflineDatabaseSync, type OfflineDatabaseGuard } from "./time-cutover-rehearsal"

const tower = Array.from({ length: 10 }, (_, index) => `20:${1381 + index}`)
const challenge = [...Array.from({ length: 19 }, (_, index) => `13:${1001 + index}`), "13:1038", "13:1039", "13:1040"]
const targets = [
    { key: "boss_coin_shop:990099002", actions: ["visible", "exchange"] },
    { key: "boss_coin_shop:990099032", actions: ["visible", "exchange"] },
    { key: "boss_coin_shop:990099033", actions: ["visible", "exchange"] },
    { key: "gacha:990005", actions: ["exchange"] },
    { key: "tower_dungeon_event:1", actions: ["visible", "enter"], questKeys: tower },
    { key: "challenge_dungeon_event:1", actions: ["visible", "enter"], questKeys: challenge },
] as const
type RepairAction = "visible" | "enter" | "exchange"
const reason = "恢复既有商品与角色兑换；修正原生单期选关范围，保留原实例及全部玩家进度"
const evidence = "Existing authoritative product IDs, exchange flags and prices retained; native tower requires one ten-quest cycle; challenge list retains the reviewed permanent cycle"
function stable(value: unknown): string {
    if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`
    if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`).join(",")}}`
    return JSON.stringify(value)
}
const hash = (value: unknown) => createHash("sha256").update(stable(value)).digest("hex")
export interface ReportedContentRepairPlan {
    schemaVersion: 1
    kind: "reported-content-repair"
    catalogDigest: string
    expectedRevision: number
    createdAtMs: number
    changes: Array<{ key: string; beforeDigest: string; expectedContentDigest: string;
        actionOverrides: Partial<Record<RepairAction, ContentActionOverride>> }>
    digest: string
}

/** An explicit, bounded repair preview. No initializer, account lookup or database write. */
export function buildReportedContentRepairPlanSync(store: ContentOperationsStore, nowMs: number): ReportedContentRepairPlan {
    if (!Number.isSafeInteger(nowMs) || nowMs < 0) throw new ContentOperationError("修正时间无效")
    const changes: ReportedContentRepairPlan["changes"] = []
    for (const target of targets) {
        if (!store.rows.has(target.key)) throw new ContentOperationError(`缺少原内容：${target.key}`, 409)
        const before = store.state(target.key)
        if (before?.integrityError || before?.published === false || before?.controlled === false)
            throw new ContentOperationError(`内容完整性异常或另有运营关闭决定，请先核对：${target.key}`, 409)
        if (!before && !target.key.startsWith("boss_coin_shop:"))
            throw new ContentOperationError(`缺少已核查的原活动状态：${target.key}`, 409)
        const contentDigest = store.contentDigests.get(target.key)
        if (before && (before.catalogDigest !== store.digest || before.contentDigest !== contentDigest))
            throw new ContentOperationError(`内容身份已变化，禁止以修正计划重新认证：${target.key}`, 409)
        const actionOverrides: Partial<Record<RepairAction, ContentActionOverride>> = {}
        for (const action of target.actions) {
            const current = before?.actionOverrides?.[action]
            if (before && (!current || current.endsAtMs !== null || !["verified", "current_baseline"].includes(current.readiness)
                || current.catalogDigest !== store.digest || current.contentDigest !== contentDigest))
                throw new ContentOperationError(`动作已到期、未核查或身份变化，请单独审核：${target.key}/${action}`, 409)
            if (current?.enabled === false && !(target.key === "gacha:990005" && action === "exchange"))
                throw new ContentOperationError(`保留既有动作关闭决定，请单独核对：${target.key}/${action}`, 409)
            const scope = "questKeys" in target ? [...target.questKeys].sort() : undefined
            if (current?.enabled && current.endsAtMs === null && ["verified", "current_baseline"].includes(current.readiness)
                && (scope === undefined || stable(current.questKeys) === stable(scope))) continue
            actionOverrides[action] = { enabled: true, endsAtMs: null, readiness: "verified", evidence,
                ...(scope === undefined ? {} : { questKeys: scope }) }
        }
        if (Object.keys(actionOverrides).length) changes.push({ key: target.key, beforeDigest: hash(before),
            expectedContentDigest: contentDigest!, actionOverrides })
    }
    const body = { schemaVersion: 1 as const, kind: "reported-content-repair" as const, catalogDigest: store.digest,
        expectedRevision: store.revision(), createdAtMs: nowMs, changes }
    return { ...body, digest: hash(body) }
}

/** The normal state API supplies validation/audit and preserves instance IDs.
 * Offline correction is deliberate: startup must never undo later operator decisions. */
export function applyReportedContentRepairOfflineSync(store: ContentOperationsStore, plan: ReportedContentRepairPlan,
    options: { expectedPlanDigest: string; nowMs: number; offlineGuard?: OfflineDatabaseGuard }) {
    assertTimeCutoverOfflineDatabaseSync(store.db, options.offlineGuard)
    if (!Number.isSafeInteger(options.nowMs) || options.nowMs < 0)
        throw new ContentOperationError("修正时间无效")
    return store.db.transaction(() => {
        if (plan?.schemaVersion !== 1 || plan.kind !== "reported-content-repair" || plan.digest !== options.expectedPlanDigest
            || stable(buildReportedContentRepairPlanSync(store, plan.createdAtMs)) !== stable(plan))
            throw new ContentOperationError("修正计划或运营状态已变化，请重新预览", 409)
        const updatedKeys: string[] = []
        for (const change of plan.changes) {
            store.update(change.key, { expectedRevision: store.revision(), catalogDigest: store.digest,
                reason, actionOverrides: change.actionOverrides }, options.nowMs)
            updatedKeys.push(change.key)
        }
        for (const target of targets) for (const action of target.actions) {
            if (store.allowed(target.key, action, options.nowMs) !== true)
                throw new ContentOperationError(`修正后动作仍不可用：${target.key}/${action}`, 409)
            if ("questKeys" in target && stable(store.state(target.key)?.actionOverrides?.[action]?.questKeys) !== stable([...target.questKeys].sort()))
                throw new ContentOperationError(`修正后原生关卡范围不匹配：${target.key}`, 409)
        }
        return { applied: updatedKeys.length > 0, revision: store.revision(), catalogDigest: store.digest, updatedKeys }
    }).immediate()
}
