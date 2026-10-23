'use strict'
// Exercise the normal production startup branch using only supervised local sockets/state.
const path = require('node:path'), fs = require('node:fs'), assert = require('node:assert/strict')
const { createHash } = require('node:crypto')
assert.equal(process.env.CN_RUNTIME_IMPORT_ONLY, '0')
assert.equal(process.env.CN_LISTEN_HOST, '127.0.0.1'); assert.equal(process.env.CN_LISTEN_PORT, '0')
assert.equal(process.env.SESSION_HOST, '127.0.0.1'); assert.equal(process.env.SESSION_PORT, '0')
const app = require(path.resolve(__dirname, '../out/cn-server')).fastify
const db = require(path.resolve(__dirname, '../out/data/db')).getDb()
function protectedDigest() {
    const queries = [
        'SELECT id,free_mana,free_vmoney,vmoney FROM players ORDER BY id',
        'SELECT * FROM players_category_missions WHERE category=6 AND id=53 ORDER BY player_id',
        'SELECT * FROM players_category_mission_stages WHERE category=6 AND mission_id=53 ORDER BY player_id,id',
        'SELECT * FROM players_pass_cards ORDER BY player_id,event_id',
        'SELECT * FROM players_pass_card_rewards ORDER BY player_id,event_id,reward_id',
        'SELECT * FROM players_items WHERE id=14040 ORDER BY player_id',
        'SELECT * FROM players_active_quests ORDER BY player_id',
        'SELECT * FROM player_operation_receipts ORDER BY player_id,operation,request_key',
    ]
    return createHash('sha256').update(JSON.stringify(queries.map(sql => db.prepare(sql).all()))).digest('hex')
}
process.on('message', message => {
    if (message?.type === 'isolated:probe') process.send?.({ type: 'isolated:probe-result', protectedDigest: protectedDigest(), pooledExp: db.prepare('SELECT id,exp_pool FROM players ORDER BY id').all() })
})
const marker = path.join(process.env.CN_LOG_DIR, 'cn-server-ready.json'), deadline = Date.now() + 30000
const timer = setInterval(() => {
    if (Date.now() > deadline) { clearInterval(timer); console.error('Normal startup readiness timed out'); process.send?.({ type: 'starpoint:shutdown' }); process.exitCode = 1; void app.close(); return }
    if (!fs.existsSync(marker)) return
    clearInterval(timer)
    const ready = JSON.parse(fs.readFileSync(marker, 'utf8')), address = app.server.address()
    assert.equal(ready.pid, process.pid); assert.equal(address.address, '127.0.0.1')
    assert.ok(![8001, 8011].includes(address.port))
    assert.equal(fs.realpathSync(path.dirname(ready.database)), fs.realpathSync(process.env.DATA_DIR))
    console.log('ISOLATED_NORMAL_STARTUP_READY ' + JSON.stringify({ pid: process.pid, address, marker }))
    process.send?.({ type: 'isolated:ready', host: address.address, port: address.port, normalStartup: true, protectedDigest: protectedDigest(), pooledExp: db.prepare('SELECT id,exp_pool FROM players ORDER BY id').all() })
}, 25)
