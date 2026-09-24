import { execFile } from "node:child_process"
import { join } from "node:path"
import { performance } from "node:perf_hooks"

export interface ProcessMemoryValues {
    privateBytes: number
    workingSetBytes: number
    virtualBytes: number
    handleCount: number
    threadCount: number
    regions?: Record<string, number>
}

const fields: readonly (keyof ProcessMemoryValues)[] = [
    "privateBytes", "workingSetBytes", "virtualBytes", "handleCount", "threadCount",
]
const regionFields = ["privateCommittedBytes", "mappedCommittedBytes", "imageCommittedBytes",
    "otherCommittedBytes", "reservedBytes", "regionCount"] as const

export function readWindowsProcessMemory(signal: AbortSignal): Promise<ProcessMemoryValues> {
    // Only numeric process measurements leave the helper. Never collect command
    // lines, environment variables, database paths or another process's memory.
    return new Promise((resolve, reject) => {
        execFile(join(process.env.SystemRoot ?? "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
            ["-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                join(__dirname, "../../tools/capture-native-memory.ps1"), "-ProcessId", String(process.pid)],
            { windowsHide: true, timeout: 5_000, maxBuffer: 4_096, encoding: "utf8", signal },
            (error, stdout) => {
                if (error) { reject(error); return }
                try {
                    const value = JSON.parse(stdout.trim().replace(/^\uFEFF/, ""))
                    if (!value || value.pid !== process.pid
                        || fields.some(field => !Number.isSafeInteger(value[field]) || value[field] < 0)
                        || !value.regions || regionFields.some(field =>
                            !Number.isSafeInteger(value.regions[field]) || value.regions[field] < 0)) {
                        throw new Error("Invalid process memory sample")
                    }
                    resolve({ ...Object.fromEntries(fields.map(field => [field, value[field]])),
                        regions: Object.fromEntries(regionFields.map(field => [field, value.regions[field]])),
                    } as unknown as ProcessMemoryValues)
                } catch (error) { reject(error) }
            })
    })
}

/** One bounded, asynchronous OS request; never block a gameplay request on PowerShell. */
export class ProcessMemoryProbe {
    private sample: ProcessMemoryValues | null = null
    private sampledAt: number | null = null
    private requestAt: number | null = null
    private controller: AbortController | null = null
    private failed = false
    private closed = false

    constructor(
        readonly enabled = process.platform === "win32" && process.arch === "x64"
            && /^(1|true|yes|on)$/i.test(process.env.PROCESS_MEMORY_DIAGNOSTICS ?? "false"),
        private readonly read = readWindowsProcessMemory,
        private readonly now = () => performance.now(),
    ) {}

    request(): void {
        if (!this.enabled || this.closed || this.controller) return
        const controller = new AbortController()
        this.controller = controller
        this.requestAt = this.now()
        void Promise.resolve().then(() => {
            if (controller.signal.aborted) throw new Error("Process memory probe closed")
            return this.read(controller.signal)
        }).then(sample => {
            if (this.closed || this.controller !== controller) return
            this.sample = sample
            this.sampledAt = this.now()
            this.failed = false
        }).catch(() => {
            if (!this.closed) this.failed = true
        }).finally(() => {
            if (this.controller === controller) { this.controller = null; this.requestAt = null }
        })
    }

    snapshot() {
        const ageMs = this.sampledAt === null ? null : Math.round(this.now() - this.sampledAt)
        return { available: this.enabled, ageMs, stale: this.failed || ageMs === null || ageMs > 120_000,
            pendingMs: this.requestAt === null ? 0 : Math.round(this.now() - this.requestAt),
            failed: this.failed, memory: this.sample }
    }

    close(): void {
        this.closed = true
        this.controller?.abort()
        this.controller = null
        this.requestAt = null
    }
}
