import Database from "better-sqlite3"
import { parentPort, workerData } from "node:worker_threads"
import { installWorkerMemoryProbe } from "../lib/memory-diagnostics"

interface PersistenceStatement {
    sql: string
    params: readonly unknown[]
}

interface PersistenceCommand {
    id: number
    operation: string
    statements: readonly PersistenceStatement[]
}

interface WorkerInput {
    databasePath: string
    busyTimeoutMs: number
    maxAttempts: number
}

const input = workerData as WorkerInput
const database = new Database(input.databasePath)
database.pragma("journal_mode = WAL")
database.pragma("synchronous = NORMAL")
database.pragma(`busy_timeout = ${Math.max(0, input.busyTimeoutMs)}`)
// Checkpoint ownership remains with the optional checkpoint worker or the
// main connection. This connection only executes business write commands.
database.pragma("wal_autocheckpoint = 0")
database.pragma("foreign_keys = ON")

let closed = false
let executing = false
let completed = 0
let failed = 0
let busyRetries = 0

function isBusyError(error: unknown): boolean {
    if (!(error instanceof Error) || !("code" in error)) return false
    const code = String((error as Error & { code?: string }).code ?? "")
    return code === "SQLITE_BUSY"
        || code === "SQLITE_BUSY_SNAPSHOT"
        || code.startsWith("SQLITE_BUSY_")
}

function delay(milliseconds: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, milliseconds))
}

function runCommand(command: PersistenceCommand): { changes: number, lastInsertRowid: number | null } {
    if (!Array.isArray(command.statements) || command.statements.length === 0) {
        throw new Error("Persistence command must contain at least one statement.")
    }
    return database.transaction(() => {
        let changes = 0
        let lastInsertRowid: number | null = null
        for (const statement of command.statements) {
            if (!statement || typeof statement.sql !== "string" || statement.sql.length === 0) {
                throw new Error("Persistence command contains an invalid SQL statement.")
            }
            const result = database.prepare(statement.sql).run(...(statement.params ?? []))
            changes += result.changes
            lastInsertRowid = Number(result.lastInsertRowid)
        }
        return { changes, lastInsertRowid }
    }).immediate()
}

async function execute(command: PersistenceCommand): Promise<void> {
    if (closed) throw new Error("SQLite persistence worker is closed.")
    executing = true
    try {
        let lastError: unknown
        for (let attempt = 1; attempt <= Math.max(1, input.maxAttempts); attempt += 1) {
            try {
                const result = runCommand(command)
                completed++
                parentPort?.postMessage({
                    type: "result", id: command.id, operation: command.operation, ...result,
                })
                return
            } catch (error) {
                lastError = error
                if (!isBusyError(error) || attempt >= input.maxAttempts) throw error
                busyRetries++
                await delay(10 * (2 ** (attempt - 1)))
            }
        }
        throw lastError
    } catch (error) {
        failed++
        parentPort?.postMessage({
            type: "error",
            id: command.id,
            operation: command.operation,
            code: error instanceof Error && "code" in error
                ? String((error as Error & { code?: string }).code ?? "") : null,
            error: error instanceof Error ? error.message : String(error),
        })
    } finally {
        executing = false
    }
}

installWorkerMemoryProbe(() => ({ completed, failed, busyRetries, executing }))

parentPort?.on("message", (message: PersistenceCommand | { type: "close" }) => {
    if (typeof message === "object" && "type" in message && message.type === "close") {
        if (executing || closed) return
        closed = true
        try { database.close() } catch {}
        parentPort?.postMessage({ type: "closed" })
        return
    }
    void execute(message as PersistenceCommand)
})
