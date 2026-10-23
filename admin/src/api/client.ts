import { setLoginExpired } from "./auth"

// 统一 fetch 封装：所有请求走 /api（dev 由 Vite 代理到 8001）
export class ApiError extends Error {
    constructor(public status: number, message: string) {
        super(message)
    }
}

export function shouldRetryQuery(failureCount: number, error: Error): boolean {
    return !(error instanceof ApiError && (error.status === 401 || error.status === 403)) && failureCount < 1
}

function fallbackError(status: number): string {
    if (status >= 500) return `服务暂时不可用（HTTP ${status}），请稍后重试。`
    return ({ 400: "请求参数无效，请检查输入。", 404: "请求的内容不存在或已删除。", 409: "数据已更新，请刷新后重试。", 413: "上传内容过大，请缩小后重试。", 429: "请求过于频繁，请稍后重试。" } as Record<number, string>)[status]
        ?? `请求失败（HTTP ${status}），请稍后重试。`
}

/** Bound error reads; proxy HTML/stack dumps must not become enormous user messages. */
async function responseError(res: Response): Promise<string> {
    const fallback = fallbackError(res.status)
    if (!/\bapplication\/(?:[\w.-]+\+)?json\b/i.test(res.headers.get("content-type") ?? "")) {
        await res.body?.cancel().catch(() => {})
        return fallback
    }
    const reader = res.body?.getReader()
    if (!reader) return fallback
    try {
        const decoder = new TextDecoder()
        let bytes = 0, text = ""
        while (true) {
            const part = await reader.read()
            if (part.done) break
            bytes += part.value.byteLength
            if (bytes > 16_384) { await reader.cancel(); return fallback }
            text += decoder.decode(part.value, { stream: true })
        }
        const value = JSON.parse(text + decoder.decode())
        if (typeof value?.error !== "string" || !value.error.trim() || /<(?:!doctype|html|head|body|script|style)\b/i.test(value.error)) return fallback
        return value.error.length <= 1000 ? value.error : `${value.error.slice(0, 1000)}…`
    } catch { return fallback } finally { reader.releaseLock() }
}

async function handle<T>(res: Response): Promise<T> {
    if (!res.ok) {
        if (res.status === 401) {
            setLoginExpired(true)
            void res.body?.cancel().catch(() => {})
            throw new ApiError(401, "管理登录已失效，请重新登录后重试；当前未保存内容仍保留。")
        } else if (res.status === 403) {
            void res.body?.cancel().catch(() => {})
            throw new ApiError(403, "没有执行此操作的权限，请检查管理权限。")
        }
        throw new ApiError(res.status, await responseError(res))
    }
    const ct = res.headers.get("content-type") ?? ""
    return ct.includes("application/json") ? res.json() : (res.text() as unknown as T)
}

export function apiGet<T>(url: string, options?: { signal?: AbortSignal }): Promise<T> {
    return fetch(url, { headers: { Accept: "application/json" }, signal: options?.signal }).then(r => handle<T>(r))
}

export function apiPost<T>(url: string, body?: unknown): Promise<T> {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body)
    }).then(r => handle<T>(r))
}

export function apiPut<T>(url: string, body?: unknown): Promise<T> {
    return fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body)
    }).then(r => handle<T>(r))
}

export function apiPatch<T>(url: string, body?: unknown): Promise<T> {
    return fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body)
    }).then(r => handle<T>(r))
}

export function apiDelete<T>(url: string): Promise<T> {
    return fetch(url, { method: "DELETE", headers: { Accept: "application/json" } })
        .then(r => handle<T>(r))
}

// multipart 上传：不手动设 Content-Type，交给浏览器带 boundary
export function apiUpload<T>(url: string, file: File, fieldName = "file"): Promise<T> {
    const fd = new FormData()
    fd.append(fieldName, file)
    return fetch(url, { method: "POST", headers: { Accept: "application/json" }, body: fd })
        .then(r => handle<T>(r))
}
