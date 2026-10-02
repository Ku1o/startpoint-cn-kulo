const path = require('node:path')
const { execFileSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const rounds = Math.max(1, Number(process.env.PERF_ROUNDS || 3))
const requests = Math.max(1, Number(process.env.PERF_LOAD_REQUESTS || 30))
const scenarios = [
    { name: 'legacy-sqlite-settings', env: { CN_MULTICORE: '0', PERF_RESPONSE_WORKERS: '0', PERF_LOAD_MODES: 'disabled' } },
    { name: 'validated-default', env: { CN_MULTICORE: '1', PERF_RESPONSE_WORKERS: '0', PERF_LOAD_MODES: 'disabled' } },
    { name: 'one-response-worker', env: { CN_MULTICORE: '1', PERF_RESPONSE_WORKERS: '1', PERF_LOAD_MODES: 'off' } },
    { name: 'two-response-workers', env: { CN_MULTICORE: '1', PERF_RESPONSE_WORKERS: '2', PERF_LOAD_MODES: 'off' } },
    { name: 'third-response-worker', env: { CN_MULTICORE: '1', PERF_RESPONSE_WORKERS: '3', PERF_LOAD_MODES: 'off' } },
    { name: 'gzip', env: { CN_MULTICORE: '1', PERF_RESPONSE_WORKERS: '0', PERF_LOAD_MODES: 'gzip' } },
]
function median(values) {
    return [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)]
}
const report = { node: process.version, requests, rounds, scenarios: {} }
for (const scenario of scenarios) {
    const samples = []
    for (let round = 0; round < rounds; round++) {
        const stdout = execFileSync(process.execPath, [
            path.join(root, 'tools/run-isolated-check.cjs'),
            '--test', 'tests/cn-load-worker-integration.test.cjs',
        ], {
            cwd: root,
            encoding: 'utf8',
            maxBuffer: 4 * 1024 * 1024,
            env: { ...process.env, ...scenario.env, PERF_LOAD_REQUESTS: String(requests) },
        })
        const resultLine = stdout.split('\n').find(line => line.startsWith('RESULT '))
        if (!resultLine) throw Error(`Missing benchmark result for ${scenario.name}`)
        samples.push(JSON.parse(resultLine.slice('RESULT '.length)))
    }
    report.scenarios[scenario.name] = {
        wallMedianMs: median(samples.map(sample => sample.wallMs)),
        cpuMedianMs: median(samples.map(sample => sample.cpuMs)),
        mainEluMedianPct: median(samples.map(sample => sample.mainEluPct)),
        fallback: samples.reduce((total, sample) => total + sample.fallback, 0),
        failed: samples.reduce((total, sample) => total + sample.failed, 0),
    }
}
console.log(JSON.stringify(report, null, 2))
