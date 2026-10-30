'use strict'
const assert = require('node:assert/strict')
const http = require('node:http')
const { performance } = require('node:perf_hooks')

// The client has its own event loop. A stalled server cannot also stall the
// producer of this measurement and make missing requests disappear.
async function client(port) {
    const agent = new http.Agent({ keepAlive: true, maxSockets: 1 })
    const samples = []
    let stopping = false, ready = false
    process.on('message', message => { if (message.type === 'stop') stopping = true })
    try {
        while (!stopping) {
            const start = performance.now()
            const sample = await new Promise((resolve, reject) => {
                const request = http.get({ hostname: '127.0.0.1', port, path: '/probe', agent }, response => {
                    let body = ''
                    response.setEncoding('utf8')
                    response.on('data', value => { body += value })
                    response.once('end', () => {
                        try {
                            assert.equal(response.statusCode, 200)
                            resolve({ ...JSON.parse(body), elapsedMs: performance.now() - start, receivedNs: process.hrtime.bigint().toString() })
                        } catch (error) { reject(error) }
                    })
                    response.once('error', reject)
                })
                request.setTimeout(2000, () => request.destroy(Error('HTTP probe exceeded the coarse 2 second ceiling')))
                request.once('error', reject)
            })
            samples.push(sample)
            if (!ready) { ready = true; process.send({ type: 'ready' }) }
        }
        process.send({ type: 'summary', samples })
    } finally {
        agent.destroy()
        process.disconnect()
    }
}

if (process.argv[2] === '--client') {
    client(Number(process.argv[3])).catch(error => { console.error(error); process.exitCode = 1 })
} else {
    const { test } = require('node:test')
    const fs = require('node:fs')
    const os = require('node:os')
    const path = require('node:path')
    const { spawn } = require('node:child_process')
    const Database = require('better-sqlite3')
    const out = process.env.STARPOINT_TEST_OUT_DIR
    if (!out) throw Error('Use the current isolated build via STARPOINT_TEST_OUT_DIR')
    const api = require(path.join(out, 'lib/admin-database-backup-worker'))

    test('independent HTTP client receives responses during real database copying', { timeout: 30000 }, async t => {
        const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-backup-http-'))
        const source = path.join(directory, 'source.db'), destination = path.join(directory, 'backup.db')
        let db, server, child, childClosed
        t.after(async () => {
            api.cancelActiveDatabaseBackups('responsiveness test cleanup')
            await api.drainDatabaseBackups()
            if (child && child.exitCode === null) child.kill()
            if (childClosed) await childClosed
            if (server?.listening) await new Promise(resolve => server.close(resolve))
            if (db?.open) db.close()
            assert.ok(path.resolve(directory).startsWith(path.resolve(os.tmpdir()) + path.sep))
            assert.ok(path.basename(directory).startsWith('sp-backup-http-'))
            fs.rmSync(directory, { recursive: true, force: true })
        })
        db = new Database(source)
        db.pragma('journal_mode=WAL')
        db.pragma('wal_autocheckpoint=0')
        db.exec('CREATE TABLE payloads(id INTEGER PRIMARY KEY, data BLOB)')
        const put = db.prepare('INSERT INTO payloads VALUES(?,?)'), payload = Buffer.alloc(3800, 11)
        const rows = 24576
        db.transaction(() => { for (let index = 0; index < rows; index++) put.run(index, payload) })()
        db.pragma('wal_checkpoint(TRUNCATE)')
        db.pragma('user_version=1')
        const databaseBytes = db.pragma('page_count', { simple: true }) * db.pragma('page_size', { simple: true })
        assert.ok(databaseBytes >= 64 * 1024 * 1024 && databaseBytes <= 128 * 1024 * 1024)

        let phase = 'idle', copyingObserved = false
        server = http.createServer((request, response) => {
            response.writeHead(200, { 'content-type': 'application/json' })
            response.end(JSON.stringify({ phase }))
        })
        await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
        child = spawn(process.execPath, [__filename, '--client', String(server.address().port)], { env: process.env, stdio: ['ignore', 'pipe', 'pipe', 'ipc'] })
        let output = ''
        child.stdout.on('data', value => { output += value })
        child.stderr.on('data', value => { output += value })
        childClosed = new Promise(resolve => child.once('exit', resolve))
        let readyResolve, summaryResolve, summaryReject
        const ready = new Promise(resolve => { readyResolve = resolve })
        const summary = new Promise((resolve, reject) => { summaryResolve = resolve; summaryReject = reject })
        // Attach immediately, so a client failure is always observed while the
        // backup is awaiting native work rather than becoming unhandled.
        const observedSummary = summary.then(value => ({ value }), error => ({ error }))
        child.on('message', message => {
            if (message.type === 'ready') readyResolve()
            if (message.type === 'summary') summaryResolve(message.samples)
        })
        child.once('error', summaryReject)
        child.once('exit', code => { if (code !== 0) summaryReject(Error(`HTTP child exited ${code}: ${output}`)) })
        const readyTimeout = setTimeout(() => { readyResolve(); summaryReject(Error(`HTTP client handshake timed out: ${output}`)) }, 10000)
        await ready
        clearTimeout(readyTimeout)

        phase = 'opening'
        const startNs = process.hrtime.bigint()
        const result = await api.backupDatabaseInWorker(source, destination, {
            onProgress(progress) {
                phase = progress.phase
                if (progress.phase === 'copying' && progress.remainingPages > 0) copyingObserved = true
            },
        })
        const endNs = process.hrtime.bigint()
        phase = 'completed'
        child.send({ type: 'stop' })
        const clientResult = await observedSummary
        if (clientResult.error) throw clientResult.error
        assert.equal(await childClosed, 0, output)
        const concurrent = clientResult.value.filter(sample => sample.phase === 'copying'
            && BigInt(sample.receivedNs) >= startNs && BigInt(sample.receivedNs) <= endNs)
        assert.equal(copyingObserved, true)
        assert.ok(concurrent.length >= 3, `expected multiple responses actually received during copying, got ${concurrent.length}`)
        const waits = concurrent.map(sample => sample.elapsedMs).sort((a, b) => a - b)
        const maximum = waits.at(-1), p95 = waits[Math.ceil(waits.length * 0.95) - 1]
        assert.ok(maximum < 2000, `maximum concurrent HTTP wait ${maximum.toFixed(1)}ms exceeded coarse 2 second ceiling`)
        assert.equal(result.quickCheck, 'ok')
        assert.equal(result.snapshot, true)
        const copy = new Database(destination, { readonly: true })
        try { assert.equal(copy.prepare('SELECT count(*) FROM payloads').pluck().get(), rows) } finally { copy.close() }
        console.log(`SYNTHETIC HTTP concurrency: database=${(databaseBytes / 1024 / 1024).toFixed(2)}MiB rows=${rows} requestsDuringCopy=${concurrent.length} requestsTotal=${clientResult.value.length} max=${maximum.toFixed(2)}ms p95=${p95.toFixed(2)}ms backup=${result.elapsedMs}ms result=${result.quickCheck}; loopback fixture only`)
    })
}
