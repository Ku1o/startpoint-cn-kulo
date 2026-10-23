import { useEffect, useRef, useState } from "react"
import { Alert, Button, Drawer, Empty, Input, Modal, Pagination, Select, Skeleton, Space, Switch, Tag, Timeline, Tooltip, message } from "antd"
import { BellRing, ChevronRight, CircleAlert, Gift, ImageOff, ListChecks, RefreshCw, Search, Sparkles, Ticket } from "lucide-react"
import dayjs from "dayjs"
import { useLocation } from "react-router-dom"
import { ApiError, apiGet, apiPatch, apiPost } from "../api/client"
import { requestAdminLeave, useAdminEditGuard, useAdminNavigate } from "../lib/editGuard"
import { browserPreferenceStorage, FAVORITES_LIMIT, favoritePreference, readDiscoveryPreferences, recentPreference, writeDiscoveryPreferences } from "./content-discovery-preferences"
import type { ContentView, DiscoveryPreferences } from "./content-discovery-preferences"
import "./ContentOperations.css"

type Action = "visible" | "enter" | "claim" | "exchange"
type Readiness = "unverified" | "current_baseline" | "verified" | "blocked"
type Group = "all" | "events" | "gacha" | "missions" | "exchange"
type Status = "all" | "enabled" | "disabled" | "pending" | "blocked"
interface ActionOverride {
    enabled: boolean; readiness: Readiness; evidence: string; endsAtMs: number | null
    questKeys?: string[] | null; missionKeys?: string[] | null
}
interface State {
    readiness: Readiness; evidence: string; flags: Record<Action, boolean>; endsAtMs: number | null
    instanceId: string; revision: number; integrityError?: string; controlled?: boolean; published?: boolean
    questKeys?: string[] | null; missionKeys?: string[] | null
    actionOverrides?: Partial<Record<Action, ActionOverride>>
}
interface Presentation {
    title: string; subtitle?: string; group: Group; groupLabel: string; typeLabel: string
    imageUrl?: string | null; imageFallbackUrl?: string | null; imageAlt?: string
}
interface Control {
    kind: "publication" | "exchange" | null; enabled: boolean; canToggle: boolean
    reason: string; status: Exclude<Status, "all">; label: string
}
interface Row {
    key: string; name: string; type: string; id: number; state: State | null; presentation?: Presentation
    primaryControl?: Control; originalStartMs: number | null; originalEndMs: number | null
    effectiveFlags: Partial<Record<Action, boolean>> | null; limitations?: string[]; rightsNotice?: string
    linkedActivity?: { boxTitle: string; description: string; operationNotice: string; grouped: boolean }
    deadlineControl?: { canEdit: boolean; reason: string; endsAtMs: number | null; hasMixedDeadlines?: boolean; actionLabels?: string[] }
    discovery?: { seriesKey: string; seriesTitle: string; editionLabel?: string; highlights: Array<{ label: string; names: string[]; total: number }>; notes: string[]; matchReasons: string[] }
}
interface DiscoveryEntity { id: number; name: string; relation: string; aliases?: string[]; kind?: string }
interface DiscoveryDetails {
    characters: DiscoveryEntity[]
    rewards: DiscoveryEntity[]
    aliases: string[]; notes: string[]
}
interface GroupCount { key: Group; label: string; total: number; enabled: number; disabled: number; pending: number; blocked: number }
interface SeriesGroup { key: string; title: string; total: number; enabled: number; disabled: number; pending: number; blocked: number; firstStartMs: number | null; lastStartMs: number | null; preview?: Row }
interface Listing {
    revision: number; catalogDigest: string; total: number; rows: Row[]; types?: string[]
    groups?: GroupCount[]; typeOptions?: Array<{ value: string; label: string }>; statusCounts?: { enabled: number; disabled: number; pending: number; blocked: number }
    searchInfo?: { query: string; terms: string[]; scopeTotal: number; unfilteredTotal: number; verificationNotice?: string }
    view?: "series"; contentTotal?: number; seriesGroups?: SeriesGroup[]
}
interface AuditRow { revision: number; key: string; changedAtMs: number; before: State | null; after: State; reason: string }
interface Audit { rows: AuditRow[] }
interface ReloadState { epoch: number; updatedAtMs: number }
interface ReloadResult extends ReloadState { realtime: { applied: boolean; message?: string } }
export function scopePatchFields(questEdited: boolean, questKeys: string[], missionEdited: boolean, missionKeys: string[]) {
    return { ...(questEdited ? { questKeys: [...questKeys].sort() } : {}), ...(missionEdited ? { missionKeys: [...missionKeys].sort() } : {}) }
}
export function businessPatchFields(enabled: boolean, flags: Record<Action, boolean>, questEdited: boolean, questKeys: string[], missionEdited: boolean, missionKeys: string[]) {
    return enabled ? { flags, ...scopePatchFields(questEdited, questKeys, missionEdited, missionKeys) } : {}
}
/** A legacy controlled row owns all actions; a partial row owns only its supplied action keys. */
export function actionState(state: State | null | undefined, action: Action): ActionOverride | undefined {
    if (!state || state.controlled === false) return undefined
    if (state.actionOverrides !== undefined) {
        const value = state.actionOverrides[action]
        return value ? { enabled: value.enabled, readiness: value.readiness, evidence: value.evidence, endsAtMs: value.endsAtMs,
            questKeys: value.questKeys, missionKeys: value.missionKeys } : undefined
    }
    return { enabled: state.flags[action], readiness: state.readiness, evidence: state.evidence, endsAtMs: state.endsAtMs,
        questKeys: state.questKeys, missionKeys: state.missionKeys }
}
/** No missing action is serialized as false. Omitted old scope retains its previous exact value. */
export function actionPatchFields(action: Action | undefined, draft: ActionOverride, questEdited: boolean, questKeys: string[] | null, missionEdited: boolean, missionKeys: string[] | null) {
    return action === undefined ? { readiness: draft.readiness, evidence: draft.evidence } : {
        actionOverrides: { [action]: { enabled: draft.enabled, readiness: draft.readiness, evidence: draft.evidence, endsAtMs: draft.endsAtMs,
            ...(questEdited ? { questKeys: questKeys === null ? null : [...questKeys].sort() } : {}),
            ...(missionEdited ? { missionKeys: missionKeys === null ? null : [...missionKeys].sort() } : {}) } },
    }
}
export function auditActionChanges(before: State | null, after: State) {
    return (Object.keys(actions) as Action[]).map(action => ({ action, before: actionState(before, action) ?? null, after: actionState(after, action) ?? null }))
}
const actions: Record<Action, string> = { visible: "入口显示", enter: "参与玩法", claim: "领取奖励", exchange: "兑换奖励" }
export function contentActionLabel(key: string, action: Action): string {
    return key === "gacha:100" && action === "claim" ? "续完已付乐享扭蛋" : actions[action]
}
const groupOptions: Array<{ key: Group; label: string; description: string }> = [
    { key: "all", label: "全部内容", description: "浏览所有活动与卡池" },
    { key: "events", label: "活动", description: "剧情、讨伐与挑战关卡" },
    { key: "gacha", label: "扭蛋卡池", description: "角色与装备扭蛋" },
    { key: "missions", label: "任务与通行证", description: "修行、任务与赛季奖励" },
    { key: "exchange", label: "箱池与兑换", description: "奖池与票券兑换" },
]
const groupIcons = { all: Sparkles, events: Sparkles, gacha: Ticket, missions: ListChecks, exchange: Gift }
/** Only reviewed entry links are accepted; arbitrary route values never become API filters. */
export function contentRouteFilters(search: string) {
    const params = new URLSearchParams(search), term = params.get("search")?.trim()
    const group = groupOptions.find(item => item.key === params.get("group"))?.key
    const type = params.get("type") === "gacha" ? "gacha" : undefined
    return { search: term && term.length <= 200 ? term : "", group, type }
}
const PAGE_SIZE = 24
export const contentStatusName = (status?: string) => status === "enabled" ? "已开启" : status === "disabled" ? "已关闭" : status === "blocked" ? "无法开放" : "待接入"
const statusName = contentStatusName
export const contentControlLabel = (control?: Pick<Control, "status" | "label">) => control?.label || statusName(control?.status)
const statusColor = (status?: string) => status === "enabled" ? "green" : status === "blocked" ? "red" : status === "pending" ? "gold" : undefined
const titleOf = (row: Row) => row.presentation?.title || (/[\u3400-\u9fff]/.test(row.name) ? row.name : row.presentation?.typeLabel || "游戏内容")
const originalDateFormatter = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "long", day: "numeric" })
const dateText = (value: number | null) => value == null ? "未设置" : originalDateFormatter.format(value)
export function originalPeriodNeedsReview(row: Pick<Row, "originalStartMs" | "originalEndMs">) {
    return [row.originalStartMs, row.originalEndMs].some(value => value != null && originalDateFormatter.formatToParts(value).some(part => part.type === "year" && part.value === "2011"))
}
export function originalPeriod(row: Pick<Row, "originalStartMs" | "originalEndMs">) {
    if (row.originalStartMs == null && row.originalEndMs == null) return "暂无可靠档期资料"
    const source = `${row.originalStartMs == null ? "开始时间未记录" : dateText(row.originalStartMs)} — ${row.originalEndMs == null ? "结束时间未记录" : dateText(row.originalEndMs)}`
    return originalPeriodNeedsReview(row) ? `原始档期待核实（源记录：${source}）` : source
}
export function originalSeriesPeriod(firstStartMs: number | null, lastStartMs: number | null) {
    const source = `${dateText(firstStartMs)} — ${dateText(lastStartMs)}`
    return originalPeriodNeedsReview({ originalStartMs: firstStartMs, originalEndMs: lastStartMs }) ? `原始档期跨度待核实（源记录：${source}）` : `原档期跨度：${source}`
}
const deadlineFormatter = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
export function deadlineInputValue(endsAtMs: number | null) {
    return endsAtMs == null ? "" : new Date(endsAtMs + 8 * 3600000).toISOString().slice(0, 16)
}
export function parseContentDeadline(mode: "permanent" | "limited", input: string, nowMs = Date.now()): number | null {
    if (mode === "permanent") return null
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(input)) throw new Error("请选择完整的截止日期和时间。")
    const value = Date.parse(`${input}:00+08:00`)
    if (!Number.isSafeInteger(value) || deadlineInputValue(value) !== input) throw new Error("截止日期或时间无效。")
    if (value <= nowMs) throw new Error("截止时间需要晚于当前时间。")
    return value
}
export function contentDeadlineText(control: Row["deadlineControl"]) {
    return !control ? "" : control.canEdit === false ? "暂不可设置" : control.hasMixedDeadlines ? "入口与参与的截止时间不同" : control.endsAtMs == null ? "常驻开放" : `开放至 ${deadlineFormatter.format(control.endsAtMs)}`
}
export function contentDeadlineRequest(row: Pick<Row, "key" | "deadlineControl" | "presentation" | "name">, revision: number, digest: string, endsAtMs: number | null) {
    if (!row.deadlineControl?.canEdit) throw new Error("这项内容尚不能设置开放时间。")
    return { path: `/api/content/${encodeURIComponent(row.key)}/deadline`, payload: { expectedRevision: revision, catalogDigest: digest, endsAtMs,
        reason: `管理面板调整开放时间：${titleOf(row as Row)}` } }
}
export function contentSearchFilters(previous: string, next: string, status: Status, type?: string) {
    return !previous.trim() && next.trim() ? { status: "all" as Status, type: undefined, scope: "all" as const } : { status, type }
}
interface DiscoveryQueryOptions { view?: ContentView; keys?: string[]; keyOrder?: boolean; sort?: "relevance" | "dateDesc" | "dateAsc"; series?: string }
export function contentSearchParams(group: Group, status: Status, type: string | undefined, query: string, scope: "all" | "group", page: number, options: DiscoveryQueryOptions = {}) {
    const params = new URLSearchParams({ projection: "cards", group: query && scope === "all" ? "all" : group, status, search: query, offset: String((page - 1) * PAGE_SIZE), limit: String(PAGE_SIZE) })
    if (type) params.set("type", type)
    if (options.series) params.set("series", options.series)
    else if (options.view === "series") params.set("view", "series")
    if (options.keys !== undefined) {
        params.set("keys", options.keys.join(","))
        if (options.keyOrder && !query && (!options.sort || options.sort === "relevance")) params.set("keyOrder", "true")
    }
    if (options.sort) params.set("sort", options.sort)
    return params
}
export function discoveryRelationLabel(relation: string, reward = false): string {
    const labels: Record<string, string> = reward
        ? { up: "UP装备", pool: "池内可获得装备", drop: "掉落奖励", firstClear: "首次通关奖励", mission: "任务奖励", box: "箱池奖励", exchange: "兑换奖励", ranking: "排名奖励", overall: "全体奖励", pass: "通行证奖励" }
        : { up: "UP角色", pool: "卡池角色", exchange: "可兑换角色", reward: "可获得角色" }
    return labels[relation] || (reward ? "其他奖励" : "其他相关角色")
}
export function discoveryGroups(items: Array<{ name: string; relation: string }>, reward = false) {
    const groups = new Map<string, string[]>()
    for (const item of items) {
        const label = discoveryRelationLabel(item.relation, reward), names = groups.get(label) || []
        if (item.name && !names.includes(item.name)) names.push(item.name)
        groups.set(label, names)
    }
    return [...groups].filter(([, names]) => names.length)
}
export function discoveryDetailGroups(items: DiscoveryEntity[], query: string, reward = false) {
    const terms = query.normalize("NFKC").trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
    const groups = new Map<string, { label: string; total: number; items: DiscoveryEntity[] }>()
    for (const item of items) {
        const label = discoveryRelationLabel(item.relation, reward)
        let group = groups.get(label)
        if (!group) { group = { label, total: 0, items: [] }; groups.set(label, group) }
        group.total++
        const text = [item.name, ...(item.aliases || [])].join(" ").normalize("NFKC").toLocaleLowerCase()
        if (terms.every(term => text.includes(term))) group.items.push(item)
    }
    return [...groups.values()]
}
const friendlyError = (error: unknown, fallback = "操作未完成，请稍后重试。") => {
    if (error instanceof ApiError) {
        if (error.status === 401) return "管理面板登录已过期，请重新登录。"
        if (error.status === 409) return "设置刚刚发生变化，已刷新内容，请确认后重试。"
        if (error.status === 429) return "后台查询较多，请稍后点击重新加载。"
        if (error.status === 503) return "服务暂时无法完成操作，请稍后重试。"
    }
    return fallback
}
export function contentToggleRequest(row: Pick<Row, "key" | "name" | "type" | "state" | "primaryControl" | "presentation">, revision: number, digest: string) {
    const control = row.primaryControl
    if (!control?.canToggle || !control.kind) throw new Error("This content has no reviewed toggle")
    const enabled = !control.enabled
    const common = { expectedRevision: revision, catalogDigest: digest,
        reason: `管理面板${enabled ? "开启" : "关闭"}：${titleOf(row as Row)}` }
    if (control.kind === "publication") return { path: `/api/content/${encodeURIComponent(row.key)}/publication`, payload: { ...common, published: enabled } }
    const previous = actionState(row.state, "exchange")
    if (!previous) throw new Error("Missing reviewed exchange settings")
    return { path: `/api/content/${encodeURIComponent(row.key)}`, payload: { ...common,
        ...actionPatchFields("exchange", { ...previous, enabled }, false, null, false, null) } }
}
export function auditDescription(row: AuditRow): string {
    if (!row.before) return "设置初始开放内容"
    if ((row.before.published !== false) !== (row.after.published !== false)) return row.after.published === false ? "关闭内容入口" : "开启内容入口"
    const changed = auditActionChanges(row.before, row.after).filter(item => item.before?.enabled !== item.after?.enabled)
    if (changed.length) return changed.map(item => `${item.after?.enabled ? "开放" : "关闭"}${actions[item.action]}`).join("、")
    if (auditActionChanges(row.before, row.after).some(item => item.before?.endsAtMs !== item.after?.endsAtMs)) return "调整开放时间"
    return "更新玩法或奖励设置"
}
function ContentImage({ row }: { row: Row }) {
    const [failed, setFailed] = useState(false)
    const [fallback, setFallback] = useState(false)
    useEffect(() => { setFailed(false); setFallback(false) }, [row.key, row.presentation?.imageUrl, row.presentation?.imageFallbackUrl])
    const imageUrl = fallback ? row.presentation?.imageFallbackUrl : row.presentation?.imageUrl
    return <div className={`ops-card-image ops-card-image-${row.presentation?.group || "events"}`}>
        {imageUrl && !failed
            ? <img src={imageUrl} alt={row.presentation?.imageAlt || titleOf(row)} loading="lazy" decoding="async" onError={() => {
                if (!fallback && row.presentation?.imageFallbackUrl && row.presentation.imageFallbackUrl !== imageUrl) setFallback(true)
                else setFailed(true)
            }} />
            : <div className="ops-image-placeholder"><ImageOff size={23} aria-hidden="true" /><span>暂无游戏配图</span></div>}
    </div>
}
export default function ContentOperations() {
    const navigate = useAdminNavigate()
    const location = useLocation()
    const routeFilters = contentRouteFilters(location.search)
    const [data, setData] = useState<Listing>()
    const [group, setGroup] = useState<Group>(routeFilters.group || "events")
    const [status, setStatus] = useState<Status>("all")
    const [type, setType] = useState<string | undefined>(routeFilters.type)
    const [search, setSearch] = useState(routeFilters.search)
    const [query, setQuery] = useState(routeFilters.search)
    const [searchScope, setSearchScope] = useState<"all" | "group">(routeFilters.group ? "group" : "all")
    const [page, setPage] = useState(1)
    const [preferencesState, setPreferencesState] = useState(() => readDiscoveryPreferences(browserPreferenceStorage()))
    const [localFilter, setLocalFilter] = useState<"all" | "favorites" | "recent">("all")
    const [sort, setSort] = useState<"relevance" | "dateDesc" | "dateAsc">("relevance")
    const [seriesExpansion, setSeriesExpansion] = useState<{ key: string; parentQuery: string }>()
    const [seriesPage, setSeriesPage] = useState(1)
    const [seriesData, setSeriesData] = useState<Listing>()
    const [seriesLoading, setSeriesLoading] = useState(false)
    const [seriesError, setSeriesError] = useState("")
    const [loading, setLoading] = useState(true)
    const [loadError, setLoadError] = useState("")
    const [refresh, setRefresh] = useState(0)
    const [savingKey, setSavingKey] = useState<string>()
    const [toggleConfirmation, setToggleConfirmation] = useState<{ key: string; title: string; enabled: boolean;
        request: ReturnType<typeof contentToggleRequest>; rightsNotice?: string; linkedNotice?: string }>()
    const togglePending = useRef(false)
    const [changed, setChanged] = useState<Record<string, string>>({})
    const [selected, setSelected] = useState<Row>()
    const [selectedListing, setSelectedListing] = useState<Listing>()
    const [deadlineContext, setDeadlineContext] = useState<{ row: Row; listing: Listing }>()
    const [deadlineMode, setDeadlineMode] = useState<"permanent" | "limited">("permanent")
    const [deadlineInput, setDeadlineInput] = useState("")
    const [deadlineError, setDeadlineError] = useState("")
    const [audit, setAudit] = useState<Audit>()
    const [auditLoading, setAuditLoading] = useState(false)
    const [auditError, setAuditError] = useState("")
    const [auditRetry, setAuditRetry] = useState(0)
    const [discoveryDetails, setDiscoveryDetails] = useState<DiscoveryDetails>()
    const [discoveryLoading, setDiscoveryLoading] = useState(false)
    const [discoveryError, setDiscoveryError] = useState("")
    const [discoveryRetry, setDiscoveryRetry] = useState(0)
    const [detailQuery, setDetailQuery] = useState("")
    const [expandedDetailGroups, setExpandedDetailGroups] = useState<Record<string, boolean>>({})
    const [reloadState, setReloadState] = useState<ReloadState>()
    const [reloadError, setReloadError] = useState(false)
    const [notifyOpen, setNotifyOpen] = useState(false)
    const [notifying, setNotifying] = useState(false)
    const [cleanupEpoch, setCleanupEpoch] = useState<number>()
    const [retrying, setRetrying] = useState(false)
    const [notified, setNotified] = useState(false)
    const changedCount = Object.keys(changed).length
    const busy = !!savingKey || notifying || retrying
    const deadlineDirty = !!deadlineContext && (deadlineMode !== (deadlineContext.row.deadlineControl?.endsAtMs == null && !deadlineContext.row.deadlineControl?.hasMixedDeadlines ? "permanent" : "limited")
        || deadlineInput !== deadlineInputValue(deadlineContext.row.deadlineControl?.endsAtMs ?? null))
    useAdminEditGuard({ dirty: deadlineDirty, pending: busy, label: "内容运营" })
    const preferences = preferencesState.preferences
    const view = preferences.view
    const keyFilter = localFilter === "favorites" ? preferences.favorites.join(",") : localFilter === "recent" ? preferences.recent.join(",") : undefined
    const queryOptions: DiscoveryQueryOptions = { view, sort, keys: keyFilter === undefined ? undefined : keyFilter ? keyFilter.split(",") : [], keyOrder: localFilter === "recent" }
    const listingQuery = contentSearchParams(group, status, type, query, searchScope, page, queryOptions).toString()
    // An expansion belongs to the exact parent query that displayed it. A filter
    // change invalidates it during render, before effects can start child work.
    const expandedSeries = seriesExpansion?.parentQuery === listingQuery ? seriesExpansion.key : undefined
    const seriesQuery = expandedSeries && view === "series"
        ? contentSearchParams(group, status, type, query, searchScope, seriesPage, { ...queryOptions, series: expandedSeries }).toString() : undefined
    useEffect(() => {
        const filters = contentRouteFilters(location.search)
        if (!filters.search && !filters.group && !filters.type) return
        setSearch(filters.search); setQuery(filters.search); setGroup(filters.group || "events"); setType(filters.type)
        setSearchScope(filters.group ? "group" : "all"); setStatus("all"); setLocalFilter("all"); setPage(1)
    }, [location.search])
    useEffect(() => { const timer = window.setTimeout(() => { setQuery(search.trim()); setPage(1) }, 300); return () => window.clearTimeout(timer) }, [search])
    useEffect(() => {
        let active = true
        const controller = new AbortController()
        setLoading(true); setLoadError("")
        apiGet<Listing>(`/api/content/?${listingQuery}`, { signal: controller.signal }).then(value => {
            if (!active) return
            const lastPage = Math.max(1, Math.ceil(value.total / PAGE_SIZE))
            if (page > lastPage) { setPage(lastPage); return }
            setData(value)
        })
            .catch(error => { if (active) setLoadError(friendlyError(error, "暂时无法加载活动，请点击重新加载。")) })
            .finally(() => { if (active) setLoading(false) })
        return () => { active = false; controller.abort() }
    }, [listingQuery, refresh])
    useEffect(() => { setSeriesExpansion(undefined); setSeriesPage(1) }, [listingQuery])
    useEffect(() => {
        if (!seriesQuery) { setSeriesData(undefined); return }
        let active = true
        const controller = new AbortController()
        setSeriesLoading(true); setSeriesError(""); setSeriesData(undefined)
        apiGet<Listing>(`/api/content/?${seriesQuery}`, { signal: controller.signal }).then(value => {
            if (!active) return
            const lastPage = Math.max(1, Math.ceil(value.total / PAGE_SIZE))
            if (seriesPage > lastPage) { setSeriesPage(lastPage); return }
            setSeriesData(value)
        }).catch(error => { if (active) setSeriesError(friendlyError(error, "暂时无法读取系列内各期内容，请重试。")) })
            .finally(() => { if (active) setSeriesLoading(false) })
        return () => { active = false; controller.abort() }
    }, [seriesQuery, refresh])
    useEffect(() => {
        let active = true
        const controller = new AbortController()
        apiGet<ReloadState>("/api/server/clientReload", { signal: controller.signal }).then(value => { if (active) { setReloadState(value); setReloadError(false) } })
            .catch(() => { if (active) setReloadError(true) })
        return () => { active = false; controller.abort() }
    }, [refresh])
    useEffect(() => {
        if (!selected) return
        let active = true
        const controller = new AbortController()
        setAudit(undefined); setAuditLoading(true); setAuditError("")
        apiGet<Audit>(`/api/content/audit?key=${encodeURIComponent(selected.key)}&limit=20`, { signal: controller.signal }).then(value => { if (active) setAudit(value) })
            .catch(error => { if (active) setAuditError(friendlyError(error, "暂时无法读取操作记录。")) })
            .finally(() => { if (active) setAuditLoading(false) })
        return () => { active = false; controller.abort() }
    }, [selected, auditRetry])
    useEffect(() => { setDetailQuery(""); setExpandedDetailGroups({}) }, [selected?.key])
    useEffect(() => {
        if (!selected) return
        let active = true
        const controller = new AbortController()
        setDiscoveryDetails(undefined); setDiscoveryLoading(true); setDiscoveryError("")
        apiGet<DiscoveryDetails>(`/api/content/${encodeURIComponent(selected.key)}/discovery`, { signal: controller.signal }).then(value => { if (active) setDiscoveryDetails(value) })
            .catch(error => { if (active) setDiscoveryError(friendlyError(error, "暂时无法读取关联资料，可稍后重新打开详情。")) })
            .finally(() => { if (active) setDiscoveryLoading(false) })
        return () => { active = false; controller.abort() }
    }, [selected?.key, discoveryRetry])
    const changeGroup = (value: Group) => { setGroup(value); setType(undefined); if (search.trim()) setSearchScope(value === "all" ? "all" : "group"); setPage(1) }
    const changeSearch = (value: string) => {
        const next = contentSearchFilters(search, value, status, type)
        setSearch(value); setStatus(next.status); setType(next.type)
        if (next.scope) { setSearchScope(next.scope); setLocalFilter("all") }
    }
    const clearFilters = () => { setSearch(""); setQuery(""); setSearchScope("all"); setStatus("all"); setType(undefined); setLocalFilter("all"); setPage(1) }
    const updatePreferences = (update: (value: DiscoveryPreferences) => DiscoveryPreferences) => setPreferencesState(previous => {
        const next = update(previous.preferences)
        return { preferences: next, persistent: writeDiscoveryPreferences(next, browserPreferenceStorage()) }
    })
    const changeView = (next: ContentView) => { updatePreferences(value => ({ ...value, view: next })); setPage(1) }
    const favorite = (row: Row) => {
        if (!preferences.favorites.includes(row.key) && preferences.favorites.length >= FAVORITES_LIMIT) { message.warning("最多收藏200项，请先取消部分收藏。"); return }
        updatePreferences(value => favoritePreference(value, row.key))
    }
    function requestToggle(row: Row, context: Listing | undefined = data, childBusy = false) {
        if (!context || loading || childBusy || busy || togglePending.current || toggleConfirmation || !row.primaryControl?.canToggle) return
        setToggleConfirmation({ key: row.key, title: titleOf(row), enabled: !row.primaryControl.enabled,
            request: contentToggleRequest(row, context.revision, context.catalogDigest), rightsNotice: row.rightsNotice,
            linkedNotice: row.linkedActivity?.operationNotice })
    }
    async function confirmToggle() {
        if (!toggleConfirmation || busy || togglePending.current) return
        const confirmation = toggleConfirmation
        togglePending.current = true
        setSavingKey(confirmation.key)
        try {
            const request = confirmation.request
            await apiPatch(request.path, request.payload)
            updatePreferences(value => recentPreference(value, confirmation.key))
            setChanged(previous => ({ ...previous, [confirmation.key]: confirmation.title })); setNotified(false)
            message.success(`已${confirmation.enabled ? "开启" : "关闭"}「${confirmation.title}」`)
            setSelected(undefined); setRefresh(value => value + 1)
        } catch (error) { message.error(friendlyError(error)); setRefresh(value => value + 1) }
        finally { togglePending.current = false; setSavingKey(undefined); setToggleConfirmation(undefined) }
    }
    function openDeadline(row: Row, listing: Listing | undefined) {
        if (!listing || !row.deadlineControl?.canEdit || busy) return
        setDeadlineContext({ row, listing })
        setDeadlineMode(row.deadlineControl.endsAtMs == null && !row.deadlineControl.hasMixedDeadlines ? "permanent" : "limited")
        setDeadlineInput(deadlineInputValue(row.deadlineControl.endsAtMs)); setDeadlineError("")
    }
    async function saveDeadline() {
        if (!deadlineContext || busy) return
        let endsAtMs: number | null
        try { endsAtMs = parseContentDeadline(deadlineMode, deadlineInput) }
        catch (error) { setDeadlineError(error instanceof Error ? error.message : "请重新选择截止时间。"); return }
        const { row, listing } = deadlineContext
        setSavingKey(row.key); setDeadlineError("")
        try {
            const request = contentDeadlineRequest(row, listing.revision, listing.catalogDigest, endsAtMs)
            await apiPatch(request.path, request.payload)
            setChanged(previous => ({ ...previous, [row.key]: titleOf(row) })); setNotified(false)
            message.success("开放时间已保存，已关闭的内容仍需手动开启。")
            setDeadlineContext(undefined); setSelected(undefined); setRefresh(value => value + 1)
        } catch (error) {
            setDeadlineError(friendlyError(error, "开放时间未能保存，请刷新内容后重试。"))
            if (error instanceof ApiError && error.status === 409) { setDeadlineContext(undefined); setSelected(undefined); setRefresh(value => value + 1); message.warning("设置已变化，请重新打开详情后设置时间。") }
        } finally { setSavingKey(undefined) }
    }
    async function notifyPlayers() {
        if (!reloadState || notifying || savingKey) return
        setNotifying(true)
        try {
            const result = await apiPost<ReloadResult>("/api/server/clientReload", { expectedEpoch: reloadState.epoch, confirm: "RELOAD_ALL_CLIENTS" })
            setReloadState(result); setCleanupEpoch(result.realtime.applied ? undefined : result.epoch)
            setChanged({}); setNotified(true); setNotifyOpen(false)
            if (result.realtime.applied) message.success("已通知玩家重新登录，新内容将在登录后生效。")
            else message.warning("重登通知已保存，部分在线连接仍需重试断开。")
        } catch (error) { message.error(friendlyError(error)); setRefresh(value => value + 1) }
        finally { setNotifying(false) }
    }
    async function retryDisconnect() {
        if (cleanupEpoch === undefined || retrying) return
        setRetrying(true)
        try {
            const result = await apiPost<ReloadResult>("/api/server/clientReload/disconnect", { epoch: cleanupEpoch, confirm: "RELOAD_ALL_CLIENTS" })
            if (result.realtime.applied) { setCleanupEpoch(undefined); message.success("在线连接已清理。") }
            else message.warning("部分在线连接尚未断开，请稍后重试。")
        } catch (error) { message.error(friendlyError(error)); setRefresh(value => value + 1) }
        finally { setRetrying(false) }
    }
    const counts = data?.statusCounts
    const selectedName = groupOptions.find(item => item.key === group)?.label || "内容"
    const activeGroup = query && searchScope === "all" ? "all" : group
    const scopeName = searchScope === "all" || group === "all" ? "全部内容" : selectedName
    const typeName = data?.typeOptions?.find(item => item.value === type)?.label || "所选内容类型"
    const characterGroups = discoveryDetailGroups(discoveryDetails?.characters || [], detailQuery)
    const rewardGroups = discoveryDetailGroups(discoveryDetails?.rewards || [], detailQuery, true)
    const detailTotal = characterGroups.reduce((sum, item) => sum + item.total, 0) + rewardGroups.reduce((sum, item) => sum + item.total, 0)
    const detailMatches = characterGroups.reduce((sum, item) => sum + item.items.length, 0) + rewardGroups.reduce((sum, item) => sum + item.items.length, 0)
    const contentTotal = data?.contentTotal ?? data?.total ?? 0
    const hasResults = view === "series" ? !!data?.seriesGroups?.length : !!data?.rows?.length
    const localFilterName = localFilter === "favorites" ? "本机收藏" : "本机最近操作"
    const renderDetailGroup = (group: ReturnType<typeof discoveryDetailGroups>[number], section: string) => {
        if (!group.items.length) return null
        const key = `${section}:${group.label}`, expanded = expandedDetailGroups[key]
        const visible = expanded ? group.items : group.items.slice(0, 24)
        return <div className="ops-related-group" key={key}><h4>{group.label}<span>命中 {group.items.length} / 共 {group.total} 项</span></h4>
            <ul className="ops-related-items">{visible.map((item, index) => <li className="ops-related-item" key={`${item.kind || section}:${item.id}:${index}`}><span>{item.name}</span>{detailQuery.trim() && !!item.aliases?.length && <small>别名：{item.aliases.join("、")}</small>}</li>)}</ul>
            {group.items.length > 24 && <Button type="link" size="small" aria-expanded={!!expanded} aria-label={`${group.label}${expanded ? "收起" : "展开全部"}`} onClick={() => setExpandedDetailGroups(previous => ({ ...previous, [key]: !previous[key] }))}>{expanded ? "收起" : `展开全部 ${group.items.length} 项`}（当前显示 {visible.length} 项）</Button>}
        </div>
    }
    const renderRow = (row: Row, context: Listing | undefined, childBusy = false) => <article className={`ops-card ${view === "compact" || view === "series" ? "ops-compact-row" : ""} ${["pending", "blocked"].includes(row.primaryControl?.status || "") ? "ops-card-unavailable" : ""}`} key={row.key} aria-label={titleOf(row)}>
        <ContentImage row={row} />
        <div className="ops-card-body"><div className="ops-card-kicker"><span>{row.presentation?.typeLabel || "游戏内容"}</span><Tag color={statusColor(row.primaryControl?.status)}>{contentControlLabel(row.primaryControl)}</Tag></div>
            <h3 title={titleOf(row)}>{titleOf(row)}</h3>
            {row.presentation?.subtitle && <p className="ops-card-subtitle">{row.presentation.subtitle}</p>}
            {row.deadlineControl && <div className="ops-current-period"><span><strong>开放时间</strong>{contentDeadlineText(row.deadlineControl)}</span>
                <Tooltip title={!row.deadlineControl.canEdit ? row.deadlineControl.reason : undefined}><Button type="link" size="small" aria-label={`设置${titleOf(row)}开放时间`} disabled={!context || loading || childBusy || busy || !row.deadlineControl.canEdit} onClick={() => openDeadline(row, context)}>设置时间</Button></Tooltip></div>}
            <p className={`ops-original-period ${originalPeriodNeedsReview(row) ? "ops-period-needs-review" : ""}`}><span>原活动档期</span>{originalPeriod(row)}</p>
            {row.discovery?.editionLabel && <Tag className="ops-edition">{row.discovery.editionLabel}</Tag>}
            {!!row.discovery?.highlights?.length && <div className="ops-discovery-overview">{row.discovery.highlights.slice(0, 2).map(item => <p key={item.label}><strong>{item.label}</strong>：{item.names.slice(0, 3).join("、")}{item.total > Math.min(item.names.length, 3) ? ` 等 ${item.total} 项` : ""}</p>)}</div>}
            {!!query && !!row.discovery?.matchReasons?.length && <p className="ops-match-reasons"><strong>命中原因</strong>：{row.discovery.matchReasons.slice(0, 2).join("；")}</p>}
            {row.primaryControl?.reason && <p className="ops-unavailable-reason">{row.primaryControl.reason}</p>}
            {row.rightsNotice && <p className="ops-rights-notice">{row.rightsNotice}</p>}
            {row.linkedActivity && <p className="ops-rights-notice">{row.linkedActivity.description}（{row.linkedActivity.boxTitle}）。{row.linkedActivity.operationNotice}</p>}
        </div>
        <footer className="ops-card-footer"><Tooltip title={!row.primaryControl?.canToggle ? row.primaryControl?.reason || "暂未提供可用的开放设置" : undefined}><span className="ops-toggle"><Switch aria-label={`${row.primaryControl?.enabled ? "关闭" : "开启"}${titleOf(row)}`} checked={row.primaryControl?.enabled ?? false} disabled={loading || childBusy || busy || !row.primaryControl?.canToggle} loading={savingKey === row.key} onChange={() => requestToggle(row, context, childBusy)} /><span>{contentControlLabel(row.primaryControl)}</span></span></Tooltip>
            <div className="ops-card-links"><Button type="text" aria-label={`${preferences.favorites.includes(row.key) ? "取消收藏" : "收藏"}${titleOf(row)}`} aria-pressed={preferences.favorites.includes(row.key)} onClick={() => favorite(row)}>{preferences.favorites.includes(row.key) ? "已收藏" : "收藏"}</Button>
                <Button type="text" onClick={() => { setSelectedListing(context); setSelected(row) }}>详情 <ChevronRight size={15} /></Button></div></footer>
    </article>
    return <div className="content-ops">
        <header className="ops-heading"><div><p className="ops-eyebrow">游戏内容管理</p><h1>内容运营</h1><p>查找内容、调整开放时间与开关，再统一通知玩家重登。</p></div>
            <div className="ops-heading-actions"><Button onClick={() => navigate("/content/history")}>历史卡池资料</Button><Button icon={<RefreshCw size={16} />} loading={loading} disabled={busy} onClick={() => setRefresh(value => value + 1)}>刷新内容</Button></div></header>
        <section className={`ops-notify ${changedCount ? "ops-notify-pending" : ""}`} aria-label="应用内容更改">
            <div className="ops-notify-icon"><BellRing size={23} aria-hidden="true" /></div>
            <div className="ops-notify-copy"><strong>{changedCount ? `本次已修改 ${changedCount} 项内容` : notified ? "已发送重新登录通知" : "开关之后，让玩家重新登录"}</strong>
                <p>{changedCount ? "设置已保存。通知玩家重新登录后，他们就能看到新的开放内容。" : "可以先调整多项内容，再统一发送通知。玩家进度和服务器时间保持不变。"}</p></div>
            <Button type="primary" icon={<BellRing size={16} />} disabled={!reloadState || reloadError || busy} loading={notifying} onClick={() => setNotifyOpen(true)}>通知玩家重新登录</Button>
        </section>
        {reloadError && <Alert type="warning" showIcon message="暂时无法读取重登状态。" action={<Button size="small" disabled={busy} onClick={() => setRefresh(value => value + 1)}>重新读取</Button>} />}
        {cleanupEpoch !== undefined && <Alert type="warning" showIcon message="通知已保存，部分多人连接仍需断开。" action={<Button size="small" loading={retrying} onClick={retryDisconnect}>重试断开连接</Button>} />}
        <nav className="ops-groups" aria-label="内容分类">{groupOptions.map(item => {
            const Icon = groupIcons[item.key], number = !loading && !loadError ? data?.groups?.find(value => value.key === item.key)?.total : undefined
            return <button type="button" key={item.key} aria-pressed={activeGroup === item.key} className={`ops-group ${activeGroup === item.key ? "is-selected" : ""}`} onClick={() => changeGroup(item.key)}>
                <span className="ops-group-icon"><Icon size={22} aria-hidden="true" /></span><span><strong>{item.label}</strong><small>{item.description}</small></span><span className="ops-group-count">{number ?? "—"}</span>
            </button>
        })}</nav>
        <section className="ops-library" aria-label={`${query ? scopeName : selectedName}列表`}>
            <div className="ops-library-head"><div><h2>{query ? `${scopeName}搜索结果` : selectedName}</h2><span>{loading ? "正在读取…" : loadError ? "数量暂不可用" : view === "series" ? `${data?.total ?? 0} 个同名系列 · ${contentTotal} 项内容` : `共 ${contentTotal} 项`}</span></div>
                {!loading && !loadError && counts && <div className="ops-counts"><span><i className="ops-dot enabled" />开启 {counts.enabled}</span><span><i className="ops-dot disabled" />关闭 {counts.disabled}</span><span><i className="ops-dot pending" />待接入 {counts.pending}</span><span><i className="ops-dot blocked" />无法开放 {counts.blocked}</span></div>}
            </div>
            <div className="ops-toolbar"><Input prefix={<Search size={17} />} placeholder="搜索活动、卡池、角色、奖励或别名；空格分隔关键词" aria-label="搜索活动、角色、奖励或别名" value={search} maxLength={200} allowClear onChange={event => changeSearch(event.target.value)} />
                {!!search.trim() && <Select className="ops-search-scope" aria-label="搜索范围" value={searchScope} onChange={value => { setSearchScope(value); setPage(1) }} options={[{ value: "all", label: "搜索全部内容" }, { value: "group", label: `仅当前分类：${selectedName}` }]} />}
                <Select aria-label="按开放状态筛选" value={status} onChange={value => { setStatus(value); setPage(1) }} options={[{ value: "all", label: "全部状态" }, { value: "enabled", label: "已开启" }, { value: "disabled", label: "已关闭" }, { value: "pending", label: "待接入" }, { value: "blocked", label: "无法开放" }]} />
                {((data?.typeOptions?.length || 0) > 1 || type) && <Select aria-label="按内容类型筛选" placeholder="全部玩法类型" value={type} allowClear onChange={value => { setType(value); setPage(1) }} options={data?.typeOptions} />}
                {(search || status !== "all" || type || localFilter !== "all") && <Button type="text" onClick={clearFilters}>清除筛选</Button>}
            </div>
            <div className="ops-view-toolbar">
                <div className="ops-view-switch" role="group" aria-label="内容展示方式">{([{ value: "cards", label: "卡片" }, { value: "compact", label: "紧凑列表" }, { value: "series", label: "同名系列" }] as const).map(item => <Button key={item.value} type={view === item.value ? "primary" : "default"} aria-pressed={view === item.value} onClick={() => changeView(item.value)}>{item.label}</Button>)}</div>
                <Select aria-label="本机内容范围" value={localFilter} onChange={value => { setLocalFilter(value); setPage(1) }} options={[{ value: "all", label: "全部内容" }, { value: "favorites", label: `本机收藏（${preferences.favorites.length}）` }, { value: "recent", label: `本机最近操作（${preferences.recent.length}）` }]} />
                <Select aria-label="内容排序" value={sort} onChange={value => { setSort(value); setPage(1) }} options={[{ value: "relevance", label: localFilter === "recent" && !query ? "本机操作顺序" : "匹配优先" }, { value: "dateDesc", label: "原档期：新到旧" }, { value: "dateAsc", label: "原档期：旧到新" }]} />
            </div>
            {!preferencesState.persistent && <p className="ops-local-note" role="status">浏览器存储暂不可用，收藏、最近操作与布局仅在当前页面保留。</p>}
            {localFilter !== "all" && <p className="ops-local-note">仅限本浏览器；最近操作记录成功的开关修改。</p>}
            {view === "series" && <p className="ops-series-notice">展开查看各期；每期的开关、开放条件与资格各自独立。</p>}
            {data?.searchInfo?.verificationNotice && <Alert className="ops-verification-notice" type="warning" showIcon message={data.searchInfo.verificationNotice} />}
            {(query || status !== "all" || type || localFilter !== "all") && <div className="ops-search-feedback" aria-live="polite">
                <div className="ops-active-filters"><span>有效条件</span>{query && <><Tag>关键词：{query}</Tag><Tag>范围：{scopeName}</Tag></>}{status !== "all" && <Tag>状态：{statusName(status)}</Tag>}{type && <Tag>类型：{typeName}</Tag>}{localFilter !== "all" && <Tag>本机范围：{localFilterName}</Tag>}<Button size="small" type="link" onClick={clearFilters}>一键清除</Button></div>
                {query && <p>{loading ? "正在搜索…" : data?.searchInfo ? `全部内容命中 ${data.searchInfo.unfilteredTotal} 项，当前范围 ${data.searchInfo.scopeTotal} 项，筛选后 ${contentTotal} 项。` : `当前范围找到 ${contentTotal} 项。`}{!!data?.searchInfo?.terms?.length && ` 关键词：${data.searchInfo.terms.join("、")}（需同时匹配）。`}</p>}
                {query && data?.groups && <div className="ops-search-categories" aria-label="各分类搜索结果">{groupOptions.filter(item => item.key !== "all").map(item => <button type="button" key={item.key} aria-pressed={activeGroup === item.key} onClick={() => changeGroup(item.key)}>{item.label} {data.groups?.find(value => value.key === item.key)?.total ?? 0}</button>)}</div>}
            </div>}
            {loadError ? <div className="ops-load-error"><CircleAlert size={32} /><h3>{loadError}</h3><Button onClick={() => setRefresh(value => value + 1)}>重新加载</Button></div>
                : loading ? <div className="ops-card-grid" aria-busy="true">{Array.from({ length: 6 }, (_, index) => <div key={index} className="ops-skeleton"><Skeleton active paragraph={{ rows: 3 }} /></div>)}</div>
                    : !hasResults ? <Empty className="ops-empty" description={localFilter !== "all" && !keyFilter ? `${localFilterName}暂时为空。可先浏览全部内容。` : localFilter !== "all" ? `${localFilterName}中没有符合条件的当前内容；已移除或改名内容按服务器当前标识匹配。` : query ? data?.searchInfo?.unfilteredTotal ? "其他分类或状态下存在匹配内容，试试扩大范围或清除筛选。" : "没有找到同时符合这些关键词的内容，可尝试角色名、奖励名、别名或减少关键词。" : "当前分类或筛选条件下没有内容。"}>{query && searchScope === "group" && <Button onClick={() => { setSearchScope("all"); setPage(1) }}>搜索全部内容</Button>}<Button onClick={clearFilters}>清除筛选</Button></Empty>
                        : view === "series" ? <div className="ops-series-list">{data?.seriesGroups?.map(series => <section className="ops-series-group" key={series.key} aria-label={`同名系列：${series.title}`}>
                            <button type="button" className="ops-series-heading" aria-expanded={expandedSeries === series.key} aria-controls={`ops-series-${series.key}`} onClick={() => { setSeriesExpansion(previous => previous?.key === series.key && previous.parentQuery === listingQuery ? undefined : { key: series.key, parentQuery: listingQuery }); setSeriesPage(1) }}>
                                <ChevronRight size={18} aria-hidden="true" /><span><strong>{series.title}</strong><small>{series.total} 项内容 · 开启 {series.enabled} · 关闭 {series.disabled} · 待接入 {series.pending} · 无法开放 {series.blocked}</small><small className={originalPeriodNeedsReview({ originalStartMs: series.firstStartMs, originalEndMs: series.lastStartMs }) ? "ops-period-needs-review" : undefined}>{originalSeriesPeriod(series.firstStartMs, series.lastStartMs)}</small></span><span className="ops-series-expand">{expandedSeries === series.key ? "收起各期" : "展开各期"}</span>
                            </button>
                            {expandedSeries === series.key && <div className="ops-series-children" id={`ops-series-${series.key}`}>
                                {seriesError ? <Alert type="warning" message={seriesError} action={<Button onClick={() => setRefresh(value => value + 1)}>重试</Button>} /> : seriesLoading || !seriesData ? <Skeleton active paragraph={{ rows: 3 }} /> : <>
                                    {seriesData.rows.length ? seriesData.rows.map(row => renderRow(row, seriesData, seriesLoading)) : <Empty description="该系列当前条件下没有可显示的内容。" />}
                                    {seriesData.total > PAGE_SIZE && <Pagination className="ops-series-pagination" current={seriesPage} pageSize={PAGE_SIZE} total={seriesData.total} showSizeChanger={false} onChange={value => setSeriesPage(value)} showTotal={total => `本系列共 ${total} 项`} />}
                                </>}
                            </div>}
                        </section>)}</div>
                            : <div className={view === "compact" ? "ops-compact-list" : "ops-card-grid"}>{data?.rows.map(row => renderRow(row, data))}</div>}
            {!loadError && !!data?.total && <Pagination className="ops-pagination" current={page} pageSize={PAGE_SIZE} total={data.total} showSizeChanger={false} onChange={value => setPage(value)} showTotal={total => view === "series" ? `共 ${total} 个同名系列` : `共 ${total} 项内容`} />}
        </section>
        <details className="ops-help"><summary>操作说明与状态含义</summary><p>先设置开放时间，再按需手动开启或关闭。调整完成后统一通知玩家重新登录。开关与时间设置会保留原有进度及已获奖励，具体领奖、兑换与个人资格仍按各项原规则处理。</p><p>“待接入”需先完成开放设置；“无法开放”表示仍有未解决条件，原因见卡片和详情。同名系列只按内容类型与原名归组，各期分别操作。本机收藏与最近操作只保存内容标识，名称和状态以服务器当前资料为准。</p></details>
        <Drawer title="内容详情" open={!!selected} onClose={() => setSelected(undefined)} width="min(520px, 100vw)" rootClassName="ops-detail-drawer">
            {selected && <><ContentImage row={selected} /><h2 className="ops-detail-title">{titleOf(selected)}</h2><Space wrap><Tag>{selected.presentation?.typeLabel || "游戏内容"}</Tag><Tag color={statusColor(selected.primaryControl?.status)}>{contentControlLabel(selected.primaryControl)}</Tag></Space>
                {selected.presentation?.subtitle && <p className="ops-detail-subtitle">{selected.presentation.subtitle}</p>}
                {selected.primaryControl?.reason && <Alert type={selected.primaryControl.canToggle ? "info" : "warning"} showIcon message={selected.primaryControl.reason} />}
                {selected.rightsNotice && <Alert type="info" showIcon message={selected.rightsNotice} />}
                {selected.linkedActivity && <Alert type="info" showIcon message={`${selected.linkedActivity.description}（${selected.linkedActivity.boxTitle}）`} description={selected.linkedActivity.operationNotice} />}
                {!!selected.limitations?.length && <div className="ops-detail-limitations"><h3>尚未解决的条件</h3><ul>{selected.limitations.map(note => <li key={note}>{note}</li>)}</ul></div>}
                <section className="ops-detail-controls" aria-label="开放操作"><h3>开放操作</h3>
                    {selected.primaryControl?.canToggle && <Button block type={selected.primaryControl.enabled ? "default" : "primary"} disabled={loading || busy} loading={savingKey === selected.key} onClick={() => requestToggle(selected, selectedListing)}>{selected.primaryControl.enabled ? "关闭这项内容" : "开启这项内容"}</Button>}
                    {selected.deadlineControl && <div className="ops-deadline-settings"><Button block disabled={busy || loading || !selected.deadlineControl.canEdit} onClick={() => openDeadline(selected, selectedListing)}>设置开放时间</Button><p>{selected.deadlineControl.canEdit ? `${contentDeadlineText(selected.deadlineControl)}；保存时间后仍需手动开启。` : selected.deadlineControl.reason}</p></div>}
                </section>
                <dl className="ops-detail-facts"><div><dt>原活动档期</dt><dd className={originalPeriodNeedsReview(selected) ? "ops-period-needs-review" : undefined}>{originalPeriod(selected)}</dd></div>
                    {selected.discovery?.editionLabel && <div><dt>期次与复刻</dt><dd>{selected.discovery.editionLabel}</dd></div>}
                    <div><dt>当前开放内容</dt><dd>{Object.keys(actions).filter(key => selected.effectiveFlags?.[key as Action] === true).map(key => contentActionLabel(selected.key, key as Action)).join("、") || "暂未开放"}</dd></div>
                    {selected.deadlineControl && <div><dt>开放设置</dt><dd>{contentDeadlineText(selected.deadlineControl)}</dd></div>}
                    <div><dt>玩家进度</dt><dd>保留通关、领取和兑换记录</dd></div></dl>
                {!!selected.discovery?.matchReasons?.length && <div className="ops-detail-discovery"><h3>命中原因</h3><ul>{selected.discovery.matchReasons.map(note => <li key={note}>{note}</li>)}</ul></div>}
                <section className="ops-detail-discovery" aria-label="关联角色与奖励"><h3>关联资料</h3>
                    {discoveryLoading ? <Skeleton active paragraph={{ rows: 2 }} /> : discoveryError ? <Alert type="warning" message={discoveryError} action={<Button size="small" onClick={() => setDiscoveryRetry(value => value + 1)}>重试资料</Button>} /> : <>
                        {!!detailTotal && <><Input aria-label="查找关联角色或奖励" placeholder="查找关联角色或奖励的名称、别名" value={detailQuery} maxLength={100} allowClear onChange={event => setDetailQuery(event.target.value)} /><p className="ops-detail-filter-count" aria-live="polite">命中 {detailMatches} / 共 {detailTotal} 条关联资料，仅查找当前详情。</p></>}
                        {characterGroups.some(group => group.items.length) && <div><h3>关联角色</h3>{characterGroups.map(group => renderDetailGroup(group, "characters"))}</div>}
                        {rewardGroups.some(group => group.items.length) && <div><h3>奖励与兑换</h3>{rewardGroups.map(group => renderDetailGroup(group, "rewards"))}</div>}
                        {!!detailTotal && !detailMatches && <Empty description="没有匹配的关联角色或奖励，可尝试名称或别名。" />}
                        {!!discoveryDetails?.aliases?.length && <div><h4>别名</h4><p>{discoveryDetails.aliases.join("、")}</p></div>}
                        {[...new Set([...(selected.discovery?.notes || []), ...(discoveryDetails?.notes || [])])].map(note => <p key={note}>{note}</p>)}
                        {!detailTotal && !discoveryDetails?.aliases?.length && <p>暂无可靠的关联角色或奖励资料。</p>}
                    </>}
                </section>
                <Button className="ops-detail-favorite" block aria-pressed={preferences.favorites.includes(selected.key)} onClick={() => favorite(selected)}>{preferences.favorites.includes(selected.key) ? "取消本机收藏" : "收藏到本机"}</Button>
                <h3 className="ops-detail-section">最近操作</h3>
                {auditLoading ? <Skeleton active paragraph={{ rows: 3 }} /> : auditError ? <Alert type="warning" message={auditError} action={<Button size="small" onClick={() => setAuditRetry(value => value + 1)}>重试记录</Button>} /> : !audit?.rows.length ? <p className="ops-detail-subtitle">还没有操作记录</p>
                    : <Timeline items={audit.rows.map(item => ({ color: "gray", children: <><strong>{auditDescription(item)}</strong><p className="ops-history-time">{dayjs(item.changedAtMs).format("YYYY-MM-DD HH:mm")}</p></> }))} />}
            </>}
        </Drawer>
        <Modal title={`确认${toggleConfirmation?.enabled ? "开启" : "关闭"}内容？`} open={!!toggleConfirmation}
            onCancel={() => { if (!togglePending.current) setToggleConfirmation(undefined) }} onOk={confirmToggle}
            confirmLoading={!!savingKey} okText={`确认${toggleConfirmation?.enabled ? "开启" : "关闭"}`} cancelText="取消"
            okButtonProps={{ danger: toggleConfirmation?.enabled === false, disabled: busy }} cancelButtonProps={{ disabled: !!savingKey }}
            closable={!savingKey} maskClosable={!savingKey} keyboard={!savingKey}>
            {toggleConfirmation && <><p>即将{toggleConfirmation.enabled ? "开启" : "关闭"}「{toggleConfirmation.title}」。</p>
                <p>{toggleConfirmation.request.path.endsWith("/publication") ? "玩家重新登录后会看到新的开放状态。已有进度及原有领奖、兑换安排保留。" : "本次仅调整奖励兑换开关，已有进度和其他开放设置保持不变。"}</p>
                {toggleConfirmation.linkedNotice && <p>{toggleConfirmation.linkedNotice}</p>}
                {toggleConfirmation.rightsNotice && <p>{toggleConfirmation.rightsNotice}</p>}</>}
        </Modal>
        <Modal title="通知所有玩家重新登录？" open={notifyOpen} onCancel={() => { if (!notifying) setNotifyOpen(false) }} onOk={notifyPlayers} confirmLoading={notifying} okText="确认通知" cancelText="稍后通知" okButtonProps={{ disabled: !reloadState || !!savingKey }} closable={!notifying} maskClosable={!notifying}>
            <p>在线玩家会收到提示并返回标题界面，重新登录后加载最新内容。</p><p>你可以先完成所有开关调整，再统一通知。玩家账号、存档和服务器时间保持不变。</p>
        </Modal>
        <Modal title="设置开放时间" open={!!deadlineContext} onCancel={() => requestAdminLeave(() => { setDeadlineContext(undefined) })} onOk={saveDeadline} confirmLoading={!!savingKey} okText="保存时间设置" cancelText="取消" closable={!savingKey} maskClosable={!savingKey}>
            <div className="ops-deadline-form"><h3>{deadlineContext ? titleOf(deadlineContext.row) : ""}</h3>
                <label>开放方式<Select aria-label="开放方式" value={deadlineMode} options={[{ value: "permanent", label: "常驻开放" }, { value: "limited", label: "指定截止时间" }]} onChange={value => { setDeadlineMode(value); setDeadlineError("") }} /></label>
                {deadlineMode === "limited" && <label>截止时间（北京时间，UTC+8）<Input type="datetime-local" aria-label="截止时间" value={deadlineInput} step={60} onChange={event => { setDeadlineInput(event.target.value); setDeadlineError("") }} /></label>}
                <p>保存时间不会自动开启已关闭内容。手动开启后，指定截止时间到达时停止新参与；常驻内容持续开放，直到手动关闭。</p>
                <p>已有进度及原有领奖、兑换安排会保留。玩家重新登录后，原有时间栏显示新的开放设置。</p>
                {deadlineContext?.row.linkedActivity?.grouped && <p>关联活动与奖励箱的开放时间会一起保存。</p>}
                {deadlineError && <p className="ops-deadline-error" role="alert">{deadlineError}</p>}
            </div>
        </Modal>
    </div>
}
