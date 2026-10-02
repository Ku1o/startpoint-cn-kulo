#!/usr/bin/env node
// Read-only, streaming summary of the server's [MEM] diagnostics.
const fs = require('node:fs')
const readline = require('node:readline')

const MAX_RUNS = 32, MAX_METRICS = 384
const MEMORY_FIELDS = new Set(['heapUsed', 'heapTotal', 'external', 'arrayBuffers',
    'totalPhysicalHeap', 'mallocedMemory', 'nativeContexts', 'detachedContexts'])
const CUMULATIVE_FIELDS = new Set(['revision', 'savedRevision', 'writeCount', 'writeBytes',
    'batches', 'records', 'publishedEntries', 'fullRefreshes', 'hits', 'misses', 'evictions',
    'busyBypasses', 'perConnectionLimit', 'droppedBeforeReady', 'prepareCalls', 'prepareErrors',
    'sampledPrepareCalls', 'sampledPrepareMs', 'maxSampledPrepareMs', 'ageMs', 'pendingMs',
    'cache_size', 'page_size', 'mmap_size', 'temp_store', 'busy_timeout', 'synchronous', 'wal_autocheckpoint',
    'executeCalls', 'executeErrors', 'busyErrors', 'sampledExecuteCalls', 'sampledExecuteMs', 'maxSampledExecuteMs',
    'completed', 'failed', 'rejected', 'fallback', 'timeouts', 'maxPending', 'maxBytes'])

class MemoryLogSummary {
    constructor() {
        this.runs = []
        this.active = new Map()
        this.lines = 0
        this.invalidSamples = 0
        this.duplicateSamples = 0
        this.discardedRuns = 0
        this.sequence = 0
    }
    addLine(line) {
        this.lines++
        const marker = line.indexOf('[MEM] ')
        if (marker < 0) return
        let sample
        try { sample = JSON.parse(line.slice(marker + 6)) }
        catch { this.invalidSamples++; return }
        if (!sample || !Number.isSafeInteger(sample.pid) || sample.pid <= 0
            || !Number.isFinite(sample.uptimeSeconds) || sample.uptimeSeconds < 0
            || !Number.isFinite(sample.rss) || sample.rss <= 0) {
            this.invalidSamples++; return
        }
        let run = this.active.get(sample.pid)
        if (!run || sample.uptimeSeconds < run.lastUptime) {
            run = { id: ++this.sequence, pid: sample.pid, samples: 0,
                firstUptime: sample.uptimeSeconds, lastUptime: sample.uptimeSeconds,
                firstTimestamp: sample.timestamp, lastTimestamp: sample.timestamp,
                unavailableWorkerSamples: 0, omittedMetrics: 0, metrics: new Map() }
            this.runs.push(run)
            this.active.set(sample.pid, run)
            if (this.runs.length > MAX_RUNS) {
                const removed = this.runs.shift()
                if (this.active.get(removed.pid) === removed) this.active.delete(removed.pid)
                this.discardedRuns++
            }
        } else if (sample.uptimeSeconds === run.lastUptime) {
            this.duplicateSamples++; return
        }
        run.samples++
        run.lastUptime = sample.uptimeSeconds
        run.lastTimestamp = sample.timestamp
        const add = (name, value, unit, group) => {
            if (!Number.isFinite(value) || value < 0) return
            let metric = run.metrics.get(name)
            if (!metric) {
                if (run.metrics.size >= MAX_METRICS) { run.omittedMetrics++; return }
                metric = { name, unit, group, samples: 0, first: value, last: value,
                    min: value, max: value, firstUptime: sample.uptimeSeconds,
                    lastUptime: sample.uptimeSeconds }
                run.metrics.set(name, metric)
            }
            metric.samples++
            metric.last = value
            metric.min = Math.min(metric.min, value)
            metric.max = Math.max(metric.max, value)
            metric.lastUptime = sample.uptimeSeconds
        }
        const memory = (prefix, values) => {
            for (const field of MEMORY_FIELDS) {
                add(`${prefix}.${field}`, values?.[field], field.endsWith('Contexts') ? 'count' : 'bytes', 'memory')
            }
        }
        const counters = (prefix, values) => {
            if (!values || typeof values !== 'object' || values.unavailable === true) return
            for (const [key, value] of Object.entries(values).slice(0, 64)) {
                if (!CUMULATIVE_FIELDS.has(key)) {
                    add(`${prefix}.${key.slice(0, 80)}`, value, key.endsWith('Bytes') ? 'bytes' : 'count', 'container')
                }
            }
        }
        add('rss', sample.rss, 'bytes', 'memory')
        memory('main', sample.main)
        const os = sample.osProcess
        if (os?.available === true && os.stale === false && !os.failed
            && Number.isFinite(os.ageMs) && os.ageMs >= 0 && os.ageMs <= 120000) {
            for (const field of ['privateBytes', 'workingSetBytes', 'virtualBytes']) {
                add(`osProcess.${field}`, os.memory?.[field], 'bytes', 'memory')
            }
            for (const field of ['handleCount', 'threadCount']) {
                add(`osProcess.${field}`, os.memory?.[field], 'count', 'container')
            }
            for (const field of ['privateCommittedBytes', 'mappedCommittedBytes', 'imageCommittedBytes',
                'otherCommittedBytes', 'reservedBytes']) {
                add(`osProcess.regions.${field}`, os.memory?.regions?.[field], 'bytes', 'memory')
            }
            add('osProcess.regions.regionCount', os.memory?.regions?.regionCount, 'count', 'container')
        }
        for (const worker of (Array.isArray(sample.workers) ? sample.workers : []).slice(0, 16)) {
            if (!worker || typeof worker.name !== 'string' || !Number.isSafeInteger(worker.threadId)) continue
            const prefix = `worker.${worker.name.slice(0, 80)}#${worker.threadId}`
            if (!worker.memory || worker.stale === true || !Number.isFinite(worker.ageMs) || worker.ageMs > 120000) {
                run.unavailableWorkerSamples++
                continue
            }
            memory(prefix, worker.memory)
            counters(`${prefix}.counters`, worker.counters)
            for (const [name, values] of Object.entries(worker.diagnostics ?? {}).slice(0, 32)) {
                counters(`${prefix}.diagnostics.${name.slice(0, 80)}`, values)
            }
        }
        if (sample.counters && typeof sample.counters === 'object') {
            for (const [name, values] of Object.entries(sample.counters).slice(0, 32)) {
                counters(`counters.${name.slice(0, 80)}`, values)
            }
        }
    }
    report() {
        return { lines: this.lines, invalidSamples: this.invalidSamples,
            duplicateSamples: this.duplicateSamples, discardedRuns: this.discardedRuns,
            runs: this.runs.map(run => ({ ...run, metrics: [...run.metrics.values()].map(metric => ({
                ...metric, delta: metric.last - metric.first,
                perHour: metric.lastUptime - metric.firstUptime >= 600
                    ? (metric.last - metric.first) * 3600 / (metric.lastUptime - metric.firstUptime) : null,
            })) })) }
    }
}

async function analyzeFiles(files) {
    const summary = new MemoryLogSummary()
    // Files must be supplied in chronological order; no whole-file buffering.
    for (const file of files) {
        const input = fs.createReadStream(file, { encoding: 'utf8' })
        const lines = readline.createInterface({ input, crlfDelay: Infinity })
        try { for await (const line of lines) summary.addLine(line) }
        finally { lines.close(); input.destroy() }
    }
    return summary.report()
}
function renderReport(report) {
    if (report.runs.length === 0) return '未发现有效的 [MEM] 采样。旧版日志不含线程诊断数据；部署新监测后再分析 stderr 日志。'
    const output = ['# 服务端内存变化报告', '',
        '数值只描述观察区间，不能单独认定泄漏。文件须按时间先后传入；PID 或运行时长回退会分段。',
        '累计写入、SQL 命中等计数不参与增长排名；过期 worker 样本不作为当前内存；不足 10 分钟不估算每小时变化。', '']
    const format = (value, unit) => value === null ? '—' : unit === 'bytes' ? `${(value / 1048576).toFixed(2)} MiB` : value.toFixed(2).replace(/\.00$/, '')
    const safe = name => name.replace(/[|\r\n`]/g, '_')
    for (const run of report.runs) {
        output.push(`## PID ${run.pid} · 片段 ${run.id}`, '',
            `采样 ${run.samples} 次，观察 ${run.lastUptime - run.firstUptime} 秒；跳过不可用/过期线程样本 ${run.unavailableWorkerSamples} 次。`, '')
        for (const [group, title] of [['memory', '内存指标'], ['container', '容器与队列（增长量最大的前 12 项）']]) {
            const metrics = run.metrics.filter(metric => metric.group === group)
                .sort((a, b) => b.delta - a.delta || a.name.localeCompare(b.name))
            const shown = group === 'container' ? metrics.filter(metric => metric.delta > 0).slice(0, 12) : metrics
            output.push(`### ${title}`, '')
            if (!shown.length) { output.push('未观察到可比较的正向增长。', ''); continue }
            output.push('| 指标 | 首次 | 最后 | 增量 | 每小时变化 | 最小～最大 |', '| --- | ---: | ---: | ---: | ---: | ---: |')
            for (const metric of shown) {
                output.push(`| ${safe(metric.name)} | ${format(metric.first, metric.unit)} | ${format(metric.last, metric.unit)} | ${format(metric.delta, metric.unit)} | ${format(metric.perHour, metric.unit)} | ${format(metric.min, metric.unit)}～${format(metric.max, metric.unit)} |`)
            }
            output.push('')
        }
        if (run.omittedMetrics) output.push(`指标数量达到上限，省略 ${run.omittedMetrics} 次指标更新；建议缩小日志区间。`, '')
    }
    output.push(`解析失败 ${report.invalidSamples} 行；重复采样 ${report.duplicateSamples} 行；超出保留上限的早期进程片段 ${report.discardedRuns} 个。`, '',
        '优先对照同一观察区间的线程堆和容器/队列变化。RSS 增长而已采集线程堆稳定时，继续查原生内存、SQLite、映射及分配器保留；不把差额直接认定为泄漏。',
        'arrayBuffers 包含在 external 中，不能重复相加；各指标可能缺样或跨不同区间，JSON 报告中保留了每项的采样数与运行时长。')
    return output.join('\n')
}
module.exports = { MemoryLogSummary, analyzeFiles, renderReport }

if (require.main === module) {
    const args = process.argv.slice(2), json = args.includes('--json')
    const files = args.filter(arg => arg !== '--json')
    if (args.includes('--help') || !files.length) {
        console.log('用法: node tools/analyze-memory-log.cjs [--json] <较早.stderr.log> [较晚.stderr.log ...]')
        if (!args.includes('--help')) process.exitCode = 2
    } else if (files.some(file => file.startsWith('--'))) {
        console.error('不支持的选项；使用 --help 查看用法。'); process.exitCode = 2
    } else {
        analyzeFiles(files).then(report => {
            console.log(json ? JSON.stringify(report, null, 2) : renderReport(report))
            if (!report.runs.length) process.exitCode = 2
        }).catch(error => { console.error(`日志读取失败: ${error.message}`); process.exitCode = 1 })
    }
}
