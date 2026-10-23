import { useState } from "react"
import { Alert, Card, Descriptions, Table, Button, Space, InputNumber, Popconfirm, message, Tag, Tabs, Spin, Typography, Collapse, Switch, DatePicker, Input, Upload, Modal } from "antd"
import { SaveOutlined, DeleteOutlined, PlusOutlined, DownloadOutlined, UploadOutlined, UndoOutlined, SearchOutlined } from "@ant-design/icons"
import { useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import dayjs from "dayjs"
import { apiGet, apiPost, apiPatch, apiDelete, apiUpload } from "../api/client"
import { AdminPage, StateCard } from "../components/AdminPage"
import { useMailPlayerMutation } from "./MailPlayerMutation"
import { useLookup, type LookupKind } from "../api/lookups"
import { ADMIN_INT_MAX, PLAYER_TIME_OFFSET_MAX, integerError, playerNumberError } from "../lib/adminNumbers"
import "./PlayerComms.css"
import { useAdminEditGuard, useAdminNavigate } from "../lib/editGuard"

const { Text } = Typography

interface PlayerInfo {
    id: number; accountId: number; name: string; comment: string
    stamina: number; boostPoint: number; bossBoostPoint: number
    vmoney: number; freeVmoney: number; freeMana: number; paidMana: number
    rankPoint: number; starCrumb: number; bondToken: number
    expPool: number; degreeId: number; leaderCharacterId: number
    birth: number; enableAuto3x: boolean; tutorialStep: number | null
    lastLoginTime: string; staminaHealTime: string; expPooledTime: string; timeOffset: number | null
}

interface CharRow { code: number; joinTime: string; entryCount: number; evolutionLevel: number; overLimitStep: number; exp: number; stack: number; manaBoardIndex: number }
interface ItemRow { id: number; count: number }
interface EquipRow { id: number; level: number; enhancementLevel: number }
interface QuestRow { section: number; questId: number; finished: boolean; highScore: number | null; clearRank: number | null; bestElapsedTimeMs: number | null }
interface DrawnQuestRow { categoryId: number; questId: number; oddsId: number }
interface UnisonRepairResult {
    ok: boolean
    repaired: boolean
    status: string
    changes?: number
    message: string
}

interface ImportSaveResult {
    ok: boolean
    snapshotVersion: number
    backup?: string | null
    retainedBackups?: number | null
    removedBackups?: number
    backupCleanupError?: string | null
    restored?: {
        restoredTables: number
        restoredRows: number
        skippedTables: string[]
        resetTables: string[]
    }
}

interface DetailData {
    player: PlayerInfo
    characters: CharRow[]
    items: ItemRow[]
    equipment: EquipRow[]
    questProgress: QuestRow[]
    drawnQuests: DrawnQuestRow[]
}

interface Lookups {
    characters: Record<number, { name: string; title: string; rarity: string; element: string }>
    items: Record<number, string>
    equipment: Record<number, { name: string; rarity: string; category: string }>
    quests: Record<string, string>
}

const resourceFields: { key: string; label: string }[] = [
    { key: "expPool", label: "经验池" },
    { key: "freeVmoney", label: "星导石(免费)" },
    { key: "vmoney", label: "星导石(付费)" },
    { key: "freeMana", label: "Mana(免费)" },
    { key: "paidMana", label: "Mana(付费)" },
    { key: "stamina", label: "体力" },
    { key: "rankPoint", label: "等级经验" },
    { key: "starCrumb", label: "星屑" },
    { key: "bondToken", label: "羁绊证" },
    { key: "bossBoostPoint", label: "Boss Boost" },
    { key: "boostPoint", label: "Boost" },
]

const gridStyle: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }
const tabSections = { characters: "characters", items: "items", equipment: "equipment", quests: "questProgress", drawn: "drawnQuests" } as const
type PlayerTab = keyof typeof tabSections

export default function PlayerDetailRoute() {
    const { playerId } = useParams()
    // Route parameters can change without unmounting a matching React Router route.
    // Keep drafts and mutation observers scoped to one player.
    return <PlayerDetail key={playerId} />
}

export function PlayerDetail() {
    const { playerId } = useParams()
    const pid = Number(playerId)
    const navigate = useAdminNavigate()
    const qc = useQueryClient()
    const [editValues, setEditValues] = useState<Record<string, any>>({})
    const [addCharCode, setAddCharCode] = useState<number | undefined>()
    const [addItemId, setAddItemId] = useState<number | undefined>()
    const [addItemCount, setAddItemCount] = useState<number | null>(1)
    const [searchChars, setSearchChars] = useState("")
    const [searchItems, setSearchItems] = useState("")
    const [searchEquip, setSearchEquip] = useState("")
    const [searchQuests, setSearchQuests] = useState("")
    const [searchDrawn, setSearchDrawn] = useState("")
    const [activeTab, setActiveTab] = useState<PlayerTab>("characters")
    const section = tabSections[activeTab]

    const { data, isLoading, isError, refetch } = useQuery({
        queryKey: ["playerDetail", pid, "player"],
        queryFn: ({ signal }) => apiGet<Pick<DetailData, "player">>(`/api/player/${pid}/detail?section=player`, { signal }),
        enabled: !isNaN(pid),
    })
    const sectionQuery = useQuery({
        queryKey: ["playerDetail", pid, section],
        queryFn: ({ signal }) => apiGet<Partial<DetailData>>(`/api/player/${pid}/detail?section=${section}`, { signal }),
        enabled: !isNaN(pid),
        staleTime: 30_000,
        gcTime: 5 * 60_000,
    })
    const lookupKind: LookupKind = activeTab === "quests" || activeTab === "drawn" ? "quests" : activeTab
    const lookupQuery = useLookup(lookupKind, !isNaN(pid))
    const lookups: Lookups = { characters: {}, items: {}, equipment: {}, quests: {}, [lookupKind]: lookupQuery.data ?? {} }

    const refresh = (sections: readonly string[] = ["player"]) => Promise.all(sections.map(key =>
        qc.invalidateQueries({ queryKey: ["playerDetail", pid, key] })))

    const editField = useMailPlayerMutation({
        mutationFn: ({ field, value }: { field: string; value: any }) => {
            const problem = playerNumberError(field, value)
            if (problem) throw new Error(problem)
            return apiPatch(`/api/player/${pid}/field`, { field, value })
        },
        onSuccess: (_, { field, value }) => {
            message.success(`${resourceFields.find(item => item.key === field)?.label ?? ({ degreeId: "称号", leaderCharacterId: "队长角色", birth: "生日", tutorialStep: "教程步骤", enableAuto3x: "3倍加速", staminaHealTime: "体力恢复时间", lastLoginTime: "最后登录时间", expPooledTime: "经验池结算锚点", timeOffset: "结算时间基准" } as Record<string, string>)[field] ?? field}已保存`)
            setEditValues(v => {
                if (!Object.is(v[field], value)) return v
                const n = { ...v }
                delete n[field]
                return n
            })
            refresh()
        },
        onError: (e: Error) => { void message.error(e.message) },
    })

    const addChar = useMailPlayerMutation({
        mutationFn: (code: number) => {
            const problem = integerError(code, "角色编号", 1, Number.MAX_SAFE_INTEGER)
            if (problem) throw new Error(problem)
            return apiPost(`/api/player/${pid}/character`, { code })
        },
        onSuccess: (_, code) => { message.success("角色已直接写入存档"); setAddCharCode(current => current === code ? undefined : current); refresh(["player", "characters"]) },
        onError: (e: Error) => { void message.error(e.message) },
    })

    const delChar = useMailPlayerMutation({
        mutationFn: (code: number) => apiDelete(`/api/player/${pid}/character/${code}`),
        onSuccess: () => { message.success("角色已删除"); refresh(["player", "characters"]) },
    })

    const addItem = useMailPlayerMutation({
        mutationFn: ({ id, count }: { id: number; count: number }) => {
            const problem = integerError(id, "道具编号", 1, Number.MAX_SAFE_INTEGER) || integerError(count, "道具数量", 0, ADMIN_INT_MAX)
            if (problem) throw new Error(problem)
            return apiPost(`/api/player/${pid}/item`, { id, count })
        },
        onSuccess: () => { message.success("道具已设置"); setAddItemId(undefined); setAddItemCount(1); refresh(["items"]) },
        onError: (e: Error) => { void message.error(e.message) },
    })

    const delItem = useMailPlayerMutation({
        mutationFn: (itemId: number) => apiDelete(`/api/player/${pid}/item/${itemId}`),
        onSuccess: () => { message.success("道具已删除"); refresh(["items"]) },
    })

    const delQuestProgress = useMailPlayerMutation({
        mutationFn: ({ section, questId }: { section: number; questId: number }) =>
            apiDelete(`/api/player/${pid}/quest_progress/${section}/${questId}`),
        onSuccess: () => { message.success("关卡记录已删除"); refresh(["questProgress"]) },
    })

    const clearAllQuestProgress = useMailPlayerMutation({
        mutationFn: () => apiDelete(`/api/player/${pid}/quest_progress`),
        onSuccess: () => { message.success("全部关卡记录已清除"); refresh(["questProgress"]) },
    })

    const delDrawnQuest = useMailPlayerMutation({
        mutationFn: ({ category, questId }: { category: number; questId: number }) =>
            apiDelete(`/api/player/${pid}/drawn_quest/${category}/${questId}`),
        onSuccess: () => { message.success("抽选记录已删除"); refresh(["drawnQuests"]) },
    })

    const clearAllDrawnQuests = useMailPlayerMutation({
        mutationFn: () => apiDelete(`/api/player/${pid}/drawn_quest`),
        onSuccess: () => { message.success("全部抽选记录已清除"); refresh(["drawnQuests"]) },
    })

    const clearExBoost = useMailPlayerMutation({
        mutationFn: () => apiPost(`/api/player/${pid}/clear_ex_boost`),
        onSuccess: () => { message.success("EX Boost 已清除"); refresh(["characters"]) },
    })

    const clearReceiveHistory = useMailPlayerMutation({
        mutationFn: () => apiPost(`/api/player/${pid}/clear_receive_history`),
        onSuccess: () => { message.success("接收历史已清除"); refresh() },
        onError: (e: Error) => { void message.error(e.message) },
    })

    const repairUnisonUnlock = useMailPlayerMutation({
        mutationFn: () => apiPost<UnisonRepairResult>(`/api/player/${pid}/repair_unison_unlock`),
        onSuccess: result => {
            if (result.repaired) message.success(result.message)
            else message.info(result.message)
            refresh(["questProgress"])
        },
        onError: (e: Error) => { void message.error(e.message) },
    })

    const resetParties = useMailPlayerMutation({
        mutationFn: () => apiPost(`/api/player/${pid}/reset_parties`),
        onSuccess: () => { message.success("编队已重置"); refresh() },
    })

    const clearMail = useMailPlayerMutation({
        mutationFn: () => apiDelete(`/api/player/${pid}/mail`),
        onSuccess: () => { message.success("邮箱已清空"); refresh() },
    })

    const resetChallenge = useMailPlayerMutation({
        mutationFn: () => apiPost(`/api/player/${pid}/reset_challenge`),
        onSuccess: () => { message.success("每日挑战已重置"); refresh() },
    })

    const importSave = useMailPlayerMutation({
        mutationFn: (file: File) => apiUpload<ImportSaveResult>(`/api/player/save?id=${pid}`, file),
        onSuccess: result => {
            const backup = result.backup ? `；原存档回滚备份：${result.backup}` : ""
            message.success(`完整存档 V${result.snapshotVersion} 已导入${backup}`, 10)
            if (result.backupCleanupError) {
                message.warning(`存档已成功导入，但旧个人回滚备份清理失败：${result.backupCleanupError}`, 10)
            }
            qc.invalidateQueries({ queryKey: ["playerDetail", pid] })
            qc.invalidateQueries({ queryKey: ["accounts"] })
            qc.invalidateQueries({ queryKey: ["accountSummary"] })
            qc.invalidateQueries({ queryKey: ["accountTargets"] })
        },
        onError: (e: Error) => { void message.error(e.message) },
    })
    useAdminEditGuard({
        dirty: Object.entries(editValues).some(([key, value]) => !Object.is((data?.player as any)?.[key], value)) || addCharCode != null || addItemId != null || !Object.is(addItemCount, 1),
        pending: [editField, addChar, delChar, addItem, delItem, delQuestProgress, clearAllQuestProgress, delDrawnQuest,
            clearAllDrawnQuests, clearExBoost, clearReceiveHistory, repairUnisonUnlock, resetParties, clearMail, resetChallenge, importSave].some(mutation => mutation.isPending),
        label: "玩家详情",
    })

    const openImportSaveConfirmation = (file: File) => {
        Modal.confirm({
            title: `确认覆盖存档 #${pid}？`,
            content: (
                <Space direction="vertical">
                    <Text>将使用“{file.name}”覆盖当前玩家的持久化数据。</Text>
                    <Text type="secondary">导入前会把目标玩家当前存档导出为完整 V2 个人回滚备份，不会备份整个数据库。</Text>
                    <Text type="secondary">仅接受与当前数据库结构匹配的完整 V2 存档；旧版 V1 文件会被拒绝。</Text>
                    <Text type="secondary">账号绑定、设备会话和跨玩家关系保留；未完成的战斗恢复数据会清除。</Text>
                </Space>
            ),
            okText: "确认覆盖",
            cancelText: "取消",
            okButtonProps: { danger: true },
            onOk: async () => {
                try {
                    await importSave.mutateAsync(file)
                } catch {
                    // 错误信息由 mutation 统一展示。
                }
            },
        })
    }

    const confirmImportSave = (file: File) => {
        openImportSaveConfirmation(file)
        return Upload.LIST_IGNORE
    }

    if (isNaN(pid)) return <Card><Text type="danger">无效的玩家 ID</Text></Card>
    if (isLoading) return <StateCard><Spin size="large" /></StateCard>
    if (isError || !data) return <Card><Space><Text type="danger">玩家详情加载失败</Text><Button onClick={() => refetch()}>重试</Button></Space></Card>

    const { player } = data
    const { characters = [], items = [], equipment = [], questProgress = [], drawnQuests = [] } = sectionQuery.data ?? {}
    const playerTarget = `${player.name}（存档 #${pid}）`
    const charProblem = integerError(addCharCode, "角色编号", 1, Number.MAX_SAFE_INTEGER)
    const itemProblem = integerError(addItemId, "道具编号", 1, Number.MAX_SAFE_INTEGER) || integerError(addItemCount, "道具数量", 0, ADMIN_INT_MAX)

    // 内联可编辑数字字段（复用于资源/账号字段）
    const numField = (key: string, label: string, opts: { min?: number; allowNull?: boolean } = {}) => {
        const has = key in editValues
        const current = (player as any)[key]
        const shown = has ? editValues[key] : current
        const changed = has && editValues[key] !== current
        const problem = playerNumberError(key, shown)
        return (
            <div key={key}>
                <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
                <Space.Compact style={{ width: "100%" }}>
                    <InputNumber
                        style={{ width: "100%" }}
                        size="small"
                        value={shown}
                        aria-label={label}
                        min={key === "timeOffset" ? -PLAYER_TIME_OFFSET_MAX : opts.min}
                        max={key === "timeOffset" ? PLAYER_TIME_OFFSET_MAX : ADMIN_INT_MAX}
                        status={problem ? "error" : undefined}
                        onChange={v => setEditValues(prev => ({ ...prev, [key]: v }))}
                    />
                    {changed && (
                        <Button size="small" type="primary" icon={<SaveOutlined />}
                            aria-label={`保存${label}`}
                            disabled={!!problem}
                            loading={editField.isPending}
                            onClick={() => editField.mutate({ field: key, value: editValues[key] })}
                        />
                    )}
                </Space.Compact>
                {problem && <Text type="danger" role="alert" style={{ display: "block", fontSize: 12 }}>{problem}</Text>}
            </div>
        )
    }

    const dateField = (key: string, label: string) => {
        const iso = (player as any)[key] as string | null
        return (
            <div key={key}>
                <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
                <DatePicker
                    showTime
                    allowClear={false}
                    size="small"
                    style={{ width: "100%" }}
                    value={iso ? dayjs(iso) : null}
                    onChange={date => date && editField.mutate({ field: key, value: date.toISOString() })}
                />
            </div>
        )
    }

    const searchBox = (value: string, setValue: (s: string) => void) => (
        <Input allowClear size="small" prefix={<SearchOutlined />} placeholder="搜索名称或 ID"
            value={value} onChange={e => setValue(e.target.value)} style={{ width: 260, maxWidth: "100%" }} />
    )

    // 大表格搜索过滤（名称或 ID）
    const norm = (s: string) => s.trim().toLowerCase()
    const fChars = characters.filter(r => {
        const s = norm(searchChars); if (!s) return true
        const c = lookups?.characters[r.code]
        return String(r.code).includes(s) || (c?.name ?? "").toLowerCase().includes(s) || (c?.title ?? "").toLowerCase().includes(s)
    })
    const fItems = items.filter(r => {
        const s = norm(searchItems); if (!s) return true
        return String(r.id).includes(s) || String((lookups?.items as any)?.[r.id] ?? "").toLowerCase().includes(s)
    })
    const fEquip = equipment.filter(r => {
        const s = norm(searchEquip); if (!s) return true
        return String(r.id).includes(s) || String((lookups?.equipment as any)?.[r.id]?.name ?? "").toLowerCase().includes(s)
    })
    const fQuests = questProgress.filter(r => {
        const s = norm(searchQuests); if (!s) return true
        return String(r.section).includes(s) || String(r.questId).includes(s) || String((lookups?.quests as any)?.[`${r.section}_${r.questId}`] ?? "").toLowerCase().includes(s)
    })
    const fDrawn = drawnQuests.filter(r => {
        const s = norm(searchDrawn); if (!s) return true
        return String(r.categoryId).includes(s) || String(r.questId).includes(s) || String((lookups?.quests as any)?.[`${r.categoryId}_${r.questId}`] ?? "").toLowerCase().includes(s)
    })

    const tabItems = [
        {
            key: "characters",
            label: sectionQuery.data?.characters ? `角色 (${characters.length})` : "角色",
            children: (
                <Space direction="vertical" style={{ width: "100%" }}>
                    <div className="admin-toolbar">
                        <InputNumber
                            placeholder="角色编号"
                            aria-label="直接添加角色编号"
                            min={1}
                            value={addCharCode}
                            onChange={value => setAddCharCode(value ?? undefined)}
                            style={{ width: 140 }}
                        />
                        <Popconfirm
                            title={`将“${lookups.characters[addCharCode ?? 0]?.name ?? "此角色"}”直接写入 ${player.name}？`}
                            description={`目标：${playerTarget}；角色编号 ${addCharCode ?? "未填写"}。该操作绕过抽卡、邮件领取和相关统计，只应用于测试或坏档修复。`}
                            onConfirm={() => addCharCode && addChar.mutate(addCharCode)}
                            okText="确认写入"
                            cancelText="取消"
                            disabled={!!charProblem}
                        >
                            <Button icon={<PlusOutlined />} disabled={!!charProblem} loading={addChar.isPending}>
                                高级：直接添加
                            </Button>
                        </Popconfirm>
                        {searchBox(searchChars, setSearchChars)}
                    </div>
                    {addCharCode != null && charProblem && <Text type="danger" role="alert">{charProblem}</Text>}
                    <Table rowKey="code" dataSource={fChars} size="small" pagination={{ pageSize: 50 }}
                        scroll={{ x: "max-content" }}
                        columns={[
                            { title: "名字", render: (_, r: CharRow) => lookups?.characters[r.code]?.name ?? "?" },
                            { title: "称号", render: (_, r: CharRow) => lookups?.characters[r.code]?.title ?? "-", responsive: ["lg"] as any },
                            { title: "编号", dataIndex: "code", width: 80, render: value => <Text type="secondary">{value}</Text> },
                            { title: "稀有度", render: (_, r: CharRow) => lookups?.characters[r.code] ? `${lookups.characters[r.code].rarity} ${lookups.characters[r.code].element}` : "-", width: 100 },
                            { title: "入手时间", dataIndex: "joinTime", render: (t: string) => t.replace("T", " ").substring(0, 19), responsive: ["md"] as any },
                            {
                                title: "", width: 60,
                                render: (_, r: CharRow) => r.code === 1 ? <Tag>Alk</Tag> : (
                                    <Popconfirm title={`从 ${player.name} 删除“${lookups.characters[r.code]?.name ?? "此角色"}”？`}
                                        description={`目标：${playerTarget}；角色编号 ${r.code}。编队中的相关角色引用也会清除。`}
                                        onConfirm={() => delChar.mutate(r.code)} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true }}>
                                        <Button size="small" danger loading={delChar.isPending && delChar.variables === r.code} disabled={delChar.isPending} icon={<DeleteOutlined />} />
                                    </Popconfirm>
                                ),
                            },
                        ]}
                    />
                </Space>
            ),
        },
        {
            key: "items",
            label: sectionQuery.data?.items ? `道具 (${items.length})` : "道具",
            children: (
                <Space direction="vertical" style={{ width: "100%" }}>
                    <div className="admin-toolbar">
                        <InputNumber placeholder="道具编号" aria-label="设置道具编号" disabled={addItem.isPending} value={addItemId} min={1} onChange={v => setAddItemId(v ?? undefined)} style={{ width: 120 }} />
                        <InputNumber placeholder="数量" aria-label="设置道具数量" value={addItemCount} onChange={setAddItemCount} disabled={addItem.isPending} min={0} max={ADMIN_INT_MAX} style={{ width: 140 }} />
                        <Popconfirm title={`把“${lookups.items[addItemId ?? 0] ?? "此道具"}”数量设为 ${Number.isFinite(addItemCount) ? addItemCount : "未填写"}？`}
                            description={`目标：${playerTarget}；道具编号 ${addItemId ?? "未填写"}。这是覆盖现有数量，不是追加。`}
                            disabled={!!itemProblem} okText="确认设置" cancelText="取消"
                            onConfirm={() => addItemId != null && addItemCount != null && addItem.mutate({ id: addItemId, count: addItemCount })}>
                            <Button icon={<PlusOutlined />} disabled={!!itemProblem} loading={addItem.isPending}>设置道具数量</Button>
                        </Popconfirm>
                        {searchBox(searchItems, setSearchItems)}
                    </div>
                    {addItemId != null && itemProblem && <Text type="danger" role="alert">{itemProblem}</Text>}
                    <Table rowKey="id" dataSource={fItems} size="small" pagination={{ pageSize: 50 }}
                        scroll={{ x: "max-content" }}
                        columns={[
                            { title: "名字", render: (_, r: ItemRow) => (lookups?.items as any)?.[r.id] ?? "-" },
                            { title: "ID", dataIndex: "id", width: 80 },
                            { title: "数量", dataIndex: "count", width: 100 },
                            {
                                title: "", width: 60,
                                render: (_, r: ItemRow) => (
                                    <Popconfirm title={`从 ${player.name} 删除“${lookups.items[r.id] ?? "此道具"}”？`}
                                        description={`目标：${playerTarget}；道具编号 ${r.id}。`} onConfirm={() => delItem.mutate(r.id)} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true }}>
                                        <Button size="small" danger loading={delItem.isPending && delItem.variables === r.id} disabled={delItem.isPending} icon={<DeleteOutlined />} />
                                    </Popconfirm>
                                ),
                            },
                        ]}
                    />
                </Space>
            ),
        },
        {
            key: "equipment",
            label: sectionQuery.data?.equipment ? `装备 (${equipment.length})` : "装备",
            children: (
                <Space direction="vertical" style={{ width: "100%" }}>
                    {searchBox(searchEquip, setSearchEquip)}
                    <Table rowKey="id" dataSource={fEquip} size="small" pagination={{ pageSize: 50 }}
                        scroll={{ x: "max-content" }}
                        columns={[
                            { title: "名字", render: (_, r: EquipRow) => (lookups?.equipment as any)?.[r.id]?.name ?? "-" },
                            { title: "ID", dataIndex: "id", width: 80 },
                            { title: "稀有度", render: (_, r: EquipRow) => { const eq = (lookups?.equipment as any)?.[r.id]; return eq ? `${eq.rarity}★` : "-" }, width: 80 },
                            { title: "类型", render: (_, r: EquipRow) => (lookups?.equipment as any)?.[r.id]?.category ?? "-", width: 80 },
                            { title: "等级", dataIndex: "level", width: 80 },
                            { title: "强化", dataIndex: "enhancementLevel", width: 80 },
                        ]}
                    />
                </Space>
            ),
        },
        {
            key: "quests",
            label: sectionQuery.data?.questProgress ? `关卡 (${questProgress.length})` : "关卡",
            children: (
                <Space direction="vertical" style={{ width: "100%" }}>
                    <div className="admin-toolbar">
                        <Popconfirm title={`清除 ${player.name} 的全部关卡进度？`} description={`目标：${playerTarget}。此操作无法在页面内撤销。`}
                            onConfirm={() => clearAllQuestProgress.mutate()} okText="确认清除" cancelText="取消" okButtonProps={{ danger: true }}>
                            <Button danger size="small" loading={clearAllQuestProgress.isPending} icon={<DeleteOutlined />}>清除全部</Button>
                        </Popconfirm>
                        {searchBox(searchQuests, setSearchQuests)}
                    </div>
                    <Table rowKey={(r: QuestRow) => `${r.section}_${r.questId}`} dataSource={fQuests} size="small" pagination={{ pageSize: 50 }}
                        scroll={{ x: "max-content" }}
                        columns={[
                            { title: "名字", render: (_, r: QuestRow) => (lookups?.quests as any)?.[`${r.section}_${r.questId}`] ?? "-" },
                            { title: "Section", dataIndex: "section", width: 80 },
                            { title: "Quest", dataIndex: "questId", width: 80 },
                            { title: "通关", render: (_, r: QuestRow) => r.finished ? "已通关" : "—", width: 72 },
                            { title: "最高分", dataIndex: "highScore", render: (v: number | null) => v ?? "—", width: 80 },
                            { title: "评价", dataIndex: "clearRank", render: (v: number | null) => v ?? "—", width: 60 },
                            { title: "最佳时间", dataIndex: "bestElapsedTimeMs", render: (v: number | null) => v ?? "—", width: 100 },
                            {
                                title: "", width: 60,
                                render: (_, r: QuestRow) => (
                                    <Popconfirm title={`删除“${lookups.quests[`${r.section}_${r.questId}`] ?? "此关卡"}”的进度？`}
                                        description={`目标：${playerTarget}；分类 ${r.section}，关卡编号 ${r.questId}。`}
                                        onConfirm={() => delQuestProgress.mutate({ section: r.section, questId: r.questId })} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true }}>
                                        <Button size="small" danger loading={delQuestProgress.isPending && delQuestProgress.variables?.section === r.section && delQuestProgress.variables?.questId === r.questId} disabled={delQuestProgress.isPending} icon={<DeleteOutlined />} />
                                    </Popconfirm>
                                ),
                            },
                        ]}
                    />
                </Space>
            ),
        },
        {
            key: "drawn",
            label: sectionQuery.data?.drawnQuests ? `抽选关卡 (${drawnQuests.length})` : "抽选关卡",
            children: (
                <Space direction="vertical" style={{ width: "100%" }}>
                    <div className="admin-toolbar">
                        <Popconfirm title={`清除 ${player.name} 的全部抽选记录？`} description={`目标：${playerTarget}。此操作无法在页面内撤销。`}
                            onConfirm={() => clearAllDrawnQuests.mutate()} okText="确认清除" cancelText="取消" okButtonProps={{ danger: true }}>
                            <Button danger size="small" loading={clearAllDrawnQuests.isPending} icon={<DeleteOutlined />}>清除全部</Button>
                        </Popconfirm>
                        {searchBox(searchDrawn, setSearchDrawn)}
                    </div>
                    <Table rowKey={(r: DrawnQuestRow) => `${r.categoryId}_${r.questId}`} dataSource={fDrawn} size="small" pagination={{ pageSize: 50 }}
                        scroll={{ x: "max-content" }}
                        columns={[
                            { title: "名字", render: (_, r: DrawnQuestRow) => (lookups?.quests as any)?.[`${r.categoryId}_${r.questId}`] ?? "-" },
                            { title: "Category", dataIndex: "categoryId", width: 80 },
                            { title: "Quest", dataIndex: "questId", width: 80 },
                            { title: "Odds", dataIndex: "oddsId", width: 80 },
                            {
                                title: "", width: 60,
                                render: (_, r: DrawnQuestRow) => (
                                    <Popconfirm title={`删除“${lookups.quests[`${r.categoryId}_${r.questId}`] ?? "此关卡"}”的抽选记录？`}
                                        description={`目标：${playerTarget}；分类 ${r.categoryId}，关卡编号 ${r.questId}。`}
                                        onConfirm={() => delDrawnQuest.mutate({ category: r.categoryId, questId: r.questId })} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true }}>
                                        <Button size="small" danger loading={delDrawnQuest.isPending && delDrawnQuest.variables?.category === r.categoryId && delDrawnQuest.variables?.questId === r.questId} disabled={delDrawnQuest.isPending} icon={<DeleteOutlined />} />
                                    </Popconfirm>
                                ),
                            },
                        ]}
                    />
                </Space>
            ),
        },
    ]

    return (
        <AdminPage
            eyebrow="PLAYER"
            title={`${player.name} (#${player.id})`}
            description={`所属内部账号 #${player.accountId}。先核对目标存档；奖励发放使用邮件，直接改档仅用于维护。`}
            actions={<Button onClick={() => navigate("/accounts")}>返回账号 / 存档</Button>}
        >
        <Space direction="vertical" size="large" className="admin-stack player-detail-stack" style={{ minWidth: 0, maxWidth: "100%" }}>
            <Card title="存档标识">
                    <Descriptions bordered size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
                        <Descriptions.Item label="存档名">{player.name}</Descriptions.Item>
                        <Descriptions.Item label="存档 ID">{player.id}</Descriptions.Item>
                        <Descriptions.Item label="内部账号 ID">{player.accountId}</Descriptions.Item>
                    </Descriptions>
            </Card>

            <div className="admin-card-grid">
                    <Card title="资源编辑" size="small">
                        <Text type="secondary" className="player-edit-hint">修改后点击该项保存；每项分别生效。</Text>
                        <div style={gridStyle}>
                            {resourceFields.map(f => numField(f.key, f.label, { min: 0 }))}
                        </div>
                    </Card>

                    <Card title="存档设置" size="small">
                        <div style={gridStyle}>
                            <div>
                                <Text type="secondary" style={{ fontSize: 12 }}>3x加速</Text>
                                <div>
                                    <Switch checked={player.enableAuto3x} loading={editField.isPending}
                                        onChange={v => editField.mutate({ field: "enableAuto3x", value: v })} />
                                </div>
                            </div>
                            {numField("degreeId", "称号编号", { min: 0 })}
                            {numField("leaderCharacterId", "队长角色ID", { min: 0 })}
                            {numField("birth", "生日(birth)", { min: 0 })}
                            {numField("tutorialStep", "教程步骤(空=null)", { min: 0, allowNull: true })}
                        </div>
                    </Card>

            </div>

            <Card className="admin-table-card" style={{ minWidth: 0, maxWidth: "100%" }}>
                <Tabs activeKey={activeTab} onChange={key => setActiveTab(key as PlayerTab)} items={tabItems.map(tab => ({
                    ...tab,
                    children: tab.key !== activeTab ? null : sectionQuery.isPending ? <StateCard><Spin /></StateCard>
                        : sectionQuery.isError ? <Alert type="error" showIcon message="当前页签读取失败"
                            action={<Button onClick={() => sectionQuery.refetch()}>重试</Button>} />
                        : <Space direction="vertical" className="admin-stack">
                            {lookupQuery.isLoading && <Text type="secondary">正在读取名称资料…</Text>}
                            {lookupQuery.isError && <Alert type="warning" showIcon message="名称资料读取失败，暂以编号显示"
                                action={<Button size="small" onClick={() => lookupQuery.refetch()}>重试</Button>} />}
                            {tab.children}
                        </Space>,
                }))} />
            </Card>
            <Collapse className="player-maintenance" items={[{ key: "maintenance", label: "高级维护 · 时间兼容、修复与存档覆盖", children: (
                <Space direction="vertical" size="middle" className="admin-stack">
                    <Alert type="warning" showIcon message={`操作目标：${playerTarget}`} description="覆盖、删除和重置会改变玩家进度。操作前请先导出完整存档，并核对每项确认说明。" />
                    <Card title="存档时间（高级兼容设置）" size="small">
                        <div style={gridStyle}>
                            {dateField("staminaHealTime", "体力恢复时间")}
                            {dateField("lastLoginTime", "最后登录时间")}
                            {dateField("expPooledTime", "经验池结算锚点（非实时）")}
                            {numField("timeOffset", "结算时间基准偏移(ms，旧存档可空)", { allowNull: true })}
                        </div>
                    </Card>

                    <Card title="修复、清理与存档覆盖" size="small">
                        <Space wrap>
                            <Popconfirm title={`清除 ${player.name} 的全部 EX Boost？`} description={`目标：${playerTarget}。`} onConfirm={() => clearExBoost.mutate()} okText="确认" cancelText="取消">
                                <Button size="small" loading={clearExBoost.isPending}>清除 EX Boost</Button>
                            </Popconfirm>
                            <Popconfirm title={`把 ${player.name} 的编队重置到默认？`} description={`目标：${playerTarget}。当前编队配置将被替换。`} onConfirm={() => resetParties.mutate()} okText="确认" cancelText="取消">
                                <Button size="small" loading={resetParties.isPending} icon={<UndoOutlined />}>重置编队</Button>
                            </Popconfirm>
                            <Popconfirm title={`清空 ${player.name} 的邮箱？`} description={`目标：${playerTarget}。此操作无法在页面内撤销。`} onConfirm={() => clearMail.mutate()} okText="确认" cancelText="取消" okButtonProps={{ danger: true }}>
                                <Button size="small" danger loading={clearMail.isPending}>清空邮箱</Button>
                            </Popconfirm>
                            <Popconfirm title={`重置 ${player.name} 的每日挑战点？`} description={`目标：${playerTarget}。`} onConfirm={() => resetChallenge.mutate()} okText="确认" cancelText="取消">
                                <Button size="small" loading={resetChallenge.isPending} icon={<UndoOutlined />}>重置每日挑战</Button>
                            </Popconfirm>
                            <Popconfirm title={`清除 ${player.name} 的一次性道具领取记录？`} description={`目标：${playerTarget}。`} onConfirm={() => clearReceiveHistory.mutate()} okText="确认" cancelText="取消">
                                <Button size="small" loading={clearReceiveHistory.isPending}>清除接收历史</Button>
                            </Popconfirm>
                            <Popconfirm
                                title={`检查并修复 ${player.name} 的合击解锁记录？`}
                                description={`目标：${playerTarget}。仅当存档已有第一章 6-1 或后续主线通关记录时才会补齐。`}
                                onConfirm={() => repairUnisonUnlock.mutate()}
                                okText="检查并修复"
                                cancelText="取消"
                            >
                                <Button size="small" icon={<UndoOutlined />} loading={repairUnisonUnlock.isPending}>
                                    修复合击解锁
                                </Button>
                            </Popconfirm>
                            <Button size="small" icon={<DownloadOutlined />} href={`/api/player/save?id=${pid}`} target="_blank">导出完整存档</Button>
                            <Upload accept=".json,application/json" showUploadList={false} maxCount={1}
                                beforeUpload={confirmImportSave}>
                                <Button size="small" icon={<UploadOutlined />} danger loading={importSave.isPending}>导入存档(覆盖)</Button>
                            </Upload>
                        </Space>
                    </Card>
                </Space>
            ) }]} />
        </Space>
        </AdminPage>
    )
}
