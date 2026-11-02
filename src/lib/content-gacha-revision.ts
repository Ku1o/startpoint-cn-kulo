import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import path from "node:path"
import type { Database } from "better-sqlite3"
import { ContentOperationError, type ContentOperationsStore } from "./content-operations-store"
import { rebindReviewedContentIdentitiesOfflineSync } from "./content-history-bootstrap"
import { assertDeploymentMaintenanceContextSync, getDeploymentDatabaseFingerprintSync,
    type DeploymentMaintenanceContext } from "./deployment-maintenance-guard"
import { readContentResourceSourceSync } from "./content-resource-source"
import { CONTENT_RELEASE_ID, readContentDeploymentRequiredKeysSync,
    type ContentReleaseSource, type ReleaseCaptureSession, type ReleaseIdentityReview } from "./content-release-supplement"

export const GACHA_REVISION_ID = "epuration-179981-gacha-356-v1"
export const GACHA_REVISION_TABLE = "content_gacha_revisions"
const pools = ["gacha:990001", "gacha:990002"]
const sources = ["assets/gacha_cnmod.json", "assets/gacha_rank_p5b.json"]
const logicals = ["master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap",
    "master/gacha_odds/cnmod_ashen_verdict_gacha_character_5.orderedmap"]
const mutable = new Set(["content_operations_state", "content_operations_meta", "content_operations_audit", GACHA_REVISION_TABLE])
const canonical = (value: unknown): string => typeof value === "bigint" ? JSON.stringify({ integer: value.toString() })
    : Array.isArray(value) ? `[${value.map(canonical).join(",")}]`
        : value && typeof value === "object" ? `{${Object.keys(value).sort().map(key =>
            `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`).join(",")}}` : JSON.stringify(value)
const sha = (value: string | Buffer): string => createHash("sha256").update(value).digest("hex")
const hash = (value: unknown): string => sha(canonical(value))
const validHash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value)
function fail(message: string): never { throw new ContentOperationError(message, 409) }
const quote = (value: string): string => `"${value.replace(/"/g, '""')}"`
const states = (db: Database): Array<{ key: string; raw: string }> => db.prepare(
    "SELECT content_key AS key,value_json AS raw FROM content_operations_state ORDER BY content_key").all() as Array<{ key: string; raw: string }>
const current = (store: ContentOperationsStore, key: string): boolean => {
    const state = store.state(key)
    return !!state && !state.integrityError && state.catalogDigest === store.digest
        && state.contentDigest === store.contentDigests.get(key) && store.runtimeDefinitions.get(key)?.matchesCatalog === true
        && Object.values(state.actionOverrides ?? {}).every(value => value?.catalogDigest === store.digest
            && value.contentDigest === store.contentDigests.get(key))
}
function protectedFingerprint(db: Database): string {
    const schema = (db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").all() as
        Array<{ type: string; name: string; tbl_name: string }>).filter(row => !mutable.has(row.tbl_name))
    const result = createHash("sha256").update(canonical(schema))
    for (const pragma of ["user_version", "application_id", "encoding"]) result.update(canonical(db.pragma(pragma)))
    for (const row of schema) if (row.type === "table") {
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
function legacyReceipt(db: Database): { raw: string; value: any } {
    if (!db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_release_supplements'").get()) fail("缺少350补充回执")
    const value = db.prepare("SELECT * FROM content_release_supplements WHERE release_id=?").get(CONTENT_RELEASE_ID) as any
    if (!value || !validHash(value.plan_digest) || !validHash(value.catalog_digest) || !validHash(value.source_sha256)
        || !validHash(value.baseline_sha256)) fail("350补充回执身份无效")
    const keys: unknown = JSON.parse(value.keys_json)
    if (!Array.isArray(keys) || keys.some(key => typeof key !== "string") || new Set(keys).size !== keys.length) fail("350回执项目无效")
    return { raw: canonical(value), value }
}
function baselineFingerprint(db: Database): string {
    return hash(["content_operations_initialization", "content_operations_deployment", "content_box_exchange_deployment"].map(table => {
        const rows = db.prepare(`SELECT * FROM ${quote(table)} ORDER BY id`).all()
        if (rows.length !== 1) fail("原迁移标记缺失或重复")
        return [table, rows]
    }))
}
/** Exact authorized addition. Every retained field survives; only the derived
 * rarity of rank-five rows follows odds / new total * 1000. */
export function validateGacha179981DeltaSync(key: string, before: any, after: any): void {
    const index = pools.indexOf(key)
    if (index < 0 || !before?.pool || !after?.pool) fail("非本次卡池修订")
    const { pool: left, ...leftFields } = before, { pool: right, ...rightFields } = after
    if (canonical(leftFields) !== canonical(rightFields) || Object.keys(left).join() !== Object.keys(right).join()
        || canonical(Object.fromEntries(Object.entries(left).filter(([rank]) => rank !== "1")))
            !== canonical(Object.fromEntries(Object.entries(right).filter(([rank]) => rank !== "1")))) fail("卡池价格、支付或其他星级发生变化")
    const oldRows = left["1"], newRows = right["1"], odds = index === 0 ? 1000 : 10000
    if (!Array.isArray(oldRows) || !Array.isArray(newRows) || newRows.length !== oldRows.length + 1
        || oldRows.some(row => row.id === 179981) || newRows.filter(row => row.id === 179981).length !== 1) fail("179981必须是唯一新增五星角色")
    const added = newRows.find(row => row.id === 179981)
    const { rarity: addedRarity, ...addedFields } = added
    if (canonical(addedFields) !== canonical({ id: 179981, rank: 5, odds, isRateUp: true,
        isLimited: true, isExchangeable: true, trialReadingForced: false })) fail("179981新增字段不符合本次范围")
    const retained = newRows.filter(row => row.id !== 179981)
    const total = newRows.reduce((sum, row) => sum + row.odds, 0)
    if (!Number.isSafeInteger(total) || total <= 0) fail("新卡池总权重无效")
    for (let i = 0; i < oldRows.length; i++) {
        const { rarity: oldRarity, ...oldFields } = oldRows[i], { rarity: newRarity, ...newFields } = retained[i]
        if (canonical(oldFields) !== canonical(newFields) || !Number.isFinite(oldRarity)
            || newRarity !== retained[i].odds / total * 1000) fail("原有角色权重、限制或派生概率发生未授权变化")
    }
    if (addedRarity !== odds / total * 1000) fail("新增角色派生概率不匹配")
}
function capture(session: ReleaseCaptureSession | undefined, keys: string[]): ReleaseIdentityReview {
    const producer = require(path.resolve(__dirname, "../../tools/content-release-capture.cjs"))
    if (!session || !producer.isReleaseCaptureSession(session)) fail("必须使用固定实际访问器捕获，不能接受声明JSON")
    const review = session.capture(keys)
    for (const view of [review.before, review.current]) if (!view.inputReceipt
        || keys.some(key => view.keys[key]?.captureEngineSha256 !== producer.PRODUCER_SHA256)) fail("实际捕获回执缺失")
    return review
}
function metadata(session: ReleaseCaptureSession, source: ContentReleaseSource): string {
    const read = (root: string, name: string) => JSON.parse(readFileSync(path.join(root, "assets", name), "utf8"))
    const old = read(session.previousSourceRoot, "content_catalog.json"), next = read(session.currentSourceRoot, "content_catalog.json")
    const previousResource = read(session.previousSourceRoot, "content_resource_source.json"), nextResource = read(session.currentSourceRoot, "content_resource_source.json")
    const manifest = readFileSync(path.join(session.currentSourceRoot, "assets/asset-patch/manifest.json"))
    if (previousResource.source?.assetVersion !== "1.4.350" || source.assetVersion !== "1.4.356"
        || canonical(source) !== canonical(nextResource.source) || sha(manifest) !== source.manifestSha256
        || JSON.parse(manifest.toString("utf8")).cdn_version !== "1.4.356") fail("本修订只接受350业务来源到356")
    const candidate = JSON.parse(JSON.stringify(old)), resourceCandidate = JSON.parse(JSON.stringify(previousResource))
    const baseOld = read(session.previousSourceRoot, "gacha.json"), baseNext = read(session.currentSourceRoot, "gacha.json")
    const baseCandidate = JSON.parse(JSON.stringify(baseOld))
    for (let i = 0; i < pools.length; i++) {
        const id = pools[i].split(":")[1], effective = JSON.parse(readFileSync(path.join(session.currentSourceRoot, sources[i]), "utf8"))[id]
        if (canonical(baseNext[id]) !== canonical(effective)) fail("base卡池镜像与实际胜出表不一致")
        baseCandidate[id] = effective
    }
    if (canonical(baseCandidate) !== canonical(baseNext)) fail("base卡池镜像包含其他卡池变化")
    for (const file of ["assets/gacha.json", ...sources]) {
        const fileSha = sha(readFileSync(path.join(session.currentSourceRoot, file)))
        if (next.serverResources[file]?.sha256 !== fileSha) fail("服务端整表来源不匹配：" + file)
        candidate.serverResources[file] = next.serverResources[file]
    }
    for (const row of candidate.rows) if (row.definitionEvidence?.serverSources?.some((file: string) => ["assets/gacha.json", ...sources].includes(file))) {
        const expected = sha(JSON.stringify(row.definitionEvidence.serverSources.map((file: string) =>
            [file, sha(readFileSync(path.join(session.currentSourceRoot, file)))])))
        if (next.rows.find((value: any) => value.key === row.key)?.serverDefinitionDigest !== expected) fail("卡池原生整表身份不匹配：" + row.key)
        row.serverDefinitionDigest = expected
    }
    for (let i = 0; i < pools.length; i++) {
        const oldRow = candidate.rows.find((row: any) => row.key === pools[i]), newRow = next.rows.find((row: any) => row.key === pools[i])
        const fileSha = sha(readFileSync(path.join(session.currentSourceRoot, sources[i])))
        if (!oldRow || !newRow || next.serverResources[sources[i]]?.sha256 !== fileSha
            || newRow.serverDefinitionDigest !== sha(JSON.stringify([[sources[i], fileSha]]))
            || next.resources[logicals[i]]?.sha256 !== nextResource.resources[logicals[i]]?.sha256
            || next.resources[logicals[i]]?.archive !== nextResource.resources[logicals[i]]?.archive
            || nextResource.resources[logicals[i]]?.sha256 === previousResource.resources[logicals[i]]?.sha256) fail("本次服务端或客户端来源登记不匹配")
        candidate.resources[logicals[i]] = next.resources[logicals[i]]
        resourceCandidate.resources[logicals[i]] = nextResource.resources[logicals[i]]
    }
    resourceCandidate.source = source
    if (canonical(candidate) !== canonical(next) || canonical(resourceCandidate) !== canonical(nextResource)) fail("内容登记存在本次两池之外的变化")
    return previousResource.source.manifestSha256
}
export interface GachaRevisionPlan {
    schemaVersion: 1; revisionId: typeof GACHA_REVISION_ID; digest: string; evidenceDigest: string
    source: ContentReleaseSource; catalogDigest: string; legacyReceiptSha256: string
    expectedRevision: number; databaseFingerprint: string; protectedSha256: string
    operationsSha256: string; baselineSha256: string; auditCount: number; auditSha256: string
    existingKeys: string[]; requiredLegacyKeys: readonly string[]; identityReview: ReleaseIdentityReview
    bindings: Array<{ key: string; previousRawSha256: string; nextContentDigest: string }>
}
function validateReview(store: ContentOperationsStore, review: ReleaseIdentityReview, rows: Array<{ key: string; raw: string }>, oldSource: string): void {
    const legacy = legacyReceipt(store.db).value
    if (legacy.catalog_digest !== review.before.catalogDigest || legacy.source_sha256 !== oldSource
        || review.current.catalogDigest !== store.digest || baselineFingerprint(store.db) !== legacy.baseline_sha256) fail("旧350身份或迁移标记不一致")
    for (const row of rows) {
        const state = store.state(row.key), before = review.before.keys[row.key], after = review.current.keys[row.key]
        if (!state || state.integrityError || !before || !after || !before.runtimeMatches || !after.runtimeMatches
            || state.catalogDigest !== review.before.catalogDigest || state.contentDigest !== before.contentDigest
            || after.contentDigest !== store.contentDigests.get(row.key) || after.runtimeDigest !== store.runtimeDefinitions.get(row.key)?.digest
            || store.runtimeDefinitions.get(row.key)?.matchesCatalog !== true
            || Object.values(state.actionOverrides ?? {}).some(value => value?.catalogDigest !== state.catalogDigest || value.contentDigest !== state.contentDigest)) fail("既有控制或实际定义身份无法核对：" + row.key)
        for (const field of ["businessRow", "operatorCapabilities", "clientCapabilities", "questMembers", "missionMembers"] as const)
            if (canonical(before[field]) !== canonical(after[field])) fail("原业务字段发生变化：" + row.key + "/" + field)
        const left = { ...before.dependencies }, right = { ...after.dependencies }
        if (pools.includes(row.key)) {
            if (!before.approvedDeltaValues || !after.approvedDeltaValues
                || hash(before.approvedDeltaValues.actualGacha) !== left.actualGacha
                || hash(after.approvedDeltaValues.actualGacha) !== right.actualGacha) fail("卡池原始访问器值缺失")
            validateGacha179981DeltaSync(row.key, before.approvedDeltaValues.actualGacha, after.approvedDeltaValues.actualGacha)
            delete left.actualGacha; delete right.actualGacha
        }
        if (!Object.keys(before.dependencies).length || canonical(left) !== canonical(right)) fail("卡池之外的实际依赖发生变化：" + row.key)
    }
}
function receipt(store: ContentOperationsStore): any {
    return store.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(GACHA_REVISION_TABLE)
        ? store.db.prepare(`SELECT * FROM ${GACHA_REVISION_TABLE} WHERE revision_id=?`).get(GACHA_REVISION_ID) : undefined
}
export function buildGachaRevisionPlanSync(store: ContentOperationsStore, evidenceDigest: string,
    session: ReleaseCaptureSession, source = readContentResourceSourceSync(),
    requiredLegacyKeys = readContentDeploymentRequiredKeysSync()): GachaRevisionPlan {
    if (!store.db.inTransaction) fail("修订预览必须位于显式只读快照事务中")
    if (!validHash(evidenceDigest) || receipt(store)) fail("审阅摘要无效或本修订已经应用")
    const rows = states(store.db), existingKeys = rows.map(row => row.key), legacy = legacyReceipt(store.db)
    const legacyKeys: string[] = JSON.parse(legacy.value.keys_json)
    if ([...pools, ...requiredLegacyKeys, ...legacyKeys].some(key => !existingKeys.includes(key))) fail("既有控制集合缺失，禁止用修订吸收缺口")
    const review = capture(session, existingKeys), oldSource = metadata(session, source)
    validateReview(store, review, rows, oldSource)
    const auditCount = (store.db.prepare("SELECT count(*) AS n FROM content_operations_audit").get() as { n: number }).n
    const body = { schemaVersion: 1 as const, revisionId: GACHA_REVISION_ID as typeof GACHA_REVISION_ID, evidenceDigest, source,
        catalogDigest: store.digest, legacyReceiptSha256: sha(legacy.raw), expectedRevision: store.revision(),
        databaseFingerprint: getDeploymentDatabaseFingerprintSync(store.db), protectedSha256: protectedFingerprint(store.db),
        operationsSha256: hash(rows), baselineSha256: baselineFingerprint(store.db), auditCount,
        auditSha256: auditFingerprint(store.db, auditCount), existingKeys, requiredLegacyKeys, identityReview: review,
        bindings: rows.filter(row => !current(store, row.key)).map(row => ({ key: row.key, previousRawSha256: sha(row.raw),
            nextContentDigest: store.contentDigests.get(row.key)! })) }
    return { ...body, digest: hash(body) }
}
export function validateGachaRevisionPlanSync(store: ContentOperationsStore, plan: GachaRevisionPlan,
    digest: string, source = readContentResourceSourceSync(), requiredLegacyKeys = readContentDeploymentRequiredKeysSync()): void {
    const { digest: actual, ...body } = plan
    if (!validHash(digest) || actual !== digest || hash(body) !== digest || plan.schemaVersion !== 1
        || plan.revisionId !== GACHA_REVISION_ID || plan.catalogDigest !== store.digest
        || plan.source.assetVersion !== "1.4.356" || canonical(plan.source) !== canonical(source)
        || canonical(plan.requiredLegacyKeys) !== canonical(requiredLegacyKeys)
        || !validHash(plan.evidenceDigest) || sha(legacyReceipt(store.db).raw) !== plan.legacyReceiptSha256
        || baselineFingerprint(store.db) !== plan.baselineSha256) fail("本次修订计划、旧回执或当前来源不匹配")
}
export function validateGachaRevisionCaptureSync(store: ContentOperationsStore, plan: GachaRevisionPlan,
    session: ReleaseCaptureSession, source = readContentResourceSourceSync()): void {
    const actual = capture(session, plan.existingKeys)
    if (hash(actual) !== hash(plan.identityReview)) fail("实际旧源或当前访问器发生变化，必须重新预览")
    validateReview(store, actual, states(store.db), metadata(session, source))
}
export function inspectGachaRevisionSync(store: ContentOperationsStore, source = readContentResourceSourceSync(),
    requiredLegacyKeys = readContentDeploymentRequiredKeysSync()): { ready: boolean; reasons: string[]; planDigest?: string } {
    const saved = receipt(store), reasons: string[] = []
    if (!saved) return { ready: false, reasons: ["本次卡池修订尚未应用"] }
    if (!validHash(saved.plan_digest) || saved.catalog_digest !== store.digest || saved.source_json !== canonical(source)
        || source.assetVersion !== "1.4.356" || sha(legacyReceipt(store.db).raw) !== saved.legacy_receipt_sha256
        || baselineFingerprint(store.db) !== saved.baseline_sha256) reasons.push("卡池修订回执与当前目录、来源或旧迁移不匹配")
    let keys: unknown
    try { keys = JSON.parse(saved.keys_json) } catch { keys = null }
    if (!Array.isArray(keys) || keys.some(key => typeof key !== "string") || new Set(keys).size !== keys.length
        || [...pools, ...requiredLegacyKeys, ...JSON.parse(legacyReceipt(store.db).value.keys_json)].some(key => !keys.includes(key))) reasons.push("卡池修订控制集合无效")
    else for (const key of keys) if (!current(store, key)) reasons.push("运营身份失配：" + key)
    return { ready: reasons.length === 0, reasons, planDigest: saved.plan_digest }
}
export function applyGachaRevisionSync(store: ContentOperationsStore, plan: GachaRevisionPlan, digest: string,
    context: DeploymentMaintenanceContext, nowMs: number, session?: ReleaseCaptureSession,
    source = readContentResourceSourceSync(), requiredLegacyKeys = readContentDeploymentRequiredKeysSync()): { applied: boolean; revision: number; reboundKeys: string[] } {
    assertDeploymentMaintenanceContextSync(store.db, context)
    validateGachaRevisionPlanSync(store, plan, digest, source, requiredLegacyKeys)
    if (!Number.isSafeInteger(nowMs) || nowMs < 0) fail("无效维护时间")
    const saved = receipt(store)
    if (saved) {
        if (saved.plan_digest !== digest || !inspectGachaRevisionSync(store, source, requiredLegacyKeys).ready) fail("已有修订回执不匹配，禁止重放")
        return { applied: false, revision: store.revision(), reboundKeys: [] }
    }
    const db = store.db, rows = states(db)
    if (store.revision() !== plan.expectedRevision || getDeploymentDatabaseFingerprintSync(db) !== plan.databaseFingerprint
        || hash(rows) !== plan.operationsSha256 || protectedFingerprint(db) !== plan.protectedSha256
        || canonical(rows.map(row => row.key)) !== canonical(plan.existingKeys)
        || canonical(rows.filter(row => !current(store, row.key)).map(row => row.key)) !== canonical(plan.bindings.map(row => row.key))) fail("目标数据库已变化，必须重新预览")
    if (!session) fail("修订应用需要固定旧源实际捕获")
    validateGachaRevisionCaptureSync(store, plan, session, source)
    const result = rebindReviewedContentIdentitiesOfflineSync(store, plan, { expectedRevision: plan.expectedRevision, nowMs, maintenanceContext: context })
    if (protectedFingerprint(db) !== plan.protectedSha256 || auditFingerprint(db, plan.auditCount) !== plan.auditSha256
        || store.revision() !== plan.expectedRevision + plan.bindings.length
        || (db.prepare("SELECT count(*) AS n FROM content_operations_audit").get() as { n: number }).n !== plan.auditCount + plan.bindings.length) fail("身份重绑改变了玩家数据、历史审计或预期版本")
    db.exec(`CREATE TABLE ${GACHA_REVISION_TABLE} (revision_id TEXT PRIMARY KEY,plan_digest TEXT NOT NULL,catalog_digest TEXT NOT NULL,
        source_json TEXT NOT NULL,legacy_receipt_sha256 TEXT NOT NULL,baseline_sha256 TEXT NOT NULL,keys_json TEXT NOT NULL)`)
    db.prepare(`INSERT INTO ${GACHA_REVISION_TABLE} VALUES(?,?,?,?,?,?,?)`).run(GACHA_REVISION_ID, digest, store.digest,
        canonical(source), plan.legacyReceiptSha256, plan.baselineSha256, JSON.stringify(plan.existingKeys))
    if (!inspectGachaRevisionSync(store, source, requiredLegacyKeys).ready) fail("修订应用后身份校验失败")
    return { applied: true, revision: result.revision, reboundKeys: result.reboundKeys }
}
