const Database = require('better-sqlite3')
const { performance } = require('node:perf_hooks')
const { getRaidQuestCount } = require('../out/lib/raid-event-counts')

const rows = Math.max(10_000, Number(process.env.PERF_RAID_ROWS || 100_000))
const iterations = Math.max(10, Number(process.env.PERF_RAID_ITERATIONS || 300))
const database = new Database(':memory:')

try {
    database.exec(`
        CREATE TABLE raid_event_global_kill_ledger (
            event_id INTEGER NOT NULL,
            quest_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            play_id TEXT NOT NULL UNIQUE
        );
        CREATE INDEX by_event_quest
            ON raid_event_global_kill_ledger(event_id, quest_id);
        CREATE INDEX by_player_event_quest
            ON raid_event_global_kill_ledger(player_id, event_id, quest_id);
    `)
    const insert = database.prepare(`
        INSERT INTO raid_event_global_kill_ledger
            (event_id, quest_id, player_id, play_id)
        VALUES (7, ?, ?, ?)
    `)
    database.transaction(() => {
        for (let index = 0; index < rows; index++) {
            insert.run(7001 + index % 26, 1 + index % 2_000, String(index))
        }
    })()

    const expected = database.prepare(`
        SELECT COUNT(*)
        FROM raid_event_global_kill_ledger
        WHERE event_id = 7 AND quest_id = 7002
    `).pluck().get()
    const legacy = () => Object.fromEntries(database.prepare(`
        SELECT quest_id, COUNT(*) AS kill_count
        FROM raid_event_global_kill_ledger
        WHERE event_id = 7
        GROUP BY quest_id
    `).all().map(row => [String(row.quest_id), row.kill_count]))
    const playerCounts = indexed => database.prepare(`
        SELECT quest_id, COUNT(*) AS clear_count
        FROM raid_event_global_kill_ledger ${indexed ? '' : 'NOT INDEXED'}
        WHERE player_id = 1 AND event_id = 7
        GROUP BY quest_id
    `).all()
    const expectedPlayerCounts = JSON.stringify(playerCounts(true))

    function measure(operation) {
        const cpu = process.cpuUsage()
        const started = performance.now()
        for (let index = 0; index < iterations; index++) operation()
        const used = process.cpuUsage(cpu)
        return {
            wallMs: performance.now() - started,
            cpuMs: (used.user + used.system) / 1_000,
        }
    }

    const legacyResult = measure(() => {
        if (legacy()['7002'] !== expected) throw new Error('legacy count mismatch')
    })
    const indexedResult = measure(() => {
        if (getRaidQuestCount(database, 7, 7002) !== expected) {
            throw new Error('indexed count mismatch')
        }
    })
    const playerScanResult = measure(() => {
        if (JSON.stringify(playerCounts(false)) !== expectedPlayerCounts) {
            throw new Error('player scan mismatch')
        }
    })
    const playerIndexedResult = measure(() => {
        if (JSON.stringify(playerCounts(true)) !== expectedPlayerCounts) {
            throw new Error('player index mismatch')
        }
    })
    const singlePlan = database.prepare(`
        EXPLAIN QUERY PLAN
        SELECT COUNT(*)
        FROM raid_event_global_kill_ledger
        WHERE event_id = 7 AND quest_id = 7002
    `).all().map(row => row.detail)
    const playerPlan = database.prepare(`
        EXPLAIN QUERY PLAN
        SELECT quest_id, COUNT(*)
        FROM raid_event_global_kill_ledger
        WHERE player_id = 1 AND event_id = 7
        GROUP BY quest_id
    `).all().map(row => row.detail)

    function measureInsert(includePlayerIndex) {
        const candidate = new Database(':memory:')
        try {
            candidate.exec(`
                CREATE TABLE ledger (
                    event_id INTEGER NOT NULL,
                    quest_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    play_id TEXT NOT NULL UNIQUE
                );
                CREATE INDEX event_quest ON ledger(event_id, quest_id);
            `)
            if (includePlayerIndex) {
                candidate.exec('CREATE INDEX player_event_quest ON ledger(player_id, event_id, quest_id)')
            }
            const write = candidate.prepare('INSERT INTO ledger VALUES (7, ?, ?, ?)')
            const cpu = process.cpuUsage()
            const started = performance.now()
            candidate.transaction(() => {
                for (let index = 0; index < rows; index++) {
                    write.run(7001 + index % 26, 1 + index % 2_000, String(index))
                }
            })()
            const used = process.cpuUsage(cpu)
            return {
                wallMs: performance.now() - started,
                cpuMs: (used.user + used.system) / 1_000,
            }
        } finally {
            candidate.close()
        }
    }
    const insertWithoutPlayerIndex = measureInsert(false)
    const insertWithPlayerIndex = measureInsert(true)

    console.log(JSON.stringify({
        rows,
        iterations,
        expected,
        legacy: legacyResult,
        indexed: indexedResult,
        cpuReductionPct: (1 - indexedResult.cpuMs / legacyResult.cpuMs) * 100,
        playerScan: playerScanResult,
        playerIndexed: playerIndexedResult,
        playerCpuReductionPct: (1 - playerIndexedResult.cpuMs / playerScanResult.cpuMs) * 100,
        insertWithoutPlayerIndex,
        insertWithPlayerIndex,
        insertCpuIncreasePct: (
            insertWithPlayerIndex.cpuMs / insertWithoutPlayerIndex.cpuMs - 1
        ) * 100,
        singlePlan,
        playerPlan,
    }, null, 2))
} finally {
    database.close()
}
