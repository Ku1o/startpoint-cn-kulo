import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import path from "node:path"
import type { Database } from "better-sqlite3"
import { ContentOperationError, type ContentControl, type ContentOperationsStore } from "./content-operations-store"
import { assertDeploymentMaintenanceContextSync, getDeploymentDatabaseFingerprintSync,
    type DeploymentMaintenanceContext } from "./deployment-maintenance-guard"

export const CONTENT_RELEASE_ID = "halloween-300097-v1"
export const CONTENT_RELEASE_PARENT = "advent_event:300097"
export const CONTENT_RELEASE_GACHA = "gacha:990005"
export const CONTENT_RELEASE_PRODUCTS = [9730001, 9730007, 9730008, 9730010, 9730011,
    ...Array.from({ length: 26 }, (_, index) => 9730101 + index)].map(id => `event_item_shop:${id}`)
export const CONTENT_RELEASE_QUESTS = [7, 8].flatMap(category =>
    Array.from({ length: 5 }, (_, index) => `${category}:30009700${index + 1}`))
const scope = [CONTENT_RELEASE_PARENT, ...CONTENT_RELEASE_PRODUCTS, CONTENT_RELEASE_GACHA]
const marker = "content_release_supplements"
const baselineTables = ["content_operations_initialization", "content_operations_deployment", "content_box_exchange_deployment"]
const mutableTables = new Set(["content_operations_state", "content_operations_meta", "content_operations_audit", marker])
const provenance = new Set(["definitionEvidence", "exactDefinitionEvidence", "currentParentDefinitionEvidence",
    "serverDefinitionDigest", "legacyCarrierReview"])
const actions = ["visible", "enter", "claim", "exchange"] as const
const canonical = (value: unknown): string => {
    if (typeof value === "bigint") return JSON.stringify({ integer: value.toString() })
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`
    if (value && typeof value === "object") return `{${Object.keys(value).sort().map(key =>
        `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`).join(",")}}`
    return JSON.stringify(value)
}
const sha = (value: string): string => createHash("sha256").update(value).digest("hex")
const hash = (value: unknown): string => sha(canonical(value))
const validHash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value)
function fail(message: string): never { throw new ContentOperationError(message, 409) }
const quote = (value: string): string => `"${value.replace(/"/g, '""')}"`
const rawStates = (db: Database): Array<{ key: string; raw: string }> => db.prepare(
    "SELECT content_key AS key,value_json AS raw FROM content_operations_state ORDER BY content_key").all() as Array<{ key: string; raw: string }>
const businessRow = (value: object) => Object.fromEntries(Object.entries(value).filter(([key]) => !provenance.has(key)))

/** Captures come from the same pinned original-effective-accessor engine on both
 * source versions. Hash-only declarations are not business-equivalence evidence. */
export interface ReleaseDefinitionCapture {
    kind: "pinned-original-store-capture"
    catalogDigest: string
    inputReceipt?: unknown
    keys: Record<string, {
        key: string; contentDigest: string; runtimeDigest: string; runtimeMatches: boolean
        businessRow: Record<string, unknown>; dependencies: Record<string, unknown>
        captureEngineSha256: string; operatorCapabilities: string[]; clientCapabilities: string[]
        questMembers: string[]; missionMembers: string[]
        approvedDeltaValues?: { actualGacha: unknown }
    }>
}
export interface ReleaseIdentityReview { before: ReleaseDefinitionCapture; current: ReleaseDefinitionCapture }
export interface ReleaseCaptureSession {
    readonly previousSourceRoot: string; readonly currentSourceRoot: string
    capture(keys: string[]): ReleaseIdentityReview
}
function captureActualIdentities(session: ReleaseCaptureSession | undefined, keys: string[]): ReleaseIdentityReview {
    const producer = require(path.resolve(__dirname, "../../tools/content-release-capture.cjs")) as {
        isReleaseCaptureSession(value: unknown): boolean; PRODUCER_SHA256: string
    }
    if (!session || !producer.isReleaseCaptureSession(session)) fail("身份复核必须由固定实际访问器捕获入口生成，不能接受声明JSON")
    const result = session.capture(keys)
    for (const view of [result.before, result.current]) {
        if (!view.inputReceipt || keys.some(key => view.keys[key]?.captureEngineSha256 !== producer.PRODUCER_SHA256))
            fail("实际捕获器或读取输入回执缺失")
    }
    return result
}
export interface ContentReleaseSource { assetVersion: string; manifestSha256: string }
let requiredLegacyKeys: readonly string[] | undefined
/** Read the original reviewed key set without invoking its old initializer or
 * requiring the new catalog digest to equal the historical export digest. */
export function readContentDeploymentRequiredKeysSync(): readonly string[] {
    if (requiredLegacyKeys) return requiredLegacyKeys
    const root = path.resolve(__dirname, "../.."), read = (name: string) => JSON.parse(readFileSync(path.join(root, "assets", name), "utf8"))
    const plan = read("content_deployment_review_plan.json"), july = read("content_july_controls.json")
    const { digest, ...body } = plan
    if (digest !== "eb559d9058244155b680deb8fd8f557a19c2b22ee5c6f82dd0e73788f91b52c8"
        || sha(JSON.stringify(body)) !== digest || sha(JSON.stringify(july)) !== plan.julyPlanDigest
        || plan.expected.totalControlStates !== 9599 || july.controls.length !== 1113 || plan.stage3.candidates.length !== 8486)
        fail("原部署必需项目审阅身份不匹配")
    const keys = [...july.controls, ...plan.stage3.candidates].map((row: { key: string }) => row.key).sort()
    if (keys.length !== 9599 || new Set(keys).size !== keys.length || keys.some(key => typeof key !== "string")) fail("原部署必需项目集合无效")
    requiredLegacyKeys = Object.freeze(keys)
    return requiredLegacyKeys
}
/** Catalog.source describes its original master export, not the terminal CDN. */
export function readContentReleaseSourceSync(): ContentReleaseSource {
    const bytes = readFileSync(path.resolve(__dirname, "../../assets/asset-patch/manifest.json"))
    return { assetVersion: JSON.parse(bytes.toString("utf8")).cdn_version, manifestSha256: createHash("sha256").update(bytes).digest("hex") }
}
export interface ContentReleasePlan {
    schemaVersion: 1; releaseId: typeof CONTENT_RELEASE_ID; digest: string; evidenceDigest: string
    source: ContentReleaseSource; catalogDigest: string
    expectedRevision: number; databaseFingerprint: string; operationsSha256: string
    protectedDataSha256: string; baselineMarkersSha256: string; auditCount: number; auditSha256: string
    existingKeys: string[]; createKeys: string[]; preservedKeys: string[]
    requiredLegacyKeys: readonly string[]
    preservedControls: Array<{ key: string; state: ContentControl; effectiveFlags: Record<string, boolean | null> }>
    identityReview?: ReleaseIdentityReview
    bindings: Array<{ key: string; previousRawSha256: string }>
    products: string[]; questKeys: string[]; gachaKeys: string[]
}

function baselineFingerprint(db: Database): string {
    return hash(baselineTables.map(table => {
        if (!db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(table)) fail(`缺少原迁移标记：${table}`)
        const rows = db.prepare(`SELECT * FROM ${quote(table)} ORDER BY id`).all()
        if (rows.length !== 1) fail(`原迁移标记数量异常：${table}`)
        return [table, rows]
    }))
}
/** Stream non-operations tables, including clock, inventory, stock and progress.
 * Only the one receipt table is an allowed schema addition. */
function protectedFingerprint(db: Database): string {
    const schema = db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").all() as
        Array<{ type: string; name: string; tbl_name: string }>
    const kept = schema.filter(row => !mutableTables.has(row.tbl_name))
    const result = createHash("sha256").update(canonical(kept))
    for (const pragma of ["user_version", "application_id", "encoding"]) result.update(canonical(db.pragma(pragma)))
    for (const row of kept) if (row.type === "table") {
        result.update(canonical(row.name))
        for (const values of db.prepare(`SELECT * FROM ${quote(row.name)}`).raw().safeIntegers().iterate())
            result.update(canonical(values)).update("\n")
    }
    return result.digest("hex")
}
function auditFingerprint(db: Database, count: number): string {
    const result = createHash("sha256"); let seen = 0
    for (const row of db.prepare("SELECT * FROM content_operations_audit ORDER BY revision LIMIT ?").raw().safeIntegers().iterate(count)) {
        result.update(canonical(row)).update("\n"); seen++
    }
    if (seen !== count) fail("原运营审计缺失")
    return result.digest("hex")
}
function identityCurrent(store: ContentOperationsStore, key: string, state: ContentControl | null): boolean {
    return !!state && !state.integrityError && state.catalogDigest === store.digest
        && state.contentDigest === store.contentDigests.get(key)
        && store.runtimeDefinitions.get(key)?.matchesCatalog === true
        && Object.values(state.actionOverrides ?? {}).every(value => value?.catalogDigest === store.digest
            && value.contentDigest === store.contentDigests.get(key))
}
function validateScope(store: ContentOperationsStore, source: ContentReleaseSource): void {
    if (source.assetVersion !== "1.4.350" || !validHash(source.manifestSha256))
        fail("本补充计划只接受已核对的350资源来源")
    for (const key of scope) {
        const row = store.rows.get(key)
        if (!row || store.runtimeDefinitions.get(key)?.matchesCatalog !== true) fail(`当前定义未核对：${key}`)
        const expected = key === CONTENT_RELEASE_PARENT ? ["visible", "enter", "exchange"]
            : key === CONTENT_RELEASE_GACHA ? ["visible", "enter"] : ["visible", "exchange"]
        if (expected.some(action => !store.capabilities(row).includes(action as typeof actions[number]))) fail(`内容能力不完整：${key}`)
        if (CONTENT_RELEASE_PRODUCTS.includes(key) && (row.parentKey !== CONTENT_RELEASE_PARENT || store.supportsPublicationSwitch(key)))
            fail(`商品归属或发布开关不匹配：${key}`)
    }
    if (canonical([...(store.questMembers.get(CONTENT_RELEASE_PARENT) ?? [])].sort()) !== canonical([...CONTENT_RELEASE_QUESTS].sort())
        || store.missionMembers.get(CONTENT_RELEASE_PARENT)?.size) fail("本活动关卡范围不匹配")
}
/** Exact adopted two-pool transition, captured from the old 059ae525 inputs and
 * the final unchanged pool masters. These hashes bind complete getter values:
 * price, flags and retained weights cannot ride along as unrelated edits. */
const approvedPoolTransitions: Record<string, { before: string; after: string }> = {
    "gacha:990001": { before: "096af68cf3536d9fd42029908902e63536d9fb3f230eecf2dc6e390ce7378bf1", after: "b274aafe951ec6ab4f9211eaa415292cb3f18d45be744f13085cec6594a5e095" },
    "gacha:990002": { before: "8c186fa4a5ad12697889f0eec1e0e8ab3ef646bd9bd1fb92826a783466cf0880", after: "cb16d9d0d656a48f7d30ce6057d785d9df4a180f2f8aa450b48fc8d284c4cf10" },
}
function approvedPoolDependencyChange(key: string, review: ReleaseIdentityReview): boolean {
    const transition = approvedPoolTransitions[key], before = review.before.keys[key], after = review.current.keys[key]
    if (review.before.catalogDigest !== "4bc3f197ffbff0fa0c6189483064bcdceaf2eacda3d7ee0e08603c314854f246"
        || review.current.catalogDigest !== "3087581a1c2687d259cab3db82eeeca8c44668b50372473dd127221f8e4cdd9c") return false
    if (key === "rush_event:700099") {
        // Exact adopted addition of products 9700130..9700132. They remain
        // outside this opening scope and retain the manual default-closed gate.
        const pairs: Record<string, [string, string]> = {
            "assets/event_item_shop.json#11/700099": ["1f60812400238e35c87dcc87f602d2aecb7d03ddd05e92aa2b260c91cf10a606", "be25d3a8aca33dfb26f9d692d266ba9760cec2d96079416aeeaeb78fd0b4eae8"],
            "assets/event_item_shop_id_map.json#parent:11:700099": ["fea202fcff0d441124607c6dfec17fd80d67df9e1d7d3a4e8979240d1a652299", "bad29614e7e97b3bc27867f5a984e6c0e21ff5d9968035aa064b84cb156d1683"],
        }
        const left = { ...before.dependencies }, right = { ...after.dependencies }
        for (const [selector, [oldHash, newHash]] of Object.entries(pairs)) {
            if (left[selector] !== oldHash || right[selector] !== newHash) return false
            delete left[selector]; delete right[selector]
        }
        return canonical(left) === canonical(right)
    }
    if (!transition || before.dependencies.actualGacha !== transition.before || after.dependencies.actualGacha !== transition.after
        || !before.approvedDeltaValues || !after.approvedDeltaValues
        || hash(before.approvedDeltaValues.actualGacha) !== transition.before || hash(after.approvedDeltaValues.actualGacha) !== transition.after)
        return false
    const left = { ...before.dependencies }, right = { ...after.dependencies }
    delete left.actualGacha; delete right.actualGacha
    // Payment/execution and campaign mapping must still be exactly equivalent.
    return canonical(left) === canonical(right)
}
function validateBinding(store: ContentOperationsStore, key: string, state: ContentControl, review?: ReleaseIdentityReview): void {
    const before = review?.before, current = review?.current, old = before?.keys[key], next = current?.keys[key]
    if (!review || !before || !current || before.kind !== "pinned-original-store-capture" || current.kind !== before.kind
        || before.catalogDigest !== state.catalogDigest || current.catalogDigest !== store.digest
        || !old || !next || old.key !== key || next.key !== key || old.contentDigest !== state.contentDigest
        || next.contentDigest !== store.contentDigests.get(key) || !old.runtimeMatches || !next.runtimeMatches
        || next.runtimeDigest !== store.runtimeDefinitions.get(key)?.digest || store.runtimeDefinitions.get(key)?.matchesCatalog !== true
        || !validHash(old.captureEngineSha256) || old.captureEngineSha256 !== next.captureEngineSha256
        || !old.dependencies || !Object.keys(old.dependencies).length || !next.dependencies || !Object.keys(next.dependencies).length)
        fail(`缺少同源原生字段身份复核：${key}`)
    for (const field of ["businessRow", "operatorCapabilities", "clientCapabilities", "questMembers", "missionMembers"] as const)
        if (canonical(old[field]) !== canonical(next[field])) fail(`原生业务字段发生变化，不能只重绑定：${key}/${field}`)
    if (canonical(old.dependencies) !== canonical(next.dependencies) && !approvedPoolDependencyChange(key, review))
        fail(`原生业务字段发生变化，不能只重绑定：${key}/dependencies`)
    const row = store.rows.get(key)!
    if (canonical(next.businessRow) !== canonical(businessRow(row))
        || canonical(next.operatorCapabilities) !== canonical([...store.capabilities(row)])
        || canonical(next.clientCapabilities) !== canonical([...(store.clientCapabilities?.(row) ?? [])])
        || canonical([...next.questMembers].sort()) !== canonical([...(store.questMembers.get(key) ?? [])].sort())
        || canonical([...next.missionMembers].sort()) !== canonical([...(store.missionMembers.get(key) ?? [])].sort())
        || Object.values(state.actionOverrides ?? {}).some(value => value?.contentDigest !== old.contentDigest || value.catalogDigest !== before.catalogDigest))
        fail(`字段复核与当前实际定义不一致：${key}`)
}

export function buildContentReleasePlanSync(store: ContentOperationsStore, evidenceDigest: string,
    captureSession?: ReleaseCaptureSession, source = readContentReleaseSourceSync(),
    legacyKeys = readContentDeploymentRequiredKeysSync()): ContentReleasePlan {
    if (!store.db.inTransaction) return store.db.transaction(() => buildContentReleasePlanSync(store, evidenceDigest, captureSession, source, legacyKeys))()
    validateScope(store, source)
    if (!validHash(evidenceDigest)) fail("缺少有效的逐项核查身份")
    if (readReceipt(store.db)) fail("本批已经应用；请核验已有回执，不要重新生成开放计划")
    const rows = rawStates(store.db), existing = new Set(rows.map(row => row.key))
    if (legacyKeys.some(key => !existing.has(key))) fail("原部署必需控制项缺失；禁止以补充回执吸收缺口")
    const bindings: ContentReleasePlan["bindings"] = []
    for (const row of rows) {
        const state = store.state(row.key)
        if (!store.rows.has(row.key) || !state || state.integrityError) fail(`既有运营项目无法安全复核：${row.key}`)
        if (!identityCurrent(store, row.key, state)) {
            bindings.push({ key: row.key, previousRawSha256: sha(row.raw) })
        }
    }
    const identityReview = bindings.length ? captureActualIdentities(captureSession, bindings.map(row => row.key)) : undefined
    const pending: Array<{ key: string; type: string; reason: string }> = []
    for (const binding of bindings) {
        try { validateBinding(store, binding.key, store.state(binding.key)!, identityReview) }
        catch (error) { pending.push({ key: binding.key, type: store.rows.get(binding.key)!.type, reason: String((error as Error).message) }) }
    }
    if (pending.length) {
        const error = new ContentOperationError(`原生字段复核有${pending.length}项未能证明：${pending[0].reason}`, 409)
        Object.assign(error, { pendingIdentityReviews: pending }); throw error
    }
    const auditCount = (store.db.prepare("SELECT count(*) AS n FROM content_operations_audit").get() as { n: number }).n
    const body = { schemaVersion: 1 as const, releaseId: CONTENT_RELEASE_ID as typeof CONTENT_RELEASE_ID, evidenceDigest, source,
        catalogDigest: store.digest, expectedRevision: store.revision(), databaseFingerprint: getDeploymentDatabaseFingerprintSync(store.db),
        operationsSha256: hash(rows), protectedDataSha256: protectedFingerprint(store.db), baselineMarkersSha256: baselineFingerprint(store.db),
        auditCount, auditSha256: auditFingerprint(store.db, auditCount), existingKeys: rows.map(row => row.key),
        requiredLegacyKeys: legacyKeys,
        createKeys: scope.filter(key => !existing.has(key)), preservedKeys: scope.filter(key => existing.has(key)),
        preservedControls: scope.filter(key => existing.has(key)).map(key => ({ key, state: store.state(key)!,
            effectiveFlags: Object.fromEntries(actions.map(action => [action, store.allowed(key, action, Date.now())])) })),
        ...(bindings.length ? { identityReview } : {}), bindings, products: CONTENT_RELEASE_PRODUCTS, questKeys: CONTENT_RELEASE_QUESTS,
        gachaKeys: [CONTENT_RELEASE_GACHA] }
    return { ...body, digest: hash(body) }
}
export function validateContentReleasePlanSync(store: ContentOperationsStore, plan: ContentReleasePlan, expectedDigest: string,
    source = readContentReleaseSourceSync(), legacyKeys = readContentDeploymentRequiredKeysSync()): void {
    const { digest, ...body } = plan
    if (!validHash(expectedDigest) || digest !== expectedDigest || hash(body) !== digest || plan.schemaVersion !== 1
        || plan.releaseId !== CONTENT_RELEASE_ID || plan.catalogDigest !== store.digest
        || canonical(plan.source) !== canonical(source) || !validHash(plan.evidenceDigest)
        || !Number.isSafeInteger(plan.expectedRevision) || plan.expectedRevision < 0
        || canonical(plan.products) !== canonical(CONTENT_RELEASE_PRODUCTS) || canonical(plan.questKeys) !== canonical(CONTENT_RELEASE_QUESTS)
        || canonical(plan.gachaKeys) !== canonical([CONTENT_RELEASE_GACHA])
        || canonical(plan.requiredLegacyKeys) !== canonical(legacyKeys) || legacyKeys.some(key => !plan.existingKeys.includes(key))
        || canonical(plan.createKeys) !== canonical(scope.filter(key => !plan.existingKeys.includes(key)))
        || canonical(plan.preservedKeys) !== canonical(scope.filter(key => plan.existingKeys.includes(key)))
        || canonical(plan.preservedControls.map(row => row.key)) !== canonical(plan.preservedKeys)
        || new Set(plan.existingKeys).size !== plan.existingKeys.length || new Set(plan.bindings.map(row => row.key)).size !== plan.bindings.length)
        fail("补充计划身份或精确范围不匹配")
    validateScope(store, source)
}
/** Re-run both source views immediately before application. Even a hash-valid
 * edited plan cannot substitute declared dependencies for current getters. */
export function validateContentReleaseIdentityCaptureSync(store: ContentOperationsStore, plan: ContentReleasePlan,
    captureSession?: ReleaseCaptureSession): ReleaseIdentityReview | undefined {
    if (!plan.bindings.length) {
        if (plan.identityReview !== undefined) fail("无身份重绑定时不能附加外部捕获声明")
        return undefined
    }
    if (!plan.identityReview) fail("身份重绑定计划缺少实际捕获回执")
    const actual = captureActualIdentities(captureSession, plan.bindings.map(row => row.key))
    if (hash(actual) !== hash(plan.identityReview)) fail("实际旧源或当前访问器捕获已变化；必须重新生成计划")
    for (const binding of plan.bindings) validateBinding(store, binding.key, store.state(binding.key)!, actual)
    return actual
}
interface Receipt { plan_digest: string; catalog_digest: string; keys_json: string; baseline_sha256: string; source_sha256: string }
function readReceipt(db: Database): Receipt | undefined {
    if (!db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(marker)) return undefined
    return db.prepare(`SELECT plan_digest,catalog_digest,keys_json,baseline_sha256,source_sha256 FROM ${marker} WHERE release_id=?`).get(CONTENT_RELEASE_ID) as Receipt | undefined
}
/** Later operator closes and player progress are permitted. Verification never
 * republishes a control or requires its original open flags to remain enabled. */
export function inspectContentReleaseSupplementSync(store: ContentOperationsStore,
    source = readContentReleaseSourceSync(), legacyKeys = readContentDeploymentRequiredKeysSync()): { ready: boolean; reasons: string[]; planDigest?: string } {
    const receipt = readReceipt(store.db)
    if (!receipt) return { ready: false, reasons: ["本批显式补充计划尚未应用"] }
    const reasons: string[] = []
    if (source.assetVersion !== "1.4.350" || receipt.source_sha256 !== source.manifestSha256) reasons.push("补充回执与当前发布链不匹配")
    if (receipt.catalog_digest !== store.digest || !validHash(receipt.plan_digest)) reasons.push("补充回执与当前目录不匹配")
    if (baselineFingerprint(store.db) !== receipt.baseline_sha256) reasons.push("原迁移标记发生变化")
    const keys: unknown = JSON.parse(receipt.keys_json)
    if (!Array.isArray(keys) || !keys.every(key => typeof key === "string") || new Set(keys).size !== keys.length
        || [...scope, ...legacyKeys].some(key => !keys.includes(key))) fail("补充回执项目范围无效")
    for (const key of keys as string[]) if (!identityCurrent(store, key, store.state(key))) reasons.push(`运营身份失配：${key}`)
    return { ready: reasons.length === 0, reasons, planDigest: receipt.plan_digest }
}

export function applyContentReleaseSupplementSync(store: ContentOperationsStore, plan: ContentReleasePlan,
    expectedDigest: string, context: DeploymentMaintenanceContext, nowMs: number,
    source = readContentReleaseSourceSync(), legacyKeys = readContentDeploymentRequiredKeysSync(),
    captureSession?: ReleaseCaptureSession): { applied: boolean; revision: number; createdKeys: string[]; preservedKeys: string[] } {
    assertDeploymentMaintenanceContextSync(store.db, context)
    validateContentReleasePlanSync(store, plan, expectedDigest, source, legacyKeys)
    if (!Number.isSafeInteger(nowMs) || nowMs < 0) fail("无效的真实维护时间")
    const prior = readReceipt(store.db)
    if (prior) {
        if (prior.plan_digest !== expectedDigest || !inspectContentReleaseSupplementSync(store, source, legacyKeys).ready) fail("已有补充回执不匹配；禁止重放")
        return { applied: false, revision: store.revision(), createdKeys: [], preservedKeys: plan.preservedKeys }
    }
    const db = store.db, beforeRows = rawStates(db)
    if (store.revision() !== plan.expectedRevision || hash(beforeRows) !== plan.operationsSha256
        || canonical(beforeRows.map(row => row.key)) !== canonical(plan.existingKeys)
        || getDeploymentDatabaseFingerprintSync(db) !== plan.databaseFingerprint || protectedFingerprint(db) !== plan.protectedDataSha256
        || baselineFingerprint(db) !== plan.baselineMarkersSha256 || auditFingerprint(db, plan.auditCount) !== plan.auditSha256)
        fail("目标数据已变化；必须重新预览并核查")
    const drifted = beforeRows.filter(row => !identityCurrent(store, row.key, store.state(row.key))).map(row => row.key)
    if (canonical(drifted) !== canonical(plan.bindings.map(row => row.key))) fail("身份复核项目不完整")
    for (const row of plan.preservedControls) if (canonical(row.state) !== canonical(store.state(row.key))) fail(`预览中的保留配置已变化：${row.key}`)
    const actualReview = validateContentReleaseIdentityCaptureSync(store, plan, captureSession)
    for (const binding of plan.bindings) {
        const raw = beforeRows.find(row => row.key === binding.key)?.raw, before = store.state(binding.key)!
        if (!raw || sha(raw) !== binding.previousRawSha256) fail(`原文已变化：${binding.key}`)
        validateBinding(store, binding.key, before, actualReview)
        const next: ContentControl = JSON.parse(raw), revision = store.revision()
        next.catalogDigest = store.digest; next.contentDigest = store.contentDigests.get(binding.key)!
        for (const value of Object.values(next.actionOverrides ?? {})) {
            value!.catalogDigest = store.digest; value!.contentDigest = next.contentDigest
        }
        next.revision = revision + 1
        const json = JSON.stringify(next)
        if (db.prepare("UPDATE content_operations_state SET value_json=? WHERE content_key=? AND value_json=?").run(json, binding.key, raw).changes !== 1
            || db.prepare("UPDATE content_operations_meta SET revision=? WHERE id=1 AND revision=?").run(revision + 1, revision).changes !== 1)
            fail("身份复核写入版本冲突")
        db.prepare("INSERT INTO content_operations_audit VALUES(?,?,?,?,?,?)").run(revision + 1, binding.key, nowMs, raw, json,
            `release-supplement:${expectedDigest}:identity-only`)
    }
    for (const key of plan.createKeys) {
        if (store.state(key)) fail(`新项目已存在：${key}`)
        const action = { enabled: true, readiness: "verified", endsAtMs: null, evidence: `逐项发布核查 ${plan.evidenceDigest}` }
        const actionOverrides = key === CONTENT_RELEASE_PARENT ? {
            visible: action, enter: { ...action, questKeys: CONTENT_RELEASE_QUESTS }, exchange: action,
        } : key === CONTENT_RELEASE_GACHA ? { visible: action, enter: action, exchange: { ...action, enabled: false } }
            : { visible: action, exchange: action }
        // A fresh product has no publication field. Existing controls never pass
        // through this branch, regardless of readiness or apparent default flags.
        store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
            reason: `release-supplement:${expectedDigest}:new-reviewed-content`, actionOverrides }, nowMs)
        if (!store.supportsPublicationSwitch(key) && store.state(key)!.published !== undefined) fail("商品不能生成发布标记")
    }
    const rebound = new Set(plan.bindings.map(row => row.key))
    for (const row of beforeRows) if (!rebound.has(row.key)) {
        const actual = db.prepare("SELECT value_json FROM content_operations_state WHERE content_key=?").get(row.key) as { value_json: string }
        if (actual.value_json !== row.raw) fail(`既有运营决定发生变化：${row.key}`)
    }
    if (protectedFingerprint(db) !== plan.protectedDataSha256 || baselineFingerprint(db) !== plan.baselineMarkersSha256
        || auditFingerprint(db, plan.auditCount) !== plan.auditSha256) fail("玩家数据、原迁移或旧审计发生变化")
    const expectedKeys = [...plan.existingKeys, ...plan.createKeys].sort()
    if (canonical(rawStates(db).map(row => row.key)) !== canonical(expectedKeys)
        || store.revision() !== plan.expectedRevision + plan.bindings.length + plan.createKeys.length
        || (db.prepare("SELECT count(*) AS n FROM content_operations_audit").get() as { n: number }).n !== plan.auditCount + plan.bindings.length + plan.createKeys.length)
        fail("补充写入的状态、版本或审计数量不符合计划")
    db.exec(`CREATE TABLE IF NOT EXISTS ${marker} (release_id TEXT PRIMARY KEY, plan_digest TEXT NOT NULL,
        catalog_digest TEXT NOT NULL, applied_revision INTEGER NOT NULL, keys_json TEXT NOT NULL, baseline_sha256 TEXT NOT NULL, source_sha256 TEXT NOT NULL)`)
    db.prepare(`INSERT INTO ${marker} VALUES(?,?,?,?,?,?,?)`).run(CONTENT_RELEASE_ID, expectedDigest, store.digest,
        store.revision(), JSON.stringify([...new Set([...plan.existingKeys, ...scope])].sort()), plan.baselineMarkersSha256, source.manifestSha256)
    if (!inspectContentReleaseSupplementSync(store, source, legacyKeys).ready) fail("补充应用后身份核验失败")
    return { applied: true, revision: store.revision(), createdKeys: plan.createKeys, preservedKeys: plan.preservedKeys }
}
