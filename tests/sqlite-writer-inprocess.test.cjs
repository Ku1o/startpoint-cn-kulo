'use strict'

const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'startpoint-writer-inprocess-'))
process.env.DATA_DIR = tempRoot
delete process.env.CN_WRITER_THREAD

require(path.join(__dirname, 'helpers', 'writer-test-commands.cjs'))
const { runWriterCommand } = require('../out/lib/persistence-coordinator.js')

// This suite is the rollback path: with CN_WRITER_THREAD unset nothing may be
// dispatched to a worker, and the same registry entry must run here instead.
test('commands run in-process when the writer thread is disabled', async () => {
    const result = await runWriterCommand(
        'test.pure',
        { value: 7 },
        { domain: 'player', operation: 'test.pure' },
    )
    assert.deepEqual(result, { value: 7, thread: 'main' })
})

test('an unregistered command fails with a clear error', async () => {
    await assert.rejects(
        runWriterCommand('test.not_registered', {}, { domain: 'player', operation: 'test.not_registered' }),
        /not registered/,
    )
})

console.log('sqlite writer in-process tests passed')
