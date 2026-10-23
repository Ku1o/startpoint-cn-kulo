import { useEffect, useRef, useState } from "react"
import { Alert, Button, Empty, Modal, Skeleton, Space, Switch, Tag } from "antd"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarDays, Check, ImageOff, RefreshCw } from "lucide-react"
import { ApiError, apiGet, apiPost } from "../api/client"
import { AdminPage } from "../components/AdminPage"
import { useAdminEditGuard } from "../lib/editGuard"
import "./TownThemes.css"

interface Theme {
    id: string; name: string; description: string; nativeTownContentId: number; thumbnailUrl: string
    originalPeriods: Array<{ nativeTownContentId: number; kind: "event" | "annual"; start: string; end: string }>
    annualEligible?: boolean
}
interface AnnualSchedule { themeId: string; start: string; end: string }
interface AnnualEndpoint { month: string; day: string; time: string }
interface AnnualDraft { themeId: string; start: AnnualEndpoint; end: AnnualEndpoint }
interface TownThemeState {
    schemaVersion: 1; revision: number; mode: "auto" | "manual"; themeId: string | null
    catalogDigest: string; updatedAtMs: number | null; themes: Theme[]; degradedReason?: string | null
    annualSchedules: AnnualSchedule[]; annualWarnings: Array<{ themeId: string; message: string }>; activeAnnualThemeId: string | null
}
interface Selection { mode: "auto" | "manual"; themeId: string | null }
interface Confirmation { before: TownThemeState; selection: Selection; annualSchedules: AnnualSchedule[] }
interface Notice { type: "success" | "warning" | "error" | "info"; text: string }
const endpoint = "/api/server/town-theme"
const queryKey = ["server", "town-theme"] as const
const sameSelection = (left: Selection, right: Selection) => left.mode === right.mode && left.themeId === right.themeId
const selectionName = (selection: Selection, themes: Theme[]) => selection.mode === "auto"
    ? "自动跟随日期" : themes.find(theme => theme.id === selection.themeId)?.name || "暂不可用的主题"
const themeName = (id: string, themes: Theme[]) => themes.find(theme => theme.id === id)?.name || "已失效的主题"
const annualEligible = (theme: Theme) => theme.annualEligible ?? theme.id !== "normal"
const DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
const ANNUAL_FORMAT = /^\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/
const EVENT_FORMAT = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/
const pad = (value: number) => String(value).padStart(2, "0")
const toEndpoint = (value: string): AnnualEndpoint => ({ month: value.slice(0, 2), day: value.slice(3, 5), time: value.slice(6) })
const fromSchedule = (value: AnnualSchedule): AnnualDraft => ({ themeId: value.themeId, start: toEndpoint(value.start), end: toEndpoint(value.end) })
const endpointValue = (value: AnnualEndpoint) => `${value.month}-${value.day} ${value.time}`
const scheduleKey = (values: AnnualSchedule[]) => JSON.stringify([...values].sort((a, b) => a.themeId.localeCompare(b.themeId)))
const draftKey = (values: AnnualDraft[]) => scheduleKey(values.map(value => ({ themeId: value.themeId, start: endpointValue(value.start), end: endpointValue(value.end) })))
const toSchedules = (values: AnnualDraft[]): AnnualSchedule[] => values.map(value => ({ themeId: value.themeId, start: endpointValue(value.start), end: endpointValue(value.end) }))
const annualText = (value: AnnualSchedule) => `每年 ${value.start} 至 ${value.end}${value.start > value.end ? "（跨年）" : value.start === value.end ? "（仅该时刻）" : ""}`
function annualSecond(value: string): number | null {
    if (!ANNUAL_FORMAT.test(value)) return null
    const [month, day, hour, minute, second] = value.split(/[- :]/).map(Number)
    if (month < 1 || month > 12 || day < 1 || day > DAYS[month - 1] || hour > 23 || minute > 59 || second > 59) return null
    return (DAYS.slice(0, month - 1).reduce((sum, days) => sum + days, 0) + day - 1) * 86400 + hour * 3600 + minute * 60 + second
}
function annualError(drafts: AnnualDraft[], themes: Theme[]) {
    const ranges: Array<{ name: string; segments: number[][] }> = []
    for (const draft of drafts) {
        const theme = themes.find(item => item.id === draft.themeId)
        if (!theme) return "存在已失效的主题设置，请先移除后保存。"
        if (!annualEligible(theme)) return "日常主城不能设置每年切换日期，请移除该设置。"
        const start = annualSecond(endpointValue(draft.start)), end = annualSecond(endpointValue(draft.end))
        if (start == null || end == null) return `请填写${theme.name}完整有效的开始和结束月日、时分秒；不支持2月29日。`
        const segments = start <= end ? [[start, end]] : [[start, 365 * 86400 - 1], [0, end]]
        for (const previous of ranges) if (previous.segments.some(left => segments.some(right => Math.max(left[0], right[0]) <= Math.min(left[1], right[1])))) {
            return `${previous.name}与${theme.name}的每年日期重叠，请调整。开始和结束时刻均包含在内。`
        }
        ranges.push({ name: theme.name, segments })
    }
    return ""
}

function AnnualDateFields({ label, value, onChange }: { label: string; value: AnnualEndpoint; onChange: (value: AnnualEndpoint) => void }) {
    const days = value.month ? DAYS[Number(value.month) - 1] : 31
    return <div className="town-annual-endpoint"><strong>{label}</strong><div className="town-annual-date-inputs">
        <label><span>月</span><select aria-label={`${label}月份`} value={value.month} onChange={event => {
            const month = event.target.value
            onChange({ ...value, month, day: value.day && Number(value.day) > DAYS[Number(month) - 1] ? "" : value.day })
        }}><option value="">选择月</option>{DAYS.map((_, index) => <option key={index} value={pad(index + 1)}>{index + 1}月</option>)}</select></label>
        <label><span>日</span><select aria-label={`${label}日期`} value={value.day} onChange={event => onChange({ ...value, day: event.target.value })}>
            <option value="">选择日</option>{Array.from({ length: days }, (_, index) => <option key={index} value={pad(index + 1)}>{index + 1}日</option>)}</select></label>
        <label className="town-annual-time"><span>时间（时:分:秒）</span><input aria-label={`${label}时间`} type="time" step="1" value={value.time}
            onChange={event => onChange({ ...value, time: event.target.value.length === 5 ? `${event.target.value}:00` : event.target.value })} /></label>
    </div></div>
}

function OriginalPeriods({ theme }: { theme: Theme }) {
    const periodText = (period: Theme["originalPeriods"][number]) => `${period.kind === "annual" ? "原版每年：" : ""}${period.start} 至 ${period.end}${period.kind === "annual" && period.start > period.end ? "（跨年）" : ""}`
    return <div className="town-theme-periods"><strong>原版档期 · 北京时间</strong>
        {!theme.originalPeriods.length ? <span>无原版档期限制，作为日常默认主城。</span> : <>
            <span>{periodText(theme.originalPeriods[0])}</span>
            {theme.originalPeriods.length > 1 && <details><summary>查看其余 {theme.originalPeriods.length - 1} 段原版档期</summary>
                <ul>{theme.originalPeriods.slice(1).map((period, index) => <li key={index}>{periodText(period)}</li>)}</ul></details>}
        </>}
    </div>
}

/** A proxy error page or incomplete response must never become a writable snapshot. */
function readState(value: unknown): TownThemeState {
    const state = value as TownThemeState | null
    if (!state || state.schemaVersion !== 1 || !Number.isSafeInteger(state.revision) || state.revision < 0
        || !["auto", "manual"].includes(state.mode) || typeof state.catalogDigest !== "string" || (!state.catalogDigest && !state.degradedReason)
        || !(state.updatedAtMs === null || (Number.isSafeInteger(state.updatedAtMs) && state.updatedAtMs >= 0))
        || !(state.degradedReason == null || typeof state.degradedReason === "string")
        || !Array.isArray(state.themes) || state.themes.some(theme => !theme || typeof theme.id !== "string" || !theme.id
            || typeof theme.name !== "string" || !theme.name || typeof theme.description !== "string"
            || !Number.isSafeInteger(theme.nativeTownContentId) || typeof theme.thumbnailUrl !== "string"
            || !(theme.annualEligible === undefined || typeof theme.annualEligible === "boolean")
            || !Array.isArray(theme.originalPeriods) || theme.originalPeriods.some(period => !period || !Number.isSafeInteger(period.nativeTownContentId)
                || !["event", "annual"].includes(period.kind) || typeof period.start !== "string" || typeof period.end !== "string"
                || !(period.kind === "event" ? EVENT_FORMAT : ANNUAL_FORMAT).test(period.start)
                || !(period.kind === "event" ? EVENT_FORMAT : ANNUAL_FORMAT).test(period.end)))
        || new Set(state.themes.map(theme => theme.id)).size !== state.themes.length
        || !Array.isArray(state.annualSchedules) || state.annualSchedules.some(schedule => !schedule || typeof schedule.themeId !== "string"
            || typeof schedule.start !== "string" || typeof schedule.end !== "string" || !ANNUAL_FORMAT.test(schedule.start) || !ANNUAL_FORMAT.test(schedule.end))
        || new Set(state.annualSchedules.map(schedule => schedule.themeId)).size !== state.annualSchedules.length
        || !Array.isArray(state.annualWarnings) || state.annualWarnings.some(warning => !warning || typeof warning.themeId !== "string" || typeof warning.message !== "string")
        || !(state.activeAnnualThemeId === null || typeof state.activeAnnualThemeId === "string")
        || (state.mode === "auto" ? state.themeId !== null : typeof state.themeId !== "string" || !state.themeId)) {
        throw new Error("Invalid town theme response")
    }
    return state
}

function readError(error: unknown) {
    if (error instanceof ApiError) {
        if (error.status === 401) return "管理登录已失效。重新登录后读取最新设置，当前选择会保留。"
        if (error.status === 403) return "当前账号没有读取主城外观的权限。"
        if (error.status === 429) return "读取较为频繁，请稍后重新读取。"
    }
    return "暂时无法读取主城外观。当前选择会保留，请检查网络后重新读取。"
}

function ThemeThumbnail({ theme }: { theme: Theme }) {
    const [failed, setFailed] = useState(false)
    useEffect(() => setFailed(false), [theme.thumbnailUrl])
    return <div className="town-theme-image">
        {theme.thumbnailUrl && !failed
            ? <img src={theme.thumbnailUrl} alt={`${theme.name}主城预览`} loading="lazy" decoding="async" onError={() => setFailed(true)} />
            : <span className="town-theme-image-fallback"><ImageOff size={26} aria-hidden="true" />预览暂不可用</span>}
    </div>
}

export default function TownThemes() {
    const queryClient = useQueryClient()
    const latest = useRef<TownThemeState>()
    const observed = useRef<TownThemeState>()
    const operationInFlight = useRef(false)
    const [selection, setSelection] = useState<Selection>()
    const [annualDrafts, setAnnualDrafts] = useState<AnnualDraft[]>()
    const [confirmation, setConfirmation] = useState<Confirmation>()
    const [notice, setNotice] = useState<Notice>()
    const [readRequired, setReadRequired] = useState(false)
    const [resolving, setResolving] = useState(false)
    const query = useQuery({
        queryKey,
        queryFn: async ({ signal }) => {
            const state = readState(await apiGet<unknown>(endpoint, { signal }))
            if (latest.current && state.revision < latest.current.revision && !state.degradedReason) throw new Error("Stale town theme response")
            latest.current = state
            return state
        },
        retry: false,
        refetchOnWindowFocus: false,
        staleTime: 0,
    })
    const data = query.data
    useEffect(() => {
        if (!data) return
        const before = observed.current
        setSelection(previous => !previous || (before && sameSelection(previous, before)) ? { mode: data.mode, themeId: data.themeId } : previous)
        setAnnualDrafts(previous => !previous || (before && draftKey(previous) === scheduleKey(before.annualSchedules)) ? data.annualSchedules.map(fromSchedule) : previous)
        observed.current = data
        setReadRequired(false)
        // Any new snapshot requires a fresh, explicit confirmation.
        setConfirmation(previous => previous && (previous.before.revision !== data.revision || previous.before.catalogDigest !== data.catalogDigest)
            ? undefined : previous)
    }, [data, query.dataUpdatedAt])

    const mutation = useMutation({
        retry: false,
        mutationFn: async (request: Confirmation) => {
            await queryClient.cancelQueries({ queryKey })
            return readState(await apiPost<unknown>(endpoint, {
                expectedRevision: request.before.revision, catalogDigest: request.before.catalogDigest,
                mode: request.selection.mode, themeId: request.selection.themeId, annualSchedules: request.annualSchedules, confirmation: "APPLY_TOWN_THEME",
            }))
        },
    })
    const pending = mutation.isPending || resolving
    const annualDirty = Boolean(data && annualDrafts && draftKey(annualDrafts) !== scheduleKey(data.annualSchedules))
    const dirty = Boolean(selection && data && (!sameSelection(selection, data) || annualDirty))
    const scheduleError = data && annualDrafts ? annualError(annualDrafts, data.themes) : ""
    const selectedMissing = selection?.mode === "manual" && !data?.themes.some(theme => theme.id === selection.themeId)
    useAdminEditGuard({ dirty, pending, label: "主城外观" })

    const reread = async () => {
        if (operationInFlight.current || pending) return
        setConfirmation(undefined)
        await query.refetch()
    }
    const apply = async () => {
        if (!confirmation || operationInFlight.current || pending || readRequired || query.isFetching || query.isError || data?.degradedReason) return
        const request = confirmation
        const current = latest.current
        if (!current || current.revision !== request.before.revision || current.catalogDigest !== request.before.catalogDigest
            || !selection || !sameSelection(selection, request.selection) || !annualDrafts || draftKey(annualDrafts) !== scheduleKey(request.annualSchedules)) {
            setConfirmation(undefined)
            setNotice({ type: "warning", text: "设置或主题列表已变化，请检查最新内容后重新确认。" })
            return
        }
        operationInFlight.current = true
        setNotice(undefined)
        try {
            const result = await mutation.mutateAsync(request)
            // Do not trust an old or mismatched success payload as confirmation of this write.
            if (result.revision <= request.before.revision || (latest.current && result.revision < latest.current.revision) || !sameSelection(result, request.selection)
                || result.catalogDigest !== request.before.catalogDigest || scheduleKey(result.annualSchedules) !== scheduleKey(request.annualSchedules)) throw new Error("Unexpected town theme result")
            latest.current = result
            queryClient.setQueryData(queryKey, result)
            setSelection({ mode: result.mode, themeId: result.themeId })
            setAnnualDrafts(result.annualSchedules.map(fromSchedule))
            setNotice({ type: "success", text: "主城外观已保存，玩家下次正常登录后生效。" })
        } catch (error) {
            setReadRequired(true)
            if (error instanceof ApiError && error.status === 400) {
                setReadRequired(false)
                setNotice({ type: "error", text: `保存未完成：${error.message} 当前选择和每年日期草稿已保留。` })
            } else if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 409) {
                setNotice({ type: "error", text: error.status === 401
                    ? "管理登录已失效，保存未获确认。请重新登录并读取最新设置，再重新确认。当前选择已保留。"
                    : error.status === 403 ? "当前账号没有修改权限。当前选择已保留，请重新读取设置后再确认。"
                        : "保存未完成。请重新读取最新设置后检查选择，再重新确认。" })
            } else {
                setResolving(true)
                const result = await query.refetch()
                if (result.isSuccess) {
                    setReadRequired(false)
                    setNotice({ type: "warning", text: error instanceof ApiError && error.status === 409
                        ? "设置或主题列表刚刚发生变化，已读取最新设置。你的选择和每年日期草稿已保留，请核对后重新确认。"
                        : `保存结果未获确认，已读回当前设置：${selectionName(result.data, result.data.themes)}。你的选择和每年日期草稿已保留；如仍需调整，请重新确认。` })
                } else {
                    setNotice({ type: "error", text: "保存结果尚不确定，读取最新设置也未完成。请先重新读取，当前选择已保留。" })
                }
            }
        } finally {
            operationInFlight.current = false
            setResolving(false)
            setConfirmation(undefined)
        }
    }
    const choose = (next: Selection) => {
        if (pending || operationInFlight.current) return
        setSelection(next)
        setConfirmation(undefined)
        setNotice(undefined)
    }
    const changeAnnual = (themeId: string, value?: AnnualDraft) => {
        if (pending || operationInFlight.current) return
        setAnnualDrafts(previous => [...(previous || []).filter(item => item.themeId !== themeId), ...(value ? [value] : [])])
        setConfirmation(undefined)
        setNotice(undefined)
    }
    const blocked = pending || query.isFetching || query.isError || readRequired || !data || Boolean(data.degradedReason) || !selection || !annualDrafts || !dirty || selectedMissing || Boolean(scheduleError)
    const updatedText = data?.updatedAtMs == null ? "尚未手动调整" : `最近调整：${new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).format(data.updatedAtMs)}（北京时间）`
    const confirmationWarnings = confirmation ? [...new Set(confirmation.before.annualWarnings
        .filter(warning => confirmation.annualSchedules.some(schedule => schedule.themeId === warning.themeId))
        .map(warning => themeName(warning.themeId, confirmation.before.themes)))] : []

    return <AdminPage eyebrow="日常运营" title="主城外观"
        description="选择全服主城的外观与默认音乐，在玩家下次正常登录后生效。"
        actions={<Button icon={<RefreshCw size={15} aria-hidden="true" />} onClick={() => void reread()}
            loading={query.isFetching} disabled={pending}>重新读取</Button>}>
        <div className="town-theme-page">
            <Alert showIcon type="info" message="保留玩家自选音乐"
                description="外观切换会调整主题默认音乐；玩家已在本地选择的背景音乐会保留。此操作不要求在线玩家立即重登。" />
            {notice && <Alert showIcon role="status" type={notice.type} message={notice.text} />}
            {query.isError && <Alert showIcon role="alert" type="error" message={readError(query.error)} />}
            {query.isLoading && <Skeleton active paragraph={{ rows: 5 }} />}
            {data && selection && annualDrafts && <>
                <div className="town-theme-current" aria-live="polite">
                    <div><span className="town-theme-kicker">当前全服设置</span><strong>{selectionName(data, data.themes)}</strong>
                        <span className="town-theme-current-calendar">{data.mode === "manual" ? "手动选择优先；每年设置仅在自动模式下使用。"
                            : data.activeAnnualThemeId ? `当前命中每年设置：${themeName(data.activeAnnualThemeId, data.themes)}` : "当前未命中自定义每年设置，沿用原版档期规则。"}</span></div>
                    <span>{updatedText}</span>
                </div>
                {data.degradedReason && <Alert showIcon type="warning" message="主题目录或设置暂不可用，当前页面仅供查看。"
                    description="登录时将按自动规则显示。请核查并修复主题目录或设置后，重新读取；恢复正常前无法保存。" />}
                <fieldset className="town-theme-options" disabled={pending}>
                    <legend>选择主城外观</legend>
                    <label className={`town-theme-auto ${selection.mode === "auto" ? "is-selected" : ""}`}>
                        <input type="radio" name="town-theme" checked={selection.mode === "auto"}
                            onChange={() => choose({ mode: "auto", themeId: null })} />
                        <CalendarDays size={25} aria-hidden="true" />
                        <span className="town-theme-auto-copy"><strong>自动跟随日期</strong><span>优先按已保存的每年设置切换；未命中时，按真实日期沿用原版档期规则。</span></span>
                        {data.mode === "auto" && <Tag>当前设置</Tag>}
                    </label>
                    <div className="town-theme-grid">
                        {data.themes.map(theme => {
                            const selected = selection.mode === "manual" && selection.themeId === theme.id
                            const current = data.mode === "manual" && data.themeId === theme.id
                            return <article key={theme.id} className={`town-theme-card ${selected ? "is-selected" : ""}`}>
                                <label className="town-theme-card-choice">
                                <input type="radio" name="town-theme" checked={selected}
                                    onChange={() => choose({ mode: "manual", themeId: theme.id })} aria-label={theme.name} />
                                <ThemeThumbnail theme={theme} />
                                <span className="town-theme-card-copy"><span className="town-theme-card-title"><strong>{theme.name}</strong>
                                    {selected && <Check size={18} aria-hidden="true" />}</span>
                                    <span className="town-theme-card-description">{theme.description}</span>
                                    {current && <Tag>当前设置</Tag>}
                                </span>
                                </label>
                                <OriginalPeriods theme={theme} />
                            </article>
                        })}
                    </div>
                </fieldset>
                {!data.themes.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂时没有可手动选择的主题，可使用自动跟随日期。" />}
                {selectedMissing && <Alert showIcon type="warning" message="原先选择的主题暂不可用，请选择其他主题或自动跟随日期。" />}
                <section className="town-annual-section" aria-labelledby="town-annual-title">
                    <header><h2 id="town-annual-title">每年自动切换</h2><p>设置每年重复的月日和时间，不需要选择年份。手动选择主城时，以手动选择为准；未设置或未命中时沿用原版档期。</p>
                        <p>北京时间（UTC+8），精确到秒；开始和结束时刻均包含在内，支持跨年，各主题日期不能重叠，不支持2月29日。</p></header>
                    {data.annualWarnings.length > 0 && <div className="town-annual-warnings">
                        {data.annualWarnings.map((warning, index) => {
                            const remains = annualDrafts.some(item => item.themeId === warning.themeId)
                            return <Alert key={`${warning.themeId}:${index}`} showIcon type="warning" message={`${themeName(warning.themeId, data.themes)}：${warning.message}`}
                                description={remains ? "此项不能正常参与自动切换，可移除后保存。" : "此项已从当前草稿移除，保存后生效。"}
                                action={<Button disabled={!remains || pending || Boolean(data.degradedReason)} onClick={() => changeAnnual(warning.themeId)}>移除此设置</Button>} />
                        })}
                    </div>}
                    <div className="town-annual-list">
                        {data.themes.filter(annualEligible).map(theme => {
                            const draft = annualDrafts.find(item => item.themeId === theme.id)
                            const saved = data.annualSchedules.find(item => item.themeId === theme.id)
                            const start = draft && annualSecond(endpointValue(draft.start)), end = draft && annualSecond(endpointValue(draft.end))
                            return <fieldset key={theme.id} className="town-annual-editor" disabled={pending || Boolean(data.degradedReason)}>
                                <legend className="town-visually-hidden">{theme.name}每年自动切换设置</legend>
                                <div className="town-annual-editor-header"><div><strong>{theme.name}</strong><span>{saved ? `已保存：${annualText(saved)}` : "尚未设置自定义每年日期"}</span></div>
                                    <label className="town-annual-switch"><span>每年自动切换</span><Switch checked={Boolean(draft)} aria-label={`${theme.name}每年自动切换`}
                                        onChange={enabled => changeAnnual(theme.id, enabled ? { themeId: theme.id, start: { month: "", day: "", time: "00:00:00" }, end: { month: "", day: "", time: "23:59:59" } } : undefined)} /></label></div>
                                {draft ? <div className="town-annual-fields">
                                    <AnnualDateFields label={`${theme.name}开始`} value={draft.start} onChange={value => changeAnnual(theme.id, { ...draft, start: value })} />
                                    <AnnualDateFields label={`${theme.name}结束`} value={draft.end} onChange={value => changeAnnual(theme.id, { ...draft, end: value })} />
                                    <p className="town-annual-window">{start != null && end != null ? annualText({ themeId: theme.id, start: endpointValue(draft.start), end: endpointValue(draft.end) }) : "请填写开始和结束月日、时间后保存。"}</p>
                                </div> : <p className="town-annual-off">关闭表示不设置自定义每年日期，保留原版档期规则。</p>}
                            </fieldset>
                        })}
                        {annualDrafts.filter(item => !data.themes.some(theme => theme.id === item.themeId) || !annualEligible(data.themes.find(theme => theme.id === item.themeId)!)).map((draft, index) => <div key={draft.themeId} className="town-annual-unavailable">
                            <div><strong>{themeName(draft.themeId, data.themes)}设置 {index + 1}</strong><span>{annualText({ themeId: draft.themeId, start: endpointValue(draft.start), end: endpointValue(draft.end) })}</span>
                                <span>主题已不可用或不支持每年设置，请移除此项后保存。</span></div>
                            <Button disabled={pending || Boolean(data.degradedReason)} onClick={() => changeAnnual(draft.themeId)}>移除此设置</Button>
                        </div>)}
                    </div>
                    {scheduleError && <Alert showIcon type="warning" role="status" message={scheduleError} />}
                </section>
                <div className="town-theme-save">
                    <div className="town-theme-save-copy" aria-live="polite"><strong>{dirty ? `待保存：${selectionName(selection, data.themes)}${annualDirty ? "；每年日期有修改" : ""}` : "当前选择和每年日期已保存"}</strong>
                        <span>保存后于下次正常登录生效，当前在线主城不会立即切换。</span></div>
                    <Space wrap>
                        <Button disabled={!dirty || pending} onClick={() => { setSelection({ mode: data.mode, themeId: data.themeId }); setAnnualDrafts(data.annualSchedules.map(fromSchedule)); setNotice(undefined); setConfirmation(undefined) }}>放弃修改</Button>
                        <Button type="primary" disabled={Boolean(blocked)} loading={pending}
                            onClick={() => setConfirmation({ before: data, selection: { ...selection }, annualSchedules: toSchedules(annualDrafts) })}>保存主城外观</Button>
                    </Space>
                </div>
            </>}
        </div>
        <Modal title="确认保存全服主城外观与每年日期？" open={Boolean(confirmation)} okText="确认保存" cancelText="继续选择"
            confirmLoading={pending} closable={!pending} maskClosable={!pending} keyboard={!pending}
            okButtonProps={{ disabled: pending || query.isFetching || query.isError || readRequired || Boolean(data?.degradedReason) }}
            cancelButtonProps={{ disabled: pending }} onCancel={() => { if (!pending) setConfirmation(undefined) }} onOk={() => void apply()}>
            {confirmation && <div className="town-theme-confirm">
                <p>当前设置：<strong>{selectionName(confirmation.before, confirmation.before.themes)}</strong></p>
                <p>调整为：<strong>{selectionName(confirmation.selection, confirmation.before.themes)}</strong></p>
                {confirmationWarnings.length > 0 && <Alert type="warning" showIcon style={{ margin: "16px 0" }}
                    message="年度主题资料已更新，需要重新确认"
                    description={<><p>涉及主题：<strong>{confirmationWarnings.join("、")}</strong>。</p>
                        <p>确认保存会采用这些年度主题当前更新后的定义和资源，继续使用所列每年日期。如果不希望继续使用，请返回移除相应的每年设置。</p></>} />}
                <div className="town-annual-confirm"><strong>每年日期变更</strong>
                    {scheduleKey(confirmation.before.annualSchedules) === scheduleKey(confirmation.annualSchedules) ? <p>每年日期保持不变。</p> : <ul>
                        {[...new Set([...confirmation.before.annualSchedules.map(item => item.themeId), ...confirmation.annualSchedules.map(item => item.themeId)])].map(id => {
                            const before = confirmation.before.annualSchedules.find(item => item.themeId === id), after = confirmation.annualSchedules.find(item => item.themeId === id)
                            if (before?.start === after?.start && before?.end === after?.end) return null
                            return <li key={id}><strong>{themeName(id, confirmation.before.themes)}</strong><span>原设置：{before ? annualText(before) : "未设置"}</span><span>新设置：{after ? annualText(after) : "不设置，恢复原版档期规则"}</span></li>
                        })}
                    </ul>}
                </div>
                <p>每年日期均为北京时间（UTC+8），开始和结束时刻均包含。手动选择优先于每年设置。</p>
                <p>影响全服玩家，在下次正常登录后更新主城外观与默认音乐；玩家本地自选音乐会保留。</p>
            </div>}
        </Modal>
    </AdminPage>
}
