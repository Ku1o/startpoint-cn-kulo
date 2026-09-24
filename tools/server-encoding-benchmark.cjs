// Compare the legacy encoder, local encoder and bounded workers on identical JSON strings.
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { performance, monitorEventLoopDelay } = require('node:perf_hooks')
const { pack } = require('msgpackr')
const root = path.resolve(process.argv[2] || path.join(__dirname, '..'))
const baseline = process.argv[3]
const output = process.argv[4]
const { encodeCnResponse } = require(path.join(root, 'out/lib/cn-response-encoding'))
const { CnResponseWorkerPool } = require(path.join(root, 'out/lib/cn-response-worker-pool'))
const source = fs.readFileSync(path.join(baseline, 'src/cn-server.ts'), 'utf8')
const start = source.indexOf('function fixUint32Tags('), end = source.indexOf('\nfunction appendVaryAcceptEncoding', start)
const ts = require('typescript')
const legacy = vm.runInNewContext(ts.transpileModule(source.slice(start, end), {
    compilerOptions: {target: ts.ScriptTarget.ES2020},
}).outputText + '\nfixUint32Tags', {Buffer})
const stats = xs => {
    xs.sort((a,b) => a-b)
    return {avgMs: xs.reduce((x,y) => x+y, 0)/xs.length, p95Ms: xs[Math.ceil(xs.length*.95)-1], maxMs: xs.at(-1)}
}
async function main() {
    const report = []
    for (const kib of [64, 512, 2048]) {
        const payload = JSON.stringify({data: '字符abc123'.repeat(Math.ceil(kib*1024/14))})
        const reference = legacy(pack(payload)).toString('base64')
        for (const batch of [8, 12, 16]) {
            for (const mode of ['legacy', 'local', 'workers']) {
                const pool = new CnResponseWorkerPool({size: mode === 'workers' ? 2 : 0})
                const encode = mode === 'legacy' ? async () => ({body: legacy(pack(payload)).toString('base64')})
                    : mode === 'local' ? () => encodeCnResponse({payload}) : () => pool.encode({payload})
                try {
                    await Promise.all([encode(), encode()])
                    const samples = [], ticks = [], loop = monitorEventLoopDelay({resolution: 5})
                    loop.enable()
                    await new Promise(resolve => setTimeout(resolve, 20))
                    const elu = performance.eventLoopUtilization(), cpu = process.cpuUsage(), started = performance.now()
                    let previous = performance.now()
                    const timer = setInterval(() => {const now = performance.now(); ticks.push(now - previous); previous = now}, 5)
                    for (let j = 0; j < 8; j++) {
                        await Promise.all(Array.from({length: batch}, async () => {
                            const started = performance.now()
                            const result = await encode()
                            samples.push(performance.now()-started)
                            if (result.body !== reference) throw Error('Encoding mismatch')
                        }))
                        await new Promise(resolve => setImmediate(resolve))
                    }
                    const elapsedMs = performance.now()-started, used = process.cpuUsage(cpu)
                    const utilization = performance.eventLoopUtilization(elu).utilization
                    await new Promise(resolve => setTimeout(resolve, 10))
                    clearInterval(timer); loop.disable()
                    report.push({kib, bytes: Buffer.byteLength(payload), batch, mode, jobs: samples.length,
                        elapsedMs, processCpuMs: (used.user+used.system)/1000, eventLoopUtilization: utilization,
                        loopP99Ms: loop.percentile(99)/1e6, maxTimerGapMs: Math.max(0,...ticks),
                        latency: stats(samples), pool: pool.snapshot()})
                } finally { await pool.close() }
            }
        }
    }
    fs.writeFileSync(output, JSON.stringify(report, null, 2))
    console.log(JSON.stringify(report.filter(x => x.kib === 2048), null, 2))
}
main().catch(error => {console.error(error); process.exitCode = 1})
