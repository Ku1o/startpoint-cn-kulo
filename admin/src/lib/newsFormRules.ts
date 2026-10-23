export const NEWS_ID_MAX = 2_147_483_647
export function isNewsId(value: unknown): value is number {
    return typeof value === "number" && Number.isSafeInteger(value) && value >= 1 && value <= NEWS_ID_MAX
}

/** Preserve raw input until validation. Only an empty field requests an auto ID. */
export function parseNewsIdInput(value: unknown): number | null {
    if (value == null || value === "") return null
    const parsed = typeof value === "string" && /^\d+$/.test(value) ? Number(value) : value
    if (!isNewsId(parsed)) throw new Error(`请输入1至${NEWS_ID_MAX}的整数编号`)
    return parsed
}
