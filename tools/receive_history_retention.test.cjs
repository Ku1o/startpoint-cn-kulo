const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const Database = require("better-sqlite3")

const useCompiledServer = process.env.RECEIVE_HISTORY_RETENTION_COMPILED === "1"
if (!useCompiledServer) require("ts-node/register/transpile-only")
const serverModuleRoot = useCompiledServer ? "../out" : "../src"
const {
    createReceiveHistoryRetentionService,
    getReceiveHistoryRetentionSchedule,
    isReceiveHistoryRetentionEnabled,
    millisecondsUntilNextReceiveHistoryRetentionRun,
    runReceiveHistoryRetentionPass,
} = require(`${serverModuleRoot}/lib/receive-history-retention`)

const silentLogger = { log() {}, warn() {} }

function createDatabase(filename = ":memory:") {
    const db = new Database(filename)
    db.pragma("busy_timeout = 1")
    db.exec(`
        CREATE TABLE players_receive_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            type INTEGER NOT NULL,
            type_id INTEGER,
            number INTEGER NOT NULL DEFAULT 1,
            reason_id INTEGER NOT NULL DEFAULT 0,
            create_time TEXT NOT NULL
        );
        CREATE INDEX idx_cleanup_fk_players_receive_history_0
            ON players_receive_history (player_id);
    `)
    return db
}

function insertHistory(db, playerId, count, createTimeForIndex = index => String(index).padStart(8, "0")) {
    const insert = db.prepare(`
        INSERT INTO players_receive_history
            (player_id, type, type_id, number, reason_id, create_time)
        VALUES (?, 5, 251002, 1, 0, ?)
    `)
    db.transaction(() => {
        for (let index = 0; index < count; index += 1) {
            insert.run(playerId, createTimeForIndex(index))
        }
    })()
}

function countHistory(db, playerId) {
    return db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_receive_history
        WHERE player_id = ?
    `).get(playerId).count
}

async function waitUntil(predicate, timeoutMs = 2000) {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
        if (predicate()) return
        await new Promise(resolve => setTimeout(resolve, 10))
    }
    throw new Error(`condition was not satisfied within ${timeoutMs}ms`)
}

async function testPassAndIdempotency() {
    const db = createDatabase()
    try {
        insertHistory(db, 1, 499)
        insertHistory(db, 2, 500)
        insertHistory(db, 3, 501)
        insertHistory(db, 4, 500, index => `z-new-${String(index).padStart(8, "0")}`)
        const lateOldRowId = db.prepare(`
            INSERT INTO players_receive_history
                (player_id, type, type_id, number, reason_id, create_time)
            VALUES (4, 5, 251002, 1, 0, 'a-old-00000000')
        `).run().lastInsertRowid

        const result = await runReceiveHistoryRetentionPass(db, {
            maxRows: 500,
            batchPlayers: 2,
            pauseMs: 0,
            logger: silentLogger,
        })
        assert.equal(result.candidatePlayers, 2)
        assert.equal(result.prunedPlayers, 2)
        assert.equal(result.deletedRows, 2)
        assert.equal(result.failedPlayers, 0)
        assert.equal(countHistory(db, 1), 499)
        assert.equal(countHistory(db, 2), 500)
        assert.equal(countHistory(db, 3), 500)
        assert.equal(countHistory(db, 4), 500)
        assert.equal(db.prepare(`SELECT 1 FROM players_receive_history WHERE id = ?`).get(lateOldRowId), undefined)

        const second = await runReceiveHistoryRetentionPass(db, {
            maxRows: 500,
            pauseMs: 0,
            logger: silentLogger,
        })
        assert.equal(second.candidatePlayers, 0)
        assert.equal(second.deletedRows, 0)
    } finally {
        db.close()
    }
}

async function testBusyFailureIsIsolatedAndRetryable() {
    const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "sp-receive-retention-"))
    const databasePath = path.join(temporaryDirectory, "test.db")
    const db = createDatabase(databasePath)
    const lock = new Database(databasePath)
    try {
        db.pragma("journal_mode = WAL")
        lock.pragma("journal_mode = WAL")
        lock.pragma("busy_timeout = 1")
        insertHistory(db, 10, 501)
        lock.exec("BEGIN IMMEDIATE")

        const blocked = await runReceiveHistoryRetentionPass(db, {
            maxRows: 500,
            pauseMs: 0,
            busyRetryAttempts: 2,
            busyRetryDelayMs: 1,
            logger: silentLogger,
        })
        assert.equal(blocked.failedPlayers, 1)
        assert.equal(blocked.deletedRows, 0)
        assert.equal(countHistory(db, 10), 501)

        lock.exec("ROLLBACK")
        const retried = await runReceiveHistoryRetentionPass(db, {
            maxRows: 500,
            pauseMs: 0,
            logger: silentLogger,
        })
        assert.equal(retried.failedPlayers, 0)
        assert.equal(retried.deletedRows, 1)
        assert.equal(countHistory(db, 10), 500)
    } finally {
        if (lock.inTransaction) lock.exec("ROLLBACK")
        lock.close()
        db.close()
        fs.rmSync(temporaryDirectory, { recursive: true, force: true })
    }
}

async function testAutomaticLifecycleAndEmergencySwitch() {
    assert.equal(isReceiveHistoryRetentionEnabled({}), true)
    for (const value of ["0", "false", "OFF", "no"]) {
        assert.equal(isReceiveHistoryRetentionEnabled({ RECEIVE_HISTORY_RETENTION_ENABLED: value }), false)
    }
    assert.deepEqual(getReceiveHistoryRetentionSchedule({}), { hour: 4, minute: 30 })
    assert.deepEqual(
        getReceiveHistoryRetentionSchedule({ RECEIVE_HISTORY_RETENTION_TIME: "03:15" }),
        { hour: 3, minute: 15 },
    )
    assert.deepEqual(
        getReceiveHistoryRetentionSchedule({ RECEIVE_HISTORY_RETENTION_TIME: "24:00" }),
        { hour: 4, minute: 30 },
    )
    const beforeDailyRun = new Date(2026, 7, 27, 4, 0, 0, 0)
    assert.equal(
        millisecondsUntilNextReceiveHistoryRetentionRun(beforeDailyRun, 4, 30),
        30 * 60 * 1000,
    )
    const afterDailyRun = new Date(2026, 7, 27, 4, 31, 0, 0)
    const nextDailyRun = new Date(2026, 7, 28, 4, 30, 0, 0)
    assert.equal(
        millisecondsUntilNextReceiveHistoryRetentionRun(afterDailyRun, 4, 30),
        nextDailyRun.getTime() - afterDailyRun.getTime(),
    )

    const db = createDatabase()
    const logs = []
    const logger = {
        log(message) { logs.push(message) },
        warn(message) { logs.push(message) },
    }
    try {
        insertHistory(db, 20, 510)
        const service = createReceiveHistoryRetentionService(db, {
            initialDelayMs: 0,
            pauseMs: 0,
            logger,
        })
        service.start()
        await waitUntil(() => countHistory(db, 20) === 500)
        await service.stop()
        assert.ok(logs.some(message => message.includes("deletedRows=10")))

        insertHistory(db, 20, 1)
        await new Promise(resolve => setTimeout(resolve, 30))
        assert.equal(countHistory(db, 20), 501)

        const disabled = createReceiveHistoryRetentionService(db, {
            enabled: false,
            initialDelayMs: 0,
            pauseMs: 0,
            logger,
        })
        disabled.start()
        await new Promise(resolve => setTimeout(resolve, 30))
        await disabled.stop()
        assert.equal(countHistory(db, 20), 501)
        assert.ok(logs.some(message => message.includes("retention disabled")))
    } finally {
        db.close()
    }
}

async function main() {
    await testPassAndIdempotency()
    await testBusyFailureIsIsolatedAndRetryable()
    await testAutomaticLifecycleAndEmergencySwitch()
    console.log("receive history retention tests passed")
}

main().catch(error => {
    console.error(error)
    process.exitCode = 1
})
