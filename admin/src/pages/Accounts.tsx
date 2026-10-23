import { useEffect, useRef, useState } from "react"
import { Alert, Card, Table, Button, Space, Popconfirm, Input, message, Tag, Typography, Upload, Modal, Drawer, Progress, Descriptions, Collapse, Tooltip } from "antd"
import { PlusOutlined, CopyOutlined, DeleteOutlined, SwapOutlined, EditOutlined, DownloadOutlined, UploadOutlined } from "@ant-design/icons"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { apiGet, apiPost, apiUpload } from "../api/client"
import { AdminPage } from "../components/AdminPage"
import "./PlayerComms.css"
import { requestAdminLeave, useAdminEditGuard, useAdminNavigate } from "../lib/editGuard"

interface AccountRow {
    id: number
    viewerId: string | null
    note: string | null
    loginUsername: string | null
    playerLogin: { bound: boolean; boundAt: number | null; sessionExpiresAt: number | null }
    takeoverConfigured: boolean
    latestTransfer: TransferBrief | null
    bindings: DeviceBinding[]
    saveCount: number
    defaultPlayerId: number | null
    defaultPlayerName: string | null
    activePlayerId: number | null
    players: PlayerBrief[]
    playerIds: number[]
}

interface DeviceBinding {
    deviceId: number
}

interface AccountSummary {
    accountCount: number
    saveCount: number
    unnotedAccountCount: number
    unnotedSaveCount: number
}

interface AccountPage {
    rows: AccountRow[]
    total: number
    page: number
    pageSize: number
    summary: AccountSummary
}

interface TransferBrief {
    abolishedViewerId: string | null
    oldDeviceId: number | null
    newDeviceId: number
    discardedSaveCount: number
    transferredAt: string
    source: "title" | "in_game"
}

interface PlayerBrief {
    id: number
    accountId: number
    name: string
    comment: string
    degreeId: number
    isDefault: boolean
    isActive: boolean
}

interface CleanupJob {
    ok: boolean
    jobId?: string
    status: "idle" | "running" | "completed" | "failed"
    phase?: "preparing" | "planning" | "backing_up" | "indexing" | "deleting" | "finalizing"
    totalAccounts?: number
    processedAccounts?: number
    deletedAccounts: number
    deletedSaves: number
    skippedActiveAccount: number | null
    backup: string | null
    removedBackups: number
    backupCleanupError: string | null
    createdIndexes?: number
    workerThreadId?: number | null
    error?: string | null
}

interface ImportSaveResult {
    ok: boolean
    snapshotVersion: number
    backup?: string | null
    retainedBackups?: number | null
    removedBackups?: number
    backupCleanupError?: string | null
}

const REPORTED_CLEANUP_JOB_STORAGE_KEY = "admin:unnoted-account-cleanup:last-reported-job"

function readReportedCleanupJob(): string | null {
    if (typeof window === "undefined") return null
    try {
        return window.localStorage.getItem(REPORTED_CLEANUP_JOB_STORAGE_KEY)
    } catch {
        return null
    }
}

function rememberReportedCleanupJob(jobId: string) {
    if (typeof window === "undefined") return
    try {
        window.localStorage.setItem(REPORTED_CLEANUP_JOB_STORAGE_KEY, jobId)
    } catch {
        // The in-memory ref still prevents duplicates during this mount.
    }
}

export default function Accounts() {
    const qc = useQueryClient()
    const navigate = useAdminNavigate()
    const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
    const [loginAccountId, setLoginAccountId] = useState<number | null>(null)
    const [renameId, setRenameId] = useState<number | null>(null)
    const [renameName, setRenameName] = useState("")
    const [renameOriginal, setRenameOriginal] = useState("")
    const [accountQuery, setAccountQuery] = useState("")
    const [searchQuery, setSearchQuery] = useState("")
    const [page, setPage] = useState(1)
    const [pageSize, setPageSize] = useState(20)
    const [editNoteAccountId, setEditNoteAccountId] = useState<number | null>(null)
    const [editNote, setEditNote] = useState("")
    const [noteOriginal, setNoteOriginal] = useState("")
    const reportedCleanupJob = useRef<string | null>(readReportedCleanupJob())

    useEffect(() => {
        const timer = window.setTimeout(() => { setSearchQuery(accountQuery.trim()); setPage(1) }, 300)
        return () => window.clearTimeout(timer)
    }, [accountQuery])

    const { data: accountPage, isLoading, isError: accountsError, isFetching: accountsFetching, refetch: retryAccounts } = useQuery({
        queryKey: ["accounts", "page", page, pageSize, searchQuery],
        queryFn: ({ signal }) => apiGet<AccountPage>(`/api/server/accounts/page?${new URLSearchParams({ page: String(page), pageSize: String(pageSize), q: searchQuery })}`, { signal }),
    })
    const accounts = accountPage?.rows ?? []
    useEffect(() => { if (accountPage && accountPage.page !== page) setPage(accountPage.page) }, [accountPage, page])
    const selectedQuery = useQuery({
        queryKey: ["accounts", "detail", selectedAccountId],
        queryFn: ({ signal }) => apiGet<AccountRow>(`/api/server/accounts/${selectedAccountId}`, { signal }),
        enabled: selectedAccountId !== null,
    })
    const loginQuery = useQuery({
        queryKey: ["accounts", "detail", loginAccountId],
        queryFn: ({ signal }) => apiGet<AccountRow>(`/api/server/accounts/${loginAccountId}`, { signal }),
        enabled: loginAccountId !== null,
    })
    const { data: cleanupJob, isPending: cleanupLoading, isError: cleanupError, refetch: retryCleanup } = useQuery({
        queryKey: ["unnoted-account-cleanup"],
        queryFn: () => apiGet<CleanupJob>("/api/server/deleteUnnotedAccounts/status"),
        refetchInterval: query =>
            (query.state.data as CleanupJob | undefined)?.status === "running" ? 1000 : false,
    })

    const selectedAccount = selectedQuery.data
    const loginAccount = loginQuery.data
    const savePlayers = selectedAccount?.players ?? []
    const unnotedAccountCount = accountPage?.summary.unnotedAccountCount ?? 0
    const unnotedSaveCount = accountPage?.summary.unnotedSaveCount ?? 0

    const refresh = () => {
        qc.invalidateQueries({ queryKey: ["accounts"] })
        qc.invalidateQueries({ queryKey: ["accountSummary"] })
        qc.invalidateQueries({ queryKey: ["accountTargets"] })
    }

    const activateSave = useMutation({
        mutationFn: (playerId: number) => apiPost("/api/server/activateSave?playerId=" + playerId),
        onSuccess: () => { message.success("已切换生效存档"); refresh() },
        onError: (error: Error) => { void message.error(`切换存档失败：${error.message}`) },
    })

    const newSave = useMutation({
        mutationFn: (accountId: number) => apiPost("/api/server/newSave?accountId=" + accountId),
        onSuccess: () => { message.success("新存档已创建"); refresh() },
        onError: (error: Error) => { void message.error(`新建存档失败：${error.message}`) },
    })

    const deleteSave = useMutation({
        mutationFn: (playerId: number) => apiPost("/api/server/deleteSave?playerId=" + playerId),
        onSuccess: () => { message.success("存档已删除"); refresh() },
        onError: (error: Error) => { void message.error(`删除存档失败：${error.message}`) },
    })

    const deleteAccount = useMutation({
        mutationFn: (id: number) => apiPost("/api/server/deleteAccount?id=" + id),
        onSuccess: () => {
            message.success("账号已删除")
            if (selectedAccountId === (deleteAccount.variables as number)) setSelectedAccountId(null)
            refresh()
        },
        onError: (error: Error) => { void message.error(`删除账号失败：${error.message}`) },
    })

    const renameSave = useMutation({
        mutationFn: ({ playerId, name }: { playerId: number; name: string }) => {
            if (!Number.isSafeInteger(playerId) || playerId < 1) throw new Error("存档编号无效，请重新读取账号。")
            if (!name.trim()) throw new Error("请输入存档名字，不能只含空格。")
            return apiPost("/api/server/renameSave", { playerId, name })
        },
        onSuccess: () => { message.success("已改名"); setRenameId(null); refresh() },
        onError: (error: Error) => { void message.error(`存档改名失败：${error.message}`) },
    })

    const cloneSave = useMutation({
        mutationFn: ({ playerId, accountId }: { playerId: number; accountId: number }) =>
            apiPost(`/api/server/cloneSave?playerId=${playerId}&accountId=${accountId}`),
        onSuccess: () => { message.success("存档已复制"); refresh() },
        onError: (error: Error) => { void message.error(`复制存档失败：${error.message}`) },
    })

    const renameAccount = useMutation({
        mutationFn: ({ accountId, note }: { accountId: number; note: string }) =>
            apiPost("/api/server/account/rename", { account_id: accountId, name: note.trim() }),
        onSuccess: () => {
            message.success("备注已保存")
            setEditNoteAccountId(null)
            refresh()
        },
        onError: (error: Error) => { void message.error(error.message) },
    })

    const issueTakeoverPassword = useMutation({
        mutationFn: ({ accountId }: { accountId: number; reset: boolean }) => apiPost<{ replacementPassword: string }>("/api/server/account/takeover-password/reset", {
            account_id: accountId,
            confirm: "RESET_TAKEOVER_PASSWORD",
        }),
        onSuccess: (result, { reset }) => {
            Modal.success({
                title: reset ? "继承密码已重置" : "继承密码已生成",
                content: (
                    <Space direction="vertical">
                        <Typography.Text>请把下面的新密码单独发给玩家；关闭后管理端不会再次显示。</Typography.Text>
                        <Typography.Text code copyable>{result.replacementPassword}</Typography.Text>
                    </Space>
                ),
            })
            refresh()
        },
        onError: (error: Error) => { void message.error(error.message) },
    })

    const issueLoginCode = useMutation({
        mutationFn: async (account: AccountRow) => {
            const result = await apiPost<{ ok: boolean; message?: string; data: { code: string; expires_at: number; profile: { username: string | null; viewer_id: number; name: string } } }>("/api/server/account/player-login-code", {
                viewer_id: account.viewerId,
                purpose: account.playerLogin?.bound ? "reset" : "bind",
            })
            if (!result.ok) throw new Error(result.message || "生成失败，请重试")
            return result.data
        },
        onSuccess: (result, account) => {
            Modal.success({
                title: account.playerLogin?.bound ? "登录密码重置码已生成" : "旧存档绑定码已生成",
                content: <Space direction="vertical" size="middle">
                    <Typography.Text strong>{result.profile.name} · UID {result.profile.viewer_id}</Typography.Text>
                    {result.profile.username && <Typography.Text>登录账号：{result.profile.username}</Typography.Text>}
                    <Typography.Text code copyable>{result.code}</Typography.Text>
                    <Typography.Text type="secondary">有效期至 {new Date(result.expires_at).toLocaleString()}，只能使用一次；新码替换之前的同用途验证码。</Typography.Text>
                    <Typography.Text>{account.playerLogin?.bound
                        ? "请让玩家在登录页选择“忘记密码”，使用此码设置新密码。设置成功后旧登录凭据失效，原存档与备注保留。"
                        : "请让老玩家选择“绑定旧存档 → 使用服主提供的绑定码”，确认角色和 UID 后设置账号密码。无需先注册新账号。"}</Typography.Text>
                </Space>,
            })
            refresh()
        },
        onError: (error: Error) => { void message.error(error.message) },
    })

    const importSave = useMutation({
        mutationFn: ({ playerId, file }: { playerId: number; file: File }) =>
            apiUpload<ImportSaveResult>(`/api/player/save?id=${playerId}`, file),
        onSuccess: (result, { playerId }) => {
            const backup = result.backup ? `；原存档回滚备份：${result.backup}` : ""
            message.success(`完整存档 V${result.snapshotVersion} 已导入到 #${playerId}${backup}`, 10)
            if (result.backupCleanupError) {
                message.warning(`存档已成功导入，但旧个人回滚备份清理失败：${result.backupCleanupError}`, 10)
            }
            refresh()
        },
        onError: (error: Error) => { void message.error(error.message) },
    })

    const cleanupUnnotedAccounts = useMutation({
        mutationFn: () => apiPost<CleanupJob>("/api/server/deleteUnnotedAccounts", {
            confirm: "DELETE_UNNOTED_ACCOUNTS",
        }),
        onSuccess: job => {
            qc.setQueryData(["unnoted-account-cleanup"], job)
            message.info(job.status === "running"
                ? "后台清理已启动；可以继续使用管理面板和游戏服务"
                : "没有需要清理的未备注账号")
        },
        onError: (error: Error) => { void message.error(error.message) },
    })

    useEffect(() => {
        if (!cleanupJob?.jobId || cleanupJob.status === "idle" || cleanupJob.status === "running") return
        if (reportedCleanupJob.current === cleanupJob.jobId) return
        reportedCleanupJob.current = cleanupJob.jobId
        rememberReportedCleanupJob(cleanupJob.jobId)
        if (cleanupJob.status === "completed") {
            setSelectedAccountId(null)
            message.success(
                `后台清理完成：已删除 ${cleanupJob.deletedAccounts} 个未备注账号和 ${cleanupJob.deletedSaves} 个存档`
                + (cleanupJob.backup ? `；备份：${cleanupJob.backup}` : "")
                + (cleanupJob.removedBackups ? `；已清理 ${cleanupJob.removedBackups} 个旧备份` : ""),
                10,
            )
            if (cleanupJob.backupCleanupError) {
                message.warning(`新备份已保留，但旧备份清理失败：${cleanupJob.backupCleanupError}`, 10)
            }
            refresh()
        } else {
            message.error(`后台清理失败：${cleanupJob.error ?? "未知错误"}；已完成的批次不会自动恢复`, 10)
        }
    }, [cleanupJob, qc])

    const cleanupRunning = cleanupJob?.status === "running"
    const accountWritePending = activateSave.isPending || newSave.isPending || deleteSave.isPending
        || deleteAccount.isPending || renameSave.isPending || cloneSave.isPending || renameAccount.isPending
        || issueTakeoverPassword.isPending || issueLoginCode.isPending || importSave.isPending || cleanupUnnotedAccounts.isPending
    const accountWritesDisabled = isLoading || accountsError || accountWritePending || cleanupRunning
        || (selectedAccountId !== null && (selectedQuery.isPending || selectedQuery.isError))
        || (loginAccountId !== null && (loginQuery.isPending || loginQuery.isError))
    useAdminEditGuard({
        dirty: (renameId !== null && renameName !== renameOriginal) || (editNoteAccountId !== null && editNote !== noteOriginal),
        pending: accountWritePending,
        label: "账号与存档编辑",
    })
    const cleanupPercent = cleanupRunning && cleanupJob.totalAccounts
        ? Math.round(((cleanupJob.processedAccounts ?? 0) / cleanupJob.totalAccounts) * 100)
        : 0
    const cleanupPhaseText = {
        preparing: "正在准备 Worker",
        planning: "正在整理清理清单",
        backing_up: "正在创建完整数据库备份",
        indexing: "正在检查删除索引",
        deleting: "正在分批删除",
        finalizing: "正在写入结果并清理旧备份",
    }[cleanupJob?.phase ?? "preparing"]
    const cleanupScopeText = accountsError
        ? "账号数据加载失败，暂时无法统计或清理；请重试读取。"
        : isLoading
        ? "正在统计可清理账号…"
        : `可清理 ${unnotedAccountCount} 个：所有未备注账号，不论是否绑定登录；此统计不受搜索或分页影响。`

    const confirmCleanupUnnotedAccounts = () => {
        Modal.confirm({
            title: `删除 ${unnotedAccountCount} 个未备注账号？`,
            content: (
                <Space direction="vertical" size="small">
                    <Typography.Text>
                        将同时删除这些账号下的 {unnotedSaveCount} 个存档及登录账号。空备注或纯空格均视为未备注，不论是否绑定登录或设备。
                    </Typography.Text>
                    <Typography.Text type="warning">
                        当前选中的账号也按备注判断；需要保留的账号请先填写备注。执行前服务端会创建完整数据库备份。
                    </Typography.Text>
                    <Typography.Text type="secondary">
                        Worker 整理清单后，服务端分批清理。期间可以继续登录和游戏；涉及数据库写入的操作偶尔可能短暂停顿。
                    </Typography.Text>
                    <Typography.Text type="secondary">
                        新备份和清理均成功后，只保留本次清理备份，较早的同类自动备份会被删除。
                    </Typography.Text>
                    <Typography.Text type="danger">删除后无法在面板内撤销。</Typography.Text>
                </Space>
            ),
            okText: "确认删除并备份",
            cancelText: "取消",
            okButtonProps: { danger: true },
            onOk: async () => {
                try {
                    await cleanupUnnotedAccounts.mutateAsync()
                } catch {
                    // 错误信息由 mutation 统一展示。
                }
            },
        })
    }

    const openImportSaveConfirmation = (player: PlayerBrief, file: File) => {
        Modal.confirm({
            title: `确认覆盖存档 #${player.id}？`,
            content: (
                <Space direction="vertical">
                    <Typography.Text>将使用“{file.name}”覆盖“{player.name}”的持久化数据。</Typography.Text>
                    <Typography.Text strong>目标：账号 {selectedAccount?.viewerId ?? `内部 #${player.accountId}`} · 存档 #{player.id} · {player.name}</Typography.Text>
                    <Typography.Text type="secondary">导入前会把目标玩家当前存档导出为完整 V2 个人回滚备份，不会备份整个数据库。</Typography.Text>
                    <Typography.Text type="secondary">仅接受与当前数据库结构匹配的完整 V2 存档；旧版 V1 文件会被拒绝。</Typography.Text>
                    <Typography.Text type="secondary">账号绑定、设备会话和跨玩家关系保留；未完成的战斗恢复数据会清除。</Typography.Text>
                </Space>
            ),
            okText: "确认覆盖",
            cancelText: "取消",
            okButtonProps: { danger: true },
            onOk: () => importSave.mutateAsync({ playerId: player.id, file }),
        })
    }

    const confirmImportSave = (player: PlayerBrief, file: File) => {
        if (!Number.isSafeInteger(player.id) || player.id < 1 || player.accountId !== selectedAccountId) {
            message.error("导入目标无效，请重新打开所属账号的存档列表。")
            return Upload.LIST_IGNORE
        }
        if (file.size < 1 || file.size > 64 * 1024 * 1024) {
            message.error("请选择非空的完整 JSON 存档，文件不能超过 64 MB。")
            return Upload.LIST_IGNORE
        }
        openImportSaveConfirmation(player, file)
        return Upload.LIST_IGNORE
    }

    const accountColumns = [
        {
            title: "玩家 UID",
            width: 190,
            render: (_: unknown, row: AccountRow) => (
                <div className="account-identity-cell">
                    {row.viewerId
                        ? <Typography.Text strong copyable={{ text: row.viewerId }}>{row.viewerId}</Typography.Text>
                        : <Typography.Text type="secondary">未生成</Typography.Text>}
                    <Typography.Text type="secondary" className="account-cell-meta">
                        内部 ID · #{row.id}
                    </Typography.Text>
                </div>
            ),
        },
        {
            title: <Tooltip title="旧客户端留下的设备绑定记录，不代表当前手机；账号登录不依赖此记录。">原设备 ID</Tooltip>,
            width: 150,
            responsive: ["sm"] as any,
            render: (_: unknown, row: AccountRow) => (
                <div className="account-device-cell">
                    {row.bindings.length
                        ? row.bindings.map(binding => (
                            <Typography.Text
                                key={binding.deviceId}
                                className="account-device-id"
                            >
                                {binding.deviceId}
                            </Typography.Text>
                        ))
                        : <Tooltip title="没有旧设备绑定记录"><Typography.Text type="secondary">—</Typography.Text></Tooltip>}
                </div>
            ),
        },
        {
            title: "登录账号",
            width: 240,
            render: (_: unknown, row: AccountRow) => (
                <div className="account-login-cell">
                    {row.loginUsername
                        ? <Typography.Text strong className="account-login-name"
                            ellipsis={{ tooltip: row.loginUsername }} copyable={{ text: row.loginUsername }}>
                            {row.loginUsername}
                        </Typography.Text>
                        : <Typography.Text type="secondary">尚未设置登录账号</Typography.Text>}
                    <div className="account-login-meta">
                        <Tag bordered={false} color={row.playerLogin?.bound ? "cyan" : "gold"}>
                            {row.playerLogin?.bound ? "已绑定" : "未绑定"}
                        </Tag>
                        <Button type="link" size="small" onClick={() => setLoginAccountId(row.id)}
                            aria-label={`管理账号 ${row.viewerId || row.id} 的登录与绑定`}>
                            {row.playerLogin?.bound ? "管理登录" : "绑定存档"}
                        </Button>
                    </div>
                </div>
            ),
        },
        {
            title: "备注",
            width: 220,
            render: (_: unknown, row: AccountRow) => editNoteAccountId === row.id ? (
                <div className="account-note-edit">
                    <Input
                        size="small"
                        value={editNote}
                        maxLength={100}
                        placeholder="输入账号备注"
                        disabled={accountWritesDisabled}
                        onChange={event => setEditNote(event.target.value)}
                        onPressEnter={() => renameAccount.mutate({ accountId: row.id, note: editNote })}
                    />
                    <div className="account-note-edit-actions">
                        <Button
                            size="small"
                            type="primary"
                            loading={renameAccount.isPending}
                            disabled={accountWritesDisabled}
                            onClick={() => renameAccount.mutate({ accountId: row.id, note: editNote })}
                        >
                            保存
                        </Button>
                        <Button size="small" disabled={renameAccount.isPending} onClick={() => setEditNoteAccountId(null)}>取消</Button>
                    </div>
                </div>
            ) : (
                <div className="account-note-cell">
                    <Typography.Text
                        type={row.note ? undefined : "secondary"}
                        ellipsis={{ tooltip: row.note || undefined }}
                    >
                        {row.note || "未填写"}
                    </Typography.Text>
                    <Button
                        type="text"
                        size="small"
                        aria-label={`编辑账号 ${row.id} 的备注`}
                        disabled={accountWritesDisabled}
                        icon={<EditOutlined />}
                        onClick={() => requestAdminLeave(() => {
                            setEditNoteAccountId(row.id)
                            setEditNote(row.note ?? "")
                            setNoteOriginal(row.note ?? "")
                        })}
                    />
                </div>
            ),
        },
        {
            title: "存档概况", width: 210, responsive: ["md"] as any,
            render: (_: unknown, row: AccountRow) => {
                if (!row.defaultPlayerId) return (
                    <div className="account-save-cell">
                        <Typography.Text type="secondary">无默认存档</Typography.Text>
                        <Typography.Text type="secondary" className="account-cell-meta">共 {row.saveCount} 个存档</Typography.Text>
                    </div>
                )
                const isActive = row.activePlayerId === row.defaultPlayerId
                return (
                    <div className="account-save-cell">
                        <div className="account-save-head">
                            <Typography.Text strong ellipsis={{ tooltip: row.defaultPlayerName ?? undefined }}>
                                {row.defaultPlayerName ?? `#${row.defaultPlayerId}`}
                            </Typography.Text>
                            <Tag color={isActive ? "green" : "blue"}>{isActive ? "当前活动" : "账号默认"}</Tag>
                        </div>
                        <Typography.Text type="secondary" className="account-cell-meta">
                            共 {row.saveCount} 个存档
                        </Typography.Text>
                    </div>
                )
            },
        },
        {
            title: "操作", width: 250,
            render: (_: unknown, row: AccountRow) => (
                <div className="account-action-row">
                    <Button size="small" type="primary" onClick={() => setSelectedAccountId(row.id)}>管理存档</Button>
                    <Button
                        size="small"
                        icon={<PlusOutlined />}
                        loading={newSave.isPending && newSave.variables === row.id}
                        disabled={accountWritesDisabled}
                        onClick={() => newSave.mutate(row.id)}
                    >
                        新建存档
                    </Button>
                    <Popconfirm title={`删除账号 ${row.viewerId ?? `内部 #${row.id}`} 及所有存档？`}
                        description={`默认角色：${row.defaultPlayerName ?? "无"}；共 ${row.saveCount} 个存档。账号登录与绑定一并删除，不能在面板内撤销。`}
                        overlayStyle={{ maxWidth: "min(420px, calc(100vw - 32px))" }}
                        onConfirm={() => deleteAccount.mutate(row.id)} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true, disabled: accountWritesDisabled }}>
                        <Button
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            loading={deleteAccount.isPending && deleteAccount.variables === row.id}
                            disabled={accountWritesDisabled}
                        >
                            删除
                        </Button>
                    </Popconfirm>
                </div>
            ),
        },
    ]

    const saveColumns = [
        { title: "ID", dataIndex: "id", width: 60, responsive: ["sm"] as any },
        {
            title: "存档", width: 190,
            render: (_: unknown, row: PlayerBrief) => renameId === row.id ? (
                <div className="admin-edit-compact">
                    <Input size="small" aria-label={`存档 ${row.id} 的名字`} value={renameName} disabled={accountWritesDisabled} onChange={e => setRenameName(e.target.value)} onPressEnter={() => renameSave.mutate({ playerId: row.id, name: renameName })} style={{ width: 100 }} />
                    <Button size="small" type="primary" disabled={accountWritesDisabled} loading={renameSave.isPending && renameSave.variables?.playerId === row.id} onClick={() => renameSave.mutate({ playerId: row.id, name: renameName })}>确定</Button>
                    <Button size="small" disabled={renameSave.isPending} onClick={() => setRenameId(null)}>取消</Button>
                </div>
            ) : (
                <div className="account-save-title">
                    <div className="account-save-name-row">
                    <a href={`/admin/players/${row.id}`} className="account-save-name-link" aria-label={`查看存档 ${row.id}：${row.name}`}
                        onClick={event => {
                            if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
                            event.preventDefault(); navigate(`/players/${row.id}`)
                        }}>{row.name}</a>
                    <Button type="text" size="small" disabled={accountWritesDisabled} aria-label={`修改存档 ${row.id} 的名字`} icon={<EditOutlined />} onClick={() => requestAdminLeave(() => { setRenameId(row.id); setRenameName(row.name); setRenameOriginal(row.name) })} />
                    </div>
                    <Typography.Text type="secondary" className="account-cell-meta">存档 #{row.id}{row.isDefault ? " · 账号默认" : ""}{row.isActive ? " · 当前活动" : ""}</Typography.Text>
                </div>
            ),
        },
        {
            title: "状态", width: 80, responsive: ["sm"] as any,
            render: (_: unknown, row: PlayerBrief) => (
                <Space size={4} wrap>
                    {row.isDefault && <Tag color="blue">账号默认</Tag>}
                    {row.isActive && <Tag color="green">当前活动</Tag>}
                </Space>
            ),
        },
        {
            title: "操作", width: 430,
            render: (_: unknown, row: PlayerBrief) => (
                <div className="admin-action-row">
                    <Button size="small" icon={<SwapOutlined />} disabled={accountWritesDisabled || (row.isDefault && row.isActive)} loading={activateSave.isPending && activateSave.variables === row.id} onClick={() => activateSave.mutate(row.id)}>
                        设为默认并切换
                    </Button>
                    <Button size="small" icon={<CopyOutlined />} disabled={accountWritesDisabled} loading={cloneSave.isPending && cloneSave.variables?.playerId === row.id} onClick={() => cloneSave.mutate({ playerId: row.id, accountId: selectedAccountId! })}>
                        复制
                    </Button>
                    <Button size="small" icon={<DownloadOutlined />} href={`/api/player/save?id=${row.id}`} target="_blank">
                        导出
                    </Button>
                    <Upload
                        accept=".json,application/json"
                        showUploadList={false}
                        maxCount={1}
                        disabled={accountWritesDisabled}
                        beforeUpload={file => confirmImportSave(row, file)}
                    >
                        <Button
                            size="small"
                            danger
                            icon={<UploadOutlined />}
                            loading={importSave.isPending && importSave.variables?.playerId === row.id}
                            disabled={accountWritesDisabled}
                        >
                            导入
                        </Button>
                    </Upload>
                    <Popconfirm title={`删除存档 #${row.id}「${row.name}」？`}
                        description={`所属账号：${selectedAccount?.viewerId ?? `内部 #${row.accountId}`}。此操作不能在面板内撤销。`}
                        overlayStyle={{ maxWidth: "min(420px, calc(100vw - 32px))" }}
                        onConfirm={() => deleteSave.mutate(row.id)} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true, disabled: accountWritesDisabled }}>
                        <Button size="small" danger icon={<DeleteOutlined />} disabled={accountWritesDisabled} loading={deleteSave.isPending && deleteSave.variables === row.id}>删除</Button>
                    </Popconfirm>
                </div>
            ),
        },
    ]

    return (
        <AdminPage
            eyebrow="SAVES"
            title="账号 / 存档"
            description="按登录账号、UID 或存档查找玩家，管理绑定、备注与个人存档。"
        >
        <Space direction="vertical" size="large" className="admin-stack">
            <Collapse size="small" items={[{ key: "identity", label: "账号、存档与旧设备有什么区别？", children: (
                <Typography.Paragraph style={{ marginBottom: 0 }}>
                    账号默认存档决定登录时使用的存档；“当前活动”仅代表管理端最近切换的全局状态。
                    备注属于账号。老玩家核实 UID 后可生成绑定码，已绑定账号可生成密码重置码；原设备 ID 仅用于历史定位。
                </Typography.Paragraph>
            ) }]} />
            <Card
                title="账号管理"
                className="admin-table-card"
                extra={(
                    <Space wrap className="accounts-toolbar">
                        <Input.Search
                            allowClear
                            value={accountQuery}
                            onChange={event => {
                                const value = event.target.value
                                requestAdminLeave(() => { setEditNoteAccountId(null); setRenameId(null); setAccountQuery(value) })
                            }}
                            placeholder="搜索登录账号、UID、设备 ID、备注或存档"
                            className="account-search" aria-label="搜索账号与存档"
                            style={{ width: 320, maxWidth: "100%" }}
                        />
                    </Space>
                )}
            >
                {accountsError && <Alert type="error" showIcon role="alert" style={{ marginBottom: 12 }}
                    message="账号列表加载失败" description="这不代表没有账号。当前未保存内容仍保留，请恢复登录或网络后重试读取。"
                    action={<Button loading={accountsFetching} onClick={() => void retryAccounts()}>重试账号列表</Button>} />}
                {cleanupError && <Alert type="warning" showIcon role="alert" style={{ marginBottom: 12 }}
                    message="无法读取后台清理状态" description="为避免重复启动清理，暂时禁止发起清理任务。"
                    action={<Button onClick={() => void retryCleanup()}>重试清理状态</Button>} />}
                {cleanupRunning && (
                    <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 12 }}
                        message={`${cleanupPhaseText}${cleanupJob.workerThreadId ? `（Worker #${cleanupJob.workerThreadId}）` : ""}`}
                        description={(
                            <Space direction="vertical" style={{ width: "100%" }} size={4}>
                                <Typography.Text>
                                    已处理 {cleanupJob.processedAccounts ?? 0}/{cleanupJob.totalAccounts ?? 0} 个账号，
                                    已删除 {cleanupJob.deletedAccounts ?? 0} 个账号和 {cleanupJob.deletedSaves ?? 0} 个存档。
                                </Typography.Text>
                                <Progress percent={cleanupPercent} status="active" size="small" />
                            </Space>
                        )}
                    />
                )}
                {!accountsError && <Table
                    className="accounts-overview-table"
                    rowKey="id"
                    columns={accountColumns}
                    dataSource={accounts}
                    loading={isLoading}
                    pagination={{
                        defaultPageSize: 20,
                        current: accountPage?.page ?? page,
                        pageSize,
                        total: accountPage?.total ?? 0,
                        onChange: (nextPage, nextSize) => {
                            if (!Number.isSafeInteger(nextPage) || nextPage < 1 || ![20, 50, 100].includes(nextSize)) return
                            requestAdminLeave(() => { setEditNoteAccountId(null); setRenameId(null); setPage(nextSize === pageSize ? nextPage : 1); setPageSize(nextSize) })
                        },
                        showSizeChanger: true,
                        pageSizeOptions: [20, 50, 100],
                        showTotal: total => `共 ${total} 个账号`,
                    }}
                    size="small"
                    scroll={{ x: 1210 }}
                    locale={{ emptyText: searchQuery ? "没有匹配的账号" : "暂无账号" }}
                />}
                <Collapse size="small" className="account-maintenance" items={[{ key: "cleanup", label: "批量维护 · 删除未备注账号", children: (
                    <Space direction="vertical" style={{ width: "100%" }}>
                        <Typography.Text type="secondary">{cleanupScopeText}</Typography.Text>
                        <Tooltip title={cleanupRunning ? "清理任务正在进行，请等待完成" : cleanupScopeText}>
                        <span>
                        <Button
                            danger
                            icon={<DeleteOutlined />}
                            disabled={accountWritesDisabled || cleanupLoading || cleanupError || unnotedAccountCount === 0}
                            loading={cleanupUnnotedAccounts.isPending}
                            onClick={confirmCleanupUnnotedAccounts}
                        >
                            {cleanupRunning
                                ? `后台清理中 (${cleanupJob.processedAccounts ?? 0}/${cleanupJob.totalAccounts ?? 0})`
                                : accountsError ? "删除未备注账号（数据未就绪）" : `删除未备注账号 (${unnotedAccountCount})`}
                        </Button>
                        </span>
                        </Tooltip>
                    </Space>
                ) }]} />
            </Card>

            <Modal
                title="登录与绑定管理"
                open={loginAccountId !== null}
                onCancel={() => { if (accountWritePending) requestAdminLeave(() => setLoginAccountId(null)); else setLoginAccountId(null) }}
                footer={<Button onClick={() => { if (accountWritePending) requestAdminLeave(() => setLoginAccountId(null)); else setLoginAccountId(null) }}>完成</Button>}
                width={560}
                destroyOnClose
            >
                {loginQuery.isError ? <Alert type="error" showIcon message="账号详情读取失败"
                    description="账号可能已删除，或登录/网络暂时不可用。当前未保存内容仍保留。"
                    action={<Button loading={loginQuery.isFetching} onClick={() => void loginQuery.refetch()}>重试账号详情</Button>} />
                    : loginQuery.isPending ? <Alert type="info" message="正在读取账号详情…" />
                    : loginAccount && <Space direction="vertical" size="large" className="admin-stack account-login-dialog">
                    <div className="account-login-summary">
                        <div>
                            <Typography.Text strong>{loginAccount.defaultPlayerName || "未命名角色"}</Typography.Text>
                            <Typography.Text type="secondary" className="account-cell-meta">UID {loginAccount.viewerId || "未生成"}</Typography.Text>
                        </div>
                        <Tag bordered={false} color={loginAccount.playerLogin?.bound ? "cyan" : "gold"}>
                            {loginAccount.playerLogin?.bound ? "已绑定" : "未绑定"}
                        </Tag>
                    </div>
                    <Descriptions size="small" column={1} colon={false}>
                        <Descriptions.Item label="登录账号">
                            {loginAccount.loginUsername
                                ? <Typography.Text copyable>{loginAccount.loginUsername}</Typography.Text>
                                : "尚未设置"}
                        </Descriptions.Item>
                        {loginAccount.playerLogin?.bound && <>
                            <Descriptions.Item label="绑定时间">
                                {loginAccount.playerLogin.boundAt ? new Date(loginAccount.playerLogin.boundAt).toLocaleString() : "—"}
                            </Descriptions.Item>
                            <Descriptions.Item label="凭据有效期">
                                {loginAccount.playerLogin.sessionExpiresAt && loginAccount.playerLogin.sessionExpiresAt > Date.now()
                                    ? new Date(loginAccount.playerLogin.sessionExpiresAt).toLocaleString()
                                    : "暂无有效凭据，可用账号密码登录"}
                            </Descriptions.Item>
                        </>}
                    </Descriptions>
                    <div className="account-login-recovery">
                        <Typography.Text strong>{loginAccount.playerLogin?.bound ? "找回登录密码" : "绑定原有存档"}</Typography.Text>
                        <Typography.Paragraph type="secondary">
                            {loginAccount.playerLogin?.bound
                                ? "核实玩家身份后生成重置码，玩家在登录页选择“忘记密码”设置新密码。原 UID、存档和备注保留。"
                                : "老玩家无需先注册。使用原 UID 和继承密码验证，或领取绑定码，确认原存档后设置账号密码。"}
                        </Typography.Paragraph>
                        <Popconfirm
                            title={loginAccount.playerLogin?.bound ? "生成登录密码重置码？" : "生成旧存档绑定码？"}
                            description={`请确认已核实 UID ${loginAccount.viewerId} 的存档归属。新码将替换之前的同用途验证码。`}
                            okText="生成验证码" cancelText="取消" okButtonProps={{ disabled: accountWritesDisabled }}
                            onConfirm={() => issueLoginCode.mutate(loginAccount)}
                        >
                            <Button type="primary" disabled={accountWritesDisabled || !loginAccount.viewerId}
                                loading={issueLoginCode.isPending && issueLoginCode.variables?.id === loginAccount.id}>
                                {loginAccount.playerLogin?.bound ? "生成重置码" : "生成绑定码"}
                            </Button>
                        </Popconfirm>
                        <Typography.Text type="secondary" className="account-cell-meta">15 分钟有效 · 仅限一次使用</Typography.Text>
                    </div>
                    <Collapse ghost size="small" items={[{
                        key: "legacy", label: "设备记录与继承信息",
                        children: <Space direction="vertical" size="middle" className="admin-stack">
                            <Typography.Text type="secondary">
                                原设备 ID：{loginAccount.bindings.length ? loginAccount.bindings.map(binding => binding.deviceId).join("、") : "无记录"}
                            </Typography.Text>
                            <Typography.Text type="secondary">
                                {loginAccount.playerLogin?.bound
                                    ? "设备记录仅供历史定位；旧继承入口已停用。登录凭据有效不代表当前在线。"
                                    : "绑定账号前仍沿用原设备和继承机制；绑定后使用账号密码登录。"}
                            </Typography.Text>
                            {!loginAccount.playerLogin?.bound && <Space wrap>
                                <Tag>{loginAccount.takeoverConfigured ? "已设置继承密码" : "未设置继承密码"}</Tag>
                                <Popconfirm
                                    title={loginAccount.takeoverConfigured ? "重置该账号的继承密码？" : "为该账号生成继承密码？"}
                                    description="新密码仅显示一次；已存在的旧继承密码立即失效。"
                                    okText={loginAccount.takeoverConfigured ? "确认重置" : "确认生成"} cancelText="取消"
                                    okButtonProps={{ danger: loginAccount.takeoverConfigured, disabled: accountWritesDisabled }}
                                    onConfirm={() => issueTakeoverPassword.mutate({ accountId: loginAccount.id, reset: loginAccount.takeoverConfigured })}
                                >
                                    <Button size="small" disabled={accountWritesDisabled} danger={loginAccount.takeoverConfigured}
                                        loading={issueTakeoverPassword.isPending && issueTakeoverPassword.variables?.accountId === loginAccount.id}>
                                        {loginAccount.takeoverConfigured ? "重置继承密码" : "生成继承密码"}
                                    </Button>
                                </Popconfirm>
                            </Space>}
                            {loginAccount.latestTransfer && <Typography.Text type="secondary">
                                最近继承：{new Date(loginAccount.latestTransfer.transferredAt).toLocaleString()} · {loginAccount.latestTransfer.abolishedViewerId
                                    ? `已废弃临时账号 ${loginAccount.latestTransfer.abolishedViewerId}` : "标题页直接恢复"}
                            </Typography.Text>}
                        </Space>,
                    }]} />
                </Space>}
            </Modal>

            <Drawer
                open={selectedAccountId !== null}
                onClose={() => {
                    const close = () => { setRenameId(null); setSelectedAccountId(null) }
                    if (accountWritePending || (renameId !== null && renameName !== renameOriginal)) requestAdminLeave(close)
                    else close()
                }}
                width="min(1180px, 96vw)"
                title={<span className="account-drawer-title">{selectedAccount
                    ? `账号 ${selectedAccount.viewerId ?? `内部 #${selectedAccount.id}`} 的存档`
                    : "存档管理"}</span>}
                destroyOnClose
            >
                {selectedQuery.isError ? <Alert type="error" showIcon message="存档列表读取失败"
                    description="账号可能已删除，或登录/网络暂时不可用。"
                    action={<Button loading={selectedQuery.isFetching} onClick={() => void selectedQuery.refetch()}>重试存档列表</Button>} />
                : selectedQuery.isPending ? <Alert type="info" message="正在读取存档列表…" />
                : selectedAccount ? (
                    <Table
                        rowKey="id"
                        columns={saveColumns}
                        dataSource={savePlayers}
                        pagination={false}
                        size="small"
                        locale={{ emptyText: "暂无存档" }}
                        scroll={{ x: "max-content" }}
                    />
                ) : (
                    <Alert type="warning" showIcon message="账号已不存在或刚刚被删除" />
                )}
            </Drawer>

        </Space>
        </AdminPage>
    )
}
