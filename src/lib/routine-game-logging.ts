type Family = "multiBarrier" | "multiSettlement" | "rush"
const mode = (process.env.GAME_ROUTINE_LOGS ?? "summary").toLowerCase()
const counts: Record<Family, number> = { multiBarrier: 0, multiSettlement: 0, rush: 0 }
let timer: NodeJS.Timeout | null = null

/** Keep three examples per family/minute; warnings and rejection logs bypass this helper. */
export function routineGameLog(family: Family, message: () => string): void {
    if (/^(0|false|no|off)$/.test(mode)) return
    if (mode === "full") { console.log(message()); return }
    counts[family]++
    if (counts[family] <= 3) console.log(message())
    if (!timer) {
        timer = setTimeout(flushRoutineGameLogs, 60_000)
        timer.unref()
    }
}

export function flushRoutineGameLogs(): void {
    if (timer) { clearTimeout(timer); timer = null }
    const summary = Object.entries(counts).filter(([, count]) => count > 0)
        .map(([family, count]) => `${family}=${count}(suppressed=${Math.max(0, count - 3)})`).join(" ")
    for (const family of Object.keys(counts) as Family[]) counts[family] = 0
    if (summary) console.log(`[GAME-SUMMARY] interval=60000ms ${summary}`)
}
