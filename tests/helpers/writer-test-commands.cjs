'use strict'

/**
 * Writer-thread test commands.
 *
 * The module is loaded twice: the test process requires it for the in-process
 * path, and the writer worker loads the same file through
 * SQLITE_WRITER_EXTRA_COMMANDS. Every handler therefore runs unchanged on both
 * execution paths.
 */

const { isMainThread } = require('node:worker_threads')
const { registerWriterCommand } = require('../../out/lib/persistence/command-registry.js')
const { getDb } = require('../../out/data/db.js')
const { getServerTime, getTimeOffset } = require('../../out/utils.js')

const effects = []

function insertValue(value) {
    getDb().prepare('INSERT INTO writer_test (value) VALUES (?)').run(String(value))
}

registerWriterCommand('test.insert', args => {
    insertValue(args.value)
    return { inserted: String(args.value) }
})

registerWriterCommand('test.insert_nested', args => {
    // Inside the writer batch this must degrade to a nested savepoint instead
    // of opening a second top-level transaction.
    getDb().transaction(() => { insertValue(args.value) }).immediate()
    return { inserted: String(args.value) }
})

registerWriterCommand('test.fail', args => {
    insertValue(args.value)
    throw new Error('intentional test failure')
})

registerWriterCommand('test.insert_with_effect', (args, context) => {
    insertValue(args.value)
    context.afterCommit(() => { effects.push(String(args.value)) })
    return { queued: true }
})

registerWriterCommand('test.fail_after_effect', (args, context) => {
    insertValue(args.value)
    context.afterCommit(() => { effects.push(`unexpected:${String(args.value)}`) })
    throw new Error('intentional failure after registering an effect')
})

registerWriterCommand('test.effect_log', () => effects.slice())

registerWriterCommand('test.non_cloneable', args => {
    insertValue(args.value)
    // structuredClone rejects functions, so the command must roll back rather
    // than commit a write whose result can never reach the caller.
    return { fn: () => 1 }
})

registerWriterCommand('test.rows', () => (
    getDb().prepare('SELECT value FROM writer_test ORDER BY id').all().map(row => row.value)
))

registerWriterCommand('test.pure', args => ({
    value: args.value,
    thread: isMainThread ? 'main' : 'worker',
}))

// The writer thread owns its own copy of the clock module, so the command
// reports the time it would use for settlement timestamps.
registerWriterCommand('test.clock', () => ({
    thread: isMainThread ? 'main' : 'worker',
    serverTime: getServerTime(),
    offset: getTimeOffset(),
}))

registerWriterCommand('test.slow', args => {
    const deadline = Date.now() + Math.max(0, Number(args.ms) || 0)
    while (Date.now() < deadline) { /* keep the writer thread busy */ }
    return { sleptMs: Number(args.ms) || 0 }
})
