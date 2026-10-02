const test = require('node:test')
const assert = require('node:assert/strict')
const Database = require('better-sqlite3')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { getRaidQuestCounts } = require('../out/lib/raid-event-counts')

test('incremental raid counts follow inserts, duplicates, rollback, reset and external writers', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'raid-count-cache-'))
    const filename = path.join(dir, 'fixture.sqlite')
    const db = new Database(filename)
    let other
    try {
        db.pragma('journal_mode = WAL')
        db.exec('CREATE TABLE raid_event_global_kill_ledger(event_id INTEGER, quest_id INTEGER, play_id TEXT UNIQUE)')
        const schema = db.prepare('SELECT name, sql FROM sqlite_master ORDER BY name').all()
        const insert = db.prepare('INSERT OR IGNORE INTO raid_event_global_kill_ledger VALUES (?, ?, ?)')
        const check = event => assert.deepEqual(getRaidQuestCounts(db, event), Object.fromEntries(
            db.prepare('SELECT quest_id, COUNT(*) AS n FROM raid_event_global_kill_ledger WHERE event_id = ? GROUP BY quest_id ORDER BY quest_id')
                .all(event).map(row => [String(row.quest_id), {kill_count: row.n}]),
        ))
        assert.throws(() => db.transaction(() => { check(7); insert.run(7, 10, 'rollback-schema'); check(7); throw Error('rollback') })(), /rollback/)
        check(7)
        insert.run(7, 10, 'a'); insert.run(7, 10, 'a'); insert.run(7, 11, 'b'); insert.run(8, 12, 'c')
        check(7); check(8)
        assert.throws(() => db.transaction(() => { insert.run(7, 10, 'rollback-row'); check(7); throw Error('rollback') })(), /rollback/)
        check(7)
        db.prepare('UPDATE raid_event_global_kill_ledger SET event_id = 9, quest_id = 42 WHERE play_id = ?').run('b')
        check(7); check(9)
        other = new Database(filename)
        other.prepare('INSERT INTO raid_event_global_kill_ledger VALUES (7, 10, ?)').run('external')
        check(7); check(8)
        db.prepare('DELETE FROM raid_event_global_kill_ledger WHERE event_id = ?').run(7)
        check(7)
        insert.run(7, 10, 'restart-event'); check(7)
        assert.deepEqual(db.prepare('SELECT name, sql FROM sqlite_master ORDER BY name').all(), schema)
    } finally {
        other?.close(); db.close()
        assert.equal(path.dirname(fs.realpathSync(dir)), fs.realpathSync(os.tmpdir()))
        fs.rmSync(dir, {recursive: true})
    }
})
