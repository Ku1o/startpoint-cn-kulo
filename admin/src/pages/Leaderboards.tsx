import { useEffect, useMemo, useState } from "react"
import {
    Alert,
    Button,
    Card,
    Col,
    Descriptions,
    Input,
    InputNumber,
    Popconfirm,
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
import { apiGet, apiPatch, apiPost } from "../api/client"
import { AdminPage, StateCard } from "../components/AdminPage"

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

interface RewardTier {
    fromRank: number
    toRank: number | null
    itemId: number | null
    itemName: string | null
    itemCount: number
    degreeId: number | null
    degreeName: string | null
    degreeImage: string | null
}

interface SettlementConfig {
    competitionKey: string
    autoEnabled: boolean
    settleAtMs: number | null
    repeatIntervalMs: number | null
    rewardTiers: RewardTier[]
    mailSubject: string
    mailBody: string
    excludeBots: boolean
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
}

interface CompetitionSummary {
    competition: Competition
    overview: Overview
}

interface RankRow {
    id: number
    rankNumber: number
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
    overview: Overview
    page: number
    rows: RankRow[]
    total: number
}

interface ConfigDraft {
    autoEnabled: boolean
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
        settleAtText: config.settleAtMs === null
            ? ""
            : dayjs(config.settleAtMs).format("YYYY-MM-DDTHH:mm"),
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
    const [draft, setDraft] = useState<ConfigDraft | null>(null)

    const listQuery = useQuery({
        queryKey: ["leaderboards"],
        queryFn: () => apiGet<CompetitionSummary[]>("/api/leaderboards/"),
        refetchInterval: 30_000,
    })

    useEffect(() => {
        if (selectedKey === null && listQuery.data?.length) {
            setSelectedKey(listQuery.data[0].competition.key)
        }
    }, [listQuery.data, selectedKey])

    const detailQuery = useQuery({
        queryKey: ["leaderboard", selectedKey, page],
        queryFn: () => apiGet<LeaderboardDetail>(
            `/api/leaderboards/${encodeURIComponent(selectedKey!)}` + `?page=${page}`,
        ),
        enabled: selectedKey !== null,
        refetchInterval: 30_000,
    })

    useEffect(() => {
        if (detailQuery.data) setDraft(configToDraft(detailQuery.data.overview.config))
    }, [detailQuery.data?.overview.config.updatedAtMs, selectedKey])

    const invalidate = async () => {
        await queryClient.invalidateQueries({ queryKey: ["leaderboards"] })
        await queryClient.invalidateQueries({ queryKey: ["leaderboard", selectedKey] })
    }

    const saveConfig = useMutation({
        mutationFn: async () => {
            if (selectedKey === null || draft === null) throw new Error("尚未选择排行榜。")
            let rewardTiers: RewardTier[]
            try {
                rewardTiers = JSON.parse(draft.rewardTiersText) as RewardTier[]
            } catch {
                throw new Error("奖励档位不是有效的 JSON。")
            }
            const settleAtMs = draft.settleAtText === ""
                ? null
                : dayjs(draft.settleAtText).valueOf()
            if (settleAtMs !== null && !Number.isFinite(settleAtMs)) {
                throw new Error("结算时间无效。")
            }
            return apiPatch(`/api/leaderboards/${encodeURIComponent(selectedKey)}/config`, {
                autoEnabled: draft.autoEnabled,
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
        onSuccess: async () => {
            message.success("排行榜结算配置已保存")
            await invalidate()
        },
        onError: (error: Error) => message.error(error.message),
    })

    const settle = useMutation({
        mutationFn: (rollover: boolean) => apiPost(
            `/api/leaderboards/${encodeURIComponent(selectedKey!)}/${rollover ? "rollover" : "settle"}`,
        ),
        onSuccess: async (_data, rollover) => {
            message.success(rollover ? "本赛季已结算并进入下一赛季" : "本赛季已完成结算")
            setPage(0)
            await invalidate()
        },
        onError: (error: Error) => message.error(error.message),
    })

    const rewardRows = useMemo(() => {
        if (!draft) return []
        try {
            const parsed = JSON.parse(draft.rewardTiersText)
            return Array.isArray(parsed) ? parsed as RewardTier[] : []
        } catch {
            return []
        }
    }, [draft?.rewardTiersText])

    if (listQuery.isLoading) return <StateCard><Spin size="large" /></StateCard>
    if (listQuery.isError || !listQuery.data) {
        return <Alert type="error" showIcon message="排行榜管理接口不可用" />
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
            description="查看当前赛季名次，配置排名报酬，并执行幂等结算或赛季切换。"
            actions={(
                <Button
                    icon={<ReloadOutlined />}
                    loading={listQuery.isFetching || detailQuery.isFetching}
                    onClick={() => { listQuery.refetch(); detailQuery.refetch() }}
                >刷新</Button>
            )}
        >
            <Space direction="vertical" size="large" className="admin-stack">
                <Card>
                    <Space wrap>
                        {listQuery.data.map(entry => (
                            <Button
                                key={entry.competition.key}
                                type={selectedKey === entry.competition.key ? "primary" : "default"}
                                onClick={() => { setSelectedKey(entry.competition.key); setPage(0) }}
                            >
                                {entry.competition.displayName} #{entry.competition.eventId}
                            </Button>
                        ))}
                    </Space>
                </Card>

                {detailQuery.isLoading || !detail || !competition || !overview || !draft ? (
                    <StateCard><Spin size="large" /></StateCard>
                ) : (
                    <>
                        <Row gutter={[16, 16]}>
                            <Col xs={12} lg={6}><Card><Statistic title="当前赛季" value={overview.season} /></Card></Col>
                            <Col xs={12} lg={6}><Card><Statistic title="有效排名" value={detail.total} suffix="人" /></Card></Col>
                            <Col xs={12} lg={6}><Card><Statistic title="客户端展示上限" value={competition.displayLimit} /></Card></Col>
                            <Col xs={12} lg={6}><Card><Statistic title="每页" value={competition.pageSize} suffix="人" /></Card></Col>
                        </Row>

                        <Card title="当前赛季名次">
                            <Table<RankRow>
                                rowKey="id"
                                size="small"
                                dataSource={detail.rows}
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
                                            <Space>
                                                <span>{row.displayName}</span>
                                                <Text type="secondary">#{row.playerId}</Text>
                                                {!row.playerExists && <Tag color="red">已删除</Tag>}
                                            </Space>
                                        ),
                                    },
                                    { title: "Rank", dataIndex: "rankPoint", width: 90 },
                                    {
                                        title: "client_battle_ms",
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
                        </Card>

                        <Card title="结算设置">
                            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                                <Alert
                                    type="info"
                                    showIcon
                                    message="“仅结算”可安全重复执行，不会重复发奖；“结算并换季”会冻结本赛季并清空当前榜单视图。"
                                />
                                <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
                                    <Descriptions.Item label="自动结算">
                                        <Switch
                                            checked={draft.autoEnabled}
                                            onChange={value => setDraft({ ...draft, autoEnabled: value })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="排除 rushbot 发奖">
                                        <Switch
                                            checked={draft.excludeBots}
                                            onChange={value => setDraft({ ...draft, excludeBots: value })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="下次结算时间">
                                        <Input
                                            type="datetime-local"
                                            value={draft.settleAtText}
                                            onChange={event => setDraft({ ...draft, settleAtText: event.target.value })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="重复间隔（小时，留空为一次性）">
                                        <InputNumber
                                            min={0.01}
                                            precision={2}
                                            value={draft.repeatHours}
                                            onChange={value => setDraft({ ...draft, repeatHours: value })}
                                            style={{ width: "100%" }}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="邮件标题">
                                        <Input
                                            value={draft.mailSubject}
                                            onChange={event => setDraft({ ...draft, mailSubject: event.target.value })}
                                        />
                                    </Descriptions.Item>
                                    <Descriptions.Item label="邮件正文">
                                        <Input.TextArea
                                            rows={2}
                                            value={draft.mailBody}
                                            onChange={event => setDraft({ ...draft, mailBody: event.target.value })}
                                        />
                                    </Descriptions.Item>
                                </Descriptions>

                                <Table<RewardTier>
                                    rowKey={row => `${row.fromRank}-${row.toRank ?? "tail"}`}
                                    size="small"
                                    pagination={false}
                                    dataSource={rewardRows}
                                    columns={[
                                        { title: "排名", render: (_, row) => `${row.fromRank}–${row.toRank ?? "末位"}` },
                                        { title: "道具", render: (_, row) => row.itemId === null ? "-" : `${row.itemName ?? "道具"} #${row.itemId} ×${row.itemCount}` },
                                        { title: "称号", render: (_, row) => row.degreeId === null ? "-" : `${row.degreeName ?? "称号"} #${row.degreeId}` },
                                    ]}
                                />
                                <div>
                                    <Text strong>奖励档位 JSON</Text>
                                    <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                                        档位必须从第 1 名起连续排列；toRank 为 null 表示覆盖到末位。
                                    </Paragraph>
                                    <Input.TextArea
                                        rows={12}
                                        value={draft.rewardTiersText}
                                        onChange={event => setDraft({ ...draft, rewardTiersText: event.target.value })}
                                        style={{ fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace" }}
                                    />
                                </div>

                                <Space wrap>
                                    <Button
                                        type="primary"
                                        icon={<SaveOutlined />}
                                        loading={saveConfig.isPending}
                                        onClick={() => saveConfig.mutate()}
                                    >保存设置</Button>
                                    <Popconfirm
                                        title="结算当前赛季？"
                                        description="将按当前名次发放邮件奖励；重复执行不会重复发奖。"
                                        onConfirm={() => settle.mutate(false)}
                                    >
                                        <Button loading={settle.isPending}>仅结算</Button>
                                    </Popconfirm>
                                    <Popconfirm
                                        title="结算并进入下一赛季？"
                                        description="当前榜单会冻结，活动仍可继续记录下一赛季成绩。"
                                        onConfirm={() => settle.mutate(true)}
                                    >
                                        <Button danger loading={settle.isPending}>结算并换季</Button>
                                    </Popconfirm>
                                </Space>
                            </Space>
                        </Card>

                        <Card title="结算历史">
                            <Table<SettlementHistory>
                                rowKey="id"
                                size="small"
                                pagination={false}
                                dataSource={overview.history}
                                columns={[
                                    { title: "赛季", dataIndex: "season" },
                                    { title: "来源", dataIndex: "source" },
                                    { title: "上榜人数", dataIndex: "ranked_players" },
                                    { title: "发奖人数", dataIndex: "rewarded_players" },
                                    { title: "状态", dataIndex: "status", render: value => <Tag color={value === "completed" ? "green" : "orange"}>{value}</Tag> },
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
