import { createHash } from "node:crypto"
import { CONTENT_ACTIONS, ContentOperationError, ContentOperationsStore, type ContentActionOverride } from "./content-operations-store"
import { assertTimeCutoverOfflineDatabaseSync, type OfflineDatabaseGuard } from "./time-cutover-rehearsal"
import { assertDeploymentMaintenanceContextSync, type DeploymentMaintenanceContext } from "./deployment-maintenance-guard"

const reviewedBatchConnections = new WeakSet<ContentOperationsStore["db"]>()
function assertHistoryOfflineDatabaseSync(store: ContentOperationsStore, guard?: OfflineDatabaseGuard,
    maintenanceContext?: DeploymentMaintenanceContext): void {
    if (maintenanceContext) {
        if (guard) throw new ContentOperationError("不能混用离线和部署维护许可", 409)
        assertDeploymentMaintenanceContextSync(store.db, maintenanceContext)
    } else if (!reviewedBatchConnections.has(store.db)) assertTimeCutoverOfflineDatabaseSync(store.db, guard)
    else if (!store.db.open || store.db.readonly || !store.db.inTransaction)
        throw new ContentOperationError("历史核查批处理连接已失效", 409)
}
/** Validate the explicit stopped database before taking its write transaction.
 * Only this callback may invoke the three guarded metadata stages as savepoints. */
export function runReviewedHistoryBatchOfflineSync<T>(store: ContentOperationsStore, options: {
    expectedRevision: number; offlineGuard?: OfflineDatabaseGuard
}, run: () => T): T {
    assertTimeCutoverOfflineDatabaseSync(store.db, options.offlineGuard)
    if (store.revision() !== options.expectedRevision) throw new ContentOperationError("状态版本已变化", 409)
    return store.db.transaction(() => {
        if (store.revision() !== options.expectedRevision) throw new ContentOperationError("状态版本已变化", 409)
        reviewedBatchConnections.add(store.db)
        try { return run() } finally { reviewedBatchConnections.delete(store.db) }
    }).immediate()
}

/** An explicit reviewed plan, never inferred from a banner, date, or catalog match. */
export interface ReviewedHistoryPlan {
    schemaVersion: 1
    catalogDigest: string
    evidenceDigest: string
    approvedExistingOwners?: Array<{ key: string; rawSha256: string }>
    candidates: Array<{
        key: string
        mode?: "participation" | "retained_rights"
        actionOverrides: Partial<Record<typeof CONTENT_ACTIONS[number], ContentActionOverride>>
    }>
}

export interface ContentIdentityRebindPlan {
    schemaVersion: 1
    catalogDigest: string
    evidenceDigest: string
    bindings: Array<{ key: string; previousRawSha256: string; nextContentDigest: string }>
}

export interface ExistingHistoryReviewPlan {
    schemaVersion: 1
    catalogDigest: string
    evidenceDigest: string
    upgrades: Array<{ key: string; previousRawSha256: string; defaultClosed?: boolean
        actionOverrides: Partial<Record<typeof CONTENT_ACTIONS[number], ContentActionOverride>> }>
}

/** Explicit native rule completion after identity rebinding. New participation
 * approvals on a previously closed entry must remain unpublished. */
export function completeExistingHistoryReviewsOfflineSync(store: ContentOperationsStore, plan: ExistingHistoryReviewPlan, options: {
    expectedRevision: number; nowMs: number; offlineGuard?: OfflineDatabaseGuard; maintenanceContext?: DeploymentMaintenanceContext
}): { reviewedKeys: string[]; revision: number } {
    assertHistoryOfflineDatabaseSync(store, options.offlineGuard, options.maintenanceContext)
    if (!plan || plan.schemaVersion !== 1 || plan.catalogDigest !== store.digest || !/^[a-f0-9]{64}$/.test(plan.evidenceDigest)
        || !Array.isArray(plan.upgrades) || new Set(plan.upgrades.map(row => row.key)).size !== plan.upgrades.length
        || !Number.isSafeInteger(options.nowMs) || options.nowMs < 0 || store.revision() !== options.expectedRevision)
        throw new ContentOperationError("既有内容核查计划或状态版本不匹配", 409)
    return store.db.transaction(() => {
        if (store.revision() !== options.expectedRevision) throw new ContentOperationError("状态已变化", 409)
        const reviewedKeys: string[] = []
        for (const upgrade of plan.upgrades) {
            const before = store.state(upgrade.key), raw = store.db.prepare("SELECT value_json FROM content_operations_state WHERE content_key=?")
                .get(upgrade.key) as { value_json: string } | undefined
            if (!before || before.integrityError || !raw || createHash("sha256").update(raw.value_json).digest("hex") !== upgrade.previousRawSha256
                || !upgrade.actionOverrides || Object.keys(upgrade.actionOverrides).some(action => !CONTENT_ACTIONS.includes(action as typeof CONTENT_ACTIONS[number])))
                throw new ContentOperationError("既有配置已变化，不能覆盖当前运营决定", 409)
            for (const [action, next] of Object.entries(upgrade.actionOverrides)) {
                const actionName = action as typeof CONTENT_ACTIONS[number]
                const previous = before.controlled === false ? undefined : before.actionOverrides !== undefined
                    ? before.actionOverrides[actionName] : { enabled: before.flags[actionName], endsAtMs: before.endsAtMs,
                        readiness: before.readiness, questKeys: before.questKeys, missionKeys: before.missionKeys }
                if (!next || next.readiness !== "verified" || !next.evidence?.trim() || next.endsAtMs !== (previous?.endsAtMs ?? null))
                    throw new ContentOperationError("补充核查需要明确的原生规则依据", 409)
                if (previous?.enabled && !next.enabled) throw new ContentOperationError("补充核查不得撤销既有动作权限", 409)
                if (previous?.enabled === false && next.enabled && previous.readiness !== "unverified")
                    throw new ContentOperationError("补充核查不得覆盖既有明确关闭的动作", 409)
                for (const kind of ["questKeys", "missionKeys"] as const) {
                    const oldScope = previous?.[kind], newScope = next[kind]
                    if (previous?.enabled && (oldScope === null || oldScope === undefined) && newScope !== null && newScope !== undefined)
                        throw new ContentOperationError("补充核查不得缩小既有成员范围", 409)
                    if (Array.isArray(oldScope) && newScope !== undefined && newScope !== null
                        && oldScope.some(member => !newScope.includes(member)))
                        throw new ContentOperationError("补充核查不得删除既有成员", 409)
                }
                if ((action === "visible" || action === "enter") && next.enabled && !previous?.enabled && upgrade.defaultClosed !== true)
                    throw new ContentOperationError("新增参与核查必须默认关闭", 409)
            }
            if (upgrade.defaultClosed) {
                const retainedExchange = store.allowed(upgrade.key, "exchange", options.nowMs)
                if (!store.supportsPublicationSwitch(upgrade.key) || store.allowed(upgrade.key, "visible", options.nowMs) === true
                    || store.allowed(upgrade.key, "enter", options.nowMs) === true)
                    throw new ContentOperationError("默认关闭不能改变当前已开放内容", 409)
                if (before.published !== false) store.setPublished(upgrade.key, { published: false, expectedRevision: store.revision(),
                    catalogDigest: store.digest, reason: "补齐历史核查，保留当前未开放状态" }, options.nowMs)
                if (retainedExchange === true && store.allowed(upgrade.key, "exchange", options.nowMs) !== true)
                    throw new ContentOperationError("默认关闭不得收回既有兑换权限", 409)
            }
            store.update(upgrade.key, { expectedRevision: store.revision(), catalogDigest: store.digest,
                reason: "补齐已核对的原生玩法与成员，保留运营开关及既有进度", actionOverrides: upgrade.actionOverrides }, options.nowMs)
            const after = store.state(upgrade.key)!
            if (after.instanceId !== before.instanceId || (!upgrade.defaultClosed && after.published !== before.published))
                throw new ContentOperationError("核查补全不得替换实例或运营开关", 409)
            reviewedKeys.push(upgrade.key)
        }
        return { reviewedKeys, revision: store.revision() }
    }).immediate()
}

function semanticControl(state: Record<string, unknown>): string {
    const copy = JSON.parse(JSON.stringify(state))
    delete copy.revision; delete copy.catalogDigest; delete copy.contentDigest
    // Root evidence is unused by action-scoped controls. The first explicit
    // identity review fills this formerly empty diagnostic field.
    if (copy.actionOverrides) {
        delete copy.evidence
        for (const action of Object.values(copy.actionOverrides) as Record<string, unknown>[]) {
            delete action.catalogDigest; delete action.contentDigest
        }
    }
    return JSON.stringify(copy)
}

/** Rebind explicitly reviewed loader identities, without altering any permission,
 * scope, deadline, instance, action evidence or player record. The plan binds the
 * exact previous serialized state and the exact new computed definition identity. */
export function rebindReviewedContentIdentitiesOfflineSync(store: ContentOperationsStore, plan: ContentIdentityRebindPlan, options: {
    expectedRevision: number; nowMs: number; offlineGuard?: OfflineDatabaseGuard; maintenanceContext?: DeploymentMaintenanceContext
}): { reboundKeys: string[]; revision: number } {
    assertHistoryOfflineDatabaseSync(store, options.offlineGuard, options.maintenanceContext)
    if (!plan || plan.schemaVersion !== 1 || plan.catalogDigest !== store.digest
        || !/^[a-f0-9]{64}$/.test(plan.evidenceDigest) || !Array.isArray(plan.bindings)
        || new Set(plan.bindings.map(row => row.key)).size !== plan.bindings.length
        || !Number.isSafeInteger(options.nowMs) || options.nowMs < 0
        || store.revision() !== options.expectedRevision)
        throw new ContentOperationError("定义身份复核计划或状态版本不匹配", 409)
    return store.db.transaction(() => {
        if (store.revision() !== options.expectedRevision) throw new ContentOperationError("状态已变化", 409)
        const reboundKeys: string[] = []
        for (const binding of plan.bindings) {
            const persisted = store.db.prepare("SELECT value_json FROM content_operations_state WHERE content_key=?")
                .get(binding.key) as { value_json: string } | undefined
            const before = store.state(binding.key)
            if (!persisted || !before || before.integrityError
                || createHash("sha256").update(persisted.value_json).digest("hex") !== binding.previousRawSha256
                || store.contentDigests.get(binding.key) !== binding.nextContentDigest
                || store.runtimeDefinitions.get(binding.key)?.matchesCatalog !== true)
                throw new ContentOperationError("既有运营配置或复核定义发生变化", 409)
            const common = { expectedRevision: store.revision(), catalogDigest: store.digest,
                readiness: before.readiness,
                evidence: before.evidence.trim() || `原生字段读取复核 ${plan.evidenceDigest}；逐动作原审批保持不变`,
                reason: "核对原生字段与资源身份，保持既有权限和进度" }
            const input = before.actionOverrides !== undefined ? { ...common, actionOverrides: Object.fromEntries(
                Object.entries(before.actionOverrides).map(([action, value]) => {
                    const { contentDigest: _content, catalogDigest: _catalog, ...review } = value!
                    return [action, review]
                })) } : { ...common, flags: before.flags, endsAtMs: before.endsAtMs,
                    ...(before.questKeys !== undefined ? { questKeys: before.questKeys } : {}),
                    ...(before.missionKeys !== undefined ? { missionKeys: before.missionKeys } : {}) }
            const after = store.update(binding.key, input, options.nowMs)
            if (semanticControl(before as unknown as Record<string, unknown>) !== semanticControl(after as unknown as Record<string, unknown>))
                throw new ContentOperationError("身份复核不得改变既有运营权限", 409)
            reboundKeys.push(binding.key)
        }
        return { reboundKeys, revision: store.revision() }
    }).immediate()
}

/** Prepare new controls closed in one transaction. Existing operator states always win.
 * The caller must stop writers and create an SQLite backup before applying to a file.
 * No player data, time setting, content instance or existing action scope is rewritten. */
export function prepareReviewedHistoryOfflineSync(store: ContentOperationsStore, plan: ReviewedHistoryPlan, options: {
    expectedRevision: number
    nowMs: number
    offlineGuard?: OfflineDatabaseGuard
    maintenanceContext?: DeploymentMaintenanceContext
}): { preparedKeys: string[]; preservedKeys: string[]; revision: number; planDigest: string } {
    assertHistoryOfflineDatabaseSync(store, options.offlineGuard, options.maintenanceContext)
    if (!plan || plan.schemaVersion !== 1 || plan.catalogDigest !== store.digest
        || !/^[a-f0-9]{64}$/.test(plan.evidenceDigest) || !Array.isArray(plan.candidates))
        throw new ContentOperationError("历史内容核查计划或目录不匹配", 409)
    if (!Number.isSafeInteger(options.nowMs) || options.nowMs < 0
        || !Number.isSafeInteger(options.expectedRevision) || options.expectedRevision !== store.revision())
        throw new ContentOperationError("状态版本或准备时间无效", 409)
    const keys = new Set<string>()
    const approvedOwners = new Map<string, string>()
    for (const owner of plan.approvedExistingOwners ?? []) {
        if (!owner || typeof owner.key !== "string" || !/^[a-f0-9]{64}$/.test(owner.rawSha256) || approvedOwners.has(owner.key))
            throw new ContentOperationError("既有活动商品核查计划无效", 409)
        approvedOwners.set(owner.key, owner.rawSha256)
    }
    for (const candidate of plan.candidates) {
        if (!candidate || typeof candidate.key !== "string" || keys.has(candidate.key)
            || (candidate.mode !== undefined && !["participation", "retained_rights"].includes(candidate.mode))
            || !candidate.actionOverrides || typeof candidate.actionOverrides !== "object"
            || Object.keys(candidate.actionOverrides).some(action => !CONTENT_ACTIONS.includes(action as typeof CONTENT_ACTIONS[number])))
            throw new ContentOperationError("历史内容计划存在重复项目或无效动作")
        keys.add(candidate.key)
        for (const value of Object.values(candidate.actionOverrides)) {
            if (!value || value.readiness !== "verified" || !value.evidence?.trim() || value.endsAtMs !== null)
                throw new ContentOperationError("历史内容必须具备逐项核查依据，且不沿用旧日期")
        }
    }
    const planDigest = createHash("sha256").update(JSON.stringify(plan)).digest("hex")
    return store.db.transaction(() => {
        if (store.revision() !== options.expectedRevision) throw new ContentOperationError("状态已变化，请重新检查", 409)
        const preparedKeys: string[] = [], preservedKeys: string[] = []
        for (const candidate of plan.candidates) {
            if (store.state(candidate.key)) {
                preservedKeys.push(candidate.key)
                continue
            }
            // Use the normal store validators, exact member scopes and catalog guards.
            // Initially disabling each action prevents any intermediate participation.
            const disabled = Object.fromEntries(CONTENT_ACTIONS.map(action => [action, {
                ...(candidate.actionOverrides[action] ?? { readiness: "verified", evidence: `历史核查 ${plan.evidenceDigest}`, endsAtMs: null }),
                enabled: false,
            }]))
            const request = (actionOverrides: unknown) => ({ expectedRevision: store.revision(), catalogDigest: store.digest,
                reason: "完成历史内容核查，默认关闭并保留原进度", actionOverrides })
            store.update(candidate.key, request(disabled), options.nowMs)
            // Publication is deliberately separate from the reviewed action settings.
            // This also permits preparing several mutually exclusive passes closed.
            const listing = store.rows.get(candidate.key)
            if (!listing) throw new ContentOperationError("历史内容项目不存在", 404)
            const retainedOnly = candidate.mode === "retained_rights"
            if (retainedOnly && !(listing.key === "active_mission_event:150"
                || listing.type === "gacha" && ([700000, 700001, 700002, 700003, 700004, 80000, 80001, 80002, 80003, 80004].includes(listing.id)))
                || retainedOnly && (candidate.actionOverrides.visible?.enabled || candidate.actionOverrides.enter?.enabled))
                throw new ContentOperationError("仅保留既有权益不能新增参与资格", 409)
            if (store.supportsPublicationSwitch(candidate.key)) {
                if (!retainedOnly && (candidate.actionOverrides.visible?.enabled !== true
                    || (store.capabilities(listing).includes("enter") && candidate.actionOverrides.enter?.enabled !== true))
                )
                    throw new ContentOperationError("历史内容必须同时完成入口与实际参与的核查", 409)
                store.setPublished(candidate.key, { published: false, expectedRevision: store.revision(),
                    catalogDigest: store.digest, reason: "历史内容默认关闭" }, options.nowMs)
                store.update(candidate.key, request(candidate.actionOverrides), options.nowMs)
            } else if (listing.type === "event_item_shop" && listing.parentKey) {
                // Event-shop business writes check both product and owner. Prepare
                // products only behind a closed owner; never expand an open event.
                const parent = store.state(listing.parentKey)
                const parentRaw = store.db.prepare("SELECT value_json FROM content_operations_state WHERE content_key=?").get(listing.parentKey) as { value_json: string } | undefined
                const approvedExisting = parentRaw && approvedOwners.get(listing.parentKey) === createHash("sha256").update(parentRaw.value_json).digest("hex")
                    && store.allowed(listing.parentKey, "exchange", options.nowMs) === true
                if (!parent || !(parent.published === false && store.allowed(listing.parentKey, "exchange", options.nowMs) === false) && !approvedExisting)
                    throw new ContentOperationError("历史商品必须隶属已经关闭的活动", 409)
                if (candidate.actionOverrides.exchange?.enabled !== true)
                    throw new ContentOperationError("历史商品尚未完成实际兑换核查", 409)
                store.update(candidate.key, request(candidate.actionOverrides), options.nowMs)
            } else {
                // Qualified exchanges have no new-participation publication switch.
                // Their action itself remains closed until an administrator opens it.
                if (!(retainedOnly && listing.type === "gacha") && !["special_exchange_campaign", "start_dash_exchange_campaign"].includes(listing.type)
                    || candidate.actionOverrides.exchange?.enabled !== true)
                    throw new ContentOperationError("此历史内容尚无可用的日常开关", 409)
                if (retainedOnly) store.update(candidate.key, request(candidate.actionOverrides), options.nowMs)
            }
            preparedKeys.push(candidate.key)
        }
        return { preparedKeys, preservedKeys, revision: store.revision(), planDigest }
    }).immediate()
}
