import { parentPort, workerData } from "node:worker_threads"
import { setDbOverride } from "../data/db"
import { openWriterConnection } from "../lib/persistence/writer-connection"
import { runLeaderboardSettlementWorkerSync } from "../lib/leaderboard/settlement"
import type { LeaderboardSettlementWorkerInput } from "../lib/leaderboard/background-worker"
import { configureLeaderboardSettlementCancellation, assertLeaderboardSettlementNotCancelled } from "../lib/leaderboard/worker-cancellation"
import { restoreServerClockStateSync } from "../lib/server-clock-state"

const input = workerData as LeaderboardSettlementWorkerInput
let db: ReturnType<typeof openWriterConnection> | undefined
let result: object
try {
    configureLeaderboardSettlementCancellation(input.cancelBuffer)
    assertLeaderboardSettlementNotCancelled()
    db = openWriterConnection({ databasePath: input.databasePath, busyTimeoutMs: 1000 })
    setDbOverride(db)
    assertLeaderboardSettlementNotCancelled()
    db.exec("BEGIN IMMEDIATE")
    // Each worker has its own process clock. Restore the committed coordinate
    // under the same write lock before any guarded reward or schedule write.
    // A corrupt state fails closed; absence preserves the existing legacy path.
    restoreServerClockStateSync(db)
    parentPort?.postMessage({ type: "started" })
    const outcome = runLeaderboardSettlementWorkerSync(input)
    // A cancellation racing COMMIT is resolved from the durable receipt after exit.
    // Never check again after COMMIT: an acknowledged commit cannot be rolled back.
    assertLeaderboardSettlementNotCancelled()
    db.exec("COMMIT")
    result = { type: "result", ok: true, outcome }
} catch (error) {
    if (db?.inTransaction) db.exec("ROLLBACK")
    result = { type: "result", ok: false, message: error instanceof Error ? error.message : String(error),
        code: (error as { code?: string })?.code }
} finally { db?.close() }
parentPort?.postMessage(result)
parentPort?.close()
