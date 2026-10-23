'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const path = require('node:path'), { test } = require('node:test'), assert = require('node:assert/strict')
const { explainContentHistoryReadiness } = require(path.join(__dirname, '..', compiled ? 'out' : 'src', 'lib/content-history-readiness'))
const passed = { status: 'passed', blockers: [] }

test('unreviewed primary action keeps its specific review reason without becoming blocked', () => {
    const row = { key: 'raid_event:1', actions: { visible: passed,
        enter: { status: 'unreviewed', blockers: [{ code: 'native_route_review', message: '尚需核对箱池入口与原生关卡路由' }] } } }
    assert.deepEqual(explainContentHistoryReadiness(row, ['visible', 'enter']), {
        status: 'unreviewed', reasons: ['尚需核对箱池入口与原生关卡路由'] })
})

test('only an explicit blocked required action blocks the requested entrance', () => {
    const row = { key: 'raid_event:1', staticStatus: 'blocked', actions: { visible: passed, enter: passed,
        claim: { status: 'blocked', blockers: [{ code: 'claim_review', message: '累计奖励规则尚未实现' }] } } }
    assert.deepEqual(explainContentHistoryReadiness(row, ['visible', 'enter']), { status: 'passed', reasons: [] })
    assert.deepEqual(explainContentHistoryReadiness(row, ['claim']), {
        status: 'blocked', reasons: ['累计奖励规则尚未实现'] })
})
