'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const path = require('node:path'), fs = require('node:fs'), { fork } = require('node:child_process')
const { run, inputs } = require('../tools/isolated-content-runtime.cjs')
test('a fixture root inside a registered worktree is rejected before creating its first directory', () => {
    const forbidden = path.resolve(__dirname, '..', '.isolated-forbidden-' + require('node:crypto').randomUUID())
    assert.equal(fs.existsSync(forbidden), false)
    assert.throws(() => run({ root: path.join(forbidden, 'nested') }), /outside every registered worktree/)
    assert.equal(fs.existsSync(forbidden), false)
})
test('compiled full app preserves nonempty rights, clock and controls across startup, closure and worker/process restarts in a confined fixture', { timeout: 120000 }, async () => {
    const root = process.env.STARPOINT_ISOLATED_RUNTIME_TEST_ROOT
    assert.ok(root, 'Explicit external fixture root required; no implicit real or source DB')
    const result = run({ root })
    assert.equal(result.isolation.allAuditedPathsConfined, true)
    assert.ok(result.isolation.sqliteConnections.filter(row => row.threadId > 0).length >= 6)
    assert.ok(result.results.some(row => row.restartPreserved))
    assert.ok(result.results.some(row => row.listener?.actualHttpAuthentication))
    assert.ok(result.results.some(row => row.absentMetaSeasonalFirstDecisionDenied))
    const env = JSON.parse(fs.readFileSync(path.join(result.directory, 'launch-env.json'), 'utf8'))
    for (const mode of ['manual', 'normal-startup']) {
    const child = fork(path.resolve(__dirname, mode === 'manual' ? '../tools/isolated-content-runtime-serve.cjs' : '../tools/isolated-content-runtime-startup.cjs'), [], { cwd: result.directory, env: { ...env, CN_RUNTIME_IMPORT_ONLY: mode === 'manual' ? '1' : '0', CN_WRITER_THREAD: '1' }, windowsHide: true, execArgv: ['--require', path.resolve(__dirname, '../tools/isolated-runtime-fs-guard.cjs')], stdio: ['ignore', 'pipe', 'pipe', 'ipc'] })
    let logs = ''
    child.stdout.on('data', chunk => { logs += chunk }); child.stderr.on('data', chunk => { logs += chunk })
    const exited = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })))
    try {
        const ready = await Promise.race([new Promise(resolve => child.once('message', resolve)), exited.then(status => { throw Error('Manual runtime exited before ready: ' + JSON.stringify(status) + logs) }), new Promise((_, reject) => { const timer = setTimeout(() => reject(Error('Manual startup timed out: ' + logs)), 30000); timer.unref() })])
        assert.equal(ready.type, 'isolated:ready'); assert.equal(ready.host, '127.0.0.1')
        assert.ok(![8001, 8011].includes(ready.port))
        const login = await fetch(`http://${ready.host}:${ready.port}/admin-login`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ password: env.ADMIN_PANEL_PASSWORD }) })
        assert.equal(login.status, 200)
        const cookie = login.headers.get('set-cookie').split(';')[0]
        const response = await fetch(`http://${ready.host}:${ready.port}/api/server/currentTime`, { headers: { cookie } })
        assert.equal((await response.json()).clockMode, 'real')
        let actualLoad
        if (mode === 'normal-startup') {
            const expected = JSON.parse(fs.readFileSync(path.join(result.directory, 'expected.json'), 'utf8'))
            const loadResponse = await fetch(`http://${ready.host}:${ready.port}/api/index.php/load`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ viewer_id: 880000000 + expected.ids[0] }) })
            assert.equal(loadResponse.status, 200)
            const decoded = require('msgpackr').unpack(Buffer.from(await loadResponse.text(), 'base64'))
            assert.equal(decoded.data_headers.result_code, 1, JSON.stringify(decoded.data_headers))
            assert.ok(Math.abs(decoded.data_headers.servertime * 1000 - Date.now()) < 2000)
            const probed = new Promise(resolve => child.once('message', resolve))
            child.send({ type: 'isolated:probe' })
            const after = await probed
            assert.equal(after.protectedDigest, ready.protectedDigest, 'actual login maintenance preserves seeded claims, paid rights, balances and old battles')
            const maxRealAccrual = Math.ceil((Date.now() - expected.clock.cutoverRealMs + 30000) / 60000)
            for (const row of after.pooledExp) {
                const before = ready.pooledExp.find(player => player.id === row.id).exp_pool
                assert.ok(row.exp_pool >= before && row.exp_pool <= before + maxRealAccrual, 'EXP accrues only on elapsed real time, never the legacy offset interval')
            }
            actualLoad = { resultCode: decoded.data_headers.result_code, realTimeHeader: true, protectedDigestBefore: ready.protectedDigest, protectedDigestAfter: after.protectedDigest, pooledExpBefore: ready.pooledExp, pooledExpAfter: after.pooledExp, maxRealAccrual }
        }
        child.send({ type: 'starpoint:shutdown' })
        const status = await Promise.race([exited, new Promise((_, reject) => { const timer = setTimeout(() => reject(Error('Manual shutdown timed out: ' + logs)), 15000); timer.unref() })])
        assert.equal(status.code, 0, logs)
        fs.writeFileSync(path.join(result.directory, mode + '-smoke.json'), JSON.stringify({ ready, authenticatedRealClock: true, actualLoad, gracefulShutdownExitCode: status.code }, null, 2))
        fs.writeFileSync(path.join(result.directory, mode + '-smoke.log'), logs)
    } finally { fs.writeFileSync(path.join(result.directory, mode + '-smoke.log'), logs); if (child.exitCode === null && child.signalCode === null) child.kill() }
    }
    assert.deepEqual(inputs(), result.inputIdentity, 'The verified compiled runtime and plan stayed fixed through supervised startup')
    const audit = fs.readFileSync(path.join(result.directory, 'path-audit.jsonl'), 'utf8').trim().split(/\r?\n/).map(JSON.parse)
    for (const row of audit) {
        const relative = path.relative(result.directory, row.path)
        assert.ok(relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative))
    }
    result.isolation.interceptedOperations = audit.length
    result.isolation.sqliteConnections = audit.filter(row => row.kind === 'sqlite-open')
    result.isolation.listeners = 'verification used only auto-closed 127.0.0.1 random HTTP/TCP sockets; no LAN listener'
    result.supervised = Object.fromEntries(['manual', 'normal-startup'].map(mode => [mode, JSON.parse(fs.readFileSync(path.join(result.directory, mode + '-smoke.json'), 'utf8'))]))
    result.fullVerificationPassed = true
    fs.writeFileSync(path.join(result.directory, 'result.json'), JSON.stringify(result, null, 2) + '\n')
})
