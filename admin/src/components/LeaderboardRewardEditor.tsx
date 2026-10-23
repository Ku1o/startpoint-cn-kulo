import { useMemo, useState } from "react"
import { Alert, Button, Collapse, Input, InputNumber, Popconfirm, Select, Space, Table, Typography } from "antd"
import { useLookup } from "../api/lookups"

interface Prize {
    itemId: number | null; itemName: string | null; itemCount: number
    degreeId: number | null; degreeName: string | null; degreeImage: string | null
}
export type EditableRewardTier = Prize & ({ fromRank: number; toRank: number | null } | { fromPercent: number; toPercent: number })
const isPercent = (row: EditableRewardTier): row is Prize & { fromPercent: number; toPercent: number } => "fromPercent" in row

/** Match the existing settlement contract before sending; server validation remains authoritative. */
export function rewardDraftError(value: string): string | null {
    let rows: EditableRewardTier[]
    try { rows = JSON.parse(value) } catch { return "高级配置格式有误，请修正后再保存。" }
    if (!Array.isArray(rows)) return "奖励配置必须是一组档位。"
    const percentage = rows.length > 0 && rows[0] !== null && typeof rows[0] === "object" && isPercent(rows[0])
    let next = percentage ? 0 : 1
    for (const [index, row] of rows.entries()) {
        const prefix = `第 ${index + 1} 档：`
        if (!row || typeof row !== "object") return prefix + "奖励格式有误。"
        if (isPercent(row) !== percentage) return "同一配置请统一使用百分比或固定名次。"
        if (isPercent(row)) {
            if ("fromRank" in row || "toRank" in row || !Number.isSafeInteger(row.fromPercent) || row.fromPercent !== next
                || !Number.isSafeInteger(row.toPercent) || row.toPercent <= row.fromPercent || row.toPercent > 100) {
                return prefix + "百分比须为整数，并从 0 连续排列到 100。"
            }
            next = row.toPercent
        } else {
            if ("toPercent" in row || !Number.isSafeInteger(row.fromRank) || row.fromRank !== next
                || row.toRank !== null && (!Number.isSafeInteger(row.toRank) || row.toRank < row.fromRank)
                || row.toRank === null && index !== rows.length - 1) return prefix + "名次须从第 1 名连续排列，“末位”仅用于最后一档。"
            next = row.toRank === null ? 0 : row.toRank + 1
        }
        if (row.itemId !== null && (!Number.isSafeInteger(row.itemId) || row.itemId <= 0)) return prefix + "请选择有效道具。"
        if (!Number.isSafeInteger(row.itemCount) || row.itemCount < 0 || row.itemId === null && row.itemCount !== 0
            || row.itemId !== null && (row.itemCount < 1 || typeof row.itemName !== "string" || !row.itemName.trim())) return prefix + "道具数量须为正整数；未设置道具时数量须为 0。"
        if (row.degreeId !== null && (!Number.isSafeInteger(row.degreeId) || row.degreeId <= 0 || typeof row.degreeName !== "string" || !row.degreeName.trim())) return prefix + "请选择有效称号。"
        if (row.itemId === null && row.degreeId === null) return prefix + "至少设置一项道具或称号奖励。"
    }
    return percentage && next !== 100 ? "百分比档位须连续覆盖到 100%。" : null
}

export function LeaderboardRewardEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
    const items = useLookup("items"), degrees = useLookup("degrees")
    const [emptyMode, setEmptyMode] = useState<"percent" | "rank">("percent")
    const rows = useMemo(() => {
        try { const parsed = JSON.parse(value); return Array.isArray(parsed) && parsed.every(row => row && typeof row === "object") ? parsed as EditableRewardTier[] : null }
        catch { return null }
    }, [value])
    const error = rewardDraftError(value)
    const mode = rows?.length ? isPercent(rows[0]) ? "percent" : "rank" : emptyMode
    const commit = (next: EditableRewardTier[]) => onChange(JSON.stringify(next, null, 2))
    const update = (index: number, changes: Partial<EditableRewardTier>) => {
        if (rows) commit(rows.map((row, i) => i === index ? { ...row, ...changes } as EditableRewardTier : row))
    }
    const itemOptions = useMemo(() => {
        const entries = new Map(Object.entries(items.data ?? {}).map(([id, name]) => [Number(id), name]))
        rows?.forEach(row => { if (row.itemId !== null && !entries.has(row.itemId)) entries.set(row.itemId, row.itemName || "现有道具") })
        return [...entries].map(([id, name]) => ({ value: id, label: name }))
    }, [items.data, rows])
    const degreeOptions = useMemo(() => {
        const entries = new Map(Object.entries(degrees.data ?? {}).map(([id, degree]) => [Number(id), degree.name]))
        rows?.forEach(row => { if (row.degreeId !== null && !entries.has(row.degreeId)) entries.set(row.degreeId, row.degreeName || "现有称号") })
        return [...entries].map(([id, name]) => ({ value: id, label: name }))
    }, [degrees.data, rows])
    const add = () => {
        if (!rows) return
        const last = rows[rows.length - 1], prize: Prize = { itemId: null, itemName: null, itemCount: 0, degreeId: null, degreeName: null, degreeImage: null }
        if (mode === "percent") {
            if (last && isPercent(last) && last.toPercent === 100) {
                let index = rows.length - 1
                while (index >= 0) {
                    const candidate = rows[index]
                    if (isPercent(candidate) && candidate.toPercent - candidate.fromPercent > 1) {
                        const boundary = candidate.toPercent - 1
                        commit([...rows.slice(0, index), { ...candidate, toPercent: boundary },
                            { ...prize, fromPercent: boundary, toPercent: candidate.toPercent }, ...rows.slice(index + 1)])
                        return
                    }
                    index--
                }
                return
            }
            const from = last && isPercent(last) ? last.toPercent : 0
            commit([...rows, { ...prize, fromPercent: from, toPercent: 100 }])
        } else {
            const from = last && !isPercent(last) ? (last.toRank ?? last.fromRank) + 1 : 1
            const adjusted = rows.map((row, index) => index === rows.length - 1 && !isPercent(row) && row.toRank === null ? { ...row, toRank: row.fromRank } : row)
            commit([...adjusted, { ...prize, fromRank: from, toRank: null }])
        }
    }
    const filter = (input: string, option?: { label: string; value: number }) => `${option?.label ?? ""} ${option?.value ?? ""}`.normalize("NFKC").toLowerCase().includes(input.normalize("NFKC").toLowerCase())
    return <Space direction="vertical" className="admin-stack">
        <Space wrap>
            <Typography.Text strong>奖励档位草稿</Typography.Text>
            <Select aria-label="奖励范围类型" value={mode} style={{ minWidth: 140 }} disabled={!!rows?.length}
                options={[{ value: "percent", label: "按百分比" }, { value: "rank", label: "按固定名次" }]} onChange={setEmptyMode} />
            <Button onClick={add} disabled={!rows || mode === "percent" && rows.length >= 100}>添加档位</Button>
            {!!rows?.length && <Popconfirm title="清空奖励档位？" description="只修改当前草稿，保存后才生效。可清空后改用另一种范围。" onConfirm={() => commit([])}><Button danger>清空档位</Button></Popconfirm>}
        </Space>
        <Typography.Text type="secondary">先选范围，再选择道具、数量或称号。百分比从 0 连续到 100；固定名次从第 1 名连续排列。道具与称号可同时发放。名称支持搜索名称或 ID，窄屏可横向滑动编辑表格。</Typography.Text>
        {(items.isError || degrees.isError) && <Alert type="warning" showIcon message="奖励名称资料读取失败，已有配置仍保留"
            action={<Button onClick={() => { items.refetch(); degrees.refetch() }}>重试名称资料</Button>} />}
        {error && <Alert type="warning" showIcon message={error} />}
        {rows && <div style={{ maxWidth: "100%", minWidth: 0 }}><Table<EditableRewardTier>
            rowKey={(_row, index) => String(index)} size="small" pagination={false} scroll={{ x: 1140 }} dataSource={rows}
            locale={{ emptyText: "尚未设置奖励。选择范围类型后，点击“添加档位”。" }}
            columns={[
                { title: "档位", width: 120, render: (_, row, index) => <Space direction="vertical" size={0}><Typography.Text strong>第 {index + 1} 档</Typography.Text><Typography.Text type="secondary">{isPercent(row) ? `${row.fromPercent}%–${row.toPercent}%` : `第 ${row.fromRank}–${row.toRank ?? "末位"} 名`}</Typography.Text></Space> },
                { title: "范围起点", width: 130, render: (_, row, index) => <InputNumber aria-label={`第${index + 1}档起点`} style={{ width: 108 }} min={isPercent(row) ? 0 : 1} max={isPercent(row) ? 99 : Number.MAX_SAFE_INTEGER} precision={0}
                    value={isPercent(row) ? row.fromPercent : row.fromRank} onChange={number => update(index, isPercent(row) ? { fromPercent: number ?? 0 } : { fromRank: number ?? 1 })} /> },
                { title: mode === "percent" ? "截止百分比" : "截止名次（留空为末位）", width: 165, render: (_, row, index) => <InputNumber aria-label={`第${index + 1}档终点`} style={{ width: 140 }} min={isPercent(row) ? 1 : 1} max={isPercent(row) ? 100 : Number.MAX_SAFE_INTEGER} precision={0} placeholder={isPercent(row) ? "百分比" : "末位"}
                    value={isPercent(row) ? row.toPercent : row.toRank} onChange={number => update(index, isPercent(row) ? { toPercent: number ?? 0 } : { toRank: number })} /> },
                { title: "道具奖励", width: 245, render: (_, row, index) => <Select aria-label={`第${index + 1}档道具`} allowClear showSearch style={{ width: "100%" }} loading={items.isLoading} disabled={!items.data || items.isError} value={row.itemId} placeholder="不发道具" options={itemOptions} filterOption={filter}
                    onChange={(id: number | undefined) => update(index, { itemId: id ?? null, itemName: id === undefined ? null : items.data?.[id] ?? row.itemName, itemCount: id === undefined ? 0 : row.itemCount || 1 })} /> },
                { title: "数量", width: 130, render: (_, row, index) => <InputNumber aria-label={`第${index + 1}档数量`} style={{ width: 108 }} disabled={row.itemId === null} min={row.itemId === null ? 0 : 1} max={Number.MAX_SAFE_INTEGER} precision={0} value={row.itemCount} onChange={number => update(index, { itemCount: number ?? 0 })} /> },
                { title: "称号奖励", width: 245, render: (_, row, index) => <Select aria-label={`第${index + 1}档称号`} allowClear showSearch style={{ width: "100%" }} loading={degrees.isLoading} disabled={!degrees.data || degrees.isError} value={row.degreeId} placeholder="不发称号" options={degreeOptions} filterOption={filter}
                    onChange={(id: number | undefined) => update(index, { degreeId: id ?? null, degreeName: id === undefined ? null : degrees.data?.[id]?.name ?? row.degreeName, degreeImage: id === undefined ? null : degrees.data?.[id]?.image ?? row.degreeImage })} /> },
                { title: "操作", width: 90, render: (_, _row, index) => <Button danger size="small" onClick={() => commit(rows.filter((_entry, i) => i !== index))}>移除此档</Button> },
            ]}
        /></div>}
        <Collapse items={[{ key: "advanced", label: "高级配置（JSON，与上方表格共用草稿）", children: <Input.TextArea aria-label="奖励高级配置" rows={10} value={value} onChange={event => onChange(event.target.value)} style={{ fontFamily: "monospace" }} /> }]} />
    </Space>
}
