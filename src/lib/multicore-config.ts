import { availableParallelism } from "node:os"

function count(value: string | undefined, fallback: number): number {
    if (!value?.trim()) return fallback
    const number = Number(value)
    return Number.isInteger(number) && number >= 0 ? Math.min(4, number) : fallback
}

function switchValue(value: string | undefined): boolean | undefined {
    if (/^(1|true|yes|on)$/i.test(value ?? "")) return true
    if (/^(0|false|no|off)$/i.test(value ?? "")) return false
    return undefined
}

/** CPU workers share a budget; maintenance threads are mostly sleeping. */
export function multicoreConfig(environment: NodeJS.ProcessEnv = process.env, cores = availableParallelism()) {
    const configured = switchValue(environment.CN_MULTICORE)
    const enabled = configured ?? cores >= 4
    // Response workers improve isolation for unusually large bursts, but the
    // measured 4-core workload spends less total CPU on the local encoder.
    const responseWorkers = count(environment.CN_RESPONSE_WORKERS, 0)
    const checkpointWorker = switchValue(environment.SQLITE_CHECKPOINT_WORKER) ?? enabled
    return { enabled, responseWorkers, checkpointWorker }
}
