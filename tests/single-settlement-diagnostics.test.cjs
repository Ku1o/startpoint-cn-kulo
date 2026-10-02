const test = require('node:test'), assert = require('node:assert/strict')
const { createSingleSettlementBodyTimer, drainSingleSettlementDiagnostics } = require('../out/lib/single-settlement-diagnostics')

test('body intervals are disjoint, drain once, and distinguish failed bodies from completed bodies', () => {
    drainSingleSettlementDiagnostics()
    const timer = createSingleSettlementBodyTimer(2, false)
    for (const phase of ['battle_facts','experience','mode_rewards','missions','awake','active','response']) timer.step(phase)
    timer.finish(true)
    timer.finish(false)
    const failed = createSingleSettlementBodyTimer(2, false)
    failed.step('missions')
    failed.finish(false)
    const entry = drainSingleSettlementDiagnostics()['2']
    assert.equal(entry.n, 2)
    assert.equal(entry.bodyErrors, 1)
    assert.equal(entry.phases.rewards.n, 2)
    assert.equal(entry.phases.response.n, 1)
    assert.ok(Math.abs(entry.totalMs - Object.values(entry.phases).reduce((sum,p) => sum+p.totalMs,0)) < 0.006)
    assert.deepEqual(drainSingleSettlementDiagnostics(), {})
})

test('untrusted category values stay bounded and the monitor switch disables collection', () => {
    for (let i=-100;i<100;i++) createSingleSettlementBodyTimer(i,false).finish(true)
    createSingleSettlementBodyTimer(NaN,false).finish(true)
    createSingleSettlementBodyTimer(12,true).finish(true)
    const values = drainSingleSettlementDiagnostics()
    assert.equal(Object.keys(values).length,30)
    assert.equal(values.five_boss.n,1)
    assert.ok(values.other.n > 100)
    const previous = process.env.ROUTE_PERF_SUMMARY
    try {
        process.env.ROUTE_PERF_SUMMARY='false'
        const timer=createSingleSettlementBodyTimer(2,false)
        timer.step('response');timer.finish(true)
        assert.deepEqual(drainSingleSettlementDiagnostics(),{})
    } finally {
        if(previous===undefined) delete process.env.ROUTE_PERF_SUMMARY
        else process.env.ROUTE_PERF_SUMMARY=previous
    }
})
