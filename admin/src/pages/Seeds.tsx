import { Alert, Card, Segmented, Button, Space, Statistic, Progress, Spin, Empty, Modal, Pagination, message, Typography } from "antd"
import { ReloadOutlined, CloseOutlined } from "@ant-design/icons"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState, type CSSProperties } from "react"
import { apiGet, apiPost, apiDelete } from "../api/client"
import { AdminPage, StateCard } from "../components/AdminPage"
import { useAdminEditGuard } from "../lib/editGuard"
import { assertSeedActionSucceeded, formatCatalogCoverage, type SeedAdminAction, type SeedMode } from "../lib/seedAdminActions"
import "./Seeds.css"

const { Text } = Typography

type PoolMode = SeedMode
const MODE_LABELS: Record<PoolMode, string> = { natural: "自然抽取", play: "播放优先", test: "测试抽取" }
const MODE_HELP: Record<PoolMode, string> = {
    natural: "优先使用静态动画变体目录（gacha-movie-variants）；未选到可用变体时，才回退到已学习种子的原有选择规则。",
    play: "优先选择播放池中的有效种子，再沿用原有回退规则。",
    test: "优先选择尚待验证的播放种子，再尝试待验证和未知种子。",
}

// 卡池组：每组聚合 基础 + 保底 两个 movie（与旧 seeds.html 一致）
const GROUPS = [
    { id: "fes", name: "流星祭" },
    { id: "normal", name: "普通" },
]

const TAGS = ["未测试", "热血躲避球", "普通躲避球", "冷血躲避球"] as const
const TAG_SHORT = ["未标注", "热血", "普通", "无效"]
const TAG_COLOR = ["#6e7681", "#f85149", "#1677ff", "#6e7681"]
type Tag = typeof TAGS[number]

// 每个种子附带来源 movie 与是否保底
interface SeedRow { seed: number; rarity: number; tag?: Tag; movie: string; isGuarantee: boolean }
type ListKind = "play" | "verified"
type ColumnCounts = Record<"r3" | "r4" | "r4b" | "r5" | "r5b", number>
interface SeedPage { page: number; pageSize: number; total: number; rows: SeedRow[] }
const PAGE_SIZE = 100

interface GroupData {
    mode: PoolMode
    testSeeds: (number | null)[]
    testSeedTags: (Tag | null)[]
    confirm: number; pending: number; unknown: number | null
    verified: number; play: number
    baseConfirm: number; gtConfirm: number
    total: number; tested: number | null; coverage: number | null
    catalogTotal: number; catalogKnown: number | null; catalogAvailable: boolean; learned: number; externalKnown: number | null
    columns: Record<ListKind, ColumnCounts>
}

// 列定义：★3 不分保底，★4/★5 各分普通/保底
const COLUMNS: { key: keyof ColumnCounts; label: string; rarity: number; guarantee: boolean; color: string }[] = [
    { key: "r3", label: "★3", rarity: 3, guarantee: false, color: "#f85149" },
    { key: "r4", label: "★4", rarity: 4, guarantee: false, color: "#d29922" },
    { key: "r4b", label: "★4保底", rarity: 4, guarantee: true, color: "#b0882c" },
    { key: "r5", label: "★5", rarity: 5, guarantee: false, color: "#3fb950" },
    { key: "r5b", label: "★5保底", rarity: 5, guarantee: true, color: "#2ea043" },
]

function inColumn(row: SeedRow, rarity: number, guarantee: boolean): boolean {
    if (row.rarity !== rarity) return false
    if (rarity === 3) return true // ★3 不分保底
    return row.isGuarantee === guarantee
}

export default function Seeds() {
    const qc = useQueryClient()
    const [groupId, setGroupId] = useState("fes")
    const [verifiedOpen, setVerifiedOpen] = useState(false)
    const [playOpen, setPlayOpen] = useState(false)
    const [verifiedPage, setVerifiedPage] = useState(1)
    const [playPage, setPlayPage] = useState(1)
    const [failedAction, setFailedAction] = useState<{ action: SeedAdminAction; error: string } | null>(null)
    const operationInFlight = useRef(false)

    const { data, isLoading, isError, refetch, isFetching } = useQuery({
        queryKey: ["seeds", groupId, "overview"],
        queryFn: ({ signal }) => apiGet<GroupData>(`/api/seeds/group/${groupId}/overview`, { signal }),
    })
    const verifiedQuery = useQuery({
        queryKey: ["seeds", groupId, "verified", verifiedPage],
        queryFn: ({ signal }) => apiGet<SeedPage>(`/api/seeds/group/${groupId}/list?kind=verified&page=${verifiedPage}&pageSize=${PAGE_SIZE}`, { signal }),
        enabled: verifiedOpen,
    })
    const playQuery = useQuery({
        queryKey: ["seeds", groupId, "play", playPage],
        queryFn: ({ signal }) => apiGet<SeedPage>(`/api/seeds/group/${groupId}/list?kind=play&page=${playPage}&pageSize=${PAGE_SIZE}`, { signal }),
        enabled: playOpen,
    })
    useEffect(() => { if (verifiedQuery.data && verifiedQuery.data.page !== verifiedPage) setVerifiedPage(verifiedQuery.data.page) }, [verifiedQuery.data, verifiedPage])
    useEffect(() => { if (playQuery.data && playQuery.data.page !== playPage) setPlayPage(playQuery.data.page) }, [playQuery.data, playPage])

    const invalidate = () => qc.invalidateQueries({ queryKey: ["seeds"] })

    const actionMutation = useMutation({
        mutationFn: async (action: SeedAdminAction) => {
            const result = action.kind === "mode" ? await apiPost("/api/seeds/mode", { mode: action.mode })
                : action.kind === "tag" ? await apiPost("/api/seeds/tag", { seed: action.seed, tag: action.tag, movieId: action.movie })
                    : action.kind === "set-test" ? await apiPost("/api/seeds/test-seed", { seed: action.seed, rarity: action.rarity })
                        : await apiDelete(`/api/seeds/test-seed?rarity=${action.rarity}`)
            assertSeedActionSucceeded(result, action)
        },
        onSuccess: async (_result, action) => {
            setFailedAction(null)
            message.success(action.kind === "mode" ? `已切换为${MODE_LABELS[action.mode]}` : action.kind === "tag" ? "播放标签已更新"
                : action.kind === "set-test" ? `★${action.rarity}全局测试种子已设置` : `★${action.rarity}全局测试种子已清除`)
            await invalidate()
        },
        onError: (error: Error, action) => { setFailedAction({ action, error: error.message }); message.error(error.message) },
        onSettled: () => { operationInFlight.current = false },
    })
    const pending = actionMutation.isPending
    useAdminEditGuard({ dirty: false, pending, label: "种子管理" })
    const submitAction = (action: SeedAdminAction) => {
        if (operationInFlight.current) return
        operationInFlight.current = true; setFailedAction(null); actionMutation.mutate(action)
    }
    const requestAction = (action: SeedAdminAction) => {
        if (pending || operationInFlight.current) return
        if (action.kind === "tag" && action.tag !== "冷血躲避球") { submitAction(action); return }
        const title = action.kind === "mode" ? `切换为${MODE_LABELS[action.mode]}？` : action.kind === "set-test" ? `设置★${action.rarity}全局测试种子？`
            : action.kind === "clear-test" ? `清除★${action.rarity}全局测试种子？` : "将此播放种子标记为无效？"
        const content = action.kind === "mode" ? "该模式是全服设置。进入普通种子选择流程时，同星级全局测试种子仍优先；部分特殊动画会提前返回，不经过此流程。"
            : action.kind === "set-test" ? `★${action.rarity}进入普通种子选择流程时将优先使用种子 ${action.seed}，不限定当前卡池组或抽取模式；特殊动画可能不经过此流程。其他星级保持原设置。`
                : action.kind === "clear-test" ? `清除★${action.rarity}的全局测试覆盖后，进入种子选择流程时恢复当前模式的原有规则；其他星级不变。`
                    : "原有选取规则会跳过此播放种子。已经设置的全局测试种子仍需单独清除。"
        Modal.confirm({ title, content, okText: "确认操作", cancelText: "取消", onOk: () => submitAction(action) })
    }

    // 单个种子行
    const SeedLine = ({ row, kind }: { row: SeedRow; kind: ListKind }) => {
        const cold = row.tag === "冷血躲避球"
        const isTest = data?.testSeeds[row.rarity - 3] === row.seed
        return (
            <div className="admin-seed-line" style={{ opacity: cold ? 0.45 : 1, textDecoration: cold ? "line-through" : "none" }}>
                <span className="admin-seed-id">{row.seed}</span>
                {kind === "play" && TAGS.map((t, i) => (
                    <button
                        key={t}
                        title={t}
                        aria-pressed={row.tag === t}
                        disabled={pending}
                        className={`admin-chip-button ${row.tag === t ? "is-active" : ""}`}
                        onClick={() => requestAction({ kind: "tag", seed: row.seed, tag: t, movie: row.movie })}
                        style={{ "--chip-color": TAG_COLOR[i] } as CSSProperties}
                    >
                        {TAG_SHORT[i]}
                    </button>
                ))}
                {kind === "verified" && (
                    <button
                        disabled={pending}
                        title="设置为该星级的全局测试种子"
                        className={`admin-chip-button ${isTest ? "is-active" : ""}`}
                        onClick={() => requestAction({ kind: "set-test", seed: row.seed, rarity: row.rarity })}
                        style={{ "--chip-color": "var(--admin-primary)" } as CSSProperties}
                    >
                        ★{row.rarity}全局测试
                    </button>
                )}
            </div>
        )
    }

    const SeedColumns = ({ rows, kind }: { rows: SeedRow[]; kind: ListKind }) => (
        <div className="admin-seed-grid">
            {COLUMNS.map(col => {
                const items = rows.filter(r => inColumn(r, col.rarity, col.guarantee))
                return (
                    <div key={col.key} className="admin-seed-column">
                        <div className="admin-seed-column-title" style={{ color: col.color }}>
                            {col.label} ({data?.columns[kind][col.key] ?? 0})
                        </div>
                        {items.length === 0
                            ? <Text type="secondary" style={{ fontSize: 12 }}>本页暂无</Text>
                            : items.map(r => <SeedLine key={`${r.movie}_${r.seed}`} row={r} kind={kind} />)}
                    </div>
                )
            })}
        </div>
    )

    const renderList = (kind: ListKind) => {
        const query = kind === "verified" ? verifiedQuery : playQuery
        const updatePage = kind === "verified" ? setVerifiedPage : setPlayPage
        if (query.isLoading) return <Spin />
        if (query.isError) return <Alert type="error" showIcon message="种子列表读取失败" action={<Button onClick={() => query.refetch()}>重试列表</Button>} />
        const result = query.data
        if (!result?.rows.length) return <Empty description={kind === "verified" ? "暂无已验证种子" : "暂无播放种子"} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        return <Space direction="vertical" className="admin-stack">
            <SeedColumns rows={result.rows} kind={kind} />
            <Pagination size="small" current={result.page} pageSize={PAGE_SIZE} total={result.total} showSizeChanger={false}
                onChange={updatePage} showTotal={total => `共 ${total} 条`} />
        </Space>
    }

    if (isLoading) return <StateCard><Spin size="large" /></StateCard>
    if (!data) return <Alert type="error" showIcon message="种子接口不可用" action={<Button onClick={() => refetch()}>重试</Button>} />

    return (
        <AdminPage
            eyebrow="SEEDS"
            title="种子管理"
            description="查看种子学习记录、标注播放标签，并管理全服抽取模式与全局测试种子。"
        >
        <Space direction="vertical" size="large" className="admin-stack seeds-page">
            {isError && <Alert type="error" showIcon message="刷新种子概况失败，当前数据已保留。" />}
            {pending && <Alert type="info" showIcon message="操作正在提交，请等待结果。" />}
            {failedAction && <Alert type="error" showIcon message={failedAction.error} description="请先刷新状态确认当前值，再重试。" closable onClose={() => setFailedAction(null)}
                action={<Space wrap><Button disabled={pending} onClick={() => invalidate()}>刷新状态</Button><Button disabled={pending} onClick={() => requestAction(failedAction.action)}>重试操作</Button></Space>} />}
            <Card title="全服抽取规则" size="small" extra={<Button icon={<ReloadOutlined />} loading={isFetching || verifiedQuery.isFetching || playQuery.isFetching}
                onClick={() => qc.invalidateQueries({ queryKey: ["seeds", groupId] })}>刷新状态</Button>}>
            <Space direction="vertical" size="middle" className="admin-stack">
            <div className="admin-toolbar">
                <Text strong>抽取模式</Text>
                <Segmented
                    value={data.mode}
                    disabled={pending}
                    onChange={v => requestAction({ kind: "mode", mode: v as PoolMode })}
                    options={[
                        { label: MODE_LABELS.natural, value: "natural" },
                        { label: MODE_LABELS.play, value: "play" },
                        { label: MODE_LABELS.test, value: "test" },
                    ]}
                />
            </div>
            <Alert type="info" showIcon message={`当前全服模式：${MODE_LABELS[data.mode]}`} description={MODE_HELP[data.mode]} />
            <Text type="secondary">这里控制动画种子的选择，不改变角色抽取概率。全局测试种子优先于普通选择规则；部分特殊动画会提前返回，因此不会覆盖所有动画。</Text>
            </Space>
            </Card>

            <Card title="当前卡池组的学习记录" size="small" extra={<Segmented aria-label="查看卡池组" value={groupId} disabled={pending} onChange={v => { setGroupId(v as string); setVerifiedPage(1); setPlayPage(1); setVerifiedOpen(false); setPlayOpen(false) }}
                options={GROUPS.map(g => ({ label: g.name, value: g.id }))} />}>
                <p className="seed-section-note">切换卡池组只改变下方记录与目录统计；全服模式和测试位置保持共用。数量为 0 表示此环境暂无对应记录。</p>
                <div className="admin-metric-row">
                    <Statistic title="验证池" value={data.verified} valueStyle={{ color: "var(--admin-primary-strong)" }} />
                    <Statistic title="播放池" value={data.play} valueStyle={{ color: "var(--admin-primary-strong)" }} />
                    <Statistic title="确认·非保底" value={data.baseConfirm} valueStyle={{ color: "#3fb950" }} />
                    <Statistic title="确认·保底" value={data.gtConfirm} valueStyle={{ color: "#b0882c" }} />
                </div>
            </Card>

            <Card title="验证池与全局测试位置" size="small"
                extra={<Space wrap><Text type="secondary" style={{ fontSize: 12 }}>星级已通过客户端校验</Text>
                    <Button size="small" onClick={() => setVerifiedOpen(open => !open)}>{verifiedOpen ? "收起验证池列表" : "查看验证池列表"}</Button></Space>}>
                <div style={{ marginBottom: 12 }}>
                    <Space wrap size="small">
                        <Text type="secondary" style={{ fontSize: 12 }}>★3、★4、★5各有一个共用测试位置：</Text>
                        {[3, 4, 5].map(r => {
                            const ts = data.testSeeds[r - 3]
                            return (
                                <span key={r} style={{ fontSize: 12 }}>
                                    ★{r}=
                                    {ts != null ? (
                                        <>
                                            <span style={{ color: "var(--admin-primary-strong)" }}> {ts} </span>
                                            <Button type="text" size="small" danger icon={<CloseOutlined />} disabled={pending} aria-label={`清除★${r}全局测试种子`}
                                                onClick={() => requestAction({ kind: "clear-test", rarity: r })} />
                                        </>
                                    ) : <span style={{ color: "#888" }}> [无] </span>}
                                </span>
                            )
                        })}
                    </Space>
                </div>
                <p className="seed-section-note">展开验证池后可将种子设到对应星级的测试位置；清除该位置后恢复原有选择规则。</p>
                {verifiedOpen && renderList("verified")}
            </Card>

            <Card title="播放池" size="small"
                extra={<Space wrap><Text type="secondary" style={{ fontSize: 12 }}>已播放，星级仍待客户端校验；可标注播放标签</Text>
                    <Button size="small" onClick={() => setPlayOpen(open => !open)}>{playOpen ? "收起播放池列表" : "查看播放池列表"}</Button></Space>}>
                {playOpen && renderList("play")}
            </Card>

            <Card title="学习记录与目录覆盖" size="small">
                <Space size="large" wrap style={{ marginBottom: 12 }}>
                    <Statistic title="确认池" value={data.confirm} valueStyle={{ color: "#3fb950" }} />
                    <Statistic title="等待校验" value={data.pending} valueStyle={{ color: "#3fb950" }} />
                    <Statistic title="目录未覆盖" value={data.unknown ?? "—"} valueStyle={{ color: "#6e7681" }} />
                    <Statistic title="已学习记录" value={data.learned} />
                    <Statistic title="其中目录外" value={data.externalKnown ?? "—"} />
                </Space>
                {data.catalogAvailable && data.coverage !== null && data.catalogKnown !== null
                    ? <><Progress percent={data.coverage} showInfo={false} size="small" style={{ maxWidth: 400 }} />
                        <div><Text type="secondary">目录已记录 {data.catalogKnown.toLocaleString()} / {data.catalogTotal.toLocaleString()} · 覆盖率 {formatCatalogCoverage(data.catalogKnown, data.catalogTotal)}</Text></div></>
                    : <Alert type="warning" showIcon message="种子目录未完整加载或为空，暂不计算覆盖率。" />}
                <Text type="secondary">仅统计当前卡池组；同一卡池重复记录只计一次。目录外学习记录另列，仍保留原有用途。</Text>
            </Card>
        </Space>
        </AdminPage>
    )
}
