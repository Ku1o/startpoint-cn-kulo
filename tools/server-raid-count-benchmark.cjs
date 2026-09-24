const Database = require('better-sqlite3')
const { performance } = require('node:perf_hooks')
const path = require('node:path')
const fs = require('node:fs')
const root = path.resolve(process.argv[2] || path.join(__dirname, '..'))
const { getRaidQuestCounts } = require(path.join(root, 'out/lib/raid-event-counts'))
const results = []
for (const size of [10000, 100000]) {
    const db = new Database(':memory:')
    try {
        db.exec('CREATE TABLE raid_event_global_kill_ledger(event_id INTEGER, quest_id INTEGER, play_id TEXT UNIQUE); CREATE INDEX by_event ON raid_event_global_kill_ledger(event_id,quest_id)')
        const insert = db.prepare('INSERT INTO raid_event_global_kill_ledger VALUES (7, ?, ?)')
        db.transaction(() => {for (let i = 0; i < size; i++) insert.run(7000 + i % 8, String(i))})()
        const legacy = () => Object.fromEntries(db.prepare('SELECT quest_id, COUNT(*) AS kill_count FROM raid_event_global_kill_ledger WHERE event_id = ? GROUP BY quest_id ORDER BY quest_id').all(7)
            .map(row => [String(row.quest_id), {kill_count: row.kill_count}]))
        const initial = JSON.stringify(legacy())
        const first = performance.now()
        getRaidQuestCounts(db, 7)
        const bootstrapMs = performance.now() - first
        for (const mode of ['legacy', 'incremental']) {
            const begin = performance.now()
            for (let i = 0; i < 300; i++) {
                const actual = mode === 'legacy' ? legacy() : getRaidQuestCounts(db, 7)
                if (JSON.stringify(actual) !== initial) throw Error('Raid count mismatch')
            }
            results.push({size, mode, iterations: 300, elapsedMs: performance.now()-begin, bootstrapMs})
        }
    } finally {db.close()}
}
fs.writeFileSync(process.argv[3], JSON.stringify(results,null,2))
console.log(JSON.stringify(results,null,2))
