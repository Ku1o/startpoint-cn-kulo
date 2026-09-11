const { test } = require('node:test')
const assert = require('node:assert/strict')
const { CoalescedDiagnostics } = require('../out/lib/coalesced-diagnostics')

test('retries build context once, summarize exact counts, and allow fresh evidence next window', () => {
    const messages = []
    const log = new CoalescedDiagnostics('[REPEAT]', 60000, 3, line => messages.push(line))
    let queries = 0
    for (let i = 0; i < 100; i++) log.report('same-run', () => { queries++; return 'first evidence' })
    assert.equal(queries, 1)
    assert.deepEqual(messages, ['first evidence'])
    log.flush()
    assert.deepEqual(JSON.parse(messages[1].slice('[REPEAT] '.length)).repeats,
        [{ key: 'same-run', suppressed: 99 }])
    log.report('same-run', () => { queries++; return 'new evidence' })
    assert.equal(queries, 2)
    log.flush()
})

test('distinct-key floods have bounded context reads and report overflow without evicting recent keys', () => {
    const messages = []
    const log = new CoalescedDiagnostics('[REPEAT]', 60000, 3, line => messages.push(line))
    let queries = 0
    for (let i = 0; i < 1000; i++) log.report(`run-${i}`, () => { queries++; return `evidence-${i}` })
    log.report('run-0', () => assert.fail('overflow must not evict the first identity'))
    assert.equal(queries, 3)
    log.flush()
    const summary = JSON.parse(messages[3].slice('[REPEAT] '.length))
    assert.equal(summary.overflow, 997)
    assert.deepEqual(summary.repeats, [{ key: 'run-0', suppressed: 1 }])
})

test('context failure preserves the gameplay error and a single timer eventually drains retries', async () => {
    const messages = []
    const log = new CoalescedDiagnostics('[REPEAT]', 10, 3, line => messages.push(line))
    log.report('broken', () => { throw new Error('database context unavailable') })
    assert.equal(JSON.parse(messages[0].slice('[REPEAT] '.length)).contextUnavailable, true)
    log.report('broken', () => assert.fail('failed context must also be coalesced'))
    await new Promise(resolve => setTimeout(resolve, 30))
    assert.equal(messages.length, 2)
    assert.equal(JSON.parse(messages[1].slice('[REPEAT] '.length)).repeats[0].suppressed, 1)
    log.flush()
})

test('an unavailable log sink cannot throw into a gameplay request or a summary timer', () => {
    const log = new CoalescedDiagnostics('[REPEAT]', 60000, 3, () => { throw new Error('log sink failed') })
    assert.doesNotThrow(() => log.report('run', () => 'context'))
    log.report('run', () => assert.fail('coalesced'))
    assert.doesNotThrow(() => log.flush())
})
