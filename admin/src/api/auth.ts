let loginExpired = false
const listeners = new Set<() => void>()

export const getLoginExpired = () => loginExpired

export function subscribeLoginExpired(listener: () => void) {
    listeners.add(listener)
    return () => { listeners.delete(listener) }
}

export function setLoginExpired(value: boolean) {
    if (loginExpired === value) return
    loginExpired = value
    listeners.forEach(listener => listener())
}
