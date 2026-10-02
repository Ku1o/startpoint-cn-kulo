const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { performance } = require('node:perf_hooks')

const root = path.resolve(__dirname, '..')
const rounds = Math.max(1, Number(process.env.PERF_ROUNDS || 3))
const requests = Math.max(100, Number(process.env.PERF_REQUESTS || 5000))
const sqlIterations = Math.max(1000, Number(process.env.PERF_SQL_ITERATIONS || 250000))

async function httpScenario(mode) {
    const Fastify = require('fastify')
    const sink = { write() {} }
    const logger = mode === 'info' ? { level: 'info', stream: sink }
        : mode === 'warn' ? { level: 'warn', stream: sink } : false
    const app = Fastify({ logger })
    if (mode === 'diagnostics' || mode === 'compact') {
        require('../out/lib/request-diagnostics').installRequestDiagnostics(app, {
            detailed: mode === 'diagnostics',
        })
    }
    app.post('/hot', async request => ({ ok: true, value: request.body.value + 1 }))
    await app.ready()
    for (let index = 0; index < 100; index++) {
        const response = await app.inject({ method: 'POST', url: '/hot', payload: { value: index } })
        if (response.statusCode !== 200) throw Error('Warmup failed')
    }
    const cpu = process.cpuUsage()
    const loop = performance.eventLoopUtilization()
    const started = performance.now()
    for (let offset = 0; offset < requests; offset += 32) {
        const batch = Math.min(32, requests - offset)
        const responses = await Promise.all(Array.from({ length: batch }, (_, index) => (
            app.inject({ method: 'POST', url: '/hot', payload: { value: offset + index } })
        )))
        if (responses.some(response => response.statusCode !== 200)) throw Error('Request failed')
    }
    const used = process.cpuUsage(cpu)
    const elapsed = performance.now() - started
    const elu = performance.eventLoopUtilization(loop)
    await app.close()
    return {
        wallMs: elapsed,
        cpuMs: (used.user + used.system) / 1000,
        mainEluPct: elu.utilization * 100,
    }
}

function sqlScenario(enabled) {
    process.env.SQLITE_DIAGNOSTICS = enabled ? 'true' : 'false'
    const Database = require('better-sqlite3')
    const db = new Database(':memory:')
    require('../out/lib/sqlite-diagnostics').observeSqliteDatabase(db, 'benchmark')
    const statement = db.prepare('SELECT ? AS value')
    for (let index = 0; index < 1000; index++) statement.get(index)
    const cpu = process.cpuUsage()
    const started = performance.now()
    for (let index = 0; index < sqlIterations; index++) statement.get(index)
    const used = process.cpuUsage(cpu)
    const result = {
        wallMs: performance.now() - started,
        cpuMs: (used.user + used.system) / 1000,
    }
    db.close()
    return result
}

function median(values) {
    return [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)]
}

if (process.argv[2] === '--child') {
    const mode = process.argv[3]
    const operation = mode.startsWith('sql-')
        ? Promise.resolve(sqlScenario(mode === 'sql-on'))
        : httpScenario(mode)
    operation.then(result => console.log(JSON.stringify(result)), error => {
        console.error(error)
        process.exitCode = 1
    })
} else {
    const scenarios = ['bare', 'compact', 'diagnostics', 'warn', 'info', 'sql-off', 'sql-on']
    const report = { node: process.version, requests, sqlIterations, rounds, scenarios: {} }
    for (const scenario of scenarios) {
        const samples = []
        for (let round = 0; round < rounds; round++) {
            const stdout = execFileSync(process.execPath, [__filename, '--child', scenario], {
                cwd: root,
                encoding: 'utf8',
                env: {
                    ...process.env,
                    MEMORY_DIAGNOSTICS: 'false',
                    SQLITE_DIAGNOSTICS: scenario === 'sql-on' ? 'true' : 'false',
                },
            })
            samples.push(JSON.parse(stdout.trim()))
        }
        report.scenarios[scenario] = {
            wallMedianMs: median(samples.map(sample => sample.wallMs)),
            cpuMedianMs: median(samples.map(sample => sample.cpuMs)),
            ...(samples[0].mainEluPct === undefined ? {} : {
                mainEluMedianPct: median(samples.map(sample => sample.mainEluPct)),
            }),
        }
    }
    console.log(JSON.stringify(report, null, 2))
}
