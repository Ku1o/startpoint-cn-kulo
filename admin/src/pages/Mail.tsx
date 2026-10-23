import { ReactNode, useEffect, useMemo, useRef, useState } from "react"
import { Card, Form, Select, InputNumber, Input, Button, message, Alert, Typography, Radio, Modal, Descriptions, Table, Tag, Space, Switch } from "antd"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { apiGet, apiPatch, apiPost } from "../api/client"
import { AdminPage } from "../components/AdminPage"
import { getMailAttachmentRule } from "../lib/mailRules"
import { useMailPlayerMutation } from "./MailPlayerMutation"
import { useLookup } from "../api/lookups"
import { ADMIN_INT_MAX, integerError } from "../lib/adminNumbers"
import "./PlayerComms.css"
import { useAdminEditGuard } from "../lib/editGuard"

const { TextArea } = Input
const { Text } = Typography

// 私服管理保留全部已实现的附件类型；高风险类型仍会经过预览确认。
const MAIL_TYPES = [
    { value: 1, label: "道具", needsId: true },
    { value: 3, label: "付费星导石" },
    { value: 4, label: "免费星导石" },
    { value: 5, label: "角色", needsId: true, singleOnly: true },
    { value: 6, label: "装备", needsId: true, singleOnly: true },
    { value: 7, label: "星之碎片" },
    { value: 8, label: "玛纳" },
    { value: 9, label: "经验池" },
    { value: 10, label: "羁绊之证" },
    { value: 11, label: "Boss Boost 点" },
    { value: 12, label: "Boost 点" },
    { value: 13, label: "称号", needsId: true },
    { value: 15, label: "Rank 点" },
]

const TYPE_LABEL: Record<number, string> = Object.fromEntries(MAIL_TYPES.map(t => [t.value, t.label]))

export function mailInputError(values: { type?: number; type_id?: number | null; number?: unknown }): string | null {
    const meta = MAIL_TYPES.find(type => type.value === values.type)
    if (!meta) return "请选择有效的附件类型"
    if (meta.needsId) {
        const problem = integerError(values.type_id, "附件编号", 1, ADMIN_INT_MAX)
        if (problem) return problem
    }
    const rule = getMailAttachmentRule(values.type, values.type_id)
    return integerError(values.number, "数量", rule.min, rule.max)
}

function dailyNumberError(values: DailyVmoneyMailConfig): string | null {
    return integerError(values.amount, "每日星导石数量", 1, ADMIN_INT_MAX)
        || integerError(values.sendHour, "发送小时", 0, 23)
        || integerError(values.sendMinute, "发送分钟", 0, 59)
}

type TargetMode = "all" | "account" | "player"

interface SendResult { ok: boolean; sent: number }
interface AccountRow {
    id: number
    viewerId: string | null
    note: string | null
    bindings: Array<{ deviceId: number }>
    saveCount: number
    defaultPlayerId: number | null
    defaultPlayerName: string | null
    players: PlayerBrief[]
    playerIds: number[]
}
interface PlayerBrief { id: number; accountId: number; name: string; comment: string; degreeId: number }
interface AccountTargets { accounts: AccountRow[]; accountCount: number; saveCount: number }
interface MailRecord { time: string; type: number; typeId: number | null; number: number; subject: string | null; target: string; sent: number }
interface DailyVmoneyMailConfig {
    enabled: boolean
    amount: number
    sendHour: number
    sendMinute: number
    subject: string
    description: string
    updatedAtMs: number
}
interface DailyVmoneyMailRun {
    bucket: string
    scheduledAtMs: number
    executedAtMs: number
    source: string
    amount: number
    subject: string
    description: string
    sentCount: number
}
interface DailyVmoneyMailOverview {
    config: DailyVmoneyMailConfig
    lastRun: DailyVmoneyMailRun | null
    currentBucket: string
    due: boolean
    nextRunAtMs: number | null
    totalPlayers: number
}
interface DailyVmoneyMailRunResponse {
    result: { status: "already_sent" | "sent"; run: DailyVmoneyMailRun | null }
    overview: DailyVmoneyMailOverview
}
interface CharacterLookupRow { name: string; title: string; rarity: string; element: string }
interface EquipmentLookupRow { name: string; rarity: string; category: string }
type ItemLookup = Record<string, string>
type CharacterLookup = Record<string, CharacterLookupRow>
type EquipmentLookup = Record<string, EquipmentLookupRow>
type AttachmentLookup = ItemLookup | CharacterLookup | EquipmentLookup
interface AttachmentOption {
    value: number
    label: ReactNode
    searchText: string
    titleText: string
}

interface TargetOption {
    value: number
    label: string
    searchText: string
}

function norm(value: unknown): string {
    return String(value ?? "").normalize("NFKC").trim().toLowerCase()
}

function lookupEndpoint(type: number | undefined): string | null {
    if (type === 1) return "/api/lookup/items"
    if (type === 5) return "/api/lookup/characters"
    if (type === 6) return "/api/lookup/equipment"
    return null
}

function attachmentTitle(type: number | undefined, id: number | null | undefined, lookup: AttachmentLookup | undefined): string {
    if (id == null || !lookup) return id == null ? "" : `#${id}`
    const row = lookup[String(id)]
    if (!row) return `#${id}`
    if (type === 1 && typeof row === "string") return `${row} #${id}`
    if (type === 5 && typeof row !== "string") {
        const character = row as CharacterLookupRow
        return `${character.name}${character.title ? ` · ${character.title}` : ""} #${id}`
    }
    if (type === 6 && typeof row !== "string") return `${(row as EquipmentLookupRow).name} #${id}`
    return `#${id}`
}

function buildAttachmentOptions(type: number | undefined, lookup: AttachmentLookup | undefined): AttachmentOption[] {
    if (!type || !lookup) return []
    return Object.entries(lookup)
        .map(([rawId, row]): AttachmentOption | null => {
            const id = Number(rawId)
            if (type === 1 && typeof row === "string") {
                const titleText = `${row} #${id}`
                return {
                    value: id,
                    titleText,
                    searchText: norm(`${id} ${row}`),
                    label: (
                        <Space direction="vertical" size={0}>
                            <Text>{row}</Text>
                            <Text type="secondary">#{id}</Text>
                        </Space>
                    ),
                }
            }
            if (type === 5 && typeof row !== "string") {
                const character = row as CharacterLookupRow
                const titleText = `${character.name}${character.title ? ` · ${character.title}` : ""} #${id}`
                return {
                    value: id,
                    titleText,
                    searchText: norm(`${id} ${character.name} ${character.title} ${character.rarity} ${character.element}`),
                    label: (
                        <Space direction="vertical" size={0}>
                            <Text>{character.name}</Text>
                            <Text type="secondary">#{id} · {character.title || "无称号"} · {character.rarity} · {character.element}</Text>
                        </Space>
                    ),
                }
            }
            if (type === 6 && typeof row !== "string") {
                const equipment = row as EquipmentLookupRow
                const titleText = `${equipment.name} #${id}`
                return {
                    value: id,
                    titleText,
                    searchText: norm(`${id} ${equipment.name} ${equipment.rarity} ${equipment.category}`),
                    label: (
                        <Space direction="vertical" size={0}>
                            <Text>{equipment.name}</Text>
                            <Text type="secondary">#{id} · {equipment.rarity} · {equipment.category}</Text>
                        </Space>
                    ),
                }
            }
            return null
        })
        .filter((option): option is AttachmentOption => option !== null)
        .sort((a, b) => a.value - b.value)
}

function filterAttachmentOption(input: string, option?: AttachmentOption): boolean {
    if (!option) return false
    const query = norm(input)
    if (!query) return true
    if (/^[0-9]+$/.test(query)) return String(option.value) === query
    return option.searchText.includes(query)
}

function filterTargetOption(input: string, option?: TargetOption): boolean {
    if (!option) return false
    const query = norm(input)
    return !query || option.searchText.includes(query)
}

function formatChinaTime(value: number | null): string {
    if (value === null) return "—"
    const date = new Date(value + 8 * 60 * 60 * 1000)
    const parts = [
        date.getUTCFullYear(),
        String(date.getUTCMonth() + 1).padStart(2, "0"),
        String(date.getUTCDate()).padStart(2, "0"),
    ]
    const time = [
        String(date.getUTCHours()).padStart(2, "0"),
        String(date.getUTCMinutes()).padStart(2, "0"),
        String(date.getUTCSeconds()).padStart(2, "0"),
    ]
    return `${parts.join("-")} ${time.join(":")}`
}

export default function Mail() {
    const qc = useQueryClient()
    const [form] = Form.useForm()
    const [dailyForm] = Form.useForm()
    const [targetMode, setTargetMode] = useState<TargetMode>("all")
    const type = Form.useWatch("type", form)
    const typeId = Form.useWatch("type_id", form)
    const mailDraft = Form.useWatch([], form)
    const meta = MAIL_TYPES.find(t => t.value === type)
    const needsId = !!meta?.needsId
    const attachmentEndpoint = lookupEndpoint(type)
    const quantityRule = getMailAttachmentRule(type, typeId)
    const dailyEnabled = Form.useWatch("enabled", dailyForm)
    const [dailyHasUnsavedChanges, setDailyHasUnsavedChanges] = useState(false)
    const dailyRevision = useRef(0)
    const mailTargetBaseline = useRef<{ targetMode: TargetMode; accountId: number | null; playerId: number | null }>({ targetMode: "all", accountId: null, playerId: null })

    // 预览确认：暂存待发送的表单值 + 计算好的对象描述/角色数
    const [confirm, setConfirm] = useState<null | { values: any; count: number; targetText: string; attachmentText: string; targetSignature: string }>(null)

    const accountsQuery = useQuery({
        queryKey: ["accountTargets"],
        queryFn: ({ signal }) => apiGet<AccountTargets>("/api/server/accounts/targets", { signal }),
    })
    const accounts = accountsQuery.data?.accounts ?? []
    const targetsReady = accountsQuery.data !== undefined && !accountsQuery.isError && !accountsQuery.isPending
    const targetSignature = useMemo(() => JSON.stringify(accounts.map(account => [account.id, account.saveCount,
        account.players.map(player => player.id).sort((a, b) => a - b)]).sort((a, b) => Number(a[0]) - Number(b[0]))), [accounts])
    const players = useMemo(
        () => accounts.flatMap(account => account.players).sort((a, b) => a.id - b.id),
        [accounts],
    )
    const playerOptions = useMemo(
        () => accounts.flatMap(account => {
            const accountLabel = account.viewerId ?? `内部 #${account.id}`
            const note = account.note?.trim() ?? ""
            const deviceIds = account.bindings.map(binding => binding.deviceId).join(" ")
            return account.players.map(player => ({
                value: player.id,
                label: `${player.name}（存档 #${player.id}） · 账号 ${accountLabel}${note ? ` · 备注：${note}` : ""}`,
                searchText: norm(`${player.id} ${player.name} ${player.comment} ${account.id} ${account.viewerId} ${deviceIds} ${note}`),
            }))
        }).sort((a, b) => a.value - b.value),
        [accounts],
    )
    const accountOptions = useMemo(
        () => accounts.map(account => {
            const accountLabel = account.viewerId ?? "未生成 viewer_id"
            const note = account.note?.trim() ?? ""
            const deviceIds = account.bindings.map(binding => binding.deviceId).join(" ")
            return {
                value: account.id,
                label: `账号 ${accountLabel}（内部 #${account.id}，${account.saveCount} 个存档${account.defaultPlayerName ? `，生效：${account.defaultPlayerName}` : ""}）${note ? ` · 备注：${note}` : ""}`,
                searchText: norm(`${account.id} ${account.viewerId} ${deviceIds} ${account.defaultPlayerName} ${note}`),
            }
        }),
        [accounts],
    )
    const historyQuery = useQuery({ queryKey: ["mailHistory"], queryFn: ({ signal }) => apiGet<MailRecord[]>("/api/mail/history", { signal }) })
    const history = historyQuery.data ?? []
    const { data: dailyOverview, isLoading: dailyLoading, isError: dailyError, refetch: retryDaily } = useQuery({
        queryKey: ["dailyVmoneyMail"],
        queryFn: ({ signal }) => apiGet<DailyVmoneyMailOverview>("/api/mail/daily", { signal }),
    })
    const attachmentQuery = useLookup(type === 5 ? "characters" : type === 6 ? "equipment" : "items", needsId && !!attachmentEndpoint)
    const attachmentLookup = attachmentQuery.data
    const attachmentLoading = !!attachmentEndpoint && attachmentQuery.isLoading
    const attachmentError = !!attachmentEndpoint && attachmentQuery.isError
    const attachmentOptions = useMemo(
        () => buildAttachmentOptions(type, attachmentLookup),
        [type, attachmentLookup],
    )

    const totalSaves = accounts.reduce((n, a) => n + a.saveCount, 0)

    useEffect(() => {
        if (!dailyOverview || dailyHasUnsavedChanges) return
        dailyForm.setFieldsValue(dailyOverview.config)
        setDailyHasUnsavedChanges(false)
    }, [dailyForm, dailyHasUnsavedChanges, dailyOverview])

    const dailyPersistedEnabled = dailyOverview?.config.enabled === true
    const dailyStatusMessage = dailyError ? "配置读取失败"
        : !dailyOverview
        ? "正在读取配置"
        : dailyHasUnsavedChanges
            ? (dailyEnabled ? "已启用（尚未保存）" : "已停用（尚未保存）")
            : dailyPersistedEnabled ? "自动发放已启用" : "自动发放当前停用"
    const dailyStatusDescription = dailyHasUnsavedChanges
        ? "表单有未保存更改；请先点击“保存配置”，保存成功后才能立即发放。"
        : "每天按北京时间发放一次。重启只补跑当天到点的周期，不追补更早日期；同一周期不会重复发放。"

    const saveDaily = useMailPlayerMutation({
        mutationFn: ({ values }: { values: DailyVmoneyMailConfig; revision: number }) => {
            const problem = dailyNumberError(values)
            if (problem) throw new Error(problem)
            return apiPatch<DailyVmoneyMailOverview>("/api/mail/daily", values)
        },
        onSuccess: (overview, { revision }) => {
            message.success(overview.config.enabled ? "每日自动邮件已保存并启用" : "每日自动邮件配置已保存（当前停用）")
            if (dailyRevision.current === revision) setDailyHasUnsavedChanges(false)
            qc.setQueryData(["dailyVmoneyMail"], overview)
        },
        onError: (error: Error) => { void message.error(error.message) },
    })

    const runDaily = useMailPlayerMutation({
        mutationFn: () => apiPost<DailyVmoneyMailRunResponse>("/api/mail/daily/run"),
        onSuccess: ({ result, overview }) => {
            if (result.status === "sent") {
                message.success(`已向 ${result.run?.sentCount ?? 0} 个存档发放今日星导石`)
            } else {
                message.info("今日周期已经发放过，没有重复发送")
            }
            qc.setQueryData(["dailyVmoneyMail"], overview)
        },
        onError: (error: Error) => { void message.error(error.message) },
    })

    const confirmRunDaily = () => {
        if (dailyError || !dailyOverview?.config.enabled) {
            message.error("请先保存并启用每日自动邮件")
            return
        }
        if (dailyHasUnsavedChanges || saveDaily.isPending) {
            message.warning("请先保存当前配置")
            return
        }
        Modal.confirm({
            title: "立即发放今日星导石？",
            content: `将按当前配置向尚未收到今日自动邮件的存档发放；本周期已有记录时不会重复发送。当前共 ${dailyOverview?.totalPlayers ?? totalSaves} 个存档。`,
            okText: "确认发放",
            cancelText: "取消",
            okButtonProps: { danger: true },
            onOk: async () => { await runDaily.mutateAsync() },
        })
    }

    const targetProblem = (values: any): string | null => {
        if (!targetsReady) return "发送对象尚未读取成功，请刷新对象列表后重试"
        if (values.targetMode === "player") {
            return players.some(player => player.id === values.playerId) ? null : "所选存档已不存在，请重新选择"
        }
        if (values.targetMode === "account") {
            const account = accounts.find(account => account.id === values.accountId)
            return !account ? "所选账号已不存在，请重新选择" : account.saveCount < 1 ? "所选账号没有可接收邮件的存档" : null
        }
        return values.targetMode !== "all" ? "请选择有效发送对象" : totalSaves < 1 ? "当前没有可接收邮件的存档" : null
    }

    const send = useMailPlayerMutation({
        mutationFn: (confirmed: NonNullable<typeof confirm>) => {
            const problem = targetProblem(confirmed.values)
            if (problem) throw new Error(problem)
            const inputProblem = mailInputError(confirmed.values)
            if (inputProblem) throw new Error(inputProblem)
            if (confirmed.targetSignature !== targetSignature) throw new Error("发送对象已变化，请关闭预览后重新确认")
            const v = confirmed.values
            return apiPost<SendResult>("/api/mail/send", {
                type: String(v.type),
                type_id: v.type_id != null ? String(v.type_id) : "",
                number: String(v.number ?? 1),
                subject: v.subject ?? "",
                description: v.description ?? "",
                accountId: v.targetMode === "account" && v.accountId != null ? String(v.accountId) : "",
                playerId: v.targetMode === "player" && v.playerId != null ? String(v.playerId) : "",
            })
        },
        onSuccess: (r, confirmed) => {
            message.success(`已向 ${r.sent} 个存档发送邮件`)
            mailTargetBaseline.current = {
                targetMode: confirmed.values.targetMode,
                accountId: confirmed.values.accountId ?? null,
                playerId: confirmed.values.playerId ?? null,
            }
            setConfirm(null)
            // 保留发送对象设置，仅清空附件与文案，便于连续操作
            form.resetFields(["type", "type_id", "number", "subject", "description"])
            qc.invalidateQueries({ queryKey: ["mailHistory"] })
        },
        onError: (e: Error) => { void message.error(e.message) },
    })
    useAdminEditGuard({
        dirty: dailyHasUnsavedChanges || !!(mailDraft?.type || mailDraft?.type_id || mailDraft?.subject || mailDraft?.description || confirm)
            || !!(mailDraft && "number" in mailDraft && !Object.is(mailDraft.number, 1))
            || (mailDraft?.targetMode ?? "all") !== mailTargetBaseline.current.targetMode
            || (mailDraft?.accountId ?? null) !== mailTargetBaseline.current.accountId
            || (mailDraft?.playerId ?? null) !== mailTargetBaseline.current.playerId,
        pending: send.isPending || saveDaily.isPending || runDaily.isPending,
        label: "邮件",
    })

    // 通过表单校验后，先算好预览再弹确认框
    const openConfirm = (v: any) => {
        if (send.isPending) { message.info("邮件正在发送，请等待结果"); return }
        const problem = targetProblem(v)
        if (problem) { message.error(problem); return }
        const inputProblem = mailInputError(v)
        if (inputProblem) { message.error(inputProblem); return }
        let count = 0
        let targetText = ""
        if (v.targetMode === "player") {
            const p = players.find(pp => pp.id === v.playerId)
            count = 1
            targetText = p ? `存档 #${p.id}（${p.name}）` : `存档 #${v.playerId}`
        } else if (v.targetMode === "account") {
            const a = accounts.find(aa => aa.id === v.accountId)
            count = a?.saveCount ?? 0
            targetText = a
                ? `账号 ${a.viewerId ?? `内部 #${a.id}`}（${a.saveCount} 个存档）`
                : `内部账号 #${v.accountId}`
        } else {
            count = totalSaves
            targetText = `全体（${accounts.length} 个账号 / ${totalSaves} 个存档）`
        }
        const attachmentName = attachmentTitle(v.type, v.type_id, attachmentLookup)
        const attachmentText = attachmentName
            ? `${TYPE_LABEL[v.type] ?? v.type} · ${attachmentName}`
            : `${TYPE_LABEL[v.type] ?? v.type}`
        setConfirm({ values: v, count, targetText, attachmentText, targetSignature })
    }

    return (
        <AdminPage
            eyebrow="MAIL"
            title="邮件"
            description="单次邮件先预览再发送；每日自动奖励单独配置，按周期发放。"
        >
        <Space direction="vertical" size="large" className="admin-stack mail-manage-stack" style={{ minWidth: 0, maxWidth: "100%" }}>
            <Card title="单次邮件" className="admin-form-panel">
                <Alert type={!targetsReady && accountsQuery.isError ? "error" : targetMode === "all" ? "warning" : "info"} showIcon style={{ marginBottom: 16 }}
                    message={
                        !targetsReady ? accountsQuery.isError ? "发送对象读取失败，暂不能发送邮件" : "正在读取发送对象，暂不能发送邮件"
                            : totalSaves === 0 ? "当前没有可接收邮件的存档"
                            : targetMode === "all" ? `将向全体 ${totalSaves} 个存档发送同一封邮件`
                            : targetMode === "account" ? "将向所选账号下的所有存档发送邮件"
                                : "将向所选的单个存档发送邮件"
                    }
                    action={<Button size="small" loading={accountsQuery.isFetching} onClick={() => accountsQuery.refetch()}>刷新对象</Button>}
                />
                <Form form={form} layout="vertical" onFinish={openConfirm} disabled={send.isPending} initialValues={{ number: 1, targetMode: "all" }}>
                    <Form.Item name="targetMode" label="1 · 收件范围">
                        <Radio.Group
                            optionType="button"
                            buttonStyle="solid"
                            onChange={(event) => {
                                setTargetMode(event.target.value as TargetMode)
                                form.setFieldsValue({ accountId: undefined, playerId: undefined })
                            }}
                        >
                            <Radio.Button value="all">全体存档</Radio.Button>
                            <Radio.Button value="account">指定账号</Radio.Button>
                            <Radio.Button value="player">指定存档</Radio.Button>
                        </Radio.Group>
                    </Form.Item>

                    {targetMode === "account" && (
                        <Form.Item name="accountId" label="选择账号" rules={[{ required: true, message: "请选择账号" }]}>
                            <Select<number, TargetOption>
                                showSearch
                                allowClear
                                placeholder="按原始账号 ID、内部 ID 或备注搜索"
                                options={accountOptions}
                                filterOption={filterTargetOption}
                                loading={accountsQuery.isFetching}
                                disabled={!targetsReady}
                                notFoundContent={accountsQuery.isFetching ? "正在读取账号…" : "没有匹配的账号"}
                            />
                        </Form.Item>
                    )}

                    {targetMode === "player" && (
                        <Form.Item name="playerId" label="选择存档" rules={[{ required: true, message: "请选择存档" }]}>
                            <Select<number, TargetOption>
                                showSearch
                                allowClear
                                placeholder="按存档、账号 ID 或备注搜索"
                                options={playerOptions}
                                filterOption={filterTargetOption}
                                loading={accountsQuery.isFetching}
                                disabled={!targetsReady}
                                notFoundContent={accountsQuery.isFetching ? "正在读取存档…" : "没有匹配的存档"}
                            />
                        </Form.Item>
                    )}

                    <Form.Item name="type" label="2 · 附件类型" rules={[{ required: true, message: "请选择附件类型" }]}>
                        <Radio.Group
                            className="admin-mail-type-group"
                            optionType="button"
                            buttonStyle="solid"
                            onChange={(event) => {
                                const nextRule = getMailAttachmentRule(event.target.value, null)
                                form.setFieldsValue({
                                    type_id: undefined,
                                    number: nextRule.max === 0 ? 0 : 1,
                                })
                                form.validateFields(["type_id", "number"]).catch(() => {})
                            }}
                        >
                            {MAIL_TYPES.map(t => (
                                <Radio.Button key={t.value} value={t.value} className="admin-mail-type-option">
                                    {t.label}
                                </Radio.Button>
                            ))}
                        </Radio.Group>
                    </Form.Item>

                    {needsId && (
                        <Form.Item
                            name="type_id"
                            label="附件"
                            rules={[
                                {
                                    validator: async (_, value) => {
                                        if (attachmentError) throw new Error("附件索引加载失败，无法发送")
                                        const problem = integerError(value, "附件编号", 1, ADMIN_INT_MAX)
                                        if (problem) throw new Error(problem)
                                    },
                                },
                            ]}
                            extra={attachmentEndpoint
                                ? "输入完整 ID 或中文名称搜索；数字查询按完整 ID 精确匹配，避免误选相近编号。"
                                : "输入国服称号 ID；服务端会在称号数据中校验。"}
                        >
                            {attachmentEndpoint ? (
                                <Select
                                    showSearch
                                    allowClear
                                    placeholder="输入 ID 或名称搜索附件"
                                    loading={attachmentLoading}
                                    disabled={attachmentError}
                                    options={attachmentOptions}
                                    filterOption={filterAttachmentOption}
                                    optionLabelProp="titleText"
                                    notFoundContent={attachmentLoading ? "正在加载附件索引" : "没有匹配附件"}
                                    onChange={(nextTypeId) => {
                                        const nextRule = getMailAttachmentRule(type, nextTypeId)
                                        const currentNumber = form.getFieldValue("number") ?? 1
                                        form.setFieldValue("number", Math.min(currentNumber, nextRule.max))
                                        form.validateFields(["number"]).catch(() => {})
                                    }}
                                />
                            ) : (
                                <InputNumber min={1} max={ADMIN_INT_MAX} style={{ width: "100%" }} placeholder="称号编号" />
                            )}
                        </Form.Item>
                    )}
                    {attachmentError && <Alert type="error" showIcon message="附件索引读取失败"
                        action={<Button size="small" onClick={() => attachmentQuery.refetch()}>重试</Button>} style={{ marginBottom: 16 }} />}

                    <Form.Item
                        name="number"
                        label="数量"
                        rules={[
                            { required: true, message: "请输入数量" },
                            {
                                validator: async (_, value) => {
                                    const problem = integerError(value, "数量", quantityRule.min, quantityRule.max)
                                    if (problem) throw new Error(problem)
                                },
                            },
                        ]}
                        extra={`${quantityRule.label}：${quantityRule.min}-${quantityRule.max}，仅支持整数。${quantityRule.reason}`}
                    >
                        <InputNumber
                            style={{ width: "100%" }}
                            aria-label="邮件附件数量"
                            min={quantityRule.min}
                            max={quantityRule.max}
                            disabled={quantityRule.max <= 1}
                        />
                    </Form.Item>

                    <Form.Item name="subject" label="3 · 标题（可选）">
                        <Input maxLength={64} showCount placeholder="留空使用游戏默认" />
                    </Form.Item>

                    <Form.Item name="description" label="正文（可选）">
                        <TextArea rows={3} maxLength={512} showCount placeholder="留空使用游戏默认" />
                    </Form.Item>

                    <Form.Item>
                        <Space wrap>
                            <Button type="primary" htmlType="submit" disabled={!targetsReady || totalSaves === 0} loading={send.isPending}>预览并确认</Button>
                            <Text type="secondary">发送后无法撤回，请确认附件 ID</Text>
                        </Space>
                    </Form.Item>
                </Form>
            </Card>

            <Card title="每日自动奖励 · 星导石" className="admin-form-panel" loading={dailyLoading}>
                {dailyError && <Alert type="error" showIcon message="每日邮件配置读取失败，请重试"
                    action={<Button onClick={() => retryDaily()}>重试</Button>} style={{ marginBottom: 16 }} />}
                <Alert
                    type={dailyHasUnsavedChanges ? "warning" : dailyPersistedEnabled ? "success" : "info"}
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={dailyStatusMessage}
                    description={dailyStatusDescription}
                />
                <Form
                    form={dailyForm}
                    layout="vertical"
                    initialValues={{ enabled: false, amount: 150000, sendHour: 5, sendMinute: 0, subject: "每日千抽", description: "每日星导石奖励，请查收。" }}
                    disabled={!dailyOverview || dailyError}
                    onValuesChange={() => { dailyRevision.current += 1; setDailyHasUnsavedChanges(true) }}
                    onFinish={(values) => {
                        if (!dailyOverview || dailyError) return
                        saveDaily.mutate({ values: values as DailyVmoneyMailConfig, revision: dailyRevision.current })
                    }}
                >
                    <Form.Item name="enabled" label="启用状态" valuePropName="checked">
                        <Switch checkedChildren="已启用" unCheckedChildren="已停用" />
                    </Form.Item>
                    <Space wrap align="start" size="middle">
                        <Form.Item
                            name="amount"
                            label="每日免费星导石"
                            rules={[{ validator: async (_, value) => { const problem = integerError(value, "每日星导石数量", 1, ADMIN_INT_MAX); if (problem) throw new Error(problem) } }]}
                        >
                            <InputNumber min={1} max={ADMIN_INT_MAX} aria-label="每日免费星导石" style={{ width: 220, maxWidth: "100%" }} />
                        </Form.Item>
                        <Form.Item name="sendHour" label="北京时间（时）" rules={[{ validator: async (_, value) => { const problem = integerError(value, "发送小时", 0, 23); if (problem) throw new Error(problem) } }]}>
                            <InputNumber min={0} max={23} aria-label="发送小时" style={{ width: 140 }} />
                        </Form.Item>
                        <Form.Item name="sendMinute" label="北京时间（分）" rules={[{ validator: async (_, value) => { const problem = integerError(value, "发送分钟", 0, 59); if (problem) throw new Error(problem) } }]}>
                            <InputNumber min={0} max={59} aria-label="发送分钟" style={{ width: 140 }} />
                        </Form.Item>
                    </Space>
                    <Form.Item name="subject" label="邮件标题" rules={[{ required: true, message: "请输入标题" }]}>
                        <Input maxLength={64} showCount />
                    </Form.Item>
                    <Form.Item name="description" label="邮件正文">
                        <TextArea rows={3} maxLength={512} showCount />
                    </Form.Item>
                    <Space wrap>
                        <Button type="primary" htmlType="submit" loading={saveDaily.isPending}>保存每日配置</Button>
                        <Button danger disabled={dailyError || !dailyPersistedEnabled || dailyHasUnsavedChanges || saveDaily.isPending} loading={runDaily.isPending} onClick={confirmRunDaily}>立即发放今日周期</Button>
                        <Text type="secondary">
                            {dailyHasUnsavedChanges
                                ? "请先保存配置后再发放。"
                                : "若在今日设定时间之后才启用，自动任务会从明天开始；需要当天发放时可点击“立即发放”。"}
                        </Text>
                    </Space>
                </Form>

                {saveDaily.isError && <Alert type="error" showIcon message={saveDaily.error.message} description="每日配置草稿已保留，可修改后重新保存。" style={{ marginTop: 12 }} />}
                {runDaily.isError && <Alert type="error" showIcon message={runDaily.error.message} style={{ marginTop: 12 }} />}
                <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }} style={{ marginTop: 20 }}>
                    <Descriptions.Item label="当前周期">{dailyOverview?.currentBucket ?? "—"}</Descriptions.Item>
                    <Descriptions.Item label="下次执行">
                        {dailyOverview?.due ? <Tag color="warning">等待补跑</Tag> : formatChinaTime(dailyOverview?.nextRunAtMs ?? null)}
                    </Descriptions.Item>
                    <Descriptions.Item label="当前存档数">{dailyOverview?.totalPlayers ?? totalSaves}</Descriptions.Item>
                    <Descriptions.Item label="最近发放">
                        {dailyOverview?.lastRun ? `${dailyOverview.lastRun.bucket} · ${formatChinaTime(dailyOverview.lastRun.executedAtMs)}` : "尚未发放"}
                    </Descriptions.Item>
                    <Descriptions.Item label="最近数量">{dailyOverview?.lastRun ? `${dailyOverview.lastRun.amount} / 存档` : "—"}</Descriptions.Item>
                    <Descriptions.Item label="最近发送数">{dailyOverview?.lastRun?.sentCount ?? "—"}</Descriptions.Item>
                </Descriptions>
            </Card>

            <Card title="最近群发记录" size="small" className="admin-table-card">
                {historyQuery.isError && <Alert type="error" showIcon message="群发记录读取失败"
                    action={<Button size="small" onClick={() => historyQuery.refetch()}>重试</Button>} style={{ marginBottom: 12 }} />}
                <Table<MailRecord & { key: number }>
                    rowKey="key"
                    size="small"
                    loading={historyQuery.isLoading}
                    pagination={false}
                    dataSource={history.map((h, i) => ({ ...h, key: i }))}
                    locale={{ emptyText: "暂无记录" }}
                    scroll={{ x: "max-content" }}
                    columns={[
                        { title: "时间", dataIndex: "time", width: 160 },
                        { title: "对象", dataIndex: "target" },
                        {
                            title: "附件", key: "attach",
                            render: (_: unknown, r) => `${TYPE_LABEL[r.type] ?? r.type}${r.typeId ? ` #${r.typeId}` : ""} × ${r.number}`,
                        },
                        { title: "发送数", dataIndex: "sent", width: 80, render: (n: number) => <Tag color="blue">{n}</Tag> },
                    ]}
                />
            </Card>
        </Space>

            <Modal
                open={!!confirm}
                title="发送预览与确认"
                onOk={() => confirm && send.mutate(confirm)}
                onCancel={() => { if (!send.isPending) setConfirm(null) }}
                okText="确认发送"
                cancelText="取消"
                confirmLoading={send.isPending}
                okButtonProps={{ danger: true, disabled: !targetsReady || confirm?.targetSignature !== targetSignature }}
                cancelButtonProps={{ disabled: send.isPending }}
                closable={!send.isPending}
                maskClosable={!send.isPending}
            >
                {confirm && (
                    <>
                        {(!targetsReady || confirm.targetSignature !== targetSignature) && <Alert type="warning" showIcon message="发送对象未就绪或已经变化，请关闭后重新确认" style={{ marginBottom: 12 }} />}
                        {send.isError && <Alert type="error" showIcon message={send.error.message} description="邮件内容已保留，请核对后重试。" style={{ marginBottom: 12 }} />}
                        <Descriptions column={1} size="small" bordered>
                            <Descriptions.Item label="发送对象">{confirm.targetText}</Descriptions.Item>
                            <Descriptions.Item label="接收存档数">{confirm.count} 个</Descriptions.Item>
                            <Descriptions.Item label="附件">{confirm.attachmentText}</Descriptions.Item>
                            {confirm.values.type_id != null && (
                                <Descriptions.Item label="附件 ID">{confirm.values.type_id}</Descriptions.Item>
                            )}
                            <Descriptions.Item label="数量">× {confirm.values.number}</Descriptions.Item>
                            <Descriptions.Item label="标题">{confirm.values.subject || "使用游戏默认标题"}</Descriptions.Item>
                            <Descriptions.Item label="正文"><div className="mail-preview-body">{confirm.values.description || "使用游戏默认正文"}</div></Descriptions.Item>
                        </Descriptions>
                        <Alert style={{ marginTop: 12 }} type="warning" showIcon
                            message={`将向 ${confirm.count} 个存档发送 ${TYPE_LABEL[confirm.values.type] ?? confirm.values.type} × ${confirm.values.number}，发送后无法撤回`} />
                    </>
                )}
            </Modal>
        </AdminPage>
    )
}
