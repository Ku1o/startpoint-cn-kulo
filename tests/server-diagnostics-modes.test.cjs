const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

function scenario(source, settings = {}) {
    const env = { ...process.env }
    for (const key of ['MEMORY_DIAGNOSTICS', 'MEMORY_DIAGNOSTICS_DETAIL', 'PROCESS_MEMORY_DIAGNOSTICS',
        'SQLITE_DIAGNOSTICS', 'SQL_STATEMENT_CACHE', 'ROUTE_PERF_SUMMARY', 'ROUTE_PERF_DETAIL',
        'ROUTE_PERF_INTERVAL_MS', 'GAME_VERBOSE_LOGS']) delete env[key]
    Object.assign(env, settings)
    const result = spawnSync(process.execPath, ['-e', source], {
        cwd: path.resolve(__dirname, '..'), env, encoding: 'utf8', timeout: 20000,
    })
    assert.equal(result.status, 0, result.stderr || String(result.error))
    return JSON.parse(result.stdout.trim())
}

// Exercise the production Fastify monitor, real SQLite statements and the response
// pool registry. Advance only the reporting interval; never start the game server.
const monitoringScenario = `
(async () => {
    const Fastify = require('fastify');
    const Database = require('better-sqlite3');
    const { setImmediate: tick } = require('node:timers/promises');
    let nativeCalls = 0, heapDetails = 0, resourceScans = 0, detailedCounters = 0;
    require('node:child_process').execFile = (...args) => {
        nativeCalls++; args.at(-1)(new Error('fixture OS probe failure'), '');
    };
    const v8 = require('node:v8'), readHeap = v8.getHeapStatistics;
    v8.getHeapStatistics = () => { heapDetails++; return readHeap(); };
    process.getActiveResourcesInfo = () => { resourceScans++; return ['Timeout']; };
    const { installRoutePerformanceMonitor } = require('./out/lib/route-performance');
    const { registerMemoryCounters } = require('./out/lib/memory-diagnostics');
    const { observeSqliteDatabase } = require('./out/lib/sqlite-diagnostics');
    const { cachedStatement } = require('./out/lib/cached-statement');
    const { CnResponseWorkerPool } = require('./out/lib/cn-response-worker-pool');
    const { recordServerWork } = require('./out/lib/server-work-performance');
    const intervals = [], logs = [];
    global.setInterval = fn => { const timer = { fn, unref() {} }; intervals.push(timer); return timer; };
    global.clearInterval = timer => { timer.cleared = true; };
    console.warn = line => logs.push(line);
    const app = Fastify(), db = new Database(':memory:');
    const prepare = db.prepare;
    observeSqliteDatabase(db, 'fixture');
    const wrapped = prepare !== db.prepare;
    db.exec('CREATE TABLE t(id INTEGER PRIMARY KEY)');
    const insert = cachedStatement(db, 'INSERT INTO t VALUES (?)');
    const cachePreserved = insert === cachedStatement(db, 'INSERT INTO t VALUES (?)');
    insert.run(1);
    const pool = new CnResponseWorkerPool({ size: 0 });
    registerMemoryCounters('fixtureQueue', detailed => {
        if (detailed) detailedCounters++;
        return { pending: 3, detailed };
    });
    installRoutePerformanceMonitor(app);
    app.get('/ok', () => db.prepare('SELECT COUNT(*) AS n FROM t').get());
    app.get('/error', () => { insert.run(1); return {}; });
    const ok = await app.inject('/ok'), error = await app.inject('/error');
    recordServerWork('db.single.body', 1.5);
    await tick();
    for (const timer of intervals) timer.fn();
    await app.close(); await pool.close(); db.close(); await tick();
    const parse = prefix => {
        const line = logs.find(value => value.startsWith(prefix));
        return line ? JSON.parse(line.slice(prefix.length)) : null;
    };
    process.stdout.write(JSON.stringify({ nativeCalls, heapDetails, resourceScans, detailedCounters,
        wrapped, cachePreserved, ok: ok.json(), errorStatus: error.statusCode,
        allTimersCleared: intervals.every(timer => timer.cleared),
        startup: parse('[DIAGNOSTICS] '), memory: parse('[MEM] '), sqlite: parse('[SQLITE-PERF] '),
        requests: parse('[REQUEST-PERF] '), work: parse('[WORK-PERF] '),
        hasCpuSummary: logs.some(line => line.startsWith('[PERF] ') && line.includes('loopP99=')),
    }));
})().catch(error => { console.error(error); process.exitCode = 1; });
`

function retainsPerformanceAndErrors(result) {
    assert.deepEqual(result.ok, { n: 1 })
    assert.equal(result.errorStatus, 500)
    assert.equal(result.requests.statuses['500'], 1)
    assert.equal(result.requests.statuses['200'], 1)
    assert.equal(result.hasCpuSummary, true)
    assert.equal(result.work['db.single.body'].n, 1)
    assert.equal(result.cachePreserved, true)
    assert.equal(result.allTimersCleared, true)
}

test('default monitoring retains queues and request errors without SQL or detailed scans', () => {
    const result = scenario(monitoringScenario)
    retainsPerformanceAndErrors(result)
    assert.deepEqual(result.startup, { memory: 'basic', sqlite: false, nativeMemory: false, intervalMs: 60000 })
    assert.equal(result.nativeCalls, 0)
    assert.equal(result.heapDetails, 0)
    assert.equal(result.resourceScans, 0)
    assert.equal(result.detailedCounters, 0)
    assert.ok(result.memory.rss > 0 && result.memory.main.heapUsed > 0)
    assert.equal(result.memory.counters.fixtureQueue.pending, 3)
    assert.equal(result.memory.counters.responseWorkers.active, 0)
    assert.equal(result.memory.counters['sqlite.fixture'], undefined)
})

test('production defaults suppress hot-path detail while preserving opt-in controls', () => {
    const defaults = scenario(`
        const game = require('./out/lib/game-logging');
        const diagnostics = require('./out/lib/memory-diagnostics');
        process.stdout.write(JSON.stringify({
            game: game.isGameVerboseLoggingEnabled(),
            sqlite: diagnostics.sqliteDiagnosticsEnabled(),
        }));
    `)
    assert.deepEqual(defaults, { game: false, sqlite: false })
    const enabled = scenario(`
        const game = require('./out/lib/game-logging');
        const diagnostics = require('./out/lib/memory-diagnostics');
        process.stdout.write(JSON.stringify({
            game: game.isGameVerboseLoggingEnabled(),
            sqlite: diagnostics.sqliteDiagnosticsEnabled(),
        }));
    `, { GAME_VERBOSE_LOGS: 'true', SQLITE_DIAGNOSTICS: 'true' })
    assert.deepEqual(enabled, { game: true, sqlite: true })
})

test('detailed collection is opt-in and does not implicitly launch PowerShell', () => {
    const result = scenario(monitoringScenario, { MEMORY_DIAGNOSTICS_DETAIL: 'true' })
    retainsPerformanceAndErrors(result)
    assert.equal(result.startup.memory, 'detailed')
    assert.equal(result.nativeCalls, 0)
    assert.equal(result.heapDetails, 1)
    assert.equal(result.resourceScans, 1)
    assert.equal(result.detailedCounters, 1)
    assert.equal(result.memory.counters.activeResources.Timeout, 1)
    assert.ok(result.memory.main.totalPhysicalHeap > 0)
})

test('SQL diagnostics can be disabled without removing memory, queue, error or timing metrics', () => {
    const result = scenario(monitoringScenario, { SQLITE_DIAGNOSTICS: 'false' })
    retainsPerformanceAndErrors(result)
    assert.equal(result.wrapped, false, 'disabled sampling must not wrap prepare or statement calls')
    assert.equal(result.memory.counters['sqlite.fixture'], undefined)
    assert.equal(result.memory.counters.fixtureQueue.pending, 3)
    assert.equal(result.memory.counters.responseWorkers.retainedBytes, 0)
    assert.ok(result.memory.main.heapUsed > 0)
})

test('SQL-only monitoring works without memory collection or OS probing', () => {
    const result = scenario(monitoringScenario, {
        MEMORY_DIAGNOSTICS: 'false', SQLITE_DIAGNOSTICS: 'true', PROCESS_MEMORY_DIAGNOSTICS: 'true',
    })
    retainsPerformanceAndErrors(result)
    assert.equal(result.memory, null)
    assert.equal(result.startup.memory, 'off')
    assert.equal(result.nativeCalls, 0)
    assert.equal(result.heapDetails, 0)
    assert.equal(result.resourceScans, 0)
    assert.equal(result.sqlite.counters['sqlite.fixture'].executeErrors, 1)
    assert.equal(result.sqlite.counters.fixtureQueue, undefined)
    assert.equal(result.sqlite.rss, undefined)
    assert.equal(result.wrapped, true)
})

test('turning off both diagnostic collectors still preserves CPU, request errors and work summaries', () => {
    const result = scenario(monitoringScenario, {
        MEMORY_DIAGNOSTICS: 'false', SQLITE_DIAGNOSTICS: 'false', PROCESS_MEMORY_DIAGNOSTICS: 'true',
    })
    retainsPerformanceAndErrors(result)
    assert.equal(result.memory, null)
    assert.equal(result.sqlite, null)
    assert.equal(result.nativeCalls, 0)
    assert.equal(result.wrapped, false)
})

test('explicit native opt-in uses the bounded probe and reports failure without breaking requests', {
    skip: process.platform !== 'win32' || process.arch !== 'x64',
}, () => {
    const result = scenario(monitoringScenario, { PROCESS_MEMORY_DIAGNOSTICS: 'true' })
    retainsPerformanceAndErrors(result)
    assert.equal(result.startup.nativeMemory, true)
    assert.ok(result.nativeCalls >= 1 && result.nativeCalls <= 2,
        'startup and one reporting interval may request at most two sequential samples')
    assert.equal(result.memory.osProcess.failed, true)
    assert.equal(result.memory.osProcess.stale, true)
})

test('SQL-only worker probes report database statistics without invoking memory counter callbacks', () => {
    const result = scenario(`
    (async () => {
        const { Worker } = require('node:worker_threads');
        const { once } = require('node:events');
        const path = require('node:path');
        const diagnostics = require('./out/lib/memory-diagnostics');
        const worker = new Worker(\`
            const { parentPort, workerData } = require('node:worker_threads');
            const Database = require(workerData.database);
            const { observeSqliteDatabase } = require(workerData.sqlite);
            const { installWorkerMemoryProbe } = require(workerData.memory);
            const db = new Database(':memory:');
            observeSqliteDatabase(db, 'workerFixture');
            db.prepare('SELECT 7 AS n').get();
            installWorkerMemoryProbe(() => { throw Error('memory counter must not run'); });
            parentPort.postMessage({type:'ready'});
        \`, { eval: true, workerData: {
            database: require.resolve('better-sqlite3'),
            sqlite: path.resolve('out/lib/sqlite-diagnostics.js'),
            memory: path.resolve('out/lib/memory-diagnostics.js'),
        } });
        try {
            await once(worker, 'message');
            diagnostics.observeWorkerMemory('sqlFixture', worker);
            const pending = once(worker, 'message');
            diagnostics.collectMemoryDiagnostics();
            await pending;
            const sample = diagnostics.collectMemoryDiagnostics();
            process.stdout.write(JSON.stringify(sample.workers.find(w => w.name === 'sqlFixture')));
        } finally { await worker.terminate(); }
    })().catch(error => { console.error(error); process.exitCode = 1; });
    `, { MEMORY_DIAGNOSTICS: 'false', SQLITE_DIAGNOSTICS: 'true' })
    assert.equal(result.memory, null)
    assert.deepEqual(result.counters, {})
    assert.equal(result.stale, false)
    assert.equal(result.diagnostics['sqlite.workerFixture'].executeCalls, 1)
})
