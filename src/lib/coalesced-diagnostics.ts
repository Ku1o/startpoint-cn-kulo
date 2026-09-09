interface DiagnosticCount {
    suppressed: number
}

/** First evidence is lazy; retries must not repeat database reads or formatting. */
export class CoalescedDiagnostics {
    private readonly counts = new Map<string, DiagnosticCount>()
    private overflow = 0
    private timer?: NodeJS.Timeout

    constructor(
        private readonly prefix: string,
        private readonly intervalMs = 60_000,
        private readonly maxKeys = 128,
        private readonly write: (message: string) => void = message => console.warn(message),
    ) {}

    private emit(message: string): void {
        try { this.write(message) } catch { /* A failed log sink cannot fail gameplay. */ }
    }

    report(key: string, details: () => string): void {
        // Bound retained identities even when a malformed request supplies a
        // very long play id. Valid play ids are at most 255 characters.
        key = key.slice(0, 1024)
        const count = this.counts.get(key)
        if (count) {
            count.suppressed += 1
            return
        }
        if (!this.timer) {
            this.timer = setTimeout(() => this.flush(), this.intervalMs)
            this.timer.unref()
        }
        if (this.counts.size >= this.maxKeys) {
            this.overflow += 1
            return
        }
        this.counts.set(key, { suppressed: 0 })
        try {
            this.emit(details())
        } catch {
            // Diagnostics must not replace the original gameplay error when
            // fetching its database context also fails.
            this.emit(`${this.prefix} ${JSON.stringify({ key, contextUnavailable: true })}`)
        }
    }

    flush(): void {
        if (this.timer) clearTimeout(this.timer)
        this.timer = undefined
        const repeats = [...this.counts]
            .filter(([, count]) => count.suppressed > 0)
            .map(([key, count]) => ({ key, suppressed: count.suppressed }))
        this.counts.clear()
        const overflow = this.overflow
        this.overflow = 0
        if (repeats.length || overflow) {
            this.emit(`${this.prefix} ${JSON.stringify({ intervalMs: this.intervalMs, repeats, overflow })}`)
        }
    }
}

export const fiveBossDiagnostics = new CoalescedDiagnostics("[FIVE-BOSS-REPEAT]")
