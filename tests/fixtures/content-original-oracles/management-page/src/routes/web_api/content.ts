import { FastifyInstance } from "fastify"
import { contentOperations } from "../../lib/content-operations"
import { CONTENT_ACTIONS, ContentOperationError } from "../../lib/content-operations-store"
import type { ContentCatalogListing, ContentControl, ContentManagementSnapshot } from "../../lib/content-operations-store"
import { runPersistenceTransaction } from "../../lib/persistence-coordinator"
import { hasManagementSession } from "../../lib/management-auth"
import { getContentPresentation, readContentPresentationImage, readContentPresentationThumbnail, CONTENT_PRESENTATION_GROUPS } from "../../lib/content-presentation"
import julyPlan from "../../../assets/content_july_controls.json"
import { contentHistoryReadinessReader } from "../../lib/content-history-readiness"
import { contentDiscoveryReader, discoveryTerms, groupContentSeries } from "../../lib/content-discovery"
import { runContentManagementRead } from "../../lib/content-management-work"
import { ContentManagementSharedReads, ContentSharedReadOversized } from "../../lib/content-management-shared"
import { projectContentManagementCards } from "../../lib/content-management-projection"
import { isContentBoxAssociationIndexAvailable } from "../../lib/content-box-associations"

const readinessValues = ["unverified", "current_baseline", "verified", "blocked"]
const statusValues = ["all", "enabled", "disabled", "pending", "blocked", "unsupported"]
const memberTypes = new Set(["general_shop", "treasure_shop", "star_grain_shop", "boss_coin_shop", "event_item_shop", "mission_regular", "mission_daily", "mission_event", "shop_product"])
const isMemberType = (type: string) => memberTypes.has(type) || type.startsWith("mission_")
const personalGachaQualificationIds = new Set([700000, 700001, 700002, 700003, 700004, 80000, 80001, 80002, 80003, 80004])
const boxAssociationTypes = new Set(["world_story_event", "raid_event", "box_gacha"])
type ListedRow = ContentCatalogListing["rows"][number]
type HistoryReader = ReturnType<typeof contentHistoryReadinessReader>
function managementPresentation(row: { key: string; type?: string; name?: string }, history = contentHistoryReadinessReader()) {
    const presentation = getContentPresentation(row)
    if (history.boxAssociation(row.key)?.parentKey === row.key) {
        return { ...presentation, group: "exchange" as const,
            groupLabel: CONTENT_PRESENTATION_GROUPS.find(group => group.key === "exchange")!.label,
            typeLabel: row.type === "world_story_event" ? "箱池关联关卡" : "奖励箱关联活动" }
    }
    const page = history.nativePage(row.key)
    if (row.type !== "collect_item_event" || page?.kind !== "collect_item_exchange_shop") return presentation
    return { ...presentation, group: "exchange" as const,
        groupLabel: CONTENT_PRESENTATION_GROUPS.find(group => group.key === "exchange")!.label,
        typeLabel: page.label, ...(page.description ? { subtitle: page.description } : {}) }
}
type PublicationStatus = "enabled" | "disabled" | "pending" | "blocked"
interface PublicationPresentation {
    status: PublicationStatus
    label: string
    canToggle: boolean
    reason: string
}

function retainedRightsNotice(row: ListedRow): string | undefined {
    if (row.type !== "gacha") return undefined
    if (personalGachaQualificationIds.has(row.id)) {
        return "保留已有进度和兑换，本轮不新增个人扭蛋资格。开启开关不会发放资格。"
    }
    if (row.id === 100 && row.capabilities.includes("claim")) {
        return "已使用乐享扭蛋券的玩家仍可续完本轮扭蛋。关闭卡池会保留当前候选和已保存结果。"
    }
    return undefined
}

function unavailable(row: ListedRow, fallback: string, hardBlock = false, reader = contentHistoryReadinessReader()): PublicationPresentation {
    const required = ["special_exchange_campaign", "start_dash_exchange_campaign"].includes(row.type)
        ? ["exchange" as const] : row.capabilities.includes("enter") ? ["visible" as const, "enter" as const] : ["visible" as const]
    const history = reader.get(row.key, required)
    const blocked = hardBlock || history.status === "blocked" || history.status === "not_applicable"
    return { status: blocked ? "blocked" : "pending", label: blocked ? "无法开放" : "待接入", canToggle: false,
        reason: hardBlock ? fallback : history.status === "blocked" || history.status === "not_applicable" || history.status === "unreviewed"
            ? history.reasons.join("；") : fallback }
}

function actionReview(state: ContentControl, action: typeof CONTENT_ACTIONS[number]) {
    return state.actionOverrides !== undefined ? state.actionOverrides[action]
        : { enabled: state.flags[action], readiness: state.readiness, evidence: state.evidence, endsAtMs: state.endsAtMs }
}

function participationReady(row: ListedRow | undefined, nowMs: number, parent = false): boolean {
    const state = row?.state
    return !!row && !!state && state.controlled !== false && !state.integrityError && row.publishable && row.definitionReady && !row.stale
        && (parent ? ["visible", "enter", "exchange"] as const : ["visible", "enter"] as const).every(action => {
            const review = actionReview(state, action)
            return row.capabilities.includes(action) && review?.enabled === true
                && ["verified", "current_baseline"].includes(review.readiness) && !!review.evidence.trim()
                && (review.endsAtMs === null || nowMs <= review.endsAtMs)
        })
}

function listedRow(store: ReturnType<typeof contentOperations>, key: string): ListedRow | undefined {
    const original = store.rows.get(key)
    if (!original) return undefined
    const first = store.list({ type: original.type, offset: 0, limit: 200 })
    for (let offset = 0; offset < first.total; offset += 200) {
        const page = offset === 0 ? first : store.list({ type: original.type, offset, limit: 200 })
        const row = page.rows.find(row => row.key === key)
        if (row) return row
    }
    return undefined
}

function publicationRequest(store: ReturnType<typeof contentOperations>, input: unknown) {
    if (!input || typeof input !== "object" || Array.isArray(input)
        || Object.keys(input).some(field => !["published", "expectedRevision", "catalogDigest", "reason"].includes(field)))
        throw new ContentOperationError("发布请求参数无效")
    const body = input as { published: boolean; expectedRevision: number; catalogDigest: string; reason: string }
    if (typeof body.published !== "boolean" || !Number.isSafeInteger(body.expectedRevision) || body.expectedRevision < 0)
        throw new ContentOperationError("发布请求参数无效")
    if (body.catalogDigest !== store.digest) throw new ContentOperationError("内容目录已变化，请重新核对资源", 409)
    if (typeof body.reason !== "string" || !body.reason.trim() || body.reason.length > 2000)
        throw new ContentOperationError("变更原因必须为 1 至 2000 字的说明")
    if (body.expectedRevision !== store.revision()) throw new ContentOperationError("状态已被其他操作更新，请刷新后重试", 409)
    return body
}

function associationIndexUnavailable(store: ReturnType<typeof contentOperations>, key: string) {
    return boxAssociationTypes.has(store.rows.get(key)?.type ?? "") && !isContentBoxAssociationIndexAvailable()
}

function setDailyPublication(store: ReturnType<typeof contentOperations>, key: string, input: unknown, nowMs: number) {
    const body = publicationRequest(store, input), association = contentHistoryReadinessReader().boxAssociation(key)
    if (body.published && associationIndexUnavailable(store, key))
        throw new ContentOperationError("活动与奖励箱关联资料不可用，不能开启；仍可关闭已有入口", 409)
    if (!association) {
        const state = store.setPublished(key, input, nowMs)
        return { state, revision: state.revision }
    }
    return store.db.transaction(() => {
        // Check CAS and all fields even when one side already has the requested marker.
        publicationRequest(store, input)
        if (body.published && (!association.relationshipMatches
            || !participationReady(listedRow(store, association.parentKey), nowMs, true)
            || !participationReady(listedRow(store, association.boxKey), nowMs))) {
            throw new ContentOperationError("关联活动与奖励箱都需完成参与设置，活动奖励箱入口也需核查，才能一起开启", 409)
        }
        const own = store.state(key)
        // The real store still owns every write and its definition/publication guards.
        const state = !own || own.controlled === false || own.integrityError || !store.supportsPublicationSwitch(key)
            || (own.published !== false) !== body.published ? store.setPublished(key, input, nowMs) : own
        const otherKey = key === association.parentKey ? association.boxKey : association.parentKey
        const other = store.state(otherKey), linkedStates: ContentControl[] = []
        // Taking an existing entrance offline never depends on repairing a
        // missing/corrupt peer. No peer control is created or promoted here.
        if (other && other.controlled !== false && !other.integrityError && store.supportsPublicationSwitch(otherKey)
            && (other.published !== false) !== body.published) {
            linkedStates.push(store.setPublished(otherKey, { ...body, expectedRevision: store.revision() }, nowMs))
        }
        return { state, linkedStates, revision: store.revision() }
    }).immediate()
}

function deadlinePresentation(store: ReturnType<typeof contentOperations>, row: ListedRow, snapshot?: ContentManagementSnapshot, history?: HistoryReader) {
    const own = store.deadlineControl(row.key, row.state), association = (history ?? contentHistoryReadinessReader()).boxAssociation(row.key)
    if (associationIndexUnavailable(store, row.key)) return { ...own, canEdit: false, reason: "活动与奖励箱关联资料不可用，不能单独修改截止时间" }
    if (!association || !own.canEdit) return own
    const peerKey = row.key === association.parentKey ? association.boxKey : association.parentKey
    const peer = store.deadlineControl(peerKey, snapshot ? snapshot.state(peerKey) : undefined)
    if (!association.relationshipMatches || !peer.canEdit) return { ...own, canEdit: false,
        reason: !association.relationshipMatches ? "关联活动与箱池对应关系尚未核对" : `关联内容不能修改截止时间：${peer.reason}` }
    return { ...own, hasMixedDeadlines: own.hasMixedDeadlines || peer.hasMixedDeadlines || own.endsAtMs !== peer.endsAtMs,
        reason: "同时保存活动与奖励箱入口的截止时间；保存不会自动开启。已获得奖励和原有进度保留，新的开箱随活动入口停止" }
}

function setDailyDeadline(store: ReturnType<typeof contentOperations>, key: string, input: unknown, nowMs: number) {
    if (associationIndexUnavailable(store, key))
        throw new ContentOperationError("活动与奖励箱关联资料不可用，不能单独修改截止时间；仍可关闭已有入口", 409)
    const association = contentHistoryReadinessReader().boxAssociation(key)
    if (!association) {
        const state = store.setDeadline(key, input, nowMs)
        return { state, linkedStates: [], revision: state.revision }
    }
    return store.db.transaction(() => {
        if (!association.relationshipMatches) throw new ContentOperationError("关联活动与箱池对应关系尚未核对", 409)
        const state = store.setDeadline(key, input, nowMs)
        const otherKey = key === association.parentKey ? association.boxKey : association.parentKey
        const linked = store.setDeadline(otherKey, { ...(input as Record<string, unknown>), expectedRevision: store.revision() }, nowMs)
        return { state, linkedStates: [linked], revision: store.revision() }
    }).immediate()
}

function publicationPresentation(row: ListedRow, nowMs: number, history = contentHistoryReadinessReader()): PublicationPresentation {
    const unavailableHere = (fallback: string, hardBlock = false) => unavailable(row, fallback, hardBlock, history)
    const state = row.state
    const expired = !!state && ["visible", "enter"].some(action => {
        const review = actionReview(state, action as "visible" | "enter")
        return review?.enabled && review.endsAtMs !== null && nowMs > review.endsAtMs
    })
    const participationReason = (opening: boolean) => {
        if (!row.capabilities.includes("enter") || (opening ? state && actionReview(state, "enter")?.enabled : row.effectiveFlags?.enter === true)) return ""
        const rights = ["claim", "exchange"].some(action => row.effectiveFlags?.[action as "claim" | "exchange"] === true
            || (state && actionReview(state, action as "claim" | "exchange")?.enabled))
        return rights ? "仅原有领奖或兑换资格，暂不开放新参与" : "仅显示原入口，暂不开放新参与"
    }
    // A currently visible row can always be taken offline through the existing
    // publication API, even when a different configured action needs repair.
    if (row.publishable && row.effectiveFlags?.visible === true && !expired) return { status: "enabled", label: "已开启", canToggle: true,
        reason: participationReason(false) }
    if (row.publishable && state && state.controlled !== false && !state.integrityError && state.published !== false && !expired
        && (history.boxAssociation(row.key) || boxAssociationTypes.has(row.type) && !isContentBoxAssociationIndexAvailable()))
        return { status: "enabled", label: "已保存开启", canToggle: true,
            reason: "关联入口当前不接受新参与；仍可关闭已保存的开关。不会自动补齐或开放关联内容。" }
    if (!row.publishable) return unavailableHere("该玩法的开放入口尚未接入日常开关")
    if (state?.integrityError) return unavailableHere("已保存的开放设置损坏，需修复后重新核查", true)
    if (!state || state.controlled === false) return unavailableHere("尚未完成开放设置与玩法范围的接入")
    if (!row.definitionReady) return unavailableHere("客户端与服务端内容定义缺失或不一致，需核对后开放", true)
    if (row.stale) return unavailableHere("内容配置已变化，原开放设置需要重新核查", true)
    if (expired) return { status: "disabled", label: "已到期", canToggle: false,
        reason: history.boxAssociation(row.key)
            ? "活动与奖励箱入口已到期；保存新的截止时间后仍需手动开启。保留已获得奖励与进度，不再接受新开箱。"
            : "开放期限已到；请先保存新的截止时间，再手动开启。原有领奖、兑换资格保留。" }
    const review = (action: typeof CONTENT_ACTIONS[number]) => actionReview(state, action)
    const valid = (action: typeof CONTENT_ACTIONS[number]) => {
        const value = review(action)
        return !!value && value.enabled && row.capabilities.includes(action)
            && ["verified", "current_baseline"].includes(value.readiness) && !!value.evidence.trim()
            && (action === "claim" || action === "exchange" || value.endsAtMs === null || nowMs <= value.endsAtMs)
    }
    if (!valid("visible") || CONTENT_ACTIONS.some(action => review(action)?.enabled && !valid(action))) {
        return unavailableHere(CONTENT_ACTIONS.some(action => {
            const value = review(action)
            return value?.enabled && value.endsAtMs !== null && nowMs > value.endsAtMs
        }) ? "原开放设置已到期，需重新确认开放期限" : "尚未完成所需动作与玩法范围的接入")
    }
    if (state.published !== false) return unavailableHere("已保存的开放设置尚未生效，需要重新核查")
    return { status: "disabled", label: "已关闭", canToggle: true,
        reason: participationReason(true) }
}

function primaryControl(row: ListedRow, publication: PublicationPresentation, nowMs: number) {
    if (row.publishable) return { ...publication, kind: "publication" as const, enabled: publication.status === "enabled" }
    if (["special_exchange_campaign", "start_dash_exchange_campaign"].includes(row.type)) {
        const state = row.state, review = state ? actionReview(state, "exchange") : undefined
        if (state && state.controlled !== false && !state.integrityError && !row.stale && row.definitionReady && review
            && ["verified", "current_baseline"].includes(review.readiness) && review.enabled
            && review.endsAtMs !== null && nowMs > review.endsAtMs) {
            return { kind: "exchange" as const, enabled: false, canToggle: false, status: "disabled" as const,
                label: "已到期", reason: "兑换期限已到；请先保存新的截止时间，再手动开启。不会发放新资格。" }
        }
        if (state && state.controlled !== false && review && row.effectiveFlags?.exchange === true) {
            return { kind: "exchange" as const, enabled: true, canToggle: true, status: "enabled" as const,
                label: "已开启", reason: "已有资格兑换：仅影响已有兑换资格，不会发放新资格" }
        }
        if (state && state.controlled !== false && !state.integrityError && !row.stale && row.definitionReady
            && row.capabilities.includes("exchange") && review && !!review.evidence.trim()
            && ["verified", "current_baseline"].includes(review.readiness)
            && (review.endsAtMs === null || nowMs <= review.endsAtMs)) {
            const enabled = row.effectiveFlags?.exchange === true
            return { kind: "exchange" as const, enabled, canToggle: true,
                status: enabled ? "enabled" as const : "disabled" as const, label: enabled ? "已开启" : "已关闭",
                reason: "已有资格兑换：仅影响已有兑换资格，不会发放新资格" }
        }
    }
    return { ...publication, kind: null, enabled: false }
}

function parentListing(snapshot: ContentManagementSnapshot, query: {
    type?: string; readiness?: string; candidatesOnly: boolean; referenceWindow?: readonly [number, number]
}) {
    return snapshot.all(query, row => !isMemberType(row.type))
}

async function readBatch<T, R>(rows: readonly T[], checkpoint: () => Promise<void>, read: (row: T) => R): Promise<R[]> {
    const result: R[] = []
    for (let index = 0; index < rows.length; index++) {
        if (index % 64 === 0) await checkpoint()
        result.push(read(rows[index]))
    }
    return result
}

async function typeOptions(store: ReturnType<typeof contentOperations>, group: unknown, includeMembers: boolean, history: HistoryReader, checkpoint: () => Promise<void>) {
    const labels = new Map<string, Set<string>>()
    let index = 0
    for (const row of store.catalog.rows) {
        if (!includeMembers && isMemberType(row.type)) continue
        if (index++ % 64 === 0) await checkpoint()
        const presentation = managementPresentation(row, history)
        if (group !== undefined && group !== "all" && presentation.group !== group) continue
        let values = labels.get(row.type)
        if (!values) { values = new Set(); labels.set(row.type, values) }
        values.add(presentation.typeLabel)
    }
    // Some original types contain more than one native display kind (character
    // and equipment gacha). Keep one original value without mislabelling either.
    return [...labels].map(([value, values]) => ({ value, label: [...values].join(" / ") }))
}

/** Mounted inside the existing authenticated admin /api boundary. */
export default async function routes(fastify: FastifyInstance): Promise<void> {
    const sharedCards = new ContentManagementSharedReads()
    const storeIdentities = new WeakMap<object, number>()
    let nextStoreIdentity = 0
    // The legacy server also registers web_api but does not install the global admin guard.
    fastify.addHook("onRequest", async (request, reply) => {
        if (!hasManagementSession(request)) return reply.status(401).send({ error: "unauthorized" })
    })
    fastify.get("/", async (request, reply) => {
        const q = request.query as Record<string, unknown>
        const offset = q.offset === undefined ? 0 : Number(q.offset)
        const limit = q.limit === undefined ? 50 : Number(q.limit)
        const textFields = ["search", "type", "readiness", "candidatesOnly", "julyOnly", "offset", "limit", "group", "status", "includeMembers", "view", "series", "keys", "keyOrder", "sort", "projection"]
        const groups = CONTENT_PRESENTATION_GROUPS.filter(group => String(group.key) !== "all")
        const legacyMembers = q.includeMembers === "true"
            || (q.includeMembers === undefined && typeof q.type === "string" && isMemberType(q.type))
        if (Object.keys(q).some(key => !textFields.includes(key))
            || textFields.some(key => q[key] !== undefined && typeof q[key] !== "string")
            || (q.offset !== undefined && !/^\d+$/.test(q.offset as string))
            || (q.limit !== undefined && !/^\d+$/.test(q.limit as string))
            || !Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 200
            || ((q.search as string | undefined)?.length ?? 0) > 200 || ((q.type as string | undefined)?.length ?? 0) > 100
            || (q.view !== undefined && q.view !== "series")
            || (q.series !== undefined && !/^[a-f0-9]{24}$/.test(q.series as string))
            || (q.keys !== undefined && ((q.keys as string).length > 20000 || ((q.keys as string) !== ""
                && ((q.keys as string).split(",").length > 200 || (q.keys as string).split(",").some(key => !/^[a-z_]+:\d+$/.test(key) || key.length > 100)))))
            || (q.keyOrder !== undefined && !["true", "false"].includes(q.keyOrder as string))
            || (q.keyOrder === "true" && q.keys === undefined)
            || (q.sort !== undefined && !["relevance", "dateDesc", "dateAsc"].includes(q.sort as string))
            || (q.projection !== undefined && q.projection !== "cards")
            || (q.projection === "cards" && legacyMembers)
            || (q.readiness !== undefined && !readinessValues.includes(q.readiness as string))
            || (q.candidatesOnly !== undefined && !["true", "false"].includes(q.candidatesOnly as string))
            || (q.julyOnly !== undefined && !["true", "false"].includes(q.julyOnly as string))
            || (q.includeMembers !== undefined && !["true", "false"].includes(q.includeMembers as string))
            || (q.group !== undefined && q.group !== "all" && !groups.some(group => group.key === q.group))
            || (q.status !== undefined && !statusValues.includes(q.status as string))
            || (legacyMembers && ((q.group !== undefined && q.group !== "all") || (q.status !== undefined && q.status !== "all")
                || ["view", "series", "keys", "keyOrder", "sort"].some(key => q[key] !== undefined)))) {
            return reply.status(400).send({ error: "检索参数无效" })
        }
        const cards = q.projection === "cards"
        const build = async (checkpoint: () => Promise<void>, capture?: (snapshot: ContentManagementSnapshot) => void) => {
            await checkpoint()
            const store = contentOperations(), snapshot = store.managementSnapshot(), history = contentHistoryReadinessReader()
            capture?.(snapshot)
            const query = { type: q.type as string | undefined,
                readiness: q.readiness as string | undefined, candidatesOnly: q.candidatesOnly === "true",
                referenceWindow: q.julyOnly === "true" ? [julyPlan.referenceStartMs, julyPlan.referenceEndMsExclusive] as const : undefined }
            const permanentReference = { date: julyPlan.referenceDate, timeZone: julyPlan.timeZone,
                startMs: julyPlan.referenceStartMs, endMsExclusive: julyPlan.referenceEndMsExclusive }
            // Explicit advanced-member queries retain the existing technical listing.
            // Their potentially large product/mission set never enters the default card view.
            if (legacyMembers) {
                return { ...snapshot.list({ ...query, search: q.search as string | undefined, offset, limit }),
                    permanentReference, view: "members", groups: [], typeOptions: await typeOptions(store, q.group, true, history, checkpoint) }
            }
            // Parent search spans every category before explicit filters. The legacy member API above retains its original contract.
            const result = parentListing(snapshot, { ...query, type: undefined })
            const nowMs = snapshot.nowMs
            const presented = await readBatch(result.rows, checkpoint, row => {
                let publication = publicationPresentation(row, nowMs, history)
                if (associationIndexUnavailable(store, row.key) && publication.status !== "enabled") publication = {
                    status: "blocked", label: "无法开放", canToggle: false,
                    reason: "活动与奖励箱关联资料不可用，不能开启；已有入口仍可关闭" }
                return { ...row, presentation: managementPresentation(row, history), publication,
                    primaryControl: primaryControl(row, publication, nowMs) }
            })
            const presentedByKey = new Map(presented.map(row => [row.key, row]))
            const linkedRow = (key: string) => {
                let value = presentedByKey.get(key)
                if (!value) {
                    const peer = snapshot.row(key)
                    if (!peer) return undefined
                    const publication = publicationPresentation(peer, nowMs, history)
                    value = { ...peer, presentation: managementPresentation(peer, history), publication,
                        primaryControl: primaryControl(peer, publication, nowMs) }
                    presentedByKey.set(key, value)
                }
                return value
            }
            const linked = await readBatch(presented, checkpoint, row => {
                const association = history.boxAssociation(row.key)
                if (!association) return { ...row, linkedActivity: undefined }
                const parent = linkedRow(association.parentKey)
                const box = linkedRow(association.boxKey)
                const ready = association.relationshipMatches && participationReady(parent, nowMs, true) && participationReady(box, nowMs)
                if (row.primaryControl.kind === "publication" && row.primaryControl.status === "disabled"
                    && row.primaryControl.label !== "已到期" && !ready) {
                    const blocked = [parent, box].some(value => value?.primaryControl.status === "blocked")
                    const waiting = !participationReady(parent, nowMs, true) ? parent : box
                    const reason = !association.relationshipMatches ? "活动关卡与关联箱池的入口对应关系尚未完成一致性核对"
                        : waiting && ["pending", "blocked"].includes(waiting.primaryControl.status)
                            ? `${waiting.presentation.title}：${waiting.primaryControl.reason}`
                            : `${waiting?.presentation.title || "关联内容"}尚未完成新参与玩法的开放设置；既有领奖或兑换资格仍保留。`
                    row.primaryControl = { ...row.primaryControl, status: blocked ? "blocked" : "pending",
                        label: blocked ? "无法开放" : "待接入", canToggle: false,
                        reason }
                }
                return { ...row, linkedActivity: { ...association, grouped: true,
                    boxTitle: box?.presentation.title || "关联箱池",
                    operationNotice: "活动与奖励箱一起开关、保存截止时间；关闭或到期后停止新参与和新开箱，保留已获得奖励与原有进度。" } }
            })
            const currentPass = presented.find(row => row.type === "pass_card_event" && row.publication.status === "enabled")
            if (currentPass) for (const row of presented) {
                if (row.type === "pass_card_event" && row.key !== currentPass.key && row.publication.status === "disabled") {
                    row.publication.canToggle = false
                    row.publication.reason = "请先关闭当前已开启的通行证"
                    row.primaryControl.canToggle = false
                    row.primaryControl.reason = row.publication.reason
                }
            }
            const search = (q.search as string | undefined)?.trim() || "", terms = discoveryTerms(search)
            const discovery = contentDiscoveryReader()
            const discovered = await readBatch(linked, checkpoint, row => {
                const match = discovery.match(row, terms)
                return { ...row, discovery: discovery.meta(row), searchMatch: match }
            })
            const searched = discovered.filter(row => row.searchMatch.matched)
            const inGroup = (row: typeof linked[number]) => !q.group || q.group === "all" || row.presentation.group === q.group
            const inStatus = (row: typeof linked[number]) => !q.status || q.status === "all"
                || (q.status === "unsupported" ? ["pending", "blocked"].includes(row.primaryControl.status) : row.primaryControl.status === q.status)
            const inType = (row: typeof linked[number]) => !q.type || row.type === q.type
            const counts = (rows: typeof linked) => ({ total: rows.filter(inStatus).length,
                enabled: rows.filter(row => row.primaryControl.status === "enabled").length,
                disabled: rows.filter(row => row.primaryControl.status === "disabled").length,
                pending: rows.filter(row => row.primaryControl.status === "pending").length,
                blocked: rows.filter(row => row.primaryControl.status === "blocked").length,
                // Retain the old aggregate/filter for technical API clients.
                unsupported: rows.filter(row => ["pending", "blocked"].includes(row.primaryControl.status)).length })
            const scopeRows = searched.filter(inGroup), categoryRows = scopeRows.filter(inType)
            const orderedKeys = q.keys === undefined ? null : new Map((q.keys as string).split(",").filter(Boolean).map((key, index) => [key, index]))
            const inSelection = (row: typeof discovered[number]) => (!orderedKeys || orderedKeys.has(row.key))
                && (q.series === undefined || row.discovery.seriesKey === q.series)
            const selectedRows = categoryRows.filter(inSelection), selectedUniverse = searched.filter(row => inType(row) && inSelection(row))
            const priority: Record<PublicationStatus, number> = { enabled: 0, disabled: 1, pending: 2, blocked: 3 }
            // Explicit dates preserve catalog order for ties; default ordering retains relevance/status priority.
            const filtered = selectedRows.filter(inStatus)
                .sort((left, right) => {
                    if (!terms.length && q.keyOrder === "true" && orderedKeys && (!q.sort || q.sort === "relevance"))
                        return orderedKeys.get(left.key)! - orderedKeys.get(right.key)!
                    if (q.sort === "dateDesc" || q.sort === "dateAsc") {
                        if (left.originalStartMs === null && right.originalStartMs !== null) return 1
                        if (right.originalStartMs === null && left.originalStartMs !== null) return -1
                        if (left.originalStartMs !== null && right.originalStartMs !== null)
                            return (left.originalStartMs - right.originalStartMs) * (q.sort === "dateDesc" ? -1 : 1)
                        return 0
                    }
                    return (terms.length ? right.searchMatch.score - left.searchMatch.score : 0)
                        || priority[left.primaryControl.status] - priority[right.primaryControl.status]
                })
            const hydrate = (value: typeof discovered[number]) => {
                const { searchMatch, ...row } = value
                const actionLabels = { visible: "入口", enter: "参与玩法", claim: row.key === "gacha:100" ? "续完已付乐享扭蛋" : "领取奖励", exchange: "兑换奖励" }
                const limitations = CONTENT_ACTIONS.flatMap(action => {
                    const review = history.get(row.key, [action])
                    return review.status === "blocked" ? review.reasons.map(reason => `${actionLabels[action]}：${reason}`) : []
                })
                return { ...row, discovery: { ...discovery.view(row), matchReasons: searchMatch.reasons },
                    limitations: [...new Set(limitations)], deadlineControl: deadlinePresentation(store, row, snapshot, history),
                    rightsNotice: retainedRightsNotice(row) }
            }
            const seriesGroups = q.view === "series" ? groupContentSeries(filtered) : undefined
            const responseRows = seriesGroups ? [] : await readBatch(filtered.slice(offset, offset + limit), checkpoint, hydrate)
            const responseSeries = seriesGroups ? await readBatch(seriesGroups.slice(offset, offset + limit), checkpoint,
                group => cards ? (({ preview: _preview, ...summary }) => summary)(group) : { ...group, preview: hydrate(group.preview) }) : undefined
            return { ...result, rows: responseRows,
                total: seriesGroups ? seriesGroups.length : filtered.length, contentTotal: filtered.length, view: seriesGroups ? "series" : "parents",
                ...(responseSeries ? { seriesGroups: responseSeries } : {}),
                typeOptions: await typeOptions(store, q.group, false, history, checkpoint),
                statusCounts: { ...counts(selectedRows), total: selectedRows.length },
                groups: [{ key: "all", label: "全部内容", ...counts(selectedUniverse) },
                    ...groups.map(group => ({ ...group, ...counts(selectedUniverse.filter(row => row.presentation.group === group.key)) }))],
                searchInfo: { query: search, terms, unfilteredTotal: searched.length, scopeTotal: scopeRows.length,
                    ...(discovery.verificationNotice ? { verificationNotice: discovery.verificationNotice } : {}) },
                permanentReference }
        }
        if (!cards) return runContentManagementRead(request, reply, build)
        const store = contentOperations()
        let identity = storeIdentities.get(store)
        if (identity === undefined) { identity = ++nextStoreIdentity; storeIdentities.set(store, identity) }
        // Every browser has already passed the management guard. Revisions keep
        // later requests from joining a read captured before an operator write.
        const sharedKey = JSON.stringify([identity, store.digest, store.revision(),
            Object.keys(q).sort().map(key => [key, q[key]])])
        const serializeCards = async (checkpoint: () => Promise<void>) => {
            for (let attempt = 0; attempt < 2; attempt++) {
                let captured: ContentManagementSnapshot | undefined
                const result = await build(checkpoint, snapshot => { captured = snapshot })
                const body = JSON.stringify(projectContentManagementCards(result))
                const nowMs = Date.now()
                // Time can change without a revision. Never share an enabled
                // card after a deadline crossed during cooperative construction.
                if (captured && nowMs >= captured.nowMs && nowMs < captured.nextChangeAtMs) return body
            }
            throw new ContentOperationError("开放状态正在到期更新，请刷新后重试", 409)
        }
        let body: string
        try { body = await sharedCards.read(request, reply, sharedKey, serializeCards) }
        catch (error) {
            if (!(error instanceof ContentSharedReadOversized)) throw error
            body = await runContentManagementRead(request, reply, serializeCards)
        }
        return reply.header("Cache-Control", "private, no-store").type("application/json; charset=utf-8").send(body)
    })
    fastify.get("/:key/discovery", async (request, reply) => {
        if (Object.keys(request.query as Record<string, unknown>).length) return reply.status(400).send({ error: "关联资料查询参数无效" })
        const key = (request.params as { key: string }).key
        if (!contentOperations().rows.has(key)) return reply.status(404).send({ error: "内容不存在" })
        return runContentManagementRead(request, reply, async checkpoint => {
            await checkpoint()
            return contentDiscoveryReader().details(key)
        })
    })
    fastify.get("/thumbnail/:file", async (request, reply) => {
        if (Object.keys(request.query as Record<string, unknown>).length) return reply.status(400).send({ error: "图片查询参数无效" })
        const file = (request.params as { file: string }).file
        if (!/^[a-f0-9]{64}\.webp$/.test(file)) return reply.status(400).send({ error: "图片标识无效" })
        const result = readContentPresentationThumbnail(file.slice(0, -5), key => contentOperations().rows.has(key))
        if (!result) return reply.status(404).send({ error: "该内容暂无缩略图" })
        reply.header("cache-control", "private, max-age=86400, immutable")
        reply.header("etag", result.etag)
        if (request.headers["if-none-match"] === result.etag) return reply.status(304).send()
        return reply.type(result.contentType).send(result.bytes)
    })
    fastify.get("/:key/image", async (request, reply) => {
        if (Object.keys(request.query as Record<string, unknown>).length) return reply.status(400).send({ error: "图片查询参数无效" })
        const key = (request.params as { key: string }).key
        if (!contentOperations().rows.has(key)) return reply.status(404).send({ error: "内容不存在" })
        const result = await readContentPresentationImage(key)
        if (!result) return reply.status(404).send({ error: "该内容暂无原图" })
        reply.header("cache-control", "private, max-age=300")
        reply.header("etag", result.etag)
        if (request.headers["if-none-match"] === result.etag) return reply.status(304).send()
        return reply.type(result.contentType).send(result.bytes)
    })
    fastify.get("/audit", async (request, reply) => {
        const q = request.query as Record<string, unknown>
        const limit = q.limit === undefined ? 50 : Number(q.limit)
        const beforeRevision = q.beforeRevision === undefined ? undefined : Number(q.beforeRevision)
        if (Object.keys(q).some(key => !["key", "beforeRevision", "limit"].includes(key))
            || Object.values(q).some(value => typeof value !== "string")
            || (q.key !== undefined && (!(q.key as string).trim() || (q.key as string).length > 200))
            || (q.limit !== undefined && !/^\d+$/.test(q.limit as string))
            || !Number.isSafeInteger(limit) || limit < 1 || limit > 200
            || (q.beforeRevision !== undefined && (!/^\d+$/.test(q.beforeRevision as string)
                || !Number.isSafeInteger(beforeRevision) || beforeRevision! < 1))) {
            return reply.status(400).send({ error: "审计参数无效" })
        }
        return contentOperations().audit({ key: q.key as string | undefined, beforeRevision, limit })
    })
    fastify.get("/:key/members", async (request, reply) => {
        if (Object.keys(request.query as Record<string, unknown>).length) return reply.status(400).send({ error: "范围查询不支持额外参数" })
        const key = (request.params as { key: string }).key
        const store = contentOperations(), row = store.rows.get(key)
        if (!row) return reply.status(404).send({ error: "内容不存在" })
        const questKeys = Object.entries(store.catalog.questMap).filter(([, parent]) => parent === key).map(([member]) => member).sort()
        const missionKeys = [...new Set(row.missionKeys ?? Object.entries(store.catalog.missionMap ?? {})
            .filter(([, parent]) => parent === key).map(([member]) => member))].sort()
        return { key, revision: store.revision(), catalogDigest: store.digest, questKeys, missionKeys }
    })
    fastify.patch("/:key/deadline", async (request, reply) => {
        try {
            const key = (request.params as { key: string }).key
            return await runPersistenceTransaction({ domain: "admin", operation: "content_deadline" },
                () => setDailyDeadline(contentOperations(), key, request.body, Date.now()))
        } catch (error) {
            if (error instanceof ContentOperationError) return reply.status(error.statusCode).send({ error: error.message })
            throw error
        }
    })
    fastify.patch("/:key/publication", async (request, reply) => {
        try {
            const key = (request.params as { key: string }).key
            return await runPersistenceTransaction({ domain: "admin", operation: "content_publication" },
                () => setDailyPublication(contentOperations(), key, request.body, Date.now()))
        } catch (error) {
            if (error instanceof ContentOperationError) return reply.status(error.statusCode).send({ error: error.message })
            throw error
        }
    })
    fastify.patch("/:key", async (request, reply) => {
        try {
            const key = (request.params as { key: string }).key
            const state = await runPersistenceTransaction({ domain: "admin", operation: "content_control" },
                () => contentOperations().update(key, request.body, Date.now()))
            return { state, revision: state.revision }
        } catch (error) {
            if (error instanceof ContentOperationError) return reply.status(error.statusCode).send({ error: error.message })
            throw error
        }
    })
}
