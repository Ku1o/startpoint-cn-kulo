import { useEffect, useMemo, useState } from "react"
import {
    Alert,
    Button,
    Card,
    Col,
    DatePicker,
    Descriptions,
    Form,
    Input,
    InputNumber,
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

const { TextArea } = Input

const CATEGORY_LABELS: Record<number, string> = {
    1: "最新资讯",
    2: "活动信息",
    3: "问题修复",
    4: "系统公告",
}

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
    id?: number | null
    title: string
    date: Dayjs
    category: number
    label: number
    thumbnail: number
    thumbnail_path?: string
    added_time?: Dayjs | null
    html: string
    published: boolean
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
    const [popupForm] = Form.useForm<PopupFormValues>()
    const [newsForm] = Form.useForm<NewsFormValues>()
    const [editing, setEditing] = useState<NewsItem | null | undefined>(undefined)
    const [preview, setPreview] = useState<NewsItem | null>(null)

    const overviewQuery = useQuery({
        queryKey: ["newsOverview"],
        queryFn: () => apiGet<NewsOverview>("/api/news/"),
    })

    const refresh = async () => {
        await queryClient.invalidateQueries({ queryKey: ["newsOverview"] })
    }

    useEffect(() => {
        const popup = overviewQuery.data?.popup
        if (!popup) return
        popupForm.setFieldsValue({
            ...popup,
            start_time: popup.start_time ? dayjs(popup.start_time) : null,
            end_time: popup.end_time ? dayjs(popup.end_time) : null,
        })
    }, [overviewQuery.data?.popup, popupForm])

    const savePopup = useMutation({
        mutationFn: (values: PopupFormValues) => apiPut<NewsOverview>("/api/news/popup", {
            enabled: values.enabled,
            news_id: values.news_id ?? null,
            mode: values.mode,
            start_time: toServerTime(values.start_time),
            end_time: toServerTime(values.end_time),
        }),
        onSuccess: async () => {
            message.success("登录弹窗设置已保存")
            await refresh()
        },
        onError: (error: Error) => message.error(error.message),
    })

    const saveItem = useMutation({
        mutationFn: (values: NewsFormValues) => {
            const payload = {
                id: values.id ?? undefined,
                title: values.title,
                date: toServerTime(values.date),
                category: values.category,
                label: values.label,
                thumbnail: values.thumbnail,
                thumbnail_path: values.thumbnail_path?.trim() || null,
                added_time: toServerTime(values.added_time),
                html: values.html,
                published: values.published,
            }
            return editing
                ? apiPatch<NewsOverview>(`/api/news/items/${editing.id}`, payload)
                : apiPost<NewsOverview>("/api/news/items", payload)
        },
        onSuccess: async () => {
            message.success(editing ? "公告已更新" : "公告已创建")
            setEditing(undefined)
            newsForm.resetFields()
            await refresh()
        },
        onError: (error: Error) => message.error(error.message),
    })

    const deleteItem = useMutation({
        mutationFn: (id: number) => apiDelete<NewsOverview>(`/api/news/items/${id}`),
        onSuccess: async () => {
            message.success("公告已删除")
            await refresh()
        },
        onError: (error: Error) => message.error(error.message),
    })

    const selectPopup = useMutation({
        mutationFn: (newsId: number) => apiPut<NewsOverview>("/api/news/popup", {
            enabled: true,
            news_id: newsId,
        }),
        onSuccess: async () => {
            message.success("已设为登录弹窗；玩家重新登录后生效")
            await refresh()
        },
        onError: (error: Error) => message.error(error.message),
    })

    const resetPopupReceipts = useMutation({
        mutationFn: (newsId: number | null) => apiPost<{ deleted: number }>("/api/news/popup/reset", {
            news_id: newsId,
        }),
        onSuccess: async result => {
            message.success(`已清除 ${result.deleted} 条弹出记录；相关玩家下次登录可再次看到`)
            await refresh()
        },
        onError: (error: Error) => message.error(error.message),
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
                html: "<html lang=\"zh\"><body><h2>公告标题</h2><p>在这里填写公告正文。</p></body></html>",
                published: true,
            })
            return
        }
        newsForm.setFieldsValue({
            ...editing,
            thumbnail_path: editing.thumbnail_path ?? "",
            date: dayjs(editing.date),
            added_time: editing.added_time ? dayjs(editing.added_time) : null,
        })
    }

    const openCreate = () => {
        setEditing(null)
    }

    const openEdit = (item: NewsItem) => {
        setEditing(item)
    }

    const overview = overviewQuery.data
    const popupItem = useMemo(
        () => overview?.news.find(item => item.id === overview.popup.news_id) ?? null,
        [overview],
    )
    const publishedCount = overview?.news.filter(item => item.published).length ?? 0

    if (overviewQuery.isLoading) return <StateCard><Spin size="large" /></StateCard>
    if (overviewQuery.isError || !overview) {
        return <Alert type="error" showIcon message="公告管理接口不可用" />
    }

    return (
        <AdminPage
            eyebrow="ANNOUNCEMENTS"
            title="公告管理"
            description="维护游戏内公告列表和登录强制弹窗。保存后配置立即生效，不需要重启服务。"
            actions={(
                <Space wrap>
                    <Button
                        icon={<ReloadOutlined />}
                        loading={overviewQuery.isFetching}
                        onClick={() => overviewQuery.refetch()}
                    >刷新</Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建公告</Button>
                </Space>
            )}
        >
            <Space direction="vertical" size="large" className="admin-stack">
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
                        onFinish={values => savePopup.mutate(values)}
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
                            <Button type="primary" htmlType="submit" loading={savePopup.isPending}>保存弹窗设置</Button>
                            <Popconfirm
                                title="重置弹出记录？"
                                description="使用“每账号每篇仅一次”时，已看过的玩家将可以再次看到。"
                                onConfirm={() => resetPopupReceipts.mutate(overview.popup.news_id)}
                                okText="确认重置"
                                cancelText="取消"
                            >
                                <Button loading={resetPopupReceipts.isPending} disabled={overview.popup.news_id === null}>
                                    重置弹出记录
                                </Button>
                            </Popconfirm>
                        </Space>
                    </Form>
                </Card>

                <Card title="公告列表" className="admin-table-card">
                    <Table<NewsItem>
                        rowKey="id"
                        size="small"
                        scroll={{ x: 920 }}
                        pagination={{ defaultPageSize: 10, showSizeChanger: true }}
                        dataSource={[...overview.news].sort((left, right) => right.date.localeCompare(left.date))}
                        columns={[
                            { title: "ID", dataIndex: "id", width: 76, render: value => <Typography.Text code>#{value}</Typography.Text> },
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
                                width: 285,
                                fixed: "right",
                                render: (_, item) => (
                                    <Space size={4} wrap>
                                        <Button size="small" onClick={() => setPreview(item)}>预览</Button>
                                        <Button size="small" onClick={() => openEdit(item)}>编辑</Button>
                                        <Button
                                            size="small"
                                            disabled={!item.published || overview.popup.news_id === item.id && overview.popup.enabled}
                                            loading={selectPopup.isPending && selectPopup.variables === item.id}
                                            onClick={() => selectPopup.mutate(item.id)}
                                        >设为弹窗</Button>
                                        <Popconfirm
                                            title={`删除公告 #${item.id}？`}
                                            description="相关公告阅读记录也会一并删除。"
                                            onConfirm={() => deleteItem.mutate(item.id)}
                                            okText="确认删除"
                                            cancelText="取消"
                                            okButtonProps={{ danger: true }}
                                        >
                                            <Button size="small" danger>删除</Button>
                                        </Popconfirm>
                                    </Space>
                                ),
                            },
                        ]}
                    />
                </Card>

                <Typography.Text type="secondary" className="news-source-path">
                    配置文件：{overview.source_path}
                </Typography.Text>
            </Space>

            <Modal
                open={editing !== undefined}
                title={editing ? `编辑公告 #${editing.id}` : "新建公告"}
                width={900}
                okText="保存公告"
                cancelText="取消"
                confirmLoading={saveItem.isPending}
                onOk={() => newsForm.submit()}
                onCancel={() => setEditing(undefined)}
                afterOpenChange={open => {
                    if (open) initializeNewsForm()
                }}
                destroyOnHidden
            >
                <Form<NewsFormValues>
                    form={newsForm}
                    layout="vertical"
                    onFinish={values => saveItem.mutate(values)}
                    preserve={false}
                >
                    <Row gutter={16}>
                        <Col xs={24} md={6}>
                            <Form.Item name="id" label="公告 ID" tooltip="留空自动分配；创建后不可修改">
                                <InputNumber min={1} precision={0} disabled={!!editing} style={{ width: "100%" }} />
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
                            <Form.Item name="label" label="标签编号" rules={[{ required: true }]}>
                                <InputNumber min={0} max={99} precision={0} style={{ width: "100%" }} />
                            </Form.Item>
                        </Col>
                        <Col xs={12} md={4}>
                            <Form.Item name="thumbnail" label="缩略图编号" rules={[{ required: true }]}>
                                <InputNumber min={0} max={99} precision={0} style={{ width: "100%" }} />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={8}>
                            <Form.Item name="published" label="发布状态" valuePropName="checked">
                                <Switch checkedChildren="已发布" unCheckedChildren="草稿" />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={12}>
                            <Form.Item name="date" label="公告时间" rules={[{ required: true }]}>
                                <DatePicker showTime format="YYYY-MM-DD HH:mm:ss" style={{ width: "100%" }} />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={12}>
                            <Form.Item name="added_time" label="添加时间（可选）">
                                <DatePicker showTime format="YYYY-MM-DD HH:mm:ss" style={{ width: "100%" }} />
                            </Form.Item>
                        </Col>
                        <Col span={24}>
                            <Form.Item name="thumbnail_path" label="缩略图资源路径（可选）">
                                <Input placeholder="例如 dynamic/feature_announcement/example.png" />
                            </Form.Item>
                        </Col>
                        <Col span={24}>
                            <Form.Item
                                name="html"
                                label="HTML 正文"
                                rules={[{ required: true, message: "请输入 HTML 正文" }]}
                                extra="游戏客户端支持基础 HTML；本页面预览运行在隔离沙箱中，不执行脚本。"
                            >
                                <TextArea rows={16} className="news-html-editor" />
                            </Form.Item>
                        </Col>
                    </Row>
                </Form>
            </Modal>

            <Modal
                open={preview !== null}
                title={preview ? `公告预览 · #${preview.id} ${preview.title}` : "公告预览"}
                width={920}
                footer={null}
                onCancel={() => setPreview(null)}
                destroyOnHidden
            >
                {preview && (
                    <>
                        <Descriptions size="small" bordered column={{ xs: 1, sm: 2 }} style={{ marginBottom: 16 }}>
                            <Descriptions.Item label="分类">{CATEGORY_LABELS[preview.category]}</Descriptions.Item>
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
