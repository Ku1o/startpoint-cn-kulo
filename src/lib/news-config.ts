import {
    existsSync,
    readFileSync,
    renameSync,
    unlinkSync,
    writeFileSync,
} from "fs"
import path from "path"

export const NEWS_CATEGORY_LABELS = {
    1: "最新资讯",
    2: "活动信息",
    3: "问题修复",
    4: "系统公告",
} as const

export type NewsCategory = keyof typeof NEWS_CATEGORY_LABELS
export type NewsPopupMode = "every_login" | "once_per_news"

export interface NewsItem {
    id: number
    title: string
    date: string
    category: NewsCategory
    label: number
    thumbnail: number
    thumbnail_path: string | null
    added_time: string | null
    html: string
    published: boolean
}

export interface NewsPopupConfig {
    enabled: boolean
    news_id: number | null
    mode: NewsPopupMode
    start_time: string | null
    end_time: string | null
}

export interface NewsConfig {
    version: 1
    popup: NewsPopupConfig
    news: NewsItem[]
}

export interface NewsConfigState {
    config: NewsConfig
    error: string | null
    path: string
}

const DEFAULT_POPUP: NewsPopupConfig = {
    enabled: false,
    news_id: null,
    mode: "once_per_news",
    start_time: null,
    end_time: null,
}

const DEFAULT_CONFIG: NewsConfig = {
    version: 1,
    popup: { ...DEFAULT_POPUP },
    news: [],
}

let lastGoodConfig: NewsConfig | null = null
let lastReportedError: string | null = null

export function getNewsConfigPath(): string {
    const configured = process.env.NEWS_CONFIG_PATH?.trim()
    return configured
        ? path.resolve(configured)
        : path.resolve(__dirname, "..", "..", "assets", "news.json")
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value)
}

function requiredString(value: unknown, field: string, maxLength: number): string {
    if (typeof value !== "string") throw new Error(`${field} 必须是字符串`)
    const normalized = value.trim()
    if (!normalized) throw new Error(`${field} 不能为空`)
    if (normalized.length > maxLength) throw new Error(`${field} 最多 ${maxLength} 个字符`)
    return normalized
}

function optionalString(value: unknown, field: string, maxLength: number): string | null {
    if (value === null || value === undefined || value === "") return null
    if (typeof value !== "string") throw new Error(`${field} 必须是字符串或 null`)
    const normalized = value.trim()
    if (normalized.length > maxLength) throw new Error(`${field} 最多 ${maxLength} 个字符`)
    return normalized || null
}

function integerInRange(
    value: unknown,
    field: string,
    minimum: number,
    maximum: number,
): number {
    if (!Number.isSafeInteger(value) || Number(value) < minimum || Number(value) > maximum) {
        throw new Error(`${field} 必须是 ${minimum}–${maximum} 的整数`)
    }
    return Number(value)
}

export function parseNewsDate(value: string): Date | null {
    const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(value)
    if (!match) return null
    const [, year, month, day, hour, minute, second] = match.map(Number)
    const parsed = new Date(year, month - 1, day, hour, minute, second, 0)
    if (
        parsed.getFullYear() !== year
        || parsed.getMonth() !== month - 1
        || parsed.getDate() !== day
        || parsed.getHours() !== hour
        || parsed.getMinutes() !== minute
        || parsed.getSeconds() !== second
    ) return null
    return parsed
}

function requiredDateString(value: unknown, field: string): string {
    const normalized = requiredString(value, field, 19)
    if (parseNewsDate(normalized) === null) {
        throw new Error(`${field} 必须使用 YYYY-MM-DD HH:mm:ss 格式`)
    }
    return normalized
}

function optionalDateString(value: unknown, field: string): string | null {
    const normalized = optionalString(value, field, 19)
    if (normalized !== null && parseNewsDate(normalized) === null) {
        throw new Error(`${field} 必须使用 YYYY-MM-DD HH:mm:ss 格式`)
    }
    return normalized
}

function normalizeNewsItem(value: unknown, index: number): NewsItem {
    if (!isRecord(value)) throw new Error(`news[${index}] 必须是对象`)
    // These values are enums in the shipped CN client, not arbitrary asset
    // IDs. Keeping the server-side range aligned with the client prevents a
    // malformed announcement from reaching a switch with no matching case.
    const label = integerInRange(value.label ?? 1, `news[${index}].label`, 1, 8)
    const fallbackCategory = label >= 1 && label <= 4 ? label : 1
    const category = integerInRange(
        value.category ?? fallbackCategory,
        `news[${index}].category`,
        1,
        4,
    ) as NewsCategory
    if (typeof value.html !== "string") throw new Error(`news[${index}].html 必须是字符串`)
    if (value.html.length > 1_000_000) throw new Error(`news[${index}].html 最多 1000000 个字符`)
    if (value.published !== undefined && typeof value.published !== "boolean") {
        throw new Error(`news[${index}].published 必须是布尔值`)
    }

    const thumbnailPath = optionalString(value.thumbnail_path, `news[${index}].thumbnail_path`, 512)
    if (thumbnailPath !== null) {
        throw new Error(`news[${index}].thumbnail_path 当前客户端不支持，请留空`)
    }

    return {
        id: integerInRange(value.id, `news[${index}].id`, 1, 2_147_483_647),
        title: requiredString(value.title, `news[${index}].title`, 128),
        date: requiredDateString(value.date, `news[${index}].date`),
        category,
        label,
        thumbnail: integerInRange(value.thumbnail ?? 1, `news[${index}].thumbnail`, 1, 13),
        thumbnail_path: null,
        added_time: optionalDateString(value.added_time, `news[${index}].added_time`),
        html: value.html,
        published: value.published ?? true,
    }
}

function normalizePopup(value: unknown): NewsPopupConfig {
    if (value === undefined || value === null) return { ...DEFAULT_POPUP }
    if (!isRecord(value)) throw new Error("popup 必须是对象")
    if (value.enabled !== undefined && typeof value.enabled !== "boolean") {
        throw new Error("popup.enabled 必须是布尔值")
    }
    const rawNewsId = value.news_id
    const newsId = rawNewsId === null || rawNewsId === undefined || rawNewsId === ""
        ? null
        : integerInRange(rawNewsId, "popup.news_id", 1, 2_147_483_647)
    const mode = value.mode ?? DEFAULT_POPUP.mode
    if (mode !== "every_login" && mode !== "once_per_news") {
        throw new Error("popup.mode 必须是 every_login 或 once_per_news")
    }
    return {
        enabled: value.enabled ?? false,
        news_id: newsId,
        mode,
        start_time: optionalDateString(value.start_time, "popup.start_time"),
        end_time: optionalDateString(value.end_time, "popup.end_time"),
    }
}

export function normalizeNewsConfig(value: unknown): NewsConfig {
    const root = Array.isArray(value)
        ? { version: 1, popup: DEFAULT_POPUP, news: value }
        : value
    if (!isRecord(root)) throw new Error("公告配置根节点必须是对象或兼容的公告数组")
    if (root.version !== undefined && root.version !== 1) throw new Error("公告配置 version 仅支持 1")
    if (!Array.isArray(root.news)) throw new Error("news 必须是数组")

    const news = root.news.map(normalizeNewsItem)
    const ids = new Set<number>()
    for (const item of news) {
        if (ids.has(item.id)) throw new Error(`公告 ID ${item.id} 重复`)
        ids.add(item.id)
    }
    const popup = normalizePopup(root.popup)
    if (popup.enabled && popup.news_id === null) throw new Error("启用弹窗时必须选择公告")
    if (popup.news_id !== null && !ids.has(popup.news_id)) {
        throw new Error(`弹窗公告 ID ${popup.news_id} 不存在`)
    }
    if (popup.enabled && !news.find(item => item.id === popup.news_id)?.published) {
        throw new Error("启用弹窗时必须选择已发布公告")
    }
    if (popup.start_time !== null && popup.end_time !== null) {
        if (parseNewsDate(popup.start_time)!.getTime() >= parseNewsDate(popup.end_time)!.getTime()) {
            throw new Error("弹窗结束时间必须晚于开始时间")
        }
    }

    return { version: 1, popup, news }
}

function cloneConfig(config: NewsConfig): NewsConfig {
    return JSON.parse(JSON.stringify(config)) as NewsConfig
}

export function readNewsConfigState(): NewsConfigState {
    const configPath = getNewsConfigPath()
    try {
        if (!existsSync(configPath)) throw new Error(`公告配置不存在：${configPath}`)
        const parsed = JSON.parse(readFileSync(configPath, "utf-8")) as unknown
        const config = normalizeNewsConfig(parsed)
        lastGoodConfig = cloneConfig(config)
        lastReportedError = null
        return { config, error: null, path: configPath }
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        if (lastReportedError !== message) {
            console.error(`[NEWS] 公告配置读取失败，继续使用最近一次有效配置：${message}`)
            lastReportedError = message
        }
        return {
            config: cloneConfig(lastGoodConfig ?? DEFAULT_CONFIG),
            error: message,
            path: configPath,
        }
    }
}

export function loadNewsConfig(): NewsConfig {
    return readNewsConfigState().config
}

export function saveNewsConfig(value: unknown): NewsConfig {
    const config = normalizeNewsConfig(value)
    const configPath = getNewsConfigPath()
    const temporaryPath = `${configPath}.${process.pid}.${Date.now()}.tmp`
    try {
        writeFileSync(temporaryPath, `${JSON.stringify(config, null, 4)}\n`, "utf-8")
        renameSync(temporaryPath, configPath)
    } finally {
        if (existsSync(temporaryPath)) unlinkSync(temporaryPath)
    }
    lastGoodConfig = cloneConfig(config)
    lastReportedError = null
    return config
}

export function getPublishedNews(config: NewsConfig): NewsItem[] {
    return config.news
        .filter(item => item.published)
        .sort((left, right) => right.date.localeCompare(left.date) || right.id - left.id)
}

export function getActivePopupNews(config: NewsConfig, now: Date = new Date()): NewsItem | null {
    const popup = config.popup
    if (!popup.enabled || popup.news_id === null) return null
    const start = popup.start_time === null ? null : parseNewsDate(popup.start_time)
    const end = popup.end_time === null ? null : parseNewsDate(popup.end_time)
    if (start !== null && now < start) return null
    if (end !== null && now >= end) return null
    const item = config.news.find(candidate => candidate.id === popup.news_id)
    return item?.published ? item : null
}
