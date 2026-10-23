import { Component, lazy, Suspense, useMemo, useRef, useState } from "react"
import type { ComponentType, ReactNode } from "react"
import { Alert, Button, Space, Spin } from "antd"
import { allowAdminUnload, requestAdminLeave } from "../lib/editGuard"

class PageBoundary extends Component<{ children: ReactNode; onRetry: () => void; canRetry: () => boolean }, { failed: boolean }> {
    state = { failed: false }

    static getDerivedStateFromError() { return { failed: true } }

    render() {
        if (!this.state.failed) return this.props.children
        const canRetry = this.props.canRetry()
        return <Alert type="error" showIcon role="alert" message="页面加载失败"
            description={canRetry ? "可能是网络中断或后台版本已更新。可以先重试此页；重新加载整个后台前请保留未保存内容。"
                : "此加载错误需要重新加载后台才能恢复。请先保留未保存内容，再确认重新加载。"}
            action={<Space wrap>
                {canRetry && <Button onClick={this.props.onRetry}>重试页面</Button>}
                <Button onClick={() => requestAdminLeave(() => { allowAdminUnload(); window.location.reload() })}>重新加载后台</Button>
            </Space>} />
    }
}

export function routeRetryUrl(error: unknown, pageName: string, origin: string): string | null {
    if (!(error instanceof Error) || !/^[A-Za-z]+$/.test(pageName)) return null
    for (const candidate of error.message.match(/https?:\/\/[^\s"'<>)]*/g) ?? []) {
        try {
            const url = new URL(candidate)
            if (url.origin === origin && new RegExp(`^/admin/assets/${pageName}-[A-Za-z0-9_-]{8,}\\.js$`).test(url.pathname)) return url.href
        } catch { /* A non-URL error uses the explicit full reload control. */ }
    }
    return null
}

/** Failed ES modules are cached by browsers too; a scoped retry URL bypasses that failure. */
export function createAsyncPage(load: () => Promise<{ default: ComponentType }>, pageName: string) {
    return function AsyncPage() {
        const [attempt, setAttempt] = useState(0)
        const retryUrl = useRef<string | null>(null)
        const Page = useMemo(() => lazy(async () => {
            try {
                if (attempt > 0 && retryUrl.current) {
                    const url = new URL(retryUrl.current)
                    url.searchParams.set("adminRetry", `${Date.now()}-${attempt}`)
                    return await import(/* @vite-ignore */ url.href)
                }
                return await load()
            } catch (error) {
                retryUrl.current = routeRetryUrl(error, pageName, window.location.origin)
                throw error
            }
        }), [attempt])
        return <PageBoundary key={attempt} canRetry={() => retryUrl.current !== null} onRetry={() => setAttempt(value => value + 1)}>
            <Suspense fallback={<div role="status" aria-label="正在加载页面" style={{ minHeight: 240, display: "grid", placeItems: "center" }}><Spin /></div>}>
                <Page />
            </Suspense>
        </PageBoundary>
    }
}
