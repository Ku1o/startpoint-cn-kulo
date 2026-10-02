const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { MemoryLogSummary, analyzeFiles, renderReport } = require('../tools/analyze-memory-log.cjs')
const MiB = 1048576
const line = (uptimeSeconds, overrides = {}) => `[MEM] ${JSON.stringify({
    pid:4420, uptimeSeconds, rss:100 * MiB, main:{heapUsed:10 * MiB}, ...overrides,
})}`
const metric = (run, name) => run.metrics.find(value => value.name === name)

test('summary separates RSS, thread heaps and containers while excluding cumulative counts', () => {
    const summary = new MemoryLogSummary()
    for (const [time, extra] of [[100,0],[3700,1]]) summary.addLine(line(time, {
        rss:(100 + extra * 50) * MiB,
        main:{heapUsed:(10 + extra * 2) * MiB},
        workers:[{name:'seedPersistence',threadId:2,ageMs:60000,stale:false,
            memory:{heapUsed:(15 + extra * 30) * MiB}, counters:{entries:10 + extra * 5, writeCount:1 + extra * 10000}}],
        counters:{npcPool:{entries:50+extra},sqlStatements:{hits:10+extra*100000},seedQueue1:{revision:1+extra,savedRevision:1+extra}},
    }))
    const run = summary.report().runs[0]
    assert.equal(metric(run,'rss').perHour,50 * MiB)
    assert.equal(metric(run,'worker.seedPersistence#2.heapUsed').delta,30 * MiB)
    assert.equal(metric(run,'worker.seedPersistence#2.counters.entries').delta,5)
    assert.equal(metric(run,'counters.npcPool.entries').delta,1)
    assert.equal(run.metrics.some(m=>/writeCount|hits|savedRevision|revision/.test(m.name)),false)
    assert.match(renderReport(summary.report()), /50\.00 MiB/)
})
test('PID changes and uptime resets do not mix growth; wall-clock rollback alone does not split a run', () => {
    const summary = new MemoryLogSummary()
    summary.addLine(line(100,{timestamp:'2026-09-18T00:00:00Z'}))
    summary.addLine(line(200,{timestamp:'2025-01-01T00:00:00Z'}))
    summary.addLine(line(1))
    summary.addLine(line(20,{pid:5520}))
    const report = summary.report()
    assert.equal(report.runs.length,3)
    assert.equal(report.runs[0].samples,2)
    assert.equal(metric(report.runs[1],'rss').perHour,null)
})
test('stale samples, duplicate lines and different worker generations cannot create false growth', () => {
    const summary = new MemoryLogSummary()
    const worker = (threadId, stale, heap) => ({name:'npcPool',threadId,stale,ageMs:stale?180000:60000,memory:{heapUsed:heap}})
    summary.addLine(line(60,{workers:[worker(2,false,100)]}))
    summary.addLine(line(60,{workers:[worker(2,false,100)]}))
    summary.addLine(line(120,{workers:[worker(2,true,10000)]}))
    summary.addLine(line(180,{workers:[worker(3,false,900)]}))
    summary.addLine('unrelated line')
    summary.addLine('[MEM] sample unavailable')
    summary.addLine('[MEM] null')
    const report = summary.report(), run = report.runs[0]
    assert.equal(report.invalidSamples,2)
    assert.equal(report.duplicateSamples,1)
    assert.equal(run.unavailableWorkerSamples,1)
    assert.equal(metric(run,'worker.npcPool#2.heapUsed').delta,0)
    assert.equal(metric(run,'worker.npcPool#3.heapUsed').perHour,null)
})
test('summary retains bounded process and metric state', () => {
    const summary = new MemoryLogSummary()
    for (let pid=1;pid<=40;pid++) summary.addLine(line(60,{pid}))
    assert.equal(summary.runs.length,32)
    assert.equal(summary.active.size,32)
    assert.equal(summary.report().discardedRuns,8)
    const counters = Object.fromEntries(Array.from({length:32},(_,i)=>['provider'+i,
        Object.fromEntries(Array.from({length:64},(_,j)=>['count'+j,j]))]))
    summary.addLine(line(120,{pid:40,counters}))
    assert.equal(summary.report().runs.at(-1).metrics.length,384)
    assert.ok(summary.report().runs.at(-1).omittedMetrics>0)
})

test('OS memory ignores failed and stale measurements; SQL totals cannot masquerade as retained objects', () => {
    const summary=new MemoryLogSummary()
    const os=(privateBytes,stale=false,failed=false)=>({available:true,ageMs:60000,stale,failed,
        memory:{privateBytes,workingSetBytes:80*MiB,virtualBytes:300*MiB,handleCount:20,threadCount:5,
            regions:{privateCommittedBytes:privateBytes,mappedCommittedBytes:20*MiB,regionCount:200}}})
    summary.addLine(line(60,{osProcess:os(100*MiB)}))
    summary.addLine(line(120,{osProcess:os(900*MiB,true)}))
    summary.addLine(line(180,{osProcess:os(900*MiB,false,true)}))
    summary.addLine(line(660,{osProcess:os(120*MiB),counters:{'sqlite.main':{
        prepareCalls:100000,prepareErrors:2,sampledPrepareCalls:2000,sampledPrepareMs:9000,
        maxSampledPrepareMs:12,page_size:4096,nativeBytesAvailable:false,
        executeCalls:1000000,executeErrors:5,busyErrors:2,sampledExecuteCalls:100,
        sampledExecuteMs:300,maxSampledExecuteMs:9,busy_timeout:1000,synchronous:2,wal_autocheckpoint:1000},
        responseWorkers:{completed:10000,fallback:20,rejected:20,failed:1,timeouts:1,maxPending:16,
            maxBytes:33554432,retainedBytes:1024,active:1},stdio:{stdoutQueuedBytes:64}},
        workers:[{name:'npc',threadId:2,ageMs:10,stale:false,memory:{heapUsed:10},
            diagnostics:{'sqlite.npc':{prepareCalls:10000},stdio:{stdoutQueuedBytes:32}}}]}))
    const run=summary.report().runs[0]
    assert.equal(metric(run,'osProcess.privateBytes').delta,20*MiB)
    assert.equal(metric(run,'osProcess.privateBytes').samples,2)
    assert.equal(metric(run,'osProcess.threadCount').last,5)
    assert.equal(metric(run,'osProcess.regions.privateCommittedBytes').delta,20*MiB)
    assert.equal(metric(run,'osProcess.regions.mappedCommittedBytes').last,20*MiB)
    assert.equal(run.metrics.some(m=>/prepare|Prepare|page_size|execute|Execute|busyErrors|busy_timeout|synchronous|wal_autocheckpoint/.test(m.name)),false)
    assert.equal(run.metrics.some(m=>/completed|fallback|rejected|failed|timeouts|maxPending|maxBytes/.test(m.name)),false)
    assert.equal(metric(run,'counters.responseWorkers.retainedBytes').last,1024)
    assert.equal(metric(run,'counters.stdio.stdoutQueuedBytes').last,64)
    assert.equal(metric(run,'worker.npc#2.diagnostics.stdio.stdoutQueuedBytes').last,32)
})
test('file reader accepts prefixed CRLF logs, rejects missing files and explains old logs', async () => {
    const directory=fs.mkdtempSync(path.join(os.tmpdir(),'memory-log-analysis-'))
    try {
        const file=path.join(directory,'sample.log')
        fs.writeFileSync(file,`prefix ${line(60)}\r\n${line(120,{rss:101*MiB})}\r\n`)
        const report=await analyzeFiles([file])
        assert.equal(report.runs[0].samples,2)
        assert.equal(metric(report.runs[0],'rss').delta,MiB)
        assert.equal(metric(report.runs[0],'rss').perHour,null, 'short bursts must not be extrapolated into hourly growth')
        await assert.rejects(analyzeFiles([path.join(directory,'missing.log')]),{code:'ENOENT'})
        assert.match(renderReport(new MemoryLogSummary().report()),/旧版日志/)
    } finally {
        assert.equal(path.dirname(fs.realpathSync(directory)),fs.realpathSync(os.tmpdir()))
        assert.match(path.basename(directory),/^memory-log-analysis-/)
        fs.rmSync(directory,{recursive:true})
    }
})
