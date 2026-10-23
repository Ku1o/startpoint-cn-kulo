import { useEffect, useRef, useState } from "react"
import {
    Alert,
    Button,
    Card,
    Col,
    Collapse,
    Descriptions,
    Input,
    InputNumber,
    Popconfirm,
    Modal,
    Row,
    Space,
    Spin,
    Statistic,
    Switch,
    Table,
    Tag,
    Typography,
    message,
} from "antd"
import { ReloadOutlined, SaveOutlined } from "@ant-design/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import dayjs from "dayjs"
import { formatLeaderboardDeadlineInput, parseLeaderboardDeadlineInput } from "../../../src/lib/leaderboard/schedule-time"
import { apiGet, apiPatch, apiPost } from "../api/client"
import { AdminPage, StateCard } from "../components/AdminPage"
import { LeaderboardRewardEditor, rewardDraftError } from "../components/LeaderboardRewardEditor"
import { useAdminEditGuard } from "../lib/editGuard"

const { Text, Paragraph } = Typography

interface Competition {
    key: string
    displayName: string
    category: number
    eventId: number
    folderId: number
    pageSize: number
    displayLimit: number
}

interface Reward {
    itemId: number | null
    itemName: string | null
    itemCount: number
    degreeId: number | null
    degreeName: string | null
    degreeImage: string | null
}

type RewardTier = Reward & (
    { fromRank: number; toRank: number | null }
    | { fromPercent: number; toPercent: number }
)

function rewardRange(tier: RewardTier): string {
    if ("fromPercent" in tier) {
        if (tier.fromPercent === 0) return `前 ${tier.toPercent}%`
        return tier.toPercent === 100 ? `${tier.fromPercent}% 之后的所有人`
            : `${tier.fromPercent}%～${tier.toPercent}%`
    }
    return `${tier.fromRank}–${tier.toRank ?? "末位"}`
}

interface SettlementConfig {
    competitionKey: string
    autoEnabled: boolean
    freezeEnabled: boolean
    settleAtMs: number | null
    repeatIntervalMs: number | null
    rewardTiers: RewardTier[]
    mailSubject: string
    mailBody: string
    excludeBots: boolean
    updatedAtMs: number
}

interface LeaderboardAvailability {
    competitionKey: string
    enabled: boolean
    updatedAtMs: number
}

interface SettlementHistory {
    id: number
    season: number
    source: string
    settled_at_ms: number
    ranked_players: number
    rewarded_players: number
    status: string
    summary_json: string
}

interface Overview {
    competitionKey: string
    season: number
    total: number
    config: SettlementConfig
    history: SettlementHistory[]
    resolvedRewardTiers: RewardTier[]
}

interface CompetitionSummary {
    competition: Competition
    availability: LeaderboardAvailability
    overview: Overview
}

interface RankRow {
    id: number
    rankNumber: number
    clearCount: number | null
    playerId: number
    displayName: string
    playerExists: boolean
    rankPoint: number
    clientBattleMs: number
    serverDurationMs: number | null
    finishedAtMs: number | null
}

interface LeaderboardDetail {
    competition: Competition
    availability: LeaderboardAvailability
    overview: Overview
    page: number
    rows: RankRow[]
    total: number
}

interface ConfigDraft {
    autoEnabled: boolean
    freezeEnabled: boolean
    settleAtText: string
    repeatHours: number | null
    excludeBots: boolean
    mailSubject: string
    mailBody: string
    rewardTiersText: string
}

function formatBattleTime(milliseconds: number): string {
    const minutes = Math.floor(milliseconds / 60_000)
    const seconds = Math.floor(milliseconds % 60_000 / 1000)
    const millis = milliseconds % 1000
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`
}

function configToDraft(config: SettlementConfig): ConfigDraft {
    return {
        autoEnabled: config.autoEnabled,
        freezeEnabled: config.freezeEnabled,
        settleAtText: config.settleAtMs === null
            ? ""
            : formatLeaderboardDeadlineInput(config.settleAtMs),
        repeatHours: config.repeatIntervalMs === null
            ? null
            : config.repeatIntervalMs / 3_600_000,
        excludeBots: config.excludeBots,
        mailSubject: config.mailSubject,
        mailBody: config.mailBody,
        rewardTiersText: JSON.stringify(config.rewardTiers, null, 2),
    }
}

export default function Leaderboards() {
    const queryClient = useQueryClient()
    const [selectedKey, setSelectedKey] = useState<string | null>(null)
    const [page, setPage] = useState(0)
    const [draft, replaceDraft] = useState<ConfigDraft | null>(null)
    const [dirty, setDirty] = useState(false)
    const draftOwner = useRef<string | null>(null)
    const editRevision = useRef(0)
    const draftDirty = useRef(false)
    const activeKey = useRef(selectedKey)
    activeKey.current = selectedKey
    const setDraft = (value: ConfigDraft) => {
        editRevision.current += 1
        draftDirty.current = true
        setDirty(true)
        replaceDraft(value)
    }
    const chooseCompetition = (key: string) => {
        if (key === selectedKey) return
        const apply = () => {
            draftOwner.current = null
            draftDirty.current = false
            editRevision.current += 1
            setDirty(false)
            replaceDraft(null)
            setSelectedKey(key)
            setPage(0)
        }
        if (draftDirty.current) Modal.confirm({
            title: "放弃尚未保存的结算设置？",
            content: "切换排行榜会放弃当前草稿。", okText: "放弃并切换", cancelText: "继续编辑", onOk: apply,
        })
        else apply()
    }

    const listQuery = useQuery({
        queryKey: ["leaderboards"],
        queryFn: ({ signal }) => apiGet<CompetitionSummary[]>("/api/leaderboards/?summary=1", { signal }),
        refetchInterval: 30_000,
    })

    useEffect(() => {
        if (selectedKey === null && listQuery.data?.length) {
            setSelectedKey(listQuery.data[0].competition.key)
        }
    }, [listQuery.data, selectedKey])

    const detailQuery = useQuery({
        queryKey: ["leaderboard", selectedKey, page],
        queryFn: ({ signal }) => apiGet<LeaderboardDetail>(
            `/api/leaderboards/${encodeURIComponent(selectedKey!)}` + `?page=${page}`, { signal },
        ),
        enabled: selectedKey !== null,
        refetchInterval: 30_000,
    })

    useEffect(() => {
        const data = detailQuery.data
        if (!data || data.competition.key !== selectedKey) return
        if (draftOwner.current !== selectedKey || !draftDirty.current) {
            draftOwner.current = selectedKey
            replaceDraft(configToDraft(data.overview.config))
        }
    }, [detailQuery.data, selectedKey])

    const invalidate = async (key = selectedKey) => {
        await queryClient.invalidateQueries({ queryKey: ["leaderboards"] })
        await queryClient.invalidateQueries({ queryKey: ["leaderboard", key] })
    }

    const saveConfig = useMutation({
        mutationFn: async ({ key, submitted }: { key: string; submitted: ConfigDraft; revision: number }) => {
            const draft = submitted
            const selectedKey = key
            const rewardError = rewardDraftError(draft.rewardTiersText)
            if (rewardError) throw new Error(rewardError)
            const rewardTiers = JSON.parse(draft.rewardTiersText) as RewardTier[]
            if (draft.repeatHours !== null && (!Number.isFinite(draft.repeatHours) || draft.repeatHours <= 0
                || !Number.isSafeInteger(Math.round(draft.repeatHours * 3_600_000)))) throw new Error("重复间隔须为有效的正数。")
            const settleAtMs = parseLeaderboardDeadlineInput(draft.settleAtText)
            if ((draft.freezeEnabled || draft.autoEnabled) && settleAtMs === null) {
                throw new Error("请设置截止时间（北京时间）。")
            }
            return apiPatch(`/api/leaderboards/${encodeURIComponent(selectedKey)}/config`, {
                autoEnabled: draft.autoEnabled,
                freezeEnabled: draft.freezeEnabled || draft.autoEnabled,
                settleAtMs,
                repeatIntervalMs: draft.repeatHours === null
                    ? null
                    : Math.round(draft.repeatHours * 3_600_000),
                excludeBots: draft.excludeBots,
                mailSubject: draft.mailSubject,
                mailBody: draft.mailBody,
                rewardTiers,
            })
        },
        onSuccess: async (_data, { key, revision }) => {
            if (activeKey.current === key && editRevision.current === revision) {
                draftDirty.current = false
                setDirty(false)
            }
            message.success("排行榜结算配置已保存")
            await invalidate(key)
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const settle = useMutation({
        mutationFn: () => apiPost(
            `/api/leaderboards/${encodeURIComponent(selectedKey!)}/settle`,
        ),
        onSuccess: async () => {
            message.success("本赛季已完成结算")
            await invalidate()
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const rollover = useMutation({
        mutationFn: () => apiPost(
            `/api/leaderboards/${encodeURIComponent(selectedKey!)}/rollover`,
        ),
        onSuccess: async () => {
            message.success("已进入下一赛季")
            setPage(0)
            await invalidate()
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const setAvailability = useMutation({
        mutationFn: (enabled: boolean) => apiPatch(
            `/api/leaderboards/${encodeURIComponent(selectedKey!)}/availability`,
            { enabled },
        ),
        onSuccess: async (_data, enabled) => {
            message.success(enabled ? "排行榜已开启" : "排行榜已关闭")
            await invalidate()
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const workPending = saveConfig.isPending || settle.isPending || rollover.isPending || setAvailability.isPending
    const rewardError = draft ? rewardDraftError(draft.rewardTiersText) : null
    useAdminEditGuard({ dirty, pending: workPending, label: "排行榜设置" })

    if (listQuery.isLoading) return <StateCard><Spin size="large" /></StateCard>
    if (listQuery.isError || !listQuery.data) {
        return <Alert type="error" showIcon message="排行榜列表读取失败" description="请稍后重试，当前未执行任何操作。" action={<Button onClick={() => listQuery.refetch()}>重试</Button>} />
    }
    if (listQuery.data.length === 0) {
        return <AdminPage eyebrow="LEADERBOARD" title="排行榜"><Card>当前没有已注册的竞赛。</Card></AdminPage>
    }

    const detail = detailQuery.data
    const competition = detail?.competition
    const overview = detail?.overview

    return (
        <AdminPage
            eyebrow="LEADERBOARD"
            title="排行榜"
            description="查看当前赛季名次，设置排名奖励，结算发奖或进入下一赛季。"
            actions={(
                <Button
                    icon={<ReloadOutlined />}
                    loading={listQuery.isFetching || detailQuery.isFetching}
                    onClick={() => { listQuery.refetch(); detailQuery.refetch() }}
                >刷新</Button>
            )}
        >
            <Space direction="vertical" size="large" className="admin-stack">
                <Card title="选择排行榜" size="small">
                    <Space wrap aria-label="排行榜选择">
                        {listQuery.data.map(entry => (
                            <Button
                                key={entry.competition.key}
                                type={selectedKey === entry.competition.key ? "primary" : "default"}
                                disabled={saveConfig.isPending || settle.isPending || rollover.isPending || setAvailability.isPending}
                                onClick={() => chooseCompetition(entry.competition.key)}
                            >
                                {entry.competition.displayName}
                            </Button>
                        ))}
                    </Space>
                </Card>

                {detailQuery.isError ? (
                    <Alert type="error" showIcon message="排行榜详情读取失败" description="可以重试或选择其他排行榜；尚未保存的设置仍保留。" action={<Button loading={detailQuery.isFetching} onClick={() => detailQuery.refetch()}>重试详情</Button>} />
                ) : detailQuery.isLoading || !detail || !competition || !overview || !draft ? (
                    <StateCard><Spin size="large" /></StateCard>
                ) : (
                    <>
                        <Alert type={detail.availability.enabled ? "success" : "warning"} showIcon
                            message={`${competition.displayName} · 第 ${overview.season} 赛季 · ${detail.availability.enabled ? "开放中" : "已冻结"}`}
                            description="先查看名次和已保存奖励，再调整结算设置。手动结算与换季在下方单独操作。" />
                        <Row gutter={[16, 16]}>
                            <Col xs={12} lg={6}><Card><Statistic title="当前赛季" value={overview.season} /></Card></Col>
                            <Col xs={12} lg={6}><Card><Statistic title="有效排名" value={detail.total} suffix="人" /></Card></Col>
                            <Col xs={12} lg={6}><Card><Statistic title="客户端展示上限" value={competition.displayLimit} /></Card></Col>
                            <Col xs={12} lg={6}><Card><Statistic title="每页" value={competition.pageSize} suffix="人" /></Card></Col>
                        </Row>

                        <Card title="当前赛季名次">
                            <Paragraph type="secondary">等级经验显示保存的经验值，并非玩家等级。通关用时来自客户端记录。</Paragraph>
                            <Table<RankRow>
                                rowKey="id"
                                size="small"
                                dataSource={detail.rows}
                                scroll={{ x: 980 }}
                                pagination={{
                                    current: page + 1,
                                    pageSize: competition.pageSize,
                                    total: detail.total,
                                    showSizeChanger: false,
                                    onChange: current => setPage(current - 1),
                                }}
                                columns={[
                                    { title: "名次", dataIndex: "rankNumber", width: 76 },
                                    {
                                        title: "玩家",
                                        render: (_, row) => (
                                            <Space wrap>
                                                <span style={{ overflowWrap: "anywhere" }}>{row.displayName}</span>
                                                <Text type="secondary">#{row.playerId}</Text>
                                                {!row.playerExists && <Tag color="red">已删除</Tag>}
                                            </Space>
                                        ),
                                    },
                                    { title: "等级经验", dataIndex: "rankPoint", width: 90 },
                                    {
                                        title: "通关次数",
                                        dataIndex: "clearCount",
                                        width: 100,
                                        render: value => value === null ? "未记录" : `${value}次`,
                                    },
                                    {
                                        title: "通关用时",
                                        dataIndex: "clientBattleMs",
                                        width: 180,
                                        render: value => <code>{formatBattleTime(value)}</code>,
                                    },
                                    {
                                        title: "完成时间",
                                        dataIndex: "finishedAtMs",
                                        width: 180,
                                        render: value => value === null ? "-" : dayjs(value).format("YYYY-MM-DD HH:mm:ss"),
                                    },
                                ]}
                            />
                            <Collapse ghost items={[{ key: "competition", label: "查看此竞赛参数", children: <Descriptions size="small" column={{ xs: 1, md: 3 }}>
                                <Descriptions.Item label="竞赛标识">{competition.key}</Descriptions.Item>
                                <Descriptions.Item label="玩法分类 ID">{competition.category}</Descriptions.Item>
                                <Descriptions.Item label="活动 ID">{competition.eventId}</Descriptions.Item>
                                <Descriptions.Item label="文件夹 ID">{competition.folderId}</Descriptions.Item>
                                <Descriptions.Item label="服务端记录用时">{detail.rows.filter(row => row.serverDurationMs !== null).length} / 本页 {detail.rows.length} 条有记录</Descriptions.Item>
                            </Descriptions> }]} />
                        </Card>

                        <Card title="已保存奖励预览" extra={<Tag>当前有效人数 {overview.total}</Tag>}>
                            <Paragraph type="secondary">按已保存配置和当前有效人数展开；编辑中的草稿不会改变此预览。结算后保留本期最终结果。</Paragraph>
                            <Table<RewardTier> size="small" pagination={false} rowKey={(_row, index) => String(index)}
                                dataSource={overview.resolvedRewardTiers} scroll={{ x: 540 }} locale={{ emptyText: "暂无可展示的奖励档位" }}
                                columns={[
                                    { title: "获奖名次", render: (_, row) => rewardRange(row), width: 180 },
                                    { title: "道具奖励", render: (_, row) => row.itemId === null ? "无" : `${row.itemName || `道具 #${row.itemId}`} × ${row.itemCount}` },
                                    { title: "称号奖励", render: (_, row) => row.degreeId === null ? "无" : row.degreeName || `称号 #${row.degreeId}` },
                                ]} />
                        </Card>

                        <Card title="立即操作：开放、结算与换季">
                            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                                {dirty && <Alert type="warning" showIcon message="有尚未保存的设置；请先保存或放弃修改，再执行排行榜操作。" />}
                                <Alert
                                    type={detail.availability.enabled ? "success" : "warning"}
                                    showIcon
                                    message={detail.availability.enabled ? "排行榜当前开放" : "排行榜当前已冻结"}
                                    description={detail.availability.enabled
                                        ? "玩家可以查看排行榜，完整通关成绩会继续写入当前赛季。"
                                        : "玩家仍可查看当前赛季已有名次，但不会再记录新成绩；换季前必须先完成结算。"}
                                />
                                <Space wrap>
                                    <Tag color={detail.availability.enabled ? "green" : "default"}>
                                        {detail.availability.enabled ? "开放中" : "已冻结"}
                                    </Tag>
                                    {detail.availability.enabled ? (
                                        <Popconfirm
                                            title="关闭排行榜？"
                                            description="将立即停止记录新成绩，并终止当前尚未完成的排行榜挑战；玩家仍可查看已完成名次。"
                                            okText="确认关闭"
                                            okButtonProps={{ danger: true }}
                                            onConfirm={() => { if (!draftDirty.current) setAvailability.mutate(false); else message.warning("请先保存或放弃设置修改") }}
                                        >
                                            <Button danger loading={setAvailability.isPending} disabled={dirty || workPending && !setAvailability.isPending}>关闭排行榜</Button>
                                        </Popconfirm>
                                    ) : (
                                        <Button
                                            type="primary"
                                            loading={setAvailability.isPending} disabled={dirty || workPending && !setAvailability.isPending}
                                            onClick={() => { if (!draftDirty.current) setAvailability.mutate(true) }}
                                        >开启排行榜</Button>
                                    )}
                                    <Popconfirm
                                        title="结算当前赛季？"
                                        description="将冻结当前赛季并按最终名次发放邮件奖励；重复执行不会重复发奖，不会自动换季。"
                                        onConfirm={() => { if (!draftDirty.current) settle.mutate(); else message.warning("请先保存或放弃设置修改") }}
                                    >
                                        <Button loading={settle.isPending} disabled={dirty || workPending && !settle.isPending}>结算并发奖</Button>
                                    </Popconfirm>
                                    <Popconfirm
                                        title="进入下一赛季？"
                                        description="只切换到空的新赛季，不会发奖；当前赛季必须已经结算。"
                                        okText="确认换季"
                                        okButtonProps={{ danger: true }}
                                        onConfirm={() => { if (!draftDirty.current) rollover.mutate(); else message.warning("请先保存或放弃设置修改") }}
                                    >
                                        <Button danger loading={rollover.isPending} disabled={dirty || workPending && !rollover.isPending}>进入下一赛季</Button>
                                    </Popconfirm>
                                    <Text type="secondary">
                                        状态更新时间：{dayjs(detail.availability.updatedAtMs).format("YYYY-MM-DD HH:mm:ss")}
                                    </Text>
                                </Space>
                            </Space>
                        </Card>

                        <Card title="定时、邮件与奖励设置" extra={dirty ? <Tag color="orange">有未保存的修改</Tag> : <Tag>与已保存配置一致</Tag>}>
                            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                                <Alert
                                    type="info"
                                    showIcon
                                    message="到时冻结可单独开启，停榜后由管理员审核并手动发奖；自动发奖开启时同时冻结。两个动作共用截止时间，均不会自动换季。"
                                />
                                <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
                                    <Descriptions.Item label="到时冻结">
                                        <Switch
                                            aria-label="到时冻结"
                                            checked={draft.freezeEnabled || draft.autoEnabled}
                                            disabled={draft.autoEnabled}
                                            onChange={value => setDraft({ ...draft, freezeEnabled: value })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="自动发奖">
                                        <Switch
                                            aria-label="自动发奖"
                                            checked={draft.autoEnabled}
                                            onChange={value => setDraft({ ...draft, autoEnabled: value,
                                                freezeEnabled: value || draft.freezeEnabled })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="排除机器人账号参榜及发奖">
                                        <Switch
                                            aria-label="排除机器人账号参榜及发奖"
                                            checked={draft.excludeBots}
                                            onChange={value => setDraft({ ...draft, excludeBots: value })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="截止时间（北京时间）">
                                        <Input
                                            aria-label="截止时间（北京时间）"
                                            type="datetime-local"
                                            value={draft.settleAtText}
                                            onChange={event => setDraft({ ...draft, settleAtText: event.target.value })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="自动发奖重复间隔（小时，留空为一次性）">
                                        <InputNumber
                                            aria-label="自动发奖重复间隔（小时）"
                                            disabled={!draft.autoEnabled}
                                            min={0.01}
                                            precision={2}
                                            value={draft.repeatHours}
                                            onChange={value => setDraft({ ...draft, repeatHours: value })}
                                            style={{ width: "100%" }}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="邮件标题">
                                        <Input
                                            aria-label="结算邮件标题"
                                            value={draft.mailSubject}
                                            onChange={event => setDraft({ ...draft, mailSubject: event.target.value })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="邮件正文">
                                        <Input.TextArea
                                            aria-label="结算邮件正文"
                                            rows={2}
                                            value={draft.mailBody}
                                            onChange={event => setDraft({ ...draft, mailBody: event.target.value })}
                                        />
                                    </Descriptions.Item>
                                </Descriptions>
                                <Paragraph type="secondary">
                                    仅设置时间、两个开关均关闭时不会触发操作。关闭自动发奖后，到时冻结仍保留当前设置。
                                    到点后立即停止接收新成绩；自动发奖通常在下一次定时检查时执行。
                                    时间调整或关闭定时开关不会自动重新开放已经冻结的排行榜。
                                </Paragraph>

                                <LeaderboardRewardEditor value={draft.rewardTiersText} onChange={value => setDraft({ ...draft, rewardTiersText: value })} />
                                <Paragraph type="secondary">
                                    奖励档位、邮件和定时开关都在点击“保存设置”后生效。已保存的实际名次范围见上方奖励预览。
                                </Paragraph>
                                <Space wrap>
                                    <Button
                                        type="primary"
                                        icon={<SaveOutlined />}
                                        loading={saveConfig.isPending}
                                        disabled={!!rewardError || workPending && !saveConfig.isPending}
                                        onClick={() => {
                                            if (selectedKey && draft && !saveConfig.isPending) saveConfig.mutate({
                                                key: selectedKey, submitted: { ...draft }, revision: editRevision.current,
                                            })
                                        }}
                                    >保存设置</Button>
                                    {dirty && <Popconfirm title="放弃未保存的设置？" onConfirm={() => {
                                        editRevision.current++; draftDirty.current = false; setDirty(false)
                                        replaceDraft(configToDraft(overview.config))
                                    }}><Button disabled={workPending}>放弃修改</Button></Popconfirm>}
                                </Space>
                            </Space>
                        </Card>

                        <Card title="结算历史">
                            <Table<SettlementHistory>
                                rowKey="id"
                                size="small"
                                pagination={false}
                                dataSource={overview.history}
                                scroll={{ x: 780 }}
                                columns={[
                                    { title: "赛季", dataIndex: "season" },
                                    { title: "发起方式", dataIndex: "source", render: value => ({ manual: "手动结算", scheduler: "定时结算" }[value as string] ?? "其他方式") },
                                    { title: "上榜人数", dataIndex: "ranked_players" },
                                    { title: "发奖人数", dataIndex: "rewarded_players" },
                                    { title: "状态", dataIndex: "status", render: value => <Tag color={value === "completed" ? "green" : "orange"}>{value === "completed" ? "已完成" : value === "running" ? "进行中" : "待处理"}</Tag> },
                                    { title: "结算时间", dataIndex: "settled_at_ms", render: value => dayjs(value).format("YYYY-MM-DD HH:mm:ss") },
                                ]}
                            />
                        </Card>
                    </>
                )}
            </Space>
        </AdminPage>
    )
}
