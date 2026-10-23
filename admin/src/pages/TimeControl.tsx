import { useMemo, useState } from "react"
import { Alert, Button, Card, Empty, Input, Pagination, Space, Table, Tag, Typography } from "antd"
import { ArrowLeftOutlined, ReloadOutlined } from "@ant-design/icons"
import { useQuery } from "@tanstack/react-query"
import { apiGet } from "../api/client"
import { AdminPage } from "../components/AdminPage"
import { useAdminNavigate } from "../lib/editGuard"

interface ClairvoyanceCharacter {
    id: number
    name: string
    title: string
    rarity: number | null
    element: number | null
}

interface ClairvoyanceGacha {
    id: number
    name: string
    type: "character"
    pageKind: number
    startDate: string
    endDate: string
    durationDays: number
    rateUpCharacters: ClairvoyanceCharacter[]
}

interface ClairvoyanceSearchRow {
    characterId: number
    name: string
    title: string
    gachas: Array<Pick<ClairvoyanceGacha, "id" | "name" | "startDate" | "endDate">>
}

interface ClairvoyanceGachaCatalog {
    cdnVersion: string
    baseline: string
    scope: "short-up-character-gacha"
    catalogVersion: string
    timeline: ClairvoyanceGacha[]
    searchIndex: ClairvoyanceSearchRow[]
}
function normalizeSearch(value: string): string {
    return value.normalize("NFKC").trim().toLowerCase()
}

function renderGachaPeriod(gacha: Pick<ClairvoyanceGacha, "startDate" | "endDate">): string {
    return `${gacha.startDate} - ${gacha.endDate}`
}

function renderRateUpCharacters(characters: ClairvoyanceCharacter[]) {
    return (
        <Space wrap size={[4, 4]}>
            {characters.map(character => (
                <Tag key={character.id} color={character.rarity === 5 ? "gold" : character.rarity === 4 ? "purple" : "blue"}
                    style={{ maxWidth: "100%", whiteSpace: "normal", overflowWrap: "anywhere" }}>
                    {character.name} <Typography.Text type="secondary" style={{ fontSize: 12 }}>#{character.id}</Typography.Text>
                </Tag>
            ))}
        </Space>
    )
}

export default function HistoricalGacha() {
    const navigate = useAdminNavigate()
    const [search, setSearch] = useState("")
    const [page, setPage] = useState(1)
    const { data, isPending, isFetching, isError, refetch } = useQuery({
        queryKey: ["historicalGachaCatalog"],
        queryFn: ({ signal }) => apiGet<ClairvoyanceGachaCatalog>("/api/server/clairvoyance/gacha?view=catalog", { signal }),
        staleTime: 5 * 60_000, gcTime: 15 * 60_000,
    })
    const normalized = normalizeSearch(search)
    const results = useMemo(() => normalized && data ? data.searchIndex.filter(row =>
        normalizeSearch(`${row.characterId} ${row.name} ${row.title}`).includes(normalized)) : [], [normalized, data])
    const pageSize = 20, currentPage = Math.min(page, Math.max(1, Math.ceil(results.length / pageSize)))
    const openPool = (id: number) => navigate(`/content?group=gacha&type=gacha&search=${encodeURIComponent(`gacha:${id}`)}`)
    return <AdminPage eyebrow="HISTORY" title="历史卡池资料" description="按角色查找历史 UP 卡池，查看原始档期。"
        actions={<Space wrap><Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/content")}>返回内容运营</Button>
            <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>刷新资料</Button></Space>}>
        <Space direction="vertical" size="large" className="admin-stack">
            <Alert type="info" showIcon message="这里展示历史资料，当前开放状态请到内容运营查看。"
                description="此目录只包含有明确 UP 角色的短期角色池，原始档期不决定当前开关。" />
            {isError ? <Alert type="error" showIcon message="历史卡池资料读取失败"
                action={<Button onClick={() => void refetch()}>重新加载</Button>} /> : <>
                <Card title="按 UP 角色查找" extra={data && <Tag>{data.searchIndex.length} 位角色</Tag>} loading={isPending}>
                    <Space direction="vertical" size="middle" className="admin-stack">
                        <Input allowClear aria-label="搜索 UP 角色" placeholder="角色名称、称号或编号"
                            value={search} onChange={event => { setSearch(event.target.value); setPage(1) }} />
                        {!normalized ? <Typography.Text type="secondary">输入角色名称，查看其曾经 UP 的卡池。</Typography.Text> : results.length ? <>
                            <Typography.Text role="status">找到 {results.length} 位 UP 角色 · 第 {currentPage} 页</Typography.Text>
                            {results.slice((currentPage - 1) * pageSize, currentPage * pageSize).map(row => <div className="admin-clairvoyance-panel" key={row.characterId}>
                                <Space wrap><Typography.Text strong>{row.name}</Typography.Text><Typography.Text type="secondary">{row.title}</Typography.Text></Space>
                                <Space direction="vertical" className="admin-stack" size="small">{row.gachas.map(gacha => <div className="admin-history-pool" key={gacha.id}>
                                    <div><Typography.Text>{gacha.name}</Typography.Text><br /><Typography.Text type="secondary">原档期：{renderGachaPeriod(gacha)}</Typography.Text></div>
                                    <Button size="small" onClick={() => openPool(gacha.id)}>查看运营状态</Button>
                                </div>)}</Space>
                            </div>)}
                            <Pagination size="small" responsive current={currentPage} pageSize={pageSize} total={results.length}
                                onChange={setPage} showSizeChanger={false} hideOnSinglePage />
                        </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的 UP 角色，请换用名称、称号或编号" />}
                    </Space>
                </Card>
                <Card title="原始卡池档期" extra={data && <Tag>{data.timeline.length} 个卡池</Tag>}>
                    <Table<ClairvoyanceGacha> rowKey="id" size="small" loading={isPending} dataSource={data?.timeline ?? []}
                        scroll={{ x: 1040 }} pagination={{ pageSize: 8, showSizeChanger: false, showTotal: total => `共 ${total} 个卡池` }}
                        columns={[
                            { title: "卡池", dataIndex: "name", width: 260, render: (name: string) => <Typography.Text style={{ overflowWrap: "anywhere" }}>{name}</Typography.Text> },
                            { title: "原始档期", width: 300, render: (_: unknown, row) => renderGachaPeriod(row) },
                            { title: "UP 角色", width: 320, render: (_: unknown, row) => renderRateUpCharacters(row.rateUpCharacters) },
                            { title: "操作", width: 150, render: (_: unknown, row) => <Button size="small" onClick={() => openPool(row.id)}>查看运营状态</Button> },
                        ]} />
                </Card>
            </>}
        </Space>
    </AdminPage>
}
