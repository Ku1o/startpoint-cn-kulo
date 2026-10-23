import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import path from "node:path"
import type { ContentOperationsStore, ContentControl, ContentActionOverride } from "./content-operations-store"
import { ContentOperationError } from "./content-operations-store"
import { getContentBoxAssociations, isContentBoxAssociationIndexAvailable } from "./content-box-associations"
import { getContentHistoryReadiness } from "./content-history-readiness"
import { assertDeploymentMaintenanceContextSync, type DeploymentMaintenanceContext } from "./deployment-maintenance-guard"

const root = path.resolve(__dirname, "../..")
const assetPath = path.join(root, "assets/content_box_exchange_review.json")
const indexPath = path.join(root, "assets/content_box_associations.json")
const markerTable = "content_box_exchange_deployment"
const REVIEW_DIGEST = "43ffc8ed4ca8d2366542df284be45b6b6829ed9387fe88b283bd992f48fbabf6"
const hash = (value: string) => createHash("sha256").update(value).digest("hex")

interface ReviewRow {
    parentKey: string; boxKey: string; origin: "stage3" | "july"
    parentNativeSha256: string; boxNativeSha256: string
    serverBoxDigest: string; serverRewardsDigest: string
    originalExchangeEndMs: number | null
}
interface ReviewAsset {
    schemaVersion: 1; semantics: string; catalogDigest: string; associationDigest: string
    reviewedPlanDigest: string; readinessSha256: string; stage3EvidenceDigest: string; rows: ReviewRow[]; digest: string
}
interface NativeAssociation {
    parentKey: string; boxKey: string
    parent: { rawSha256: string }; box: { rawSha256: string }
    serverBoxDigest: string; serverRewardsDigest: string
}
interface NativeIndex { associationsDigest: string; associations: NativeAssociation[] }
interface AuditRow { revision: number; reason: string; before_json: string | null; after_json: string }
export interface BoxExchangeSupplementInspection {
    ready: boolean; canApply: boolean; target: number; reasons: string[]; digest: string
}

function reviewAsset(store: ContentOperationsStore, deploymentPlanDigest: string, readinessSha256: string,
    stage3EvidenceDigest: string): ReviewAsset {
    const asset = JSON.parse(readFileSync(assetPath, "utf8")) as ReviewAsset
    const { digest, ...body } = asset
    const native = JSON.parse(readFileSync(indexPath, "utf8")) as NativeIndex
    const associations = getContentBoxAssociations()
    if (asset.schemaVersion !== 1 || digest !== REVIEW_DIGEST || hash(JSON.stringify(body)) !== digest
        || asset.semantics !== "parent exchange is native reward-box page window, not an independent event-item shop product permission"
        || asset.catalogDigest !== store.digest || asset.reviewedPlanDigest !== deploymentPlanDigest
        || asset.readinessSha256 !== readinessSha256 || asset.stage3EvidenceDigest !== stage3EvidenceDigest
        || asset.associationDigest !== native.associationsDigest
        || !isContentBoxAssociationIndexAvailable() || asset.rows.length !== 48 || native.associations.length !== 48
        || associations.length !== 48 || asset.rows.filter(row => row.origin === "stage3").length !== 47
        || asset.rows.filter(row => row.origin === "july").length !== 1)
        throw new ContentOperationError("奖励箱入口补核清单或来源身份不匹配", 409)
    const linked = new Map(associations.map(row => [row.parentKey, row]))
    const sources = new Map(native.associations.map(row => [row.parentKey, row]))
    const seen = new Set<string>()
    for (const row of asset.rows) {
        const link = linked.get(row.parentKey), source = sources.get(row.parentKey)
        const parent = store.rows.get(row.parentKey), box = store.rows.get(row.boxKey)
        if (seen.has(row.parentKey) || !link?.relationshipMatches || link.boxKey !== row.boxKey
            || !source || source.boxKey !== row.boxKey || row.parentNativeSha256 !== source.parent.rawSha256
            || row.boxNativeSha256 !== source.box.rawSha256 || row.serverBoxDigest !== source.serverBoxDigest
            || row.serverRewardsDigest !== source.serverRewardsDigest || !parent || !box
            || parent.originalExchangeEndMs !== row.originalExchangeEndMs
            || box.originalEndMs !== row.originalExchangeEndMs
            || !["raid_event", "world_story_event"].includes(parent.type) || box.type !== "box_gacha"
            || store.shopSaleParents.has(row.parentKey)
            || !store.capabilities(parent).includes("exchange")
            || !store.clientCapabilities?.(parent).includes("exchange")
            || !["visible", "enter", "claim"].every(action => store.capabilities(box).includes(action as "visible" | "enter" | "claim"))
            || getContentHistoryReadiness(row.parentKey, ["exchange"]).status !== "not_applicable"
            || getContentHistoryReadiness(row.boxKey, ["claim"]).status !== "passed")
            throw new ContentOperationError(`奖励箱入口原生关联或动作核验失败：${row.parentKey}`, 409)
        seen.add(row.parentKey)
    }
    if (seen.size !== linked.size || asset.rows.filter(row => row.origin === "july")[0]?.parentKey !== "raid_event:7")
        throw new ContentOperationError("奖励箱入口补核范围不完整", 409)
    return asset
}

function validEnabled(store: ContentOperationsStore, key: string, state: ContentControl, action: "visible" | "enter" | "claim") {
    const review = state.actionOverrides?.[action]
    return !!review && review.enabled === true && ["verified", "current_baseline"].includes(review.readiness)
        && !!review.evidence.trim() && review.catalogDigest === store.digest
        && review.contentDigest === store.contentDigests.get(key) && review.endsAtMs === null
}
function scopeReady(store: ContentOperationsStore, key: string, review: ContentActionOverride | undefined) {
    if (!review) return false
    if (store.questMembers.get(key)?.size && review.questKeys !== null
        && (!Array.isArray(review.questKeys) || review.questKeys.length === 0)) return false
    if (store.missionMembers.get(key)?.size && review.missionKeys !== null
        && (!Array.isArray(review.missionKeys) || review.missionKeys.length === 0)) return false
    return true
}
function originalAudit(store: ContentOperationsStore, key: string, origin: ReviewRow["origin"], raw: string): boolean {
    const audit = store.db.prepare(`SELECT revision,reason,before_json,after_json FROM content_operations_audit
        WHERE content_key=? ORDER BY revision`).all(key) as AuditRow[]
    const reasons = origin === "stage3"
        ? ["完成历史内容核查，默认关闭并保留原进度", "历史内容默认关闭", "完成历史内容核查，默认关闭并保留原进度"]
        : ["固定2025-07-20初始清单：permanent"]
    if (audit.length !== reasons.length || audit[0]?.before_json !== null
        || audit.at(-1)?.after_json !== raw) return false
    try {
        return audit.every((entry, index) => entry.reason === reasons[index]
            && entry.revision === JSON.parse(entry.after_json).revision
            && (index === 0 || entry.before_json === audit[index - 1].after_json))
    } catch { return false }
}
function originProblem(store: ContentOperationsStore, row: ReviewRow, stage3EvidenceDigest: string): string | null {
    const parent = store.state(row.parentKey), box = store.state(row.boxKey)
    if (!parent || !box || parent.integrityError || box.integrityError
        || parent.controlled !== true || box.controlled !== true
        || parent.catalogDigest !== store.digest || box.catalogDigest !== store.digest
        || parent.contentDigest !== store.contentDigests.get(row.parentKey)
        || box.contentDigest !== store.contentDigests.get(row.boxKey)) return "父活动或箱池状态身份无效"
    const raw = store.db.prepare("SELECT value_json FROM content_operations_state WHERE content_key=?")
        .get(row.parentKey) as { value_json: string } | undefined
    const boxRaw = store.db.prepare("SELECT value_json FROM content_operations_state WHERE content_key=?")
        .get(row.boxKey) as { value_json: string } | undefined
    if (!raw || !boxRaw || !originalAudit(store, row.parentKey, row.origin, raw.value_json)
        || !originalAudit(store, row.boxKey, row.origin, boxRaw.value_json))
        return "初始审计链已变化或存在后续运营编辑"
    if (!validEnabled(store, row.parentKey, parent, "visible")
        || !validEnabled(store, row.parentKey, parent, "enter")
        || !scopeReady(store, row.parentKey, parent.actionOverrides?.enter)
        || !validEnabled(store, row.boxKey, box, "visible")
        || !validEnabled(store, row.boxKey, box, "enter")
        || !validEnabled(store, row.boxKey, box, "claim")) return "参与、箱池领取或精确成员范围尚未核查"
    if (row.origin === "stage3") {
        const review = parent.actionOverrides?.exchange
        if (parent.published !== false || box.published !== false || !review
            || review.enabled !== false || review.readiness !== "verified" || review.endsAtMs !== null
            || review.evidence !== `历史核查 ${stage3EvidenceDigest}`
            || review.catalogDigest !== store.digest || review.contentDigest !== store.contentDigests.get(row.parentKey))
            return "父活动兑换动作并非原始未审核占位状态"
    } else if (parent.published === false || box.published === false || parent.actionOverrides?.exchange !== undefined) {
        return "固定日既有活动的入口或兑换审核已被改动"
    }
    return null
}

function marker(store: ContentOperationsStore): { review_digest: string; catalog_digest: string } | null {
    if (!store.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(markerTable)) return null
    const saved = store.db.prepare(`SELECT review_digest,catalog_digest FROM ${markerTable} WHERE id=1`).get() as
        { review_digest: string; catalog_digest: string } | undefined
    if (!saved) throw new ContentOperationError("奖励箱入口补核标记缺失", 409)
    return saved
}

export function inspectBoxExchangeSupplementSync(store: ContentOperationsStore, deploymentPlanDigest: string,
    readinessSha256: string, stage3EvidenceDigest: string, initialized: boolean): BoxExchangeSupplementInspection {
    const asset = reviewAsset(store, deploymentPlanDigest, readinessSha256, stage3EvidenceDigest)
    const saved = marker(store)
    if (saved) {
        const reasons = saved.review_digest === asset.digest && saved.catalog_digest === store.digest
            ? asset.rows.flatMap(row => {
                const state = store.state(row.parentKey), review = state?.actionOverrides?.exchange
                return !state || state.integrityError || state.controlled !== true || !review
                    || review.enabled && !["verified", "current_baseline"].includes(review.readiness)
                    || !review.evidence.trim()
                    || review.catalogDigest !== store.digest || review.contentDigest !== store.contentDigests.get(row.parentKey)
                    ? [`${row.parentKey}：奖励箱页兑换动作缺失或身份失效`] : []
            }) : ["奖励箱入口补核标记身份不匹配"]
        return { ready: reasons.length === 0, canApply: false, target: asset.rows.length, reasons, digest: asset.digest }
    }
    if (!initialized) return { ready: false, canApply: true, target: asset.rows.length,
        reasons: ["奖励箱入口补核将在内容初始化后执行"], digest: asset.digest }
    const reasons = asset.rows.flatMap(row => {
        const problem = originProblem(store, row, stage3EvidenceDigest)
        return problem ? [`${row.parentKey}：${problem}`] : []
    })
    return { ready: false, canApply: reasons.length === 0, target: asset.rows.length,
        reasons: reasons.length ? reasons : ["48 个原生奖励箱入口待完成受控补核"], digest: asset.digest }
}

/** Only inside the same exclusive content/clock maintenance transaction. */
export function applyBoxExchangeSupplementSync(store: ContentOperationsStore, context: DeploymentMaintenanceContext,
    deploymentPlanDigest: string, readinessSha256: string, stage3EvidenceDigest: string,
    nowMs: number): { applied: boolean; count: number; digest: string } {
    assertDeploymentMaintenanceContextSync(store.db, context)
    const asset = reviewAsset(store, deploymentPlanDigest, readinessSha256, stage3EvidenceDigest)
    const previous = marker(store)
    if (previous) {
        if (previous.review_digest !== asset.digest || previous.catalog_digest !== store.digest)
            throw new ContentOperationError("奖励箱入口补核标记身份不匹配", 409)
        return { applied: false, count: asset.rows.length, digest: asset.digest }
    }
    const problems = asset.rows.flatMap(row => {
        const problem = originProblem(store, row, stage3EvidenceDigest)
        return problem ? [`${row.parentKey}：${problem}`] : []
    })
    if (problems.length) throw new ContentOperationError(problems.join("；"), 409)
    for (const row of asset.rows) {
        assertDeploymentMaintenanceContextSync(store.db, context)
        store.update(row.parentKey, { expectedRevision: store.revision(), catalogDigest: store.digest,
            reason: "核查原生奖励箱页兑换窗口；不新增活动商店商品资格",
            actionOverrides: { exchange: { enabled: true, endsAtMs: null, readiness: "verified",
                evidence: `原生奖励箱页窗口核查 ${asset.digest}: ${row.parentKey} -> ${row.boxKey}；仅用于已核验箱池入口` } } }, nowMs)
        if (store.state(row.parentKey)?.actionOverrides?.exchange?.enabled !== true)
            throw new ContentOperationError(`奖励箱入口审核写入失败：${row.parentKey}`, 409)
    }
    store.db.exec(`CREATE TABLE ${markerTable} (
        id INTEGER PRIMARY KEY CHECK(id=1), review_digest TEXT NOT NULL, catalog_digest TEXT NOT NULL, applied_at_ms INTEGER NOT NULL
    )`)
    store.db.prepare(`INSERT INTO ${markerTable}(id,review_digest,catalog_digest,applied_at_ms) VALUES(1,?,?,?)`)
        .run(asset.digest, store.digest, nowMs)
    return { applied: true, count: asset.rows.length, digest: asset.digest }
}
