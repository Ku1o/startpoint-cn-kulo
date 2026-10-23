'use strict'
// Foreground local admin/API exercise only. All state remains in the generated run.
const path = require('node:path'), fs = require('node:fs'), assert = require('node:assert/strict')
const repo = path.resolve(__dirname, '..'), load = name => require(path.join(repo, 'out', name))
async function main() {
    assert.equal(process.env.CN_RUNTIME_IMPORT_ONLY, '1')
    assert.equal(fs.realpathSync(path.dirname(load('data/db').getDb().name)), fs.realpathSync(process.env.DATA_DIR))
    const app = load('cn-server').fastify, writer = load('lib/persistence/writer-client')
    process.env.CN_WRITER_THREAD = '1'
    assert.equal(writer.startSqliteWriter(load('data/db').getDb().name), true)
    assert.equal(await writer.waitForSqliteWriterReady(30000), true)
    await app.listen({ host: '127.0.0.1', port: 0 })
    const address = app.server.address()
    assert.ok(![8001, 8011].includes(address.port))
    console.log(JSON.stringify({ status: 'ready', url: `http://127.0.0.1:${address.port}/admin/`, password: process.env.ADMIN_PANEL_PASSWORD, database: load('data/db').getDb().name, limitations: 'synthetic players; loopback only; no multiplayer transport or background schedulers; source 8001 unchanged' }))
    if (process.send) process.send({ type: 'isolated:ready', host: address.address, port: address.port })
}
main().catch(error => { console.error(error); process.exit(1) })
