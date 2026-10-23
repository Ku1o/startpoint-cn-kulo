import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import path from "node:path"
import presentation from "../../assets/content_presentation.json"
import { julyContentPlan } from "./content-operations-bootstrap"
import { applyJulyContentPlanOfflineSync } from "./content-operations-bootstrap"
import { completeExistingHistoryReviewsOfflineSync, prepareReviewedHistoryOfflineSync,
    type ExistingHistoryReviewPlan, type ReviewedHistoryPlan } from "./content-history-bootstrap"
import { ContentOperationError, type ContentControl, type ContentOperationsStore } from "./content-operations-store"
import { inspectBoxExchangeSupplementSync, applyBoxExchangeSupplementSync } from "./content-box-exchange-supplement"
import { assertDeploymentMaintenanceContextSync, type DeploymentMaintenanceContext } from "./deployment-maintenance-guard"

const root = path.resolve(__dirname, "../..")
const REVIEW_PLAN_DIGEST = "eb559d9058244155b680deb8fd8f557a19c2b22ee5c6f82dd0e73788f91b52c8"
const READINESS_SHA256 = "434b45000e20c326ff35f99bcbfc8d632ccbf8ed5fcb61bc0524143acc9bdaac"
const CATALOG_DIGEST = "4bc3f197ffbff0fa0c6189483064bcdceaf2eacda3d7ee0e08603c314854f246"
const sha = (value: string | Buffer) => createHash("sha256").update(value).digest("hex")
const markerTable = "content_operations_deployment"

interface ReviewedDeploymentPlan {
    schemaVersion: 1
    referenceDate: "2025-07-20"
    catalogDigest: string
    julyPlanDigest: string
    source: { readinessSha256: string; deltaAuditSha256: string; deltaSnapshotSha256: string; generatorSha256: string }
    expected: { julyControls: number; reviewedExisting: number; historicalCandidates: number;
        totalControlStates: number; parentControls: number; unsupportedParents: string[] }
    stage2: ExistingHistoryReviewPlan
    stage3: ReviewedHistoryPlan
    digest: string
}
export interface ContentDeploymentCounts {
    phase: "initial" | "applied" | "partial"
    catalogParents: number
    targetParentControls: number
    unsupportedParents: number
    unsupportedParentKeys: string[]
    unsupportedParentReasons: Record<string, string>
    presentParentControls: number
    missingParentControls: number
    presentControlStates: number
    expectedControlStates: number
    currentRevision: number
    boxExchangeTarget: number
    boxExchangeReady: boolean
}
export interface ContentDeploymentInspection { ready: boolean; canApply: boolean; reasons: string[]; counts: ContentDeploymentCounts }
export interface ContentDeploymentApplyResult {
    applied: boolean; revision: number; planDigest: string; counts: ContentDeploymentCounts
}

function reviewedPlan(store: ContentOperationsStore): { plan: ReviewedDeploymentPlan; keys: Set<string>; parentKeys: string[];
    controlledParentKeys: Set<string> } {
    const plan = JSON.parse(readFileSync(path.join(root, "assets/content_deployment_review_plan.json"), "utf8")) as ReviewedDeploymentPlan
    const { digest, ...body } = plan
    if (digest !== REVIEW_PLAN_DIGEST || sha(JSON.stringify(body)) !== digest
        || plan.schemaVersion !== 1 || plan.referenceDate !== "2025-07-20"
        || plan.catalogDigest !== CATALOG_DIGEST || store.digest !== CATALOG_DIGEST
        || plan.julyPlanDigest !== sha(JSON.stringify(julyContentPlan))
        || plan.source.readinessSha256 !== READINESS_SHA256
        || sha(readFileSync(path.join(root, "assets/content_history_readiness.json"))) !== READINESS_SHA256
        || !/^[a-f0-9]{64}$/.test(plan.source.deltaAuditSha256)
        || !/^[a-f0-9]{64}$/.test(plan.source.deltaSnapshotSha256)
        || !/^[a-f0-9]{64}$/.test(plan.source.generatorSha256)
        || plan.stage2.catalogDigest !== store.digest || plan.stage3.catalogDigest !== store.digest
        || plan.stage2.schemaVersion !== 1 || plan.stage3.schemaVersion !== 1)
        throw new ContentOperationError("内容部署审阅计划或来源身份不匹配", 409)
    const { expected } = plan
    if (expected.julyControls !== 1113 || expected.reviewedExisting !== 20
        || expected.historicalCandidates !== 8486 || expected.totalControlStates !== 9599
        || expected.parentControls !== 1018
        || JSON.stringify(expected.unsupportedParents) !== JSON.stringify(["collect_item_event:5", "collect_item_event:80003"])
        || julyContentPlan.controls.length !== expected.julyControls
        || plan.stage2.upgrades.length !== expected.reviewedExisting
        || plan.stage3.candidates.length !== expected.historicalCandidates)
        throw new ContentOperationError("内容部署审阅范围不匹配", 409)
    const keys = new Set(julyContentPlan.controls.map(row => row.key))
    for (const candidate of plan.stage3.candidates) {
        if (keys.has(candidate.key)) throw new ContentOperationError("内容部署计划存在重复初始化", 409)
        keys.add(candidate.key)
    }
    if (keys.size !== expected.totalControlStates || new Set(plan.stage2.upgrades.map(row => row.key)).size !== expected.reviewedExisting
        || plan.stage2.upgrades.some(row => !keys.has(row.key))
        || new Set(plan.stage3.candidates.map(row => row.key)).size !== expected.historicalCandidates)
        throw new ContentOperationError("内容部署项目集合不匹配", 409)
    const parentKeys = Object.keys(presentation.rows)
    const unsupported = new Set(expected.unsupportedParents)
    const controlledParentKeys = new Set(parentKeys.filter(key => keys.has(key)))
    if (parentKeys.length !== 1020 || new Set(parentKeys).size !== 1020
        || parentKeys.some(key => !store.rows.has(key) || (keys.has(key) === unsupported.has(key)))
        || controlledParentKeys.size !== expected.parentControls)
        throw new ContentOperationError("内容部署父项覆盖范围不匹配", 409)
    return { plan, keys, parentKeys, controlledParentKeys }
}

function readMarker(store: ContentOperationsStore): { plan_digest: string; catalog_digest: string } | null {
    const exists = store.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(markerTable)
    return exists ? store.db.prepare(`SELECT plan_digest,catalog_digest FROM ${markerTable} WHERE id=1`).get() as
        { plan_digest: string; catalog_digest: string } | undefined ?? null : null
}

function currentIdentity(store: ContentOperationsStore, key: string, state: ContentControl | null): boolean {
    if (!state || state.integrityError || state.controlled !== true || state.catalogDigest !== store.digest
        || state.contentDigest !== store.contentDigests.get(key)
        || store.runtimeDefinitions.get(key)?.matchesCatalog !== true) return false
    return Object.values(state.actionOverrides ?? {}).every(action => action?.catalogDigest === store.digest
        && action.contentDigest === store.contentDigests.get(key))
}

/** Read-only status for a fresh source database or a previously completed deployment. */
export function inspectContentDeploymentSync(store: ContentOperationsStore): ContentDeploymentInspection {
    const { plan, keys, parentKeys, controlledParentKeys } = reviewedPlan(store)
    const revision = store.revision(), stateCount = (store.db.prepare("SELECT count(*) AS n FROM content_operations_state").get() as { n: number }).n
    const marker = readMarker(store)
    const reasons: string[] = []
    const initialMarker = store.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_operations_initialization'").get()
        ? store.db.prepare("SELECT plan_digest,catalog_digest FROM content_operations_initialization WHERE id=1").get() as
            { plan_digest: string; catalog_digest: string } | undefined : undefined
    const phase: ContentDeploymentCounts["phase"] = marker ? "applied" : stateCount === 0 && revision === 0 && !initialMarker ? "initial" : "partial"
    const boxExchange = inspectBoxExchangeSupplementSync(store, plan.digest, READINESS_SHA256,
        plan.stage3.evidenceDigest, phase === "applied")
    let presentControlStates = 0, presentParentControls = 0
    if (phase === "applied") {
        if (marker?.plan_digest !== plan.digest || marker.catalog_digest !== store.digest)
            reasons.push("部署标记与当前审阅计划或目录不一致")
        if (initialMarker?.plan_digest !== plan.julyPlanDigest || initialMarker.catalog_digest !== store.digest)
            reasons.push("固定7月初始化身份不一致")
        for (const key of keys) {
            const state = store.state(key)
            if (currentIdentity(store, key, state)) {
                presentControlStates++
                if (controlledParentKeys.has(key)) presentParentControls++
            }
        }
        if (presentControlStates !== plan.expected.totalControlStates) reasons.push("已审阅内容状态缺失、损坏或定义身份失配")
        if (presentParentControls !== plan.expected.parentControls) reasons.push("已审阅父项状态缺失、损坏或定义身份失配")
        if (!boxExchange.ready) reasons.push(...boxExchange.reasons)
    } else if (phase === "initial") reasons.push("内容运营尚未迁移；空白基线可应用已审阅计划")
    else reasons.push("现有运营状态不是空白基线；禁止覆盖或重放")
    const counts: ContentDeploymentCounts = {
        phase, catalogParents: parentKeys.length, targetParentControls: plan.expected.parentControls,
        unsupportedParents: plan.expected.unsupportedParents.length,
        unsupportedParentKeys: [...plan.expected.unsupportedParents], presentParentControls,
        unsupportedParentReasons: Object.fromEntries(plan.expected.unsupportedParents.map(key =>
            [key, "原生任务或兑换成员范围为空，未通过参与动作核查，暂不接管"])),
        missingParentControls: plan.expected.parentControls - presentParentControls,
        presentControlStates: phase === "initial" ? 0 : presentControlStates,
        expectedControlStates: plan.expected.totalControlStates, currentRevision: revision,
        boxExchangeTarget: boxExchange.target, boxExchangeReady: boxExchange.ready,
    }
    return { ready: phase === "applied" && reasons.length === 0,
        canApply: phase === "initial" && reasons.length === 1 && boxExchange.canApply
            || phase === "applied" && boxExchange.canApply && reasons.length === boxExchange.reasons.length,
        reasons, counts }
}

/** Called only inside the authenticated EXCLUSIVE maintenance transaction shared with clock migration. */
export function applyContentDeploymentMaintenanceSync(store: ContentOperationsStore, context: DeploymentMaintenanceContext,
    options: { nowMs: number }): ContentDeploymentApplyResult {
    assertDeploymentMaintenanceContextSync(store.db, context)
    if (!Number.isSafeInteger(options.nowMs) || options.nowMs < 0) throw new ContentOperationError("内容部署时间无效", 409)
    const before = inspectContentDeploymentSync(store)
    if (!before.ready && !before.canApply) throw new ContentOperationError(before.reasons.join("；"), 409)
    const { plan } = reviewedPlan(store)
    if (before.counts.phase === "applied") {
        if (!before.ready) applyBoxExchangeSupplementSync(store, context, plan.digest, READINESS_SHA256,
            plan.stage3.evidenceDigest, options.nowMs)
        const after = inspectContentDeploymentSync(store)
        if (!after.ready) throw new ContentOperationError("奖励箱入口补核后内容状态核验失败", 409)
        return { applied: !before.ready, revision: store.revision(), planDigest: plan.digest, counts: after.counts }
    }
    const july = applyJulyContentPlanOfflineSync(store, { expectedRevision: store.revision(), expectedCatalogDigest: store.digest,
        nowMs: options.nowMs, maintenanceContext: context })
    if (!july.applied || july.controls !== plan.expected.julyControls) throw new ContentOperationError("固定7月初始化未完成", 409)
    const reviewed = completeExistingHistoryReviewsOfflineSync(store, plan.stage2,
        { expectedRevision: store.revision(), nowMs: options.nowMs, maintenanceContext: context })
    if (reviewed.reviewedKeys.length !== plan.expected.reviewedExisting) throw new ContentOperationError("既有历史内容补核数量异常", 409)
    const prepared = prepareReviewedHistoryOfflineSync(store, plan.stage3,
        { expectedRevision: store.revision(), nowMs: options.nowMs, maintenanceContext: context })
    if (prepared.preparedKeys.length !== plan.expected.historicalCandidates || prepared.preservedKeys.length)
        throw new ContentOperationError("历史内容准备数量异常", 409)
    // Validate all reviewed keys and every UI parent before declaring the deployment complete.
    const { keys, controlledParentKeys } = reviewedPlan(store)
    let checkedParentControls = 0
    for (const key of keys) {
        if (!currentIdentity(store, key, store.state(key)))
            throw new ContentOperationError(`部署后内容状态或定义身份失配：${key}`, 409)
        if (controlledParentKeys.has(key)) checkedParentControls++
    }
    if (checkedParentControls !== plan.expected.parentControls)
        throw new ContentOperationError("部署后父项状态或定义身份失配", 409)
    store.db.exec(`CREATE TABLE ${markerTable} (
        id INTEGER PRIMARY KEY CHECK(id=1), plan_digest TEXT NOT NULL, catalog_digest TEXT NOT NULL, applied_at_ms INTEGER NOT NULL
    )`)
    store.db.prepare(`INSERT INTO ${markerTable}(id,plan_digest,catalog_digest,applied_at_ms) VALUES(1,?,?,?)`)
        .run(plan.digest, store.digest, options.nowMs)
    applyBoxExchangeSupplementSync(store, context, plan.digest, READINESS_SHA256,
        plan.stage3.evidenceDigest, options.nowMs)
    const after = inspectContentDeploymentSync(store)
    if (!after.ready || after.counts.phase !== "applied") throw new ContentOperationError("部署后内容状态核验失败", 409)
    return { applied: true, revision: store.revision(), planDigest: plan.digest, counts: after.counts }
}
