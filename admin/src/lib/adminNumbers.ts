// These are the existing server validation boundaries, not gameplay balance caps.
export const ADMIN_INT_MAX = 2147483647
export const PLAYER_TIME_OFFSET_MAX = 31_536_000_000_000

export function integerError(value: unknown, label: string, min: number, max: number, nullable = false): string | null {
    if (value === null || value === undefined || value === "") return nullable ? null : `请输入${label}`
    if (typeof value !== "number" || !Number.isSafeInteger(value)) return `${label}必须是整数`
    if (value < min || value > max) return `${label}需在 ${min}～${max} 之间`
    return null
}

const playerIntegerFields = new Set(["expPool", "freeVmoney", "vmoney", "freeMana", "paidMana", "stamina", "rankPoint", "starCrumb", "bondToken", "bossBoostPoint", "boostPoint", "degreeId", "leaderCharacterId", "birth", "tutorialStep"])
export function playerNumberError(field: string, value: unknown): string | null {
    if (field === "timeOffset") return integerError(value, "时间偏移", -PLAYER_TIME_OFFSET_MAX, PLAYER_TIME_OFFSET_MAX, true)
    return playerIntegerFields.has(field) ? integerError(value, "字段值", 0, ADMIN_INT_MAX, field === "tutorialStep") : null
}
