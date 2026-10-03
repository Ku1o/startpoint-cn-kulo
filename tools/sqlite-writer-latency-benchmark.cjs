'use strict'

/**
 * Measures main-thread event-loop delay while a write-heavy burst is executed.
 *
 * Usage:
 *   node tools/sqlite-writer-latency-benchmark.cjs                 # compare both modes
 *   node tools/sqlite-writer-latency-benchmark.cjs --mode=writer   # writer thread only
 *   node tools/sqlite-writer-latency-benchmark.cjs --mode=inprocess
 *
 * Both modes write the same rows into an isolated temporary database. The
 * comparison shows whether moving registered writes off the main thread
 * actually removes the blocking, and it does not touch `.database/`.
 */

const { spawnSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const repoRoot = path.resolve(__dirname, '..')
const commandModule = path.join(__dirname, 'writer-benchmark-commands.cjs')

function parseLength(name, fallback) {
    const match = process.argv.find(argument => argument.startsWith(`--${name}=`))
    if (!match) return fallback
    const value = Number(match.split('=')[1])
    return Number.isSafeInteger(value) && value > 0 ? value : fallback
}

function modeArg() {
    const match = process.argv.find(argument => argument.startsWith('--mode='))
    return match ? match.split('=')[1] : null
}

function percentile(sorted, fraction) {
    if (sorted.length === 0) return 0
    const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * fraction) - 1))
    return sorted[index]
}

async function runSingleMode(mode) {
    const { monitorEventLoopDelay, performance } = require('node:perf_hooks')
    const Database = require(path.join(repoRoot, 'node_modules', 'better-sqlite3'))

    const commandCount = parseLength('commands', 400)
    const concurrency = parseLength('concurrency', 16)
    const payloadBytes = parseLength('payload', 256)
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), `writer-benchmark-${mode}-`))
    const databasePath = path.join(tempRoot, 'bench.db')

    process.env.DATA_DIR = tempRoot
    process.env.SQLITE_WRITER_EXTRA_COMMANDS = commandModule
    if (mode === 'writer') {
        process.env.CN_WRITER_THREAD = '1'
    } else {
        delete process.env.CN_WRITER_THREAD
    }

    const setup = new Database(databasePath)
    setup.pragma('journal_mode = WAL')
    setup.exec('CREATE TABLE bench_writer (id INTEGER PRIMARY KEY AUTOINCREMENT, value INTEGER NOT NULL, payload TEXT NOT NULL)')
    setup.close()

    const { setDbOverride } = require(path.join(repoRoot, 'out', 'data', 'db.js'))
    const writerClient = require(path.join(repoRoot, 'out', 'lib', 'persistence', 'writer-client.js'))
    const { runWriterCommand } = require(path.join(repoRoot, 'out', 'lib', 'persistence-coordinator.js'))
    require(commandModule)

    let inProcessConnection = null
    if (mode === 'inprocess') {
        // Give the in-process path its own connection instead of running the
        // schema initializer, so both modes write through the same pragmas.
        const connection = new Database(databasePath)
        connection.pragma('journal_mode = WAL')
        connection.pragma('busy_timeout = 1000')
        setDbOverride(connection)
        inProcessConnection = connection
    } else {
        writerClient.startSqliteWriter(databasePath)
        await writerClient.waitForSqliteWriterReady(30_000)
    }

    const histogram = monitorEventLoopDelay({ resolution: 5 })
    histogram.enable()
    const payload = 'x'.repeat(payloadBytes)
    const startedAt = performance.now()
    let dispatched = 0
    const workers = []
    for (let index = 0; index < concurrency; index += 1) {
        workers.push((async () => {
            while (true) {
                const next = dispatched++
                if (next >= commandCount) return
                await runWriterCommand('bench.insert', { value: next, payload }, {
                    // Distinct player ids keep the per-player queue from
                    // serialising the whole burst.
                    domain: 'player',
                    playerId: next + 1,
                    operation: 'bench.insert',
                })
            }
        })())
    }
    await Promise.all(workers)
    const elapsedMs = performance.now() - startedAt
    histogram.disable()

    const stats = mode === 'writer' ? writerClient.sqliteWriterStats() : null
    const metrics = {
        mode,
        commands: commandCount,
        concurrency,
        payloadBytes,
        wallMs: Number(elapsedMs.toFixed(1)),
        commandsPerSecond: Math.round(commandCount / (elapsedMs / 1000)),
        loopDelayMeanMs: Number((histogram.mean / 1e6).toFixed(3)),
        loopDelayP50Ms: Number((percentileMs(histogram, 0.5)).toFixed(3)),
        loopDelayP99Ms: Number((percentileMs(histogram, 0.99)).toFixed(3)),
        loopDelayMaxMs: Number((histogram.max / 1e6).toFixed(3)),
        batches: stats ? stats.batches : null,
        maxBatchSize: stats ? stats.maxBatchSize : null,
        commitMsTotal: stats ? Number(stats.totalCommitMs.toFixed(1)) : null,
    }

    if (mode === 'writer') await writerClient.stopSqliteWriter()
    // Windows keeps the temporary directory locked while a connection is open.
    try { inProcessConnection?.close() } catch { /* already closed */ }
    fs.rmSync(tempRoot, { recursive: true, force: true })
    return metrics
}

function percentileMs(histogram, fraction) {
    const nanoseconds = histogram.percentile(fraction * 100)
    return nanoseconds / 1e6
}

function main() {
    const mode = modeArg()
    if (mode === 'writer' || mode === 'inprocess') {
        runSingleMode(mode).then(metrics => {
            // The server's own log lines share stdout, so the parent parses a
            // marked line instead of the whole stream.
            console.log(`__BENCH__${JSON.stringify(metrics)}`)
        }).catch(error => {
            console.error(error)
            process.exit(1)
        })
        return
    }
    // Parent mode: run each measurement in a fresh process so module state and
    // environment cannot leak between the two configurations.
    const results = []
    // Forward the tuning flags so `--commands`/`--concurrency` apply to both
    // measurements instead of silently falling back to the defaults.
    const forwarded = process.argv
        .slice(2)
        .filter(argument => !argument.startsWith('--mode='))
    for (const child of ['writer', 'inprocess']) {
        const run = spawnSync(process.execPath, [__filename, `--mode=${child}`, ...forwarded], {
            cwd: repoRoot,
            encoding: 'utf8',
            stdio: ['ignore', 'pipe', 'inherit'],
        })
        if (run.status !== 0) {
            console.error(`benchmark mode ${child} failed`)
            process.exit(run.status ?? 1)
        }
        const line = run.stdout.split(/\r?\n/).find(entry => entry.startsWith('__BENCH__'))
        if (!line) {
            console.error(`benchmark mode ${child} produced no result`)
            console.error(run.stdout)
            process.exit(1)
        }
        results.push(JSON.parse(line.slice('__BENCH__'.length)))
    }
    for (const metrics of results) {
        console.log(
            `${metrics.mode.padEnd(9)} commands=${metrics.commands} `
            + `wall=${metrics.wallMs}ms throughput=${metrics.commandsPerSecond}/s `
            + `loopP50=${metrics.loopDelayP50Ms}ms loopP99=${metrics.loopDelayP99Ms}ms `
            + `loopMax=${metrics.loopDelayMaxMs}ms `
            + (metrics.batches === null ? '' : `batches=${metrics.batches} maxBatch=${metrics.maxBatchSize}`),
        )
    }
}

main()
