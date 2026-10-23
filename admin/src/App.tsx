import { useRef, useState, useSyncExternalStore } from "react"
import { Alert, Layout, Menu, Grid, Button, Drawer, Space } from "antd"
import { useQueryClient } from "@tanstack/react-query"
import { apiPost } from "./api/client"
import { getLoginExpired, setLoginExpired, subscribeLoginExpired } from "./api/auth"
import { allowAdminUnload, requestAdminLeave, useAdminBeforeUnload, useAdminEditGuard } from "./lib/editGuard"
import {
    Database,
    Gauge,
    LogOut,
    Mail as MailIcon,
    Menu as MenuIcon,
    Moon,
    Newspaper,
    Trophy,
    Sparkles,
    Palette,
    Sun,
    Users,
} from "lucide-react"
import { Routes, Route, useNavigate, useLocation, Navigate } from "react-router-dom"
import { createAsyncPage } from "./components/AsyncPage"
import logoUrl from "./assets/logo.png"

const Dashboard = createAsyncPage(() => import("./pages/Dashboard"), "Dashboard")
const Accounts = createAsyncPage(() => import("./pages/Accounts"), "Accounts")
const PlayerDetail = createAsyncPage(() => import("./pages/PlayerDetail"), "PlayerDetail")
const Mail = createAsyncPage(() => import("./pages/Mail"), "Mail")
const Seeds = createAsyncPage(() => import("./pages/Seeds"), "Seeds")
const HistoricalGacha = createAsyncPage(() => import("./pages/TimeControl"), "TimeControl")
const DataMaintenance = createAsyncPage(() => import("./pages/DataMaintenance"), "DataMaintenance")
const Leaderboards = createAsyncPage(() => import("./pages/Leaderboards"), "Leaderboards")
const News = createAsyncPage(() => import("./pages/News"), "News")
const ContentOperations = createAsyncPage(() => import("./pages/ContentOperations"), "ContentOperations")
const TownThemes = createAsyncPage(() => import("./pages/TownThemes"), "TownThemes")

const { Sider, Content, Header } = Layout
const { useBreakpoint } = Grid

const navigationPages = [
    { key: "/", icon: <Gauge size={18} />, label: "总览" },
    { key: "/content", icon: <Sparkles size={18} />, label: "内容运营" },
    { key: "/town-themes", icon: <Palette size={18} />, label: "主城外观" },
    { key: "/accounts", icon: <Users size={18} />, label: "账号 / 存档" },
    { key: "/mail", icon: <MailIcon size={18} />, label: "邮件" },
    { key: "/news", icon: <Newspaper size={18} />, label: "公告" },
    { key: "/seeds", icon: <Database size={18} />, label: "种子管理" },
    { key: "/leaderboards", icon: <Trophy size={18} />, label: "排行榜" },
    { key: "/maintenance", icon: <Database size={18} />, label: "存档与备份" },
]

const menuItems = [
    navigationPages[0],
    { type: "group" as const, label: "日常运营", children: navigationPages.filter(page => ["/content", "/town-themes", "/news", "/mail", "/leaderboards"].includes(page.key)) },
    { type: "group" as const, label: "玩家管理", children: navigationPages.filter(page => page.key === "/accounts") },
    { type: "group" as const, label: "维护工具", children: navigationPages.filter(page => ["/seeds", "/maintenance"].includes(page.key)) },
]

const pageTitles: Record<string, string> = {
    "/": "总览",
    "/content": "内容运营",
    "/town-themes": "主城外观",
    "/accounts": "账号 / 存档",
    "/mail": "邮件",
    "/news": "公告",
    "/seeds": "种子管理",
    "/leaderboards": "排行榜",
    "/maintenance": "存档与备份",
}

interface AppProps {
    dark: boolean
    onToggleDark: () => void
}

export default function App({ dark, onToggleDark }: AppProps) {
    const navigate = useNavigate()
    const location = useLocation()
    const screens = useBreakpoint()
    const isMobile = !screens.md
    const [drawerOpen, setDrawerOpen] = useState(false)
    const loginExpired = useSyncExternalStore(subscribeLoginExpired, getLoginExpired)
    const queryClient = useQueryClient()
    const [logoutPending, setLogoutPending] = useState(false)
    const logoutInFlight = useRef(false)
    const [logoutError, setLogoutError] = useState("")
    useAdminBeforeUnload()
    useAdminEditGuard({ dirty: false, pending: logoutPending, label: "退出登录" })
    const logout = async () => {
        if (logoutInFlight.current) return
        logoutInFlight.current = true
        setLogoutPending(true)
        setLogoutError("")
        try {
            await apiPost("/admin-logout")
            allowAdminUnload()
            window.location.replace("/admin-login")
        } catch {
            setLogoutError("退出未完成，当前页面和未保存内容仍保留。请检查网络后重试退出。")
        } finally {
            logoutInFlight.current = false
            setLogoutPending(false)
        }
    }

    const selected = location.pathname.startsWith("/players/") ? "/accounts" : navigationPages.find(m => m.key !== "/" && location.pathname.startsWith(m.key))?.key
        ?? "/"
    const currentTitle = location.pathname.startsWith("/players/")
        ? "玩家详情"
        : location.pathname === "/content/history" ? "历史卡池资料" : pageTitles[selected] ?? "管理后台"

    const brand = (
        <div className="admin-brand">
            <span className="admin-brand-mark">
                <img src={logoUrl} alt="World Flipper 上游项目标识" />
            </span>
            <span className="admin-brand-copy">
                <span className="admin-brand-title">Starpoint CN</span>
                <span className="admin-brand-subtitle">World Flipper Server</span>
            </span>
        </div>
    )
    const menu = (
        <Menu
            className="admin-menu"
            mode="inline"
            selectedKeys={[selected]}
            items={menuItems}
            onClick={e => { if (e.key !== location.pathname) requestAdminLeave(() => { navigate(e.key); setDrawerOpen(false) }) }}
        />
    )

    return (
        <Layout className="admin-app">
            {!isMobile && (
                <Sider className="admin-sider" theme="light" width={248} breakpoint="lg" collapsedWidth={72}>
                    {brand}
                    {menu}
                </Sider>
            )}
            <Layout>
                <Header className="admin-topbar">
                    {isMobile && (
                        <Button
                            type="text"
                            icon={<MenuIcon size={18} />}
                            onClick={() => setDrawerOpen(true)}
                            aria-label="打开导航"
                        />
                    )}
                    <span className="admin-topbar-title">{currentTitle}</span>
                    <Space>
                        <Button
                            type="text"
                            icon={dark ? <Sun size={18} /> : <Moon size={18} />}
                            onClick={onToggleDark}
                            aria-label="切换明暗模式"
                            title={dark ? "切换到浅色" : "切换到深色"}
                        />
                        <Button
                            type="text"
                            danger
                            icon={<LogOut size={18} />}
                            onClick={() => requestAdminLeave(logout)}
                            loading={logoutPending}
                            aria-label="退出管理面板"
                            title="退出管理面板"
                        />
                    </Space>
                </Header>
                <Content className="admin-content">
                    {loginExpired && (
                        <Alert
                            type="warning" showIcon role="alert"
                            message="管理登录已失效"
                            description="当前页面和未保存内容仍保留。在新窗口重新登录后，返回此页重试；写入操作需要重新确认。"
                            action={<Space wrap>
                                <Button href="/admin-login" target="_blank" rel="noopener noreferrer">新窗口重新登录</Button>
                                <Button onClick={() => { setLoginExpired(false); void queryClient.invalidateQueries() }}>已登录，重试读取</Button>
                            </Space>}
                            style={{ marginBottom: 16 }}
                        />
                    )}
                    {logoutError && <Alert type="error" showIcon role="alert" message={logoutError}
                        action={<Button onClick={() => requestAdminLeave(logout)} loading={logoutPending}>重试退出</Button>}
                        style={{ marginBottom: 16 }} />}
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/time" element={<Navigate to="/content/history" replace />} />
                        <Route path="/content/history" element={<HistoricalGacha />} />
                        <Route path="/maintenance" element={<DataMaintenance />} />
                        <Route path="/content" element={<ContentOperations />} />
                        <Route path="/town-themes" element={<TownThemes />} />
                        <Route path="/accounts" element={<Accounts />} />
                        <Route path="/players/:playerId" element={<PlayerDetail />} />
                        <Route path="/mail" element={<Mail />} />
                        <Route path="/news" element={<News />} />
                        <Route path="/seeds" element={<Seeds />} />
                        <Route path="/leaderboards" element={<Leaderboards />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </Content>
            </Layout>
            {isMobile && (
                <Drawer
                    open={drawerOpen}
                    onClose={() => setDrawerOpen(false)}
                    placement="left"
                    width={260}
                    title={(
                        <Space size={8}>
                            <Sparkles size={18} />
                            <span>Starpoint CN</span>
                        </Space>
                    )}
                    styles={{ body: { padding: 0 }, header: { borderBottom: "1px solid var(--admin-border)" } }}
                >
                    {menu}
                </Drawer>
            )}
        </Layout>
    )
}
