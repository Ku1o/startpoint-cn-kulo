export function formatDuration(seconds: number): string {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (days > 0) return `${days}天${hours}小时`
    if (hours > 0) return `${hours}小时${minutes}分钟`
    return minutes > 0 ? `${minutes}分钟` : "刚启动"
}

export function formatBytes(bytes: number): string {
    if (!bytes) return "0 B"
    const units = ["B", "KB", "MB", "GB", "TB"]
    let value = bytes, unit = 0
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++ }
    return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`
}

export function formatBeijingTime(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === "") return "暂无记录"
    const date = new Date(value)
    if (!Number.isFinite(date.getTime())) return "时间不可用"
    return date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })
}
