import { useCallback, useEffect, useRef } from "react"
import { Modal } from "antd"
import { useNavigate } from "react-router-dom"
import type { NavigateOptions, To } from "react-router-dom"

interface EditGuardState { dirty: boolean; pending: boolean; label: string }
const guards = new Map<symbol, EditGuardState>()
let unloadAllowed = false

export function getAdminEditState() {
    const states = [...guards.values()]
    return { dirty: states.some(state => state.dirty), pending: states.some(state => state.pending), labels: [...new Set(states.filter(state => state.dirty || state.pending).map(state => state.label))] }
}

/** Registration and cleanup are symmetric, including React StrictMode's effect replay. */
export function useAdminEditGuard(state: EditGuardState) {
    const key = useRef(Symbol("admin-edit"))
    useEffect(() => {
        const id = key.current
        if (state.dirty || state.pending) guards.set(id, state)
        else guards.delete(id)
        return () => { guards.delete(id) }
    }, [state.dirty, state.pending, state.label])
}

export function allowAdminUnload() { unloadAllowed = true }

export function useAdminBeforeUnload() {
    useEffect(() => {
        const listener = (event: BeforeUnloadEvent) => {
            const state = getAdminEditState()
            if (!unloadAllowed && (state.dirty || state.pending)) {
                event.preventDefault()
                event.returnValue = ""
            }
        }
        window.addEventListener("beforeunload", listener)
        return () => window.removeEventListener("beforeunload", listener)
    }, [])
}

/** Guards explicit navigation only; it does not claim to block browser history traversal. */
export function requestAdminLeave(action: () => void | Promise<void>) {
    const state = getAdminEditState()
    if (state.pending) {
        Modal.info({ title: "操作尚未完成", content: `${state.labels.join("、")}正在处理。请等待完成后再离开；关闭页面不代表取消服务端操作。`, okText: "留在当前页" })
        return
    }
    if (!state.dirty) { void action(); return }
    Modal.confirm({
        title: "离开并放弃未保存的修改？",
        content: `${state.labels.join("、")}有未保存的修改。选择离开后这些修改将丢失。`,
        okText: "放弃修改并离开", cancelText: "继续编辑", okButtonProps: { danger: true },
        onOk: () => {
            if (getAdminEditState().pending) {
                Modal.info({ title: "操作尚未完成", content: "请等待当前操作完成后再离开。" })
                return
            }
            return action()
        },
    })
}

export function useAdminNavigate() {
    const navigate = useNavigate()
    return useCallback((to: To | number, options?: NavigateOptions) => {
        requestAdminLeave(() => { if (typeof to === "number") navigate(to); else navigate(to, options) })
    }, [navigate])
}
