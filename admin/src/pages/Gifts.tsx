import { useMemo, useState } from "react"
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Tag, Typography } from "antd"
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiGet, apiPatch, apiPost } from "../api/client"
import { useLookup } from "../api/lookups"
import { AdminPage } from "../components/AdminPage"
import { useAdminEditGuard } from "../lib/editGuard"
import "./Gifts.css"

interface Reward { type: number; type_id: number | null; number: number }
interface Gift { id: number; code: string; note: string; rewards: Reward[]; enabled: number; revision: number; redeemed_count: number }
interface Draft { code: string; note?: string; rewards: Reward[] }
interface GiftOverview { gifts: Gift[]; rewardIds: Record<1 | 5 | 6, number[]> }
const endpoint = "/api/server/gifts/"
const queryKey = ["server", "gifts"]
const labels: Record<number, string> = { 1: "物品", 4: "免费星导石", 5: "角色", 6: "装备", 8: "玛纳", 9: "经验池" }
const newReward = (): Reward => ({ type: 4, type_id: null, number: 1 })
const needsId = (type: number) => [1, 5, 6].includes(type)
const codeAlphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

function generateCode(existing: Set<string>): string {
    // 32 symbols, 16 uniformly random characters; the server still checks uniqueness.
    for (let attempt = 0; attempt < 8; attempt++) {
        const code = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => codeAlphabet[byte & 31]).join("")
        if (!existing.has(code)) return code
    }
    throw new Error("暂时无法生成新码，请再试一次或手动输入。")
}

export default function Gifts() {
    const [form] = Form.useForm<Draft>()
    const [dirty, setDirty] = useState(false)
    const [error, setError] = useState("")
    const [createdCode, setCreatedCode] = useState("")
    const draftCode = Form.useWatch("code", form) as string | undefined
    const draftRewards = Form.useWatch("rewards", form) as Reward[] | undefined
    const client = useQueryClient()
    const query = useQuery({ queryKey, queryFn: () => apiGet<GiftOverview>(endpoint) })
    const rewardTypes = new Set([...(draftRewards ?? []), ...(query.data?.gifts.flatMap(gift => gift.rewards) ?? [])].map(reward => reward.type))
    const items = useLookup("items", rewardTypes.has(1))
    const characters = useLookup("characters", rewardTypes.has(5))
    const equipment = useLookup("equipment", rewardTypes.has(6))
    const lookupOptions = useMemo(() => ({
        1: Object.entries(items.data ?? {}).map(([id, name]) => ({ value: Number(id), label: `${name} #${id}` })),
        5: Object.entries(characters.data ?? {}).map(([id, row]) => ({ value: Number(id), label: `${row.name}${row.title ? ` · ${row.title}` : ""} #${id}` })),
        6: Object.entries(equipment.data ?? {}).map(([id, row]) => ({ value: Number(id), label: `${row.name} #${id}` })),
    }), [items.data, characters.data, equipment.data])
    const choices = useMemo(() => {
        const allowed = query.data?.rewardIds
        const filter = (type: 1 | 5 | 6) => {
            const ids = new Set(allowed?.[type] ?? [])
            return lookupOptions[type].filter(option => ids.has(option.value))
        }
        return { 1: filter(1), 5: filter(5), 6: filter(6) }
    }, [lookupOptions, query.data?.rewardIds])
    const rewardNames = useMemo(() => Object.fromEntries(Object.entries(lookupOptions).map(([type, options]) =>
        [type, new Map(options.map(option => [option.value, option.label]))])), [lookupOptions])
    const rewardTitle = (reward: Reward) => needsId(reward.type)
        ? reward.type_id == null ? `尚未选择${labels[reward.type]}` : rewardNames[reward.type]?.get(reward.type_id) ?? `${labels[reward.type]} #${reward.type_id}`
        : labels[reward.type]
    const create = useMutation({ mutationFn: (draft: Draft) => apiPost(endpoint, { ...draft, note: draft.note ?? "",
        rewards: draft.rewards.map(reward => ({ ...reward, type_id: needsId(reward.type) ? reward.type_id : null })) }),
        onSuccess: async (_, draft) => { setCreatedCode(draft.code); form.resetFields(); setDirty(false); setError(""); await client.invalidateQueries({ queryKey }) },
        onError: (failure: Error) => setError(failure.message) })
    const toggle = useMutation({ mutationFn: (gift: Gift) => apiPatch(endpoint + gift.id, { enabled: !gift.enabled, revision: gift.revision }),
        onSuccess: async () => { setError(""); await client.invalidateQueries({ queryKey }) },
        onError: async (failure: Error) => { setError(failure.message); await client.invalidateQueries({ queryKey }) } })
    const pending = create.isPending || toggle.isPending
    useAdminEditGuard({ dirty, pending, label: "礼包码" })
    const generate = () => {
        try {
            const existing = new Set([...(query.data?.gifts.map(gift => gift.code) ?? []), draftCode ?? ""])
            form.setFieldValue("code", generateCode(existing))
            setDirty(true)
            setError("")
        } catch (failure) { setError((failure as Error).message) }
    }
    return <AdminPage eyebrow="运营" title="礼包码" description="一个兑换码可以包含多项奖励，玩家输入一次即可全部领取。每个存档每个码只能领取一次。">
        {(error || query.error) && <Alert type="error" showIcon message={error || query.error?.message} />}
        {createdCode && <Alert type="success" showIcon style={{ marginBottom: 16 }} message={<span>已创建 <Typography.Text copyable>{createdCode}</Typography.Text>。请在下方核对奖励与启用状态，再发给玩家。</span>} />}
        <Card title="创建礼包码" style={{ marginBottom: 24 }}>
            <Form form={form} layout="vertical" disabled={pending} initialValues={{ rewards: [newReward()] }}
                onValuesChange={() => setDirty(true)} onFinish={draft => create.mutate(draft)}>
                <div className="gift-basics">
                    <div>
                        <Form.Item label="兑换码（区分大小写）" required extra="可一键生成，也可自定义；最多 20 位，不能包含空白。">
                            <div className="gift-code-input">
                                <Form.Item name="code" noStyle rules={[{ required: true, message: "请生成或填写兑换码" }, { max: 20 }, { pattern: /^[^\s\x00-\x1f\x7f]+$/, message: "兑换码不能包含空白或控制字符" }]}>
                                    <Input aria-label="兑换码" maxLength={20} placeholder="例如 WELCOME2026" />
                                </Form.Item>
                                <Button icon={<ReloadOutlined />} onClick={generate}>{draftCode ? "重新生成" : "一键生成"}</Button>
                            </div>
                        </Form.Item>
                    </div>
                    <Form.Item name="note" label="管理备注" extra="仅供后台识别，不展示给玩家。"><Input maxLength={512} placeholder="例如：周末福利、开服礼包" /></Form.Item>
                </div>
                <Form.List name="rewards">{(fields, { add, remove }) => <>
                    <div className="gift-rewards-header"><Typography.Title level={5} style={{ margin: 0 }}>礼包内的奖励 <Tag>{fields.length} / 20 项</Tag></Typography.Title>
                        <Typography.Text type="secondary">每项可单独选择类型和数量，所有奖励随同一个码一起发放。</Typography.Text></div>
                    {fields.map((field, index) => <Card key={field.key} size="small" className="gift-reward-card" title={`奖励 ${index + 1}`}
                        extra={<Button size="small" aria-label={`移除奖励 ${index + 1}`} onClick={() => { remove(field.name); setDirty(true) }} disabled={pending || fields.length === 1}>移除</Button>}>
                        <div className="gift-reward-fields">
                        <Form.Item name={[field.name, "type"]} label="奖励类型" rules={[{ required: true }]}><Select options={Object.entries(labels).map(([value, label]) => ({ value: Number(value), label }))}
                            onChange={(type: number) => { form.setFieldValue(["rewards", field.name, "type_id"], null); if ([5, 6].includes(type)) form.setFieldValue(["rewards", field.name, "number"], 1) }} /></Form.Item>
                        <Form.Item shouldUpdate={(previous, current) => previous.rewards?.[field.name]?.type !== current.rewards?.[field.name]?.type} noStyle>
                            {() => {
                                const type = form.getFieldValue(["rewards", field.name, "type"]) as number
                                if (!needsId(type)) return <div className="gift-no-id"><Typography.Text type="secondary">{labels[type]}无需选择物品，填写数量即可。</Typography.Text></div>
                                const lookup = type === 1 ? items : type === 5 ? characters : equipment
                                return <div><Form.Item name={[field.name, "type_id"]} label={`选择${labels[type]}`} rules={[{ required: true, message: `请选择${labels[type]}` }]}>
                                    <Select showSearch allowClear placeholder={`搜索${labels[type]}名称或编号`} loading={lookup.isFetching}
                                        options={choices[type as keyof typeof choices]} optionFilterProp="label"
                                        notFoundContent={lookup.isFetching ? "正在加载…" : lookup.isError ? "加载失败，请重试" : "没有匹配的奖励"} />
                                </Form.Item>{lookup.isError && <Alert type="error" showIcon message="奖励列表加载失败" action={<Button size="small" onClick={() => void lookup.refetch()}>重试</Button>} />}</div>
                            }}
                        </Form.Item>
                        <Form.Item shouldUpdate={(previous, current) => previous.rewards?.[field.name]?.type !== current.rewards?.[field.name]?.type} noStyle>
                            {() => {
                                const single = [5, 6].includes(form.getFieldValue(["rewards", field.name, "type"]))
                                return <Form.Item name={[field.name, "number"]} label="数量" rules={[{ required: true },
                                    { type: "integer", min: 1, max: single ? 1 : 2147483647, message: single ? "角色或装备每项固定为一份" : "请输入有效的正整数" }]}>
                                    <InputNumber min={1} max={single ? 1 : 2147483647} precision={0} style={{ width: "100%" }} /></Form.Item>
                            }}
                        </Form.Item>
                        </div>
                    </Card>)}
                    <Button type="dashed" block icon={<PlusOutlined />} onClick={() => { add(newReward()); setDirty(true) }} disabled={pending || fields.length >= 20}>添加一项奖励</Button>
                </>}</Form.List>
                <div className="gift-preview" aria-label="礼包内容预览">
                    <Typography.Text strong>玩家将一次领到</Typography.Text>
                    <ul>{(draftRewards ?? [newReward()]).map((reward, index) => <li key={index}>{rewardTitle(reward)} × {reward.number ?? "待填数量"}</li>)}</ul>
                    <Typography.Text type="secondary">创建后码名和奖励不能修改。先保存为停用，核对后再启用；停用不会清除领取记录。</Typography.Text>
                </div>
                <Button type="primary" htmlType="submit" loading={create.isPending} style={{ marginTop: 20 }}>创建并保持停用</Button>
            </Form>
        </Card>
        <Typography.Title level={4}>已创建的礼包码</Typography.Title>
        <Table<Gift> rowKey="id" dataSource={query.data?.gifts ?? []} loading={query.isFetching} scroll={{ x: 850 }} pagination={{ pageSize: 20 }} columns={[
            { title: "兑换码", dataIndex: "code", render: code => <Typography.Text copyable>{code}</Typography.Text> }, { title: "备注", dataIndex: "note" },
            { title: "礼包奖励", render: (_, gift) => <Space direction="vertical" size={2}>{gift.rewards.map((reward, i) => <span key={i}>{rewardTitle(reward)} × {reward.number}</span>)}</Space> },
            { title: "已领取存档", dataIndex: "redeemed_count" },
            { title: "状态", render: (_, gift) => <Tag color={gift.enabled ? "green" : "default"}>{gift.enabled ? "启用" : "停用"}</Tag> },
            { title: "操作", render: (_, gift) => <Button disabled={pending} onClick={() => toggle.mutate(gift)}>{gift.enabled ? "停用" : "启用"}</Button> },
        ]} />
    </AdminPage>
}
