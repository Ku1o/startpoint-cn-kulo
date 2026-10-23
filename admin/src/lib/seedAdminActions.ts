export type SeedMode = "natural" | "play" | "test"
export type SeedTag = "未测试" | "热血躲避球" | "普通躲避球" | "冷血躲避球"
export type SeedAdminAction = { kind: "mode"; mode: SeedMode }
    | { kind: "tag"; seed: number; tag: SeedTag; movie: string }
    | { kind: "set-test"; seed: number; rarity: number }
    | { kind: "clear-test"; rarity: number }

/** A 200 response can still be an explicit failure on older admin APIs. */
export function assertSeedActionSucceeded(value: unknown, action: SeedAdminAction): void {
    const result = value && typeof value === "object" ? value as { ok?: boolean; error?: string; mode?: string } : null
    if (!result || result.ok === false || (action.kind === "mode" ? result.mode !== action.mode : result.ok !== true)) {
        throw new Error(result?.error || "操作未确认成功，请刷新状态后重试。")
    }
}

export function formatCatalogCoverage(known: number, total: number): string {
    if (!Number.isSafeInteger(known) || !Number.isSafeInteger(total) || known < 0 || known > total) return "不可用"
    if (total <= 0) return "暂无"
    if (known === 0) return "0%"
    if (known === total) return "100%"
    const percentage = known / total * 100
    if (percentage < 0.01) return "<0.01%"
    if (percentage > 99.99) return ">99.99%"
    return `${percentage.toFixed(2).replace(/\.?0+$/, "")}%`
}
