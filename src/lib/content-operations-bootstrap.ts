import data from "../../assets/content_july_controls.json"
import { createHash } from "node:crypto"
import { ContentOperationsStore, ContentOperationError, type ContentActionOverride, type ContentControl } from "./content-operations-store"
import { assertTimeCutoverOfflineDatabaseSync, type OfflineDatabaseGuard } from "./time-cutover-rehearsal"
import { isFixedJulyCandidate } from "./content-july-reference"

export const julyContentPlan = data

export const LEGACY_JULY_PLAN_DIGEST = "3cffb5dea4436042b3487e2a0cb37a7ff324c1c826698f9da6bb04a6b5eb5446"
const legacyCatalogDigest = "93ab67365cb9959c9ab737f74574a21dc460c300743ad3c1537e6512670aa765"
const planHash = (plan: typeof julyContentPlan) => createHash("sha256").update(JSON.stringify(plan)).digest("hex")
function actionInput(value: ContentActionOverride): ContentActionOverride {
    const { catalogDigest: _catalog, contentDigest: _content, ...input } = value
    return input
}
function stable(value: unknown): string {
    if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`
    if (value !== null && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`).join(",")}}`
    return JSON.stringify(value)
}

/** Upgrade only the recognized July v1 seed, using its immutable initialization audit as the merge base.
 * Operator action changes and publication choices win. No player table or earned-rights row is rewritten.
 * The caller must create a SQLite backup before invoking this explicitly offline operation. */
export function upgradeJulyContentPlanOfflineSync(store: ContentOperationsStore, options: {
    expectedRevision: number; expectedCatalogDigest: string; nowMs: number; offlineGuard?: OfflineDatabaseGuard
}): { applied: boolean; revision: number; planDigest: string; updatedKeys: string[]; preservedOperatorKeys: string[] } {
    assertTimeCutoverOfflineDatabaseSync(store.db, options.offlineGuard)
    if (store.digest !== options.expectedCatalogDigest) throw new ContentOperationError("内容目录已变化", 409)
    if (!Number.isSafeInteger(options.nowMs) || options.nowMs < 0 || store.revision() !== options.expectedRevision)
        throw new ContentOperationError("升级时间或状态版本无效", 409)
    const plan = julyContentPlan, digest = planHash(plan)
    const marker = store.db.prepare("SELECT plan_digest,catalog_digest FROM content_operations_initialization WHERE id=1").get() as
        { plan_digest: string; catalog_digest: string } | undefined
    if (marker?.plan_digest === digest && marker.catalog_digest === store.digest) {
        if (plan.controls.some(control => { const state = store.state(control.key); return !state || !!state.integrityError }))
            throw new ContentOperationError("已升级初始化状态缺失或损坏，不能以重放覆盖运营决定", 409)
        return { applied: false, revision: store.revision(), planDigest: digest, updatedKeys: [], preservedOperatorKeys: [] }
    }
    if (marker?.plan_digest !== LEGACY_JULY_PLAN_DIGEST || marker.catalog_digest !== legacyCatalogDigest)
        throw new ContentOperationError("不是已识别的旧7月初始化；禁止覆盖未知运营基线", 409)
    const initial = store.db.prepare("SELECT content_key,before_json,after_json FROM content_operations_audit WHERE reason IN (?,?) ORDER BY revision")
        .all("固定2025-07-20初始清单：permanent", "固定2025-07-20初始清单：retained_rights") as Array<{ content_key: string; before_json: string | null; after_json: string }>
    if (initial.length !== 1075 || new Set(initial.map(row => row.content_key)).size !== 1075 || initial.some(row => row.before_json !== null))
        throw new ContentOperationError("旧初始化审计不完整，不能安全三方合并", 409)
    const baseline = new Map(initial.map(row => [row.content_key, JSON.parse(row.after_json) as ContentControl]))
    for (const key of baseline.keys()) if (!store.state(key)) throw new ContentOperationError(`旧运营状态缺失：${key}`, 409)
    const updatedKeys: string[] = [], preservedOperatorKeys: string[] = []
    return store.db.transaction(() => {
        if (store.revision() !== options.expectedRevision) throw new ContentOperationError("状态版本已变化，请重新核对", 409)
        for (const control of plan.controls) {
            const row = store.rows.get(control.key)
            if (!row || row.definitionDigest !== control.expectedDefinitionDigest || row.serverDefinitionDigest !== control.expectedServerDefinitionDigest
                || (control.group === "permanent" && !isFixedJulyCandidate(row)))
                throw new ContentOperationError(`升级定义或固定日期不匹配：${control.key}`, 409)
            const current = store.state(control.key), base = baseline.get(control.key)
            if (current && !base) { preservedOperatorKeys.push(control.key); continue }
            if (current?.integrityError) throw new ContentOperationError(`运营状态损坏：${control.key}`, 409)
            if (current && (current.controlled === false || !current.actionOverrides || !base?.actionOverrides)) {
                preservedOperatorKeys.push(control.key); continue
            }
            // An explicit per-action close also wins over newly added participation.
            const closedByOperator = !!current && Object.entries(current.actionOverrides ?? {}).some(([action, value]) =>
                value?.enabled === false && base?.actionOverrides?.[action as keyof typeof base.actionOverrides]?.enabled === true)
            const patch: Record<string, ContentActionOverride> = {}
            for (const [action, requested] of Object.entries(control.actionOverrides)) {
                const desired = requested as ContentActionOverride
                const old = base?.actionOverrides?.[action as keyof typeof base.actionOverrides]
                const existing = current?.actionOverrides?.[action as keyof typeof current.actionOverrides]
                if (closedByOperator || (existing && (!old || stable(actionInput(existing)) !== stable(actionInput(old))))) {
                    if (!preservedOperatorKeys.includes(control.key)) preservedOperatorKeys.push(control.key)
                    continue
                }
                if (!existing || stable(actionInput(existing)) !== stable(desired)) patch[action] = desired
            }
            if (!Object.keys(patch).length) continue
            store.update(control.key, { expectedRevision: store.revision(), catalogDigest: store.digest,
                reason: "固定7月完整动作升级；保留运营决定和玩家进度", actionOverrides: patch }, options.nowMs)
            updatedKeys.push(control.key)
        }
        store.db.prepare("UPDATE content_operations_initialization SET plan_digest=?,catalog_digest=?,applied_at_ms=? WHERE id=1")
            .run(digest, store.digest, options.nowMs)
        return { applied: true, revision: store.revision(), planDigest: digest, updatedKeys, preservedOperatorKeys }
    }).immediate()
}

/** Deliberately offline-only. Startup never replays this plan or resets later operator choices. */
export function applyJulyContentPlanOfflineSync(store: ContentOperationsStore, options: {
    expectedRevision: number
    expectedCatalogDigest: string
    nowMs: number
    offlineGuard?: OfflineDatabaseGuard
    plan?: typeof julyContentPlan
}): { applied: boolean; revision: number; planDigest: string; controls: number } {
    assertTimeCutoverOfflineDatabaseSync(store.db, options.offlineGuard)
    const plan = options.plan ?? julyContentPlan
    if (plan.schemaVersion !== 1 || plan.referenceDate !== "2025-07-20" || plan.timeZone !== "UTC+08:00"
        || plan.referenceStartMs !== 1752940800000 || plan.referenceEndMsExclusive !== 1753027200000)
        throw new ContentOperationError("固定7月目标清单身份无效", 409)
    if (store.digest !== options.expectedCatalogDigest) throw new ContentOperationError("内容目录已变化，初始清单需复核", 409)
    const planDigest = createHash("sha256").update(JSON.stringify(plan)).digest("hex")
    const markerTable = "content_operations_initialization"
    const exists = store.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(markerTable)
    if (exists) {
        const marker = store.db.prepare(`SELECT plan_digest,catalog_digest FROM ${markerTable} WHERE id=1`).get() as { plan_digest: string; catalog_digest: string } | undefined
        if (marker) {
            if (marker.plan_digest !== planDigest || marker.catalog_digest !== store.digest)
                throw new ContentOperationError("已有不同初始化清单，禁止重放或覆盖运营决定", 409)
            return { applied: false, revision: store.revision(), planDigest, controls: plan.controls.length }
        }
    }
    if (new Set(plan.controls.map(row => row.key)).size !== plan.controls.length)
        throw new ContentOperationError("初始清单包含重复内容", 409)
    for (const control of plan.controls) {
        const row = store.rows.get(control.key)
        if (!row || row.definitionDigest !== control.expectedDefinitionDigest
            || row.serverDefinitionDigest !== control.expectedServerDefinitionDigest)
            throw new ContentOperationError(`初始清单定义不匹配：${control.key}`, 409)
        if (control.group !== "permanent" && control.group !== "retained_rights")
            throw new ContentOperationError("未知的初始内容组", 409)
        if (control.group === "permanent" && (row.personalWindow
            || (row.originalStartMs !== null && row.originalStartMs > plan.referenceStartMs)
            || (row.originalEndMs !== null && row.originalEndMs < plan.referenceEndMsExclusive - 1000)))
            throw new ContentOperationError(`不属于固定7月全天常驻目标：${control.key}`, 409)
        const actions: Partial<Record<string, { enabled?: boolean; endsAtMs?: number | null }>> = control.actionOverrides
        if (control.group === "retained_rights" && (actions.enter?.enabled || actions.visible?.enabled))
            throw new ContentOperationError("历史权益不能作为新参与入口", 409)
        if (Object.values(actions).some(action => action?.enabled && action.endsAtMs !== null))
            throw new ContentOperationError("常驻和既有权益不应由旧日期再次截止", 409)
        if (store.state(control.key)) throw new ContentOperationError(`已有运营决定，禁止初始化覆盖：${control.key}`, 409)
    }
    return store.db.transaction(() => {
        if (store.revision() !== options.expectedRevision) throw new ContentOperationError("状态版本已变化，请重新核对", 409)
        store.db.exec(`CREATE TABLE IF NOT EXISTS ${markerTable} (
            id INTEGER PRIMARY KEY CHECK(id=1), plan_digest TEXT NOT NULL, catalog_digest TEXT NOT NULL, applied_at_ms INTEGER NOT NULL
        )`)
        for (const control of plan.controls) store.update(control.key, {
            expectedRevision: store.revision(), catalogDigest: store.digest,
            reason: `固定2025-07-20初始清单：${control.group}`,
            actionOverrides: control.actionOverrides,
        }, options.nowMs)
        store.db.prepare(`INSERT INTO ${markerTable}(id,plan_digest,catalog_digest,applied_at_ms) VALUES(1,?,?,?)`)
            .run(planDigest, store.digest, options.nowMs)
        return { applied: true, revision: store.revision(), planDigest, controls: plan.controls.length }
    }).immediate()
}
