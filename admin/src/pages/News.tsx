import { useEffect, useMemo, useRef, useState } from "react"
import {
    Alert,
    Button,
    Card,
    Col,
    Collapse,
    DatePicker,
    Descriptions,
    Form,
    Grid,
    Input,
    Modal,
    Popconfirm,
    Row,
    Select,
    Space,
    Spin,
    Statistic,
    Switch,
    Table,
    Tag,
    Typography,
    message,
} from "antd"
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import dayjs, { Dayjs } from "dayjs"
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "../api/client"
import { AdminPage, StateCard } from "../components/AdminPage"
import NewsHtmlEditor from "../components/NewsHtmlEditor"
import { sanitizeNewsDocument } from "../lib/newsHtml"
import { useAdminEditGuard } from "../lib/editGuard"
import { parseNewsIdInput, NEWS_ID_MAX } from "../lib/newsFormRules"
import "./News.css"

const CATEGORY_LABELS: Record<number, string> = {
    1: "最新资讯",
    2: "活动信息",
    3: "问题修复",
    4: "系统公告",
}

const NEWS_LABEL_OPTIONS = [
    { value: 1, label: "1 · 更新" },
    { value: 2, label: "2 · 抽卡" },
    { value: 3, label: "3 · 活动" },
    { value: 4, label: "4 · 新闻" },
    { value: 5, label: "5 · 活动推广" },
    { value: 6, label: "6 · 维护" },
    { value: 7, label: "7 · BUG" },
    { value: 8, label: "8 · 系统" },
]

const NEWS_THUMBNAIL_OPTIONS = [
    { value: 1, label: "1 · 重要" },
    { value: 2, label: "2 · 更新" },
    { value: 3, label: "3 · 新闻" },
    { value: 4, label: "4 · 任务" },
    { value: 5, label: "5 · 装备" },
    { value: 6, label: "6 · 活动旗帜" },
    { value: 7, label: "7 · 战斗" },
    { value: 8, label: "8 · 活动" },
    { value: 9, label: "9 · 宝箱" },
    { value: 10, label: "10 · 设置" },
    { value: 11, label: "11 · 重要（同 1）" },
    { value: 12, label: "12 · 设置（同 10）" },
    { value: 13, label: "13 · 设置（同 10）" },
]

type PopupMode = "every_login" | "once_per_news"

interface NewsItem {
    id: number
    title: string
    date: string
    category: number
    label: number
    thumbnail: number
    thumbnail_path: string | null
    added_time: string | null
    html: string
    published: boolean
}

interface PopupConfig {
    enabled: boolean
    news_id: number | null
    mode: PopupMode
    start_time: string | null
    end_time: string | null
}

interface NewsOverview {
    version: 1
    popup: PopupConfig
    news: NewsItem[]
    load_error: string | null
    source_path: string
    active_popup_id: number | null
}

interface PopupFormValues {
    enabled: boolean
    news_id: number | null
    mode: PopupMode
    start_time: Dayjs | null
    end_time: Dayjs | null
}

interface NewsFormValues {
    id?: string | null
    title: string
    date: Dayjs
    category: number
    label: number
    thumbnail: number
    thumbnail_path?: string | null
    added_time?: Dayjs | null
    html: string
    published: boolean
}

interface NewsSubmission {
    values: NewsFormValues
    targetId: number | null
    session: number
    version: number
    knownIds: number[]
}

function toServerTime(value: Dayjs | null | undefined): string | null {
    return value ? value.format("YYYY-MM-DD HH:mm:ss") : null
}

function buildPreviewDocument(item: NewsItem): string {
    const html = item.html.trim()
    if (/<!doctype|<html[\s>]/i.test(html)) return html
    return `<!doctype html><html lang="zh"><head><meta charset="utf-8"></head><body>${html}</body></html>`
}

export default function News() {
    const queryClient = useQueryClient()
    const screens = Grid.useBreakpoint()
    const [popupForm] = Form.useForm<PopupFormValues>()
    const [newsForm] = Form.useForm<NewsFormValues>()
    const [editing, setEditing] = useState<NewsItem | null | undefined>(undefined)
    const [preview, setPreview] = useState<NewsItem | null>(null)
    const [popupDirty, setPopupDirty] = useState(false)
    const [itemDirty, setItemDirty] = useState(false)
    const popupDirtyRef = useRef(false)
    const popupVersion = useRef(0)
    const editorSession = useRef(0)
    const editorVersion = useRef(0)

    const overviewQuery = useQuery({
        queryKey: ["newsOverview"],
        queryFn: ({ signal }) => apiGet<NewsOverview>("/api/news/", { signal }),
    })

    const refresh = async () => {
        await queryClient.invalidateQueries({ queryKey: ["newsOverview"] })
    }

    useEffect(() => {
        const popup = overviewQuery.data?.popup
        if (!popup || popupDirtyRef.current) return
        popupForm.setFieldsValue({
            ...popup,
            start_time: popup.start_time ? dayjs(popup.start_time) : null,
            end_time: popup.end_time ? dayjs(popup.end_time) : null,
        })
    }, [overviewQuery.data?.popup, popupForm])

    const savePopup = useMutation({
        mutationFn: ({ values }: { values: PopupFormValues; version: number }) => apiPut<NewsOverview>("/api/news/popup", {
            enabled: values.enabled,
            news_id: values.news_id ?? null,
            mode: values.mode,
            start_time: toServerTime(values.start_time),
            end_time: toServerTime(values.end_time),
        }),
        onSuccess: async (result, submission) => {
            await queryClient.cancelQueries({ queryKey: ["newsOverview"] })
            const unchanged = popupVersion.current === submission.version
            if (unchanged) { popupDirtyRef.current = false; setPopupDirty(false) }
            message.success(unchanged ? "登录弹窗设置已保存" : "提交的弹窗设置已保存；后续修改仍待保存")
            queryClient.setQueryData(["newsOverview"], result)
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const saveItem = useMutation({
        mutationFn: ({ values, targetId }: NewsSubmission) => {
            const payload = {
                id: parseNewsIdInput(values.id) ?? undefined,
                title: values.title,
                date: toServerTime(values.date),
                category: values.category,
                label: values.label,
                thumbnail: values.thumbnail,
                // The shipped client only supports its built-in thumbnail
                // enum; custom resource paths are not implemented.
                thumbnail_path: null,
                added_time: toServerTime(values.added_time),
                html: sanitizeNewsDocument(values.html),
                published: values.published,
            }
            return targetId !== null
                ? apiPatch<NewsOverview>(`/api/news/items/${targetId}`, payload)
                : apiPost<NewsOverview>("/api/news/items", payload)
        },
        onSuccess: async (result, submission) => {
            await queryClient.cancelQueries({ queryKey: ["newsOverview"] })
            if (editorSession.current === submission.session) {
                if (editorVersion.current === submission.version) {
                    setEditing(undefined)
                    setItemDirty(false)
                    newsForm.resetFields()
                } else {
                    // A create response must bind later edits to the created item,
                    // without replacing any of the draft's newer field values.
                    const submittedId = parseNewsIdInput(submission.values.id)
                    const saved = result.news.find(item => submission.targetId !== null
                        ? item.id === submission.targetId
                        : submittedId !== null ? item.id === submittedId : !submission.knownIds.includes(item.id))
                    if (saved) { setEditing(saved); newsForm.setFieldValue("id", String(saved.id)) }
                }
            }
            message.success(editorSession.current === submission.session && editorVersion.current !== submission.version
                ? "提交的公告已保存；后续修改仍待保存" : submission.targetId !== null ? "公告已更新" : "公告已创建")
            queryClient.setQueryData(["newsOverview"], result)
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const deleteItem = useMutation({
        mutationFn: (id: number) => apiDelete<NewsOverview>(`/api/news/items/${id}`),
        onSuccess: async result => {
            await queryClient.cancelQueries({ queryKey: ["newsOverview"] })
            message.success("公告已删除")
            queryClient.setQueryData(["newsOverview"], result)
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const selectPopup = useMutation({
        mutationFn: (newsId: number) => apiPut<NewsOverview>("/api/news/popup", {
            enabled: true,
            news_id: newsId,
        }),
        onSuccess: async result => {
            await queryClient.cancelQueries({ queryKey: ["newsOverview"] })
            message.success("已设为登录弹窗；玩家重新登录后生效")
            queryClient.setQueryData(["newsOverview"], result)
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const resetPopupReceipts = useMutation({
        mutationFn: async (newsId: number | null) => {
            const result = await apiPost<{ ok?: boolean; deleted: number; error?: string }>("/api/news/popup/reset", { news_id: newsId })
            if (result.ok === false || !Number.isSafeInteger(result.deleted) || result.deleted < 0) throw new Error(result.error || "重置未确认完成，请刷新后重试。")
            return result
        },
        onSuccess: async result => {
            message.success(`已清除 ${result.deleted} 条弹出记录；相关玩家下次登录可再次看到`)
            await refresh()
        },
        onError: (error: Error) => { message.error(error.message) },
    })

    const initializeNewsForm = () => {
        if (editing === undefined) return
        if (editing === null) {
            const now = dayjs()
            newsForm.setFieldsValue({
                id: null,
                title: "",
                date: now,
                category: 1,
                label: 1,
                thumbnail: 1,
                thumbnail_path: "",
                added_time: now,
                html: "",
                published: true,
            })
            return
        }
        newsForm.setFieldsValue({
            ...editing,
            id: String(editing.id),
            date: dayjs(editing.date),
            added_time: editing.added_time ? dayjs(editing.added_time) : null,
        })
    }

    const openCreate = () => {
        editorSession.current++; editorVersion.current = 0; setItemDirty(false); saveItem.reset()
        setEditing(null)
    }

    const openEdit = (item: NewsItem) => {
        editorSession.current++; editorVersion.current = 0; setItemDirty(false); saveItem.reset()
        setEditing(item)
    }

    const previewDraft = async () => {
        try {
            const values = await newsForm.validateFields()
            setPreview({ ...values, id: editing?.id ?? parseNewsIdInput(values.id) ?? 0,
                date: toServerTime(values.date) ?? "", added_time: toServerTime(values.added_time),
                thumbnail_path: values.thumbnail_path ?? null, html: sanitizeNewsDocument(values.html) })
        } catch {
            void message.info("请先补全公告内容，再预览")
        }
    }

    const overview = overviewQuery.data
    const popupItem = useMemo(
        () => overview?.news.find(item => item.id === overview.popup.news_id) ?? null,
        [overview],
    )
    const publishedCount = overview?.news.filter(item => item.published).length ?? 0
    const writePending = savePopup.isPending || saveItem.isPending || deleteItem.isPending || selectPopup.isPending || resetPopupReceipts.isPending
    const writesBlocked = writePending || !!overview?.load_error
    useAdminEditGuard({ dirty: popupDirty || editing !== undefined && itemDirty, pending: writePending, label: "公告" })
    const listOperationError = deleteItem.error || selectPopup.error || resetPopupReceipts.error
    const closeEditor = () => {
        if (saveItem.isPending) { Modal.info({ title: "公告正在保存", content: "请等待保存结果后再关闭；关闭窗口不代表撤销已提交的操作。", okText: "继续等待" }); return }
        const close = () => { editorSession.current++; setEditing(undefined); setItemDirty(false) }
        if (!itemDirty) { close(); return }
        Modal.confirm({ title: "放弃这篇公告的未保存修改？", content: "已经保存的公告不会被撤销。", okText: "放弃修改", cancelText: "继续编辑", onOk: close })
    }

    const discardPopupDraft = () => {
        const popup = overview?.popup
        if (!popup) return
        popupVersion.current++; popupDirtyRef.current = false; setPopupDirty(false); savePopup.reset()
        popupForm.setFieldsValue({ ...popup, start_time: popup.start_time ? dayjs(popup.start_time) : null,
            end_time: popup.end_time ? dayjs(popup.end_time) : null })
    }

    if (overviewQuery.isLoading) return <StateCard><Spin size="large" /></StateCard>
    if (!overview) {
        return <Alert type="error" showIcon message="公告管理接口不可用" action={<Button onClick={() => overviewQuery.refetch()} loading={overviewQuery.isFetching}>重试</Button>} />
    }

    return (
        <AdminPage
            eyebrow="ANNOUNCEMENTS"
            title="公告管理"
            description="新建或编辑后预览，确认发布状态再保存；登录弹窗另行设置，保存立即生效。"
            actions={(
                <Space wrap>
                    <Button
                        icon={<ReloadOutlined />}
                        loading={overviewQuery.isFetching}
                        onClick={() => overviewQuery.refetch()}
                    >刷新</Button>
                    <Button type="primary" icon={<PlusOutlined />} disabled={writesBlocked} onClick={openCreate}>新建公告</Button>
                </Space>
            )}
        >
            <Space direction="vertical" size="large" className="admin-stack news-manage-stack">
                {overviewQuery.isError && <Alert type="error" showIcon message="刷新公告失败，已保留当前数据和未保存修改，请重试。" />}
                {listOperationError && <Alert type="error" showIcon message={listOperationError.message} description="请刷新当前状态后重试。"
                    action={<Button disabled={writePending} onClick={() => overviewQuery.refetch()}>刷新状态</Button>} />}
                {overview.load_error && (
                    <Alert
                        type="error"
                        showIcon
                        message="公告配置读取失败"
                        description={overview.load_error}
                    />
                )}

                <Row gutter={[16, 16]}>
                    <Col xs={12} lg={6}><Card><Statistic title="公告总数" value={overview.news.length} /></Card></Col>
                    <Col xs={12} lg={6}><Card><Statistic title="已发布" value={publishedCount} /></Card></Col>
                    <Col xs={12} lg={6}>
                        <Card><Statistic title="登录弹窗" value={overview.popup.enabled ? "已开启" : "未开启"} /></Card>
                    </Col>
                    <Col xs={12} lg={6}>
                        <Card><Statistic title="当前生效" value={overview.active_popup_id === null ? "无" : `#${overview.active_popup_id}`} /></Card>
                    </Col>
                </Row>

                <Card title="公告列表" className="admin-table-card">
                    <Table<NewsItem>
                        rowKey="id"
                        size="small"
                        scroll={{ x: 920 }}
                        pagination={{ defaultPageSize: 10, showSizeChanger: true }}
                        dataSource={[...overview.news].sort((left, right) => right.date.localeCompare(left.date))}
                        columns={[
                            { title: "编号", dataIndex: "id", width: 90, render: value => <Typography.Text code>#{value}</Typography.Text> },
                            {
                                title: "公告",
                                dataIndex: "title",
                                render: (value, item) => (
                                    <Space direction="vertical" size={0}>
                                        <Typography.Text strong>{value}</Typography.Text>
                                        <Typography.Text type="secondary">{item.date}</Typography.Text>
                                    </Space>
                                ),
                            },
                            {
                                title: "分类",
                                dataIndex: "category",
                                width: 110,
                                render: value => <Tag color={value === 4 ? "purple" : "blue"}>{CATEGORY_LABELS[value] ?? value}</Tag>,
                            },
                            {
                                title: "状态",
                                width: 120,
                                render: (_, item) => (
                                    <Space size={4} wrap>
                                        <Tag color={item.published ? "green" : "default"}>{item.published ? "已发布" : "草稿"}</Tag>
                                        {overview.popup.news_id === item.id && <Tag color="gold">弹窗</Tag>}
                                    </Space>
                                ),
                            },
                            {
                                title: "操作",
                                width: screens.md ? 285 : 180,
                                fixed: screens.md ? "right" as const : undefined,
                                render: (_, item) => (
                                    <Space size={4} wrap>
                                        <Button size="small" onClick={() => setPreview(item)}>预览</Button>
                                        <Button size="small" disabled={writesBlocked} onClick={() => openEdit(item)}>编辑</Button>
                                        <Button
                                            size="small"
                                            disabled={writesBlocked || popupDirty || !item.published || overview.popup.news_id === item.id && overview.popup.enabled}
                                            loading={selectPopup.isPending && selectPopup.variables === item.id}
                                            onClick={() => selectPopup.mutate(item.id)}
                                        >设为弹窗</Button>
                                        <Popconfirm
                                            title={`删除公告 #${item.id}？`}
                                            description="相关公告阅读记录也会一并删除。"
                                            onConfirm={() => { if (!writesBlocked) deleteItem.mutate(item.id) }}
                                            okText="确认删除"
                                            cancelText="取消"
                                            okButtonProps={{ danger: true }}
                                        >
                                            <Button size="small" danger disabled={writesBlocked} loading={deleteItem.isPending && deleteItem.variables === item.id}>删除</Button>
                                        </Popconfirm>
                                    </Space>
                                ),
                            },
                        ]}
                    />
                </Card>

                <Card
                    title="登录弹窗"
                    extra={popupItem && (
                        <Button size="small" onClick={() => setPreview(popupItem)}>预览当前公告</Button>
                    )}
                >
                    <Alert
                        type={overview.active_popup_id === null ? "info" : "success"}
                        showIcon
                        message={overview.active_popup_id === null
                            ? "当前没有处于生效时间内的登录弹窗"
                            : `公告 #${overview.active_popup_id} 会在符合策略的玩家重新登录后弹出`}
                        style={{ marginBottom: 18 }}
                    />
                    <Form<PopupFormValues>
                        form={popupForm}
                        layout="vertical"
                        onFinish={values => { if (!writesBlocked) savePopup.mutate({ values, version: popupVersion.current }) }}
                        onValuesChange={() => { popupVersion.current++; popupDirtyRef.current = true; setPopupDirty(true) }}
                        className="news-popup-form"
                    >
                        <Row gutter={16}>
                            <Col xs={24} md={6}>
                                <Form.Item name="enabled" label="启用登录弹窗" valuePropName="checked">
                                    <Switch checkedChildren="启用" unCheckedChildren="关闭" />
                                </Form.Item>
                            </Col>
                            <Col xs={24} md={10}>
                                <Form.Item
                                    name="news_id"
                                    label="弹出公告"
                                    dependencies={["enabled"]}
                                    rules={[
                                        ({ getFieldValue }) => ({
                                            validator: (_, value) => (
                                                !getFieldValue("enabled") || value !== null && value !== undefined
                                                    ? Promise.resolve()
                                                    : Promise.reject(new Error("启用登录弹窗时请选择公告"))
                                            ),
                                        }),
                                    ]}
                                >
                                    <Select
                                        allowClear
                                        placeholder="选择一篇已发布公告"
                                        options={overview.news.map(item => ({
                                            value: item.id,
                                            disabled: !item.published,
                                            label: `#${item.id} · ${item.title}${item.published ? "" : "（未发布）"}`,
                                        }))}
                                    />
                                </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                                <Form.Item name="mode" label="弹出策略" rules={[{ required: true }]}>
                                    <Select options={[
                                        { value: "once_per_news", label: "每账号每篇仅一次" },
                                        { value: "every_login", label: "每次登录都弹出" },
                                    ]} />
                                </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                                <Form.Item name="start_time" label="开始时间（留空立即生效）">
                                    <DatePicker showTime format="YYYY-MM-DD HH:mm:ss" style={{ width: "100%" }} />
                                </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                                <Form.Item name="end_time" label="结束时间（留空长期有效）">
                                    <DatePicker showTime format="YYYY-MM-DD HH:mm:ss" style={{ width: "100%" }} />
                                </Form.Item>
                            </Col>
                        </Row>
                        <Space wrap>
                            <Button type="primary" htmlType="submit" loading={savePopup.isPending} disabled={writesBlocked}>保存弹窗设置</Button>
                            {popupDirty && <><Tag color="orange">弹窗设置尚未保存</Tag><Button onClick={discardPopupDraft} disabled={writePending}>放弃本地修改</Button></>}
                            <Popconfirm
                                title="重置弹出记录？"
                                description="使用“每账号每篇仅一次”时，已看过的玩家将可以再次看到。"
                                onConfirm={() => { if (!writesBlocked && !popupDirty) resetPopupReceipts.mutate(overview.popup.news_id) }}
                                okText="确认重置"
                                cancelText="取消"
                            >
                                <Button loading={resetPopupReceipts.isPending} disabled={writesBlocked || popupDirty || overview.popup.news_id === null}>
                                    重置弹出记录
                                </Button>
                            </Popconfirm>
                        </Space>
                        {savePopup.isError && <Alert type="error" showIcon message={savePopup.error.message} description="弹窗草稿已保留，可修改后重新保存。" style={{ marginTop: 12 }} />}
                    </Form>
                </Card>

                <Collapse size="small" items={[{ key: "source", label: "高级 · 配置来源", children: (
                    <Typography.Text type="secondary" className="news-source-path">{overview.source_path}</Typography.Text>
                ) }]} />
            </Space>

            <Modal
                open={editing !== undefined}
                title={editing ? `编辑公告 #${editing.id}` : "新建公告"}
                width={900}
                className="news-editor-modal"
                okText="按当前状态保存"
                cancelText="取消"
                confirmLoading={saveItem.isPending}
                okButtonProps={{ disabled: writesBlocked }}
                onOk={() => { if (!writesBlocked) newsForm.submit() }}
                onCancel={closeEditor}
                afterOpenChange={open => {
                    if (open) initializeNewsForm()
                }}
                destroyOnHidden
            >
                <Form<NewsFormValues>
                    form={newsForm}
                    layout="vertical"
                    onFinish={values => { if (!writesBlocked) saveItem.mutate({ values, targetId: editing?.id ?? null,
                        session: editorSession.current, version: editorVersion.current, knownIds: overview.news.map(item => item.id) }) }}
                    onValuesChange={() => { editorVersion.current++; setItemDirty(true) }}
                    preserve={false}
                >
                    <Alert type="info" showIcon message="保存“已发布”会立即更新游戏公告；保存“草稿”不会出现在游戏公告列表。" style={{ marginBottom: 16 }} />
                    {saveItem.isError && <Alert type="error" showIcon message={saveItem.error.message} description="公告草稿已保留，可修改后重新保存。" style={{ marginBottom: 12 }} />}
                    <Row gutter={16}>
                        <Col xs={24} md={6}>
                            <Form.Item name="id" label="公告编号" tooltip={`留空自动分配；范围1至${NEWS_ID_MAX}，创建后不可修改`}
                                rules={[{ validator: (_, value) => {
                                    try {
                                        const id = parseNewsIdInput(value)
                                        return editing === null && id !== null && overview.news.some(item => item.id === id)
                                            ? Promise.reject(new Error("该编号已存在，请换一个或留空自动分配")) : Promise.resolve()
                                    } catch (error) { return Promise.reject(error) }
                                } }]}>
                                <Input inputMode="numeric" disabled={!!editing} />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={18}>
                            <Form.Item name="title" label="标题" rules={[{ required: true, message: "请输入标题" }, { max: 128 }]}>
                                <Input maxLength={128} showCount />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={8}>
                            <Form.Item name="category" label="分类" rules={[{ required: true }]}>
                                <Select options={Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value: Number(value), label }))} />
                            </Form.Item>
                        </Col>
                        <Col xs={12} md={4}>
                            <Form.Item name="label" label="标签" tooltip="编号对应客户端公告标签样式" rules={[{ required: true }]}>
                                <Select options={NEWS_LABEL_OPTIONS} />
                            </Form.Item>
                        </Col>
                        <Col xs={12} md={4}>
                            <Form.Item name="thumbnail" label="缩略图" tooltip="编号对应客户端内置图标；11 与 1 相同，12、13 与 10 相同" rules={[{ required: true }]}>
                                <Select options={NEWS_THUMBNAIL_OPTIONS} />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={8}>
                            <Form.Item name="published" label="保存后的状态" valuePropName="checked">
                                <Switch checkedChildren="已发布" unCheckedChildren="草稿" />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={12}>
                            <Form.Item name="date" label="公告时间" extra="格式：YYYY-MM-DD HH:mm:ss，按服务端当前时间填写" rules={[{ required: true }]}>
                                <DatePicker showTime format="YYYY-MM-DD HH:mm:ss" style={{ width: "100%" }} />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={12}>
                            <Form.Item name="added_time" label="添加时间（可选）" extra="留空时沿用公告时间；格式同上">
                                <DatePicker showTime format="YYYY-MM-DD HH:mm:ss" style={{ width: "100%" }} />
                            </Form.Item>
                        </Col>
                        <Col span={24}>
                            <Form.Item
                                name="html"
                                label="公告正文"
                                rules={[{ required: true, message: "请输入公告正文" }]}
                                extra="支持标题、加粗、列表和图片；需要精细调整时可使用高级编辑。"
                            >
                                <NewsHtmlEditor />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Button onClick={() => void previewDraft()}>预览当前编辑内容</Button>
                </Form>
            </Modal>

            <Modal
                open={preview !== null}
                title={preview ? `公告预览 · ${preview.id > 0 ? `#${preview.id}` : "待分配编号"} ${preview.title}` : "公告预览"}
                width={920}
                className="news-preview-modal"
                footer={null}
                onCancel={() => setPreview(null)}
                destroyOnHidden
            >
                {preview && (
                    <>
                        <Descriptions size="small" bordered column={{ xs: 1, sm: 2 }} style={{ marginBottom: 16 }}>
                            <Descriptions.Item label="分类">{CATEGORY_LABELS[preview.category]}</Descriptions.Item>
                            <Descriptions.Item label="预览状态">{preview.published ? "已发布" : "草稿"}</Descriptions.Item>
                            <Descriptions.Item label="公告时间">{preview.date}</Descriptions.Item>
                        </Descriptions>
                        <iframe
                            className="news-preview-frame"
                            title={`公告 ${preview.id} 预览`}
                            sandbox=""
                            srcDoc={buildPreviewDocument(preview)}
                        />
                    </>
                )}
            </Modal>
        </AdminPage>
    )
}
