'use strict'

/**
 * Commands used by tools/sqlite-writer-latency-benchmark.cjs.
 *
 * Kept outside the test helpers so the benchmark can be run on any machine
 * without loading the test suite.
 */

const { registerWriterCommand } = require('../out/lib/persistence/command-registry.js')
const { getDb } = require('../out/data/db.js')

registerWriterCommand('bench.insert', args => {
    getDb()
        .prepare('INSERT INTO bench_writer (value, payload) VALUES (?, ?)')
        .run(Number(args.value), String(args.payload))
    return { inserted: Number(args.value) }
})
