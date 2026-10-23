import { useState } from "react"
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Tag } from "antd"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiGet, apiPatch, apiPost } from "../api/client"
import { AdminPage } from "../components/AdminPage"
import { useAdminEditGuard } from "../lib/editGuard"

interface Reward { type: number; type_id: number | null; number: number }
interface Gift { id: number; code: string; note: string; rewards: Reward[]; enabled: number; revision: number; redeemed_count: number }
interface Draft { code: string; note?: string; rewards: Reward[] }
const endpoint = "/api/server/gifts/"
const queryKey = ["server", "gifts"]
const labels: Record<number, string> = { 1: "物品", 4: "免费星导石", 5: "角色", 6: "装备", 8: "玛纳", 9: "经验池" }

export default function Gifts() {
    const [form] = Form.useForm<Draft>()
    const [dirty, setDirty] = useState(false)
    const [error, setError] = useState("")
    const client = useQueryClient()
    const query = useQuery({ queryKey, queryFn: () => apiGet<{ gifts: Gift[] }>(endpoint) })
    const create = useMutation({ mutationFn: (draft: Draft) => apiPost(endpoint, { ...draft, note: draft.note ?? "",
        rewards: draft.rewards.map(reward => ({ ...reward, type_id: [1, 5, 6].includes(reward.type) ? reward.type_id : null })) }),
        onSuccess: async () => { form.resetFields(); setDirty(false); setError(""); await client.invalidateQueries({ queryKey }) },
        onError: (failure: Error) => setError(failure.message) })
    const toggle = useMutation({ mutationFn: (gift: Gift) => apiPatch(endpoint + gift.id, { enabled: !gift.enabled, revision: gift.revision }),
        onSuccess: async () => { setError(""); await client.invalidateQueries({ queryKey }) },
        onError: async (failure: Error) => { setError(failure.message); await client.invalidateQueries({ queryKey }) } })
    const pending = create.isPending || toggle.isPending
    useAdminEditGuard({ dirty, pending, label: "礼包码" })
    return <AdminPage eyebrow="运营" title="礼包码" description="每个存档每个码只能领取一次。先创建停用的礼包码，核对奖励后启用。奖励内容与码名创建后不可修改；停用不会清除领取记录。">
        {(error || query.error) && <Alert type="error" showIcon message={error || query.error?.message} />}
        <Card title="创建礼包码" style={{ marginBottom: 24 }}>
            <Form form={form} layout="vertical" disabled={pending} initialValues={{ rewards: [{ type: 4, type_id: null, number: 1 }] }}
                onValuesChange={() => setDirty(true)} onFinish={draft => create.mutate(draft)}>
                <Space align="start" wrap>
                    <Form.Item name="code" label="兑换码（区分大小写）" rules={[{ required: true }, { max: 20 }, { pattern: /^\S+$/, message: "兑换码不能包含空白" }]}><Input maxLength={20} /></Form.Item>
                    <Form.Item name="note" label="管理备注"><Input maxLength={512} /></Form.Item>
                </Space>
                <Form.List name="rewards">{(fields, { add, remove }) => <>
                    {fields.map(field => <Space key={field.key} align="start" wrap>
                        <Form.Item name={[field.name, "type"]} label="奖励类型" rules={[{ required: true }]}><Select style={{ width: 150 }} options={Object.entries(labels).map(([value, label]) => ({ value: Number(value), label }))}
                            onChange={(type: number) => { form.setFieldValue(["rewards", field.name, "type_id"], null); if ([5, 6].includes(type)) form.setFieldValue(["rewards", field.name, "number"], 1) }} /></Form.Item>
                        <Form.Item shouldUpdate={(previous, current) => previous.rewards?.[field.name]?.type !== current.rewards?.[field.name]?.type} noStyle>
                            {() => [1, 5, 6].includes(form.getFieldValue(["rewards", field.name, "type"]))
                                ? <Form.Item name={[field.name, "type_id"]} label="物品 / 角色 / 装备 ID" rules={[{ required: true }]}><InputNumber min={1} precision={0} /></Form.Item> : null}
                        </Form.Item>
                        <Form.Item shouldUpdate={(previous, current) => previous.rewards?.[field.name]?.type !== current.rewards?.[field.name]?.type} noStyle>
                            {() => {
                                const single = [5, 6].includes(form.getFieldValue(["rewards", field.name, "type"]))
                                return <Form.Item name={[field.name, "number"]} label="数量" rules={[{ required: true },
                                    { type: "integer", min: 1, max: single ? 1 : 2147483647, message: single ? "角色或装备每项固定为一份" : "请输入有效的正整数" }]}>
                                    <InputNumber min={1} max={single ? 1 : 2147483647} precision={0} /></Form.Item>
                            }}
                        </Form.Item>
                        <Button onClick={() => { remove(field.name); setDirty(true) }} disabled={pending || fields.length === 1} style={{ marginTop: 30 }}>移除</Button>
                    </Space>)}
                    <div><Button onClick={() => { add({ type: 4, type_id: null, number: 1 }); setDirty(true) }} disabled={pending || fields.length >= 20}>添加奖励</Button></div>
                </>}</Form.List>
                <Button type="primary" htmlType="submit" loading={create.isPending} style={{ marginTop: 20 }}>创建并保持停用</Button>
            </Form>
        </Card>
        <Table<Gift> rowKey="id" dataSource={query.data?.gifts ?? []} loading={query.isFetching} scroll={{ x: 800 }} pagination={{ pageSize: 20 }} columns={[
            { title: "兑换码", dataIndex: "code" }, { title: "备注", dataIndex: "note" },
            { title: "奖励", render: (_, gift) => gift.rewards.map((reward, i) => <div key={i}>{labels[reward.type]}{reward.type_id !== null ? ` #${reward.type_id}` : ""} × {reward.number}</div>) },
            { title: "已领取存档", dataIndex: "redeemed_count" },
            { title: "状态", render: (_, gift) => <Tag color={gift.enabled ? "green" : "default"}>{gift.enabled ? "启用" : "停用"}</Tag> },
            { title: "操作", render: (_, gift) => <Button disabled={pending} onClick={() => toggle.mutate(gift)}>{gift.enabled ? "停用" : "启用"}</Button> },
        ]} />
    </AdminPage>
}
