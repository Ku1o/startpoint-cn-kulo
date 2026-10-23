import { Alert, Button, Card, Col, Collapse, Descriptions, Divider, Row, Space, Statistic, Tag, Typography } from "antd"
import { ReloadOutlined } from "@ant-design/icons"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { apiGet } from "../api/client"
import type { ServerStatus } from "../api/serverStatus"
import { AdminPage } from "../components/AdminPage"
import { formatBeijingTime, formatBytes, formatDuration } from "../lib/adminFormat"
import { useAdminNavigate } from "../lib/editGuard"

const cdnScopeLabels: Record<string, string> = { items: "道具", characters: "角色", events: "活动", quests: "任务", shops: "商店" }

export default function Dashboard() {
    const qc = useQueryClient(), navigate = useAdminNavigate()
    const { data: accountSummary, isLoading: accountsLoading, isError: accountsError, isFetching: accountsFetching } = useQuery({
        queryKey: ["accountSummary"], queryFn: ({ signal }) => apiGet<{ accountCount: number; saveCount: number }>("/api/server/accounts/summary", { signal }),
    })
    const { data: status, isPending: statusLoading, isError: statusError, isFetching: statusFetching } = useQuery({
        queryKey: ["serverStatus"], queryFn: ({ signal }) => apiGet<ServerStatus>("/api/server/status", { signal }), refetchInterval: 30_000,
    })
    const { data: serverTime, isPending: timeLoading, isError: timeError } = useQuery({
        queryKey: ["serverTime"], queryFn: ({ signal }) => apiGet<{ date: string; isCustom: boolean }>("/api/server/currentTime", { signal }), refetchInterval: 30_000,
    })
    const refreshOverview = () => {
        void qc.invalidateQueries({ queryKey: ["accountSummary"] })
        void qc.invalidateQueries({ queryKey: ["serverStatus"] })
        void qc.invalidateQueries({ queryKey: ["serverTime"] })
    }
    return <AdminPage eyebrow="OPERATIONS" title="服务器总览" description="查看服务器运行情况，进入常用管理功能。"
        actions={<Button icon={<ReloadOutlined />} loading={accountsFetching || statusFetching} onClick={refreshOverview}>刷新总览</Button>}>
        <Space direction="vertical" size="large" className="admin-stack">
                <Card title="服务端状态" loading={statusLoading} extra={status && <Tag>资源版本 {status.cdn.baseline.cnFinalVersion}</Tag>}>
                    {statusError || !status ? (
                        <Alert type="error" showIcon message="服务端状态加载失败" description="接口 /api/server/status 不可用。" />
                    ) : (
                        <>
                            <Row gutter={[16, 16]}>
                                <Col xs={12} sm={5}>
                                    <Statistic title="当前在线" value={status.server.onlinePlayers} suffix="人" />
                                </Col>
                                <Col xs={12} sm={8}>
                                    <Statistic
                                        title="运行时间"
                                        value={formatDuration(status.server.uptimeSeconds)}
                                        valueStyle={{ whiteSpace: "nowrap" }}
                                    />
                                </Col>
                                <Col xs={12} sm={6}>
                                    <Statistic title="RSS 内存" value={formatBytes(status.server.memory.rss)} />
                                </Col>
                                <Col xs={12} sm={5}>
                                    <Statistic title="PID" value={status.server.pid} />
                                </Col>
                            </Row>
                            <Divider style={{ margin: "16px 0" }} />
                            <Descriptions size="small" column={1}>
                                    <Descriptions.Item label="服务器时间（北京时间）">{timeError ? "读取失败" : timeLoading ? "读取中" : formatBeijingTime(serverTime?.date)} {serverTime && <Tag color={serverTime.isCustom ? "orange" : "blue"}>{serverTime.isCustom ? "历史兼容时间" : "跟随真实时间"}</Tag>}</Descriptions.Item>
                                <Descriptions.Item label="Node">{status.server.nodeVersion}</Descriptions.Item>
                                <Descriptions.Item label="平台">{status.server.platform}</Descriptions.Item>
                                <Descriptions.Item label="监听">{status.server.listenHost}:{status.server.listenPort}</Descriptions.Item>
                            </Descriptions>
                        </>
                    )}
                </Card>

            <Card title="账号与存档" loading={accountsLoading}>
                {accountsError ? <Alert type="error" showIcon message="账号概况读取失败" action={<Button onClick={refreshOverview}>重试</Button>} /> : <Row gutter={[16,16]}>
                    <Col xs={12}><Statistic title="账号总数" value={accountSummary?.accountCount ?? "—"} /></Col>
                    <Col xs={12}><Statistic title="存档总数" value={accountSummary?.saveCount ?? "—"} /></Col>
                </Row>}
            </Card>
            <Card title="常用操作">
                <div className="admin-shortcuts">
                    <Button type="primary" size="large" onClick={() => navigate("/content")}>管理活动与卡池</Button>
                    <Button size="large" onClick={() => navigate("/accounts")}>账号 / 存档</Button>
                    <Button size="large" onClick={() => navigate("/news")}>管理公告</Button>
                    <Button size="large" onClick={() => navigate("/mail")}>发送邮件</Button>
                    <Button size="large" onClick={() => navigate("/leaderboards")}>排行榜</Button>
                    <Button size="large" onClick={() => navigate("/maintenance")}>存档与备份</Button>
                </div>
            </Card>
            <Collapse items={[{key:"resource-details",label:"资源与技术详情",children:(
                    <Card title="CDN 固定基线 / 扩展层" loading={statusLoading}>
                        {statusError || !status ? (
                            <Alert type="error" showIcon message="CDN 信息加载失败" />
                        ) : (
                            <Space direction="vertical" className="admin-stack">
                                <Alert
                                    type="info"
                                    showIcon
                                    message="当前版本策略：固定国服最终 CDN 基线"
                                    description={`道具、角色、活动、任务和商店等基础数据现在都以国服最终 CDN ${status.cdn.baseline.cnFinalVersion} 为唯一基线；后台展示不会改变底层版本逻辑。`}
                                />
                                <div className="admin-metric-row">
                                    <Statistic title="国服最终基线" value={status.cdn.baseline.cnFinalVersion} />
                                    <Statistic title="基础包版本" value={status.cdn.baseline.fullVersion} />
                                    <Statistic title="版本策略" value={status.cdn.baseline.pinned ? "固定" : "可变"} />
                                </div>
                                <Descriptions size="small" column={1}>
                                    <Descriptions.Item label="CDN 地址">{status.cdn.baseUrl}</Descriptions.Item>
                                    <Descriptions.Item label="数据来源">{status.cdn.baseline.source}</Descriptions.Item>
                                    <Descriptions.Item label="覆盖范围">
                                        <Space wrap>
                                            {status.cdn.baseline.dataScope.map(scope => (
                                                <Tag key={scope}>{cdnScopeLabels[scope] || scope}</Tag>
                                            ))}
                                        </Space>
                                    </Descriptions.Item>
                                    <Descriptions.Item label="归档检测版本">{status.cdn.baseline.detectedArchiveVersion}</Descriptions.Item>
                                    <Descriptions.Item label="目录">
                                        <Space wrap>
                                            <code>{status.cdn.storage.configuredDir}/cn</code>
                                            {status.cdn.storage.directoryPresent ? <Tag color="green">存在</Tag> : <Tag color="red">未找到</Tag>}
                                        </Space>
                                    </Descriptions.Item>
                                    <Descriptions.Item label="归档">
                                        {status.cdn.storage.archiveCount} 个 ZIP / {formatBytes(status.cdn.storage.archiveBytes)}
                                    </Descriptions.Item>
                                    <Descriptions.Item label="最新修改">
                                        {status.cdn.storage.latestArchiveMtime ? new Date(status.cdn.storage.latestArchiveMtime).toLocaleString("zh-CN") : "无"}
                                    </Descriptions.Item>
                                </Descriptions>
                                <Divider style={{ margin: "4px 0" }} />
                                <Space direction="vertical" size="small" className="admin-stack">
                                    <Typography.Text strong>自制角色 / 活动补丁版本层</Typography.Text>
                                    <Space wrap>
                                        <Tag color={status.cdn.extension.runtimeEnabled ? "orange" : "default"}>
                                            {status.cdn.extension.runtimeEnabled ? "资源扩展已启用" : "资源扩展未启用"}
                                        </Tag>
                                        <Tag>补丁 {status.cdn.extension.enabledPatchCount}/{status.cdn.extension.totalPatchCount}</Tag>
                                        <Tag>active {status.cdn.extension.activePatchArchiveCount}</Tag>
                                        <Tag>预览版本 {status.cdn.extension.effectiveVersionPreview}</Tag>
                                    </Space>
                                    <Alert
                                        type="warning"
                                        showIcon
                                        message="扩展层说明"
                                        description={status.cdn.extension.note}
                                    />
                                </Space>
                            </Space>
                        )}
                    </Card>
            )}]} />
        </Space>
    </AdminPage>
}
