/** Native event pages consume one seasonal set at a time. Static membership
 * in a master table does not authorize presenting every historical set at once. */
interface PresentationAction {
    enabled: boolean
    questKeys?: readonly string[] | null
}
interface PresentationControl {
    controlled?: boolean
    flags: { visible: boolean; enter: boolean }
    questKeys?: readonly string[] | null
    actionOverrides?: { visible?: PresentationAction; enter?: PresentationAction }
}

function action(control: PresentationControl, name: "visible" | "enter"): PresentationAction | undefined {
    if (control.controlled === false) return undefined
    return control.actionOverrides !== undefined ? control.actionOverrides[name]
        : { enabled: control.flags[name], questKeys: control.questKeys }
}
function sameKeys(first: readonly string[], second: readonly string[]): boolean {
    const sortedSecond = [...second].sort()
    return first.length === second.length && [...first].sort().every((key, index) => key === sortedSecond[index])
}

/** Validate a proposed visible/enter edit, without touching persisted player
 * progress or applying this restriction to a registered battle's finish/abort. */
export function nativePresentationScopeError(
    row: { key: string; type: string; id: number }, control: PresentationControl,
): string | null {
    const tower = row.type === "tower_dungeon_event"
    const beast = row.key === "challenge_dungeon_event:1"
    if (!tower && !beast) return null
    const visible = action(control, "visible"), enter = action(control, "enter")
    // Suspension may retain the reviewed participation scope for reopening.
    // The store separately enforces its existing entry/publication policy.
    if (visible?.enabled === false || (!visible?.enabled && !enter?.enabled)) return null
    const opened = [["显示", visible], ["参与", enter]] as const
    for (const [label, setting] of opened) {
        if (!setting?.enabled) continue
        const keys = setting.questKeys
        if (!Array.isArray(keys) || keys.length === 0 || new Set(keys).size !== keys.length)
            return `${tower ? "幽玄域" : "崩坏域"}${label}必须指定精确关卡范围，不能使用全部历史关卡`
        if (tower) {
            const ids = keys.map(key => /^20:\d+$/.test(key) ? Number(key.slice(3)) : NaN).sort((a, b) => a - b)
            const first = ids[0], member = first - row.id * 1000
            if (ids.length !== 10 || !Number.isSafeInteger(first) || member < 1 || member > 991
                || (member - 1) % 10 !== 0 || ids.some((id, index) => id !== first + index || Math.floor(id / 1000) !== row.id))
                return `幽玄域${label}必须选择同一期完整的10个战斗关卡`
        } else {
            const periods = new Set(keys.filter(key => /^13:10(2\d|3\d|40)$/.test(key))
                .map(key => Math.floor((Number(key.slice(3)) - 1020) / 3)))
            if (periods.size > 1) return `崩坏域${label}不能同时开放多期临境域·深渊之兽`
        }
    }
    if (visible?.enabled && enter?.enabled && tower && !sameKeys(visible.questKeys!, enter.questKeys!))
        return "幽玄域显示和参与必须选择同一期10个关卡"
    if (visible?.enabled && enter?.enabled && beast) {
        const shown = new Set(visible.questKeys)
        if (enter.questKeys!.some(key => !shown.has(key))) return "崩坏域参与关卡必须包含在同一显示范围内"
    }
    return null
}
