import Database from "better-sqlite3"
import { parentPort, workerData } from "worker_threads"
import { createPlayerSaveSnapshotV2Sync } from "../data/snapshots/player-snapshot"

interface PlayerSaveExportWorkerData {
    databasePath: string
    playerId: number
    maxBytes: number
}

const input = workerData as PlayerSaveExportWorkerData

function send(message: Record<string, unknown>, transferList: ArrayBuffer[] = []): void {
    parentPort?.postMessage(message, transferList)
}

function main(): void {
    const database = new Database(input.databasePath, {
        readonly: true,
        fileMustExist: true,
    })
    database.pragma("query_only = ON")
    database.pragma("busy_timeout = 5000")

    let snapshot: ReturnType<typeof createPlayerSaveSnapshotV2Sync>
    try {
        // One read transaction pins a consistent WAL snapshot while gameplay
        // remains free to write through the main process connection.
        snapshot = database.transaction(() => (
            createPlayerSaveSnapshotV2Sync(input.playerId, database)
        ))()
    } finally {
        database.close()
    }

    const payload = new TextEncoder().encode(JSON.stringify(snapshot))
    if (payload.byteLength > input.maxBytes) {
        send({
            type: "failed",
            code: "too-large",
            error: `存档超过 ${input.maxBytes / 1024 / 1024} MB 安全上限`,
        })
        return
    }
    send({
        type: "completed",
        payload: payload.buffer,
        byteLength: payload.byteLength,
        rowCount: snapshot.summary.rowCount,
    }, [payload.buffer])
}

try {
    main()
} catch (error) {
    send({
        type: "failed",
        code: "export-failed",
        error: error instanceof Error ? error.message : String(error),
    })
    process.exitCode = 1
}
