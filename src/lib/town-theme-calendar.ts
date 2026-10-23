import { townThemeRecord, type TownThemeCatalog } from "./town-theme-catalog"

export interface TownAnnualSchedule { themeId: string; start: string; end: string }
export interface StoredTownAnnualSchedule extends TownAnnualSchedule { themeDigest: string }
export interface TownAnnualWarning { themeId: string; message: string }
export class TownThemeCalendarError extends Error {}
const FIRST = "01-01 00:00:00", LAST = "12-31 23:59:59"
const DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
const KEY = /^[a-z][a-z0-9_]{0,63}$/
/** Configured boundaries use a non-leap calendar. Actual leap days keep their natural month/day order. */
export function validAnnualDate(value: unknown): value is string {
    if (typeof value !== "string") return false
    const match = /^(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(value)
    if (!match) return false
    const [month, day, hour, minute, second] = match.slice(1).map(Number)
    return month >= 1 && month <= 12 && day >= 1 && day <= DAYS[month - 1] && hour <= 23 && minute <= 59 && second <= 59
}
function validShape(value: unknown, stored: boolean): value is TownAnnualSchedule | StoredTownAnnualSchedule {
    return townThemeRecord(value) && Object.keys(value).length === (stored ? 4 : 3)
        && typeof value.themeId === "string" && KEY.test(value.themeId) && validAnnualDate(value.start) && validAnnualDate(value.end)
        && (!stored || typeof value.themeDigest === "string" && /^[a-f0-9]{64}$/.test(value.themeDigest))
}
function segments(row: TownAnnualSchedule): string[][] {
    return row.start <= row.end ? [[row.start, row.end]] : [[row.start, LAST], [FIRST, row.end]]
}
function relationError(rows: readonly TownAnnualSchedule[], name: (id: string) => string): string | null {
    for (let index = 0; index < rows.length; index++) for (let other = 0; other < index; other++) {
        const left = rows[other], right = rows[index]
        if (left.themeId === right.themeId) return `“${name(right.themeId)}”每年只能设置一个日期段。`
        if (segments(left).some(a => segments(right).some(b => a[0] <= b[1] && b[0] <= a[1])))
            return `“${name(left.themeId)}”与“${name(right.themeId)}”的年度日期段重叠；起止两端均包含，请调整日期。`
    }
    return null
}
export function validStoredAnnualSchedules(value: unknown): value is StoredTownAnnualSchedule[] {
    return Array.isArray(value) && value.length <= 100 && value.every(row => validShape(row, true)) && !relationError(value, id => id)
}
export function bindAnnualSchedules(value: unknown, catalog: TownThemeCatalog): StoredTownAnnualSchedule[] {
    if (!Array.isArray(value) || value.length > 100 || value.some(row => !validShape(row, false)))
        throw new TownThemeCalendarError("年度日期设置无效；最多100个日期段，格式为MM-DD HH:mm:ss，边界不能使用02-29。")
    const rows = value as TownAnnualSchedule[]
    const name = (id: string) => catalog.find(id)?.name ?? "已失效主题"
    for (const row of rows) {
        const theme = catalog.find(row.themeId)
        if (!theme || !catalog.themeDigest(row.themeId)) throw new TownThemeCalendarError(`“${name(row.themeId)}”未登记或资源尚未核验，不能设置年度日期。`)
        if (theme.nativeRow[1] === "0") throw new TownThemeCalendarError(`“${theme.name}”是默认主城，不需要设置年度日期。`)
    }
    const conflict = relationError(rows, name)
    if (conflict) throw new TownThemeCalendarError(conflict)
    return rows.map(row => ({ themeId: row.themeId, start: row.start, end: row.end, themeDigest: catalog.themeDigest(row.themeId)! }))
        .sort((a, b) => a.themeId < b.themeId ? -1 : a.themeId > b.themeId ? 1 : 0)
}
/** Real UTC milliseconds only. No serverOffset, business clock or process timezone. Milliseconds are discarded. */
export function beijingAnnualTime(nowMs: number): string {
    if (!Number.isSafeInteger(nowMs) || nowMs < 0 || nowMs > 8640000000000000 - 28800000) throw new TownThemeCalendarError("年度日期核对时间无效。")
    const date = new Date(nowMs + 28800000), pad = (n: number) => String(n).padStart(2, "0")
    return `${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`
}
export function resolveAnnualSchedules(rows: readonly StoredTownAnnualSchedule[], catalog: TownThemeCatalog, nowMs: number): {
    activeThemeId: string | null; warnings: TownAnnualWarning[]
} {
    const current = beijingAnnualTime(nowMs), warnings: TownAnnualWarning[] = []
    let activeThemeId: string | null = null
    for (const row of rows) {
        const theme = catalog.find(row.themeId)
        if (!theme || theme.nativeRow[1] === "0" || catalog.themeDigest(row.themeId) !== row.themeDigest) {
            warnings.push({ themeId: row.themeId, message: `“${theme?.name ?? "已失效主题"}”的主题定义或资源已变化或不可用，已跳过该年度日期段；请重新确认或移除。` })
        } else if (segments(row).some(([start, end]) => start <= current && current <= end)) activeThemeId = row.themeId
    }
    return { activeThemeId, warnings }
}
