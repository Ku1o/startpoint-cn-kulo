'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net')
const { spawn, execFile } = require('node:child_process'), { promisify } = require('node:util')
const { randomInt } = require('node:crypto')
const loggerFile = path.resolve(__dirname, '../scripts/run-cn-logged.cjs'), stopScript = path.resolve(__dirname, '../scripts/stop-cn-logged.ps1')
const { runLoggedServer, validStopRequest, STOP_REQUEST_MAX_AGE_MS, GRACEFUL_STOP_WAIT_MS } = require(loggerFile)
const exec = promisify(execFile), delay = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(check, name, ms = 7000) { const end = Date.now() + ms; while (true) { const result = await check(); if (result) return result; if (Date.now() >= end) throw Error('timeout: ' + name); await delay(20) } }
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'))
function temporary(t) { return fs.mkdtempSync(path.join(os.tmpdir(), 'logged-stop-')) }
function request(receipt, patch = {}) { return { version: 1, pid: receipt.pid, loggerPid: receipt.loggerPid, startedAt: receipt.startedAt,
    stopToken: receipt.stopToken, requestedAt: new Date().toISOString(), ...patch } }
function publish(receipt, value = request(receipt)) {
    return new Promise((resolve, reject) => {
        const socket = net.connect(receipt.stopPipe)
        let buffered = '', complete = false
        const finish = (error, result) => { if (complete) return; complete = true; socket.destroy(); error ? reject(error) : resolve(result) }
        socket.setEncoding('utf8'); socket.setTimeout(5000)
        socket.once('connect', () => socket.write(JSON.stringify(value) + '\n'))
        socket.on('data', chunk => {
            buffered += chunk
            if (buffered.length > 16384) return finish(Error('stop pipe response exceeds bound'))
            const newline = buffered.indexOf('\n')
            if (newline < 0) return
            try {
                const result = JSON.parse(buffered.slice(0, newline))
                assert.equal(typeof result.accepted, 'boolean')
                if (!result.accepted) assert.equal(typeof result.error, 'string')
                finish(null, result)
            } catch (error) { finish(error) }
        })
        socket.once('error', error => finish(error))
        socket.once('timeout', () => finish(Error('stop pipe response timed out')))
        socket.once('end', () => { if (!complete) finish(Error('stop pipe ended before a complete response')) })
        socket.once('close', () => { if (!complete) finish(Error('stop pipe closed before a complete response')) })
    })
}
const syntheticChild = `
const fs = require('node:fs'); let stopping = false;
const release = process.argv[1];
const hold = setInterval(() => { if (fs.existsSync(release)) { clearInterval(hold); console.error('drained-final-tail'); process.disconnect(); } }, 20);
process.on('message', value => { if (value?.type === 'starpoint:shutdown') { console.log('IPC_SHUTDOWN'); stopping = true; } });
console.log('synthetic-child-ready');
`
async function inProcess(t, waitMs = GRACEFUL_STOP_WAIT_MS) {
    const root = temporary(t), directory = path.join(root, '.logs'), release = path.join(root, 'release')
    const running = runLoggedServer({ root, directory, args: ['-e', syntheticChild, release], gracefulStopWaitMs: waitMs })
    const receiptPath = path.join(directory, 'cn-server-current.json')
    let receipt, complete = false
    t.after(async () => { if (!complete) { fs.writeFileSync(release, 'release'); if (receipt?.stopPipe) await publish(receipt).catch(() => {}); await running } fs.rmSync(root, { recursive: true, force: true }) })
    receipt = await until(() => { try { const r = read(receiptPath); return r.stopPipe && fs.readFileSync(r.log, 'utf8').includes('synthetic-child-ready') && r } catch { return false } }, 'receipt')
    return { root, receipt, receiptPath, release, running, complete: () => { complete = true } }
}

test('stop request identity, freshness and default 180-second bound are strict', () => {
    const now = Date.now(), receipt = { pid: 11, loggerPid: 22, startedAt: new Date(now - 60000).toISOString(), stopToken: 'unique-instance' }
    assert.equal(GRACEFUL_STOP_WAIT_MS, 180000)
    assert.equal(validStopRequest(request(receipt), receipt, now), true)
    for (const patch of [{ version: 2 }, { pid: 12 }, { loggerPid: 23 }, { startedAt: 'other' }, { stopToken: 'other' },
        { requestedAt: 'invalid' }, { requestedAt: new Date(now - STOP_REQUEST_MAX_AGE_MS - 1).toISOString() }, { requestedAt: new Date(now + 5001).toISOString() }]) {
        assert.equal(validStopRequest(request(receipt, patch), receipt, now), false, JSON.stringify(patch))
    }
})

test('a local stop pipe bind failure rejects before the synthetic server can start', async t => {
    const root = temporary(t), marker = path.join(root, 'must-not-start')
    const originalListen = net.Server.prototype.listen
    t.after(() => fs.rmSync(root, { recursive: true, force: true }))
    try {
        net.Server.prototype.listen = function () { throw Object.assign(new Error('synthetic bind failure'), { code: 'EACCES' }) }
        await assert.rejects(runLoggedServer({ root, directory: path.join(root, '.logs'),
            args: ['-e', `require('node:fs').writeFileSync(${JSON.stringify(marker)}, 'started')`],
        }), /synthetic bind failure/)
        assert.equal(fs.existsSync(marker), false)
    } finally { net.Server.prototype.listen = originalListen }
})

test('foreign and expired pipe requests are rejected; an accepted request sends IPC only once and drains', { timeout: 15000 }, async t => {
    const f = await inProcess(t)
    for (const patch of [{ pid: f.receipt.pid + 1 }, { stopToken: 'foreign' }, { requestedAt: '2000-01-01T00:00:00Z' }]) {
        const rejected = await publish(f.receipt, request(f.receipt, patch))
        assert.equal(rejected.accepted, false); assert.ok(rejected.error.length)
        await until(() => read(f.receiptPath).stopRequestRejection, 'rejection receipt')
        assert.equal(read(f.receiptPath).gracefulStop, undefined)
        assert.doesNotThrow(() => process.kill(f.receipt.pid, 0))
    }
    assert.equal((await publish(f.receipt)).accepted, true)
    await until(() => read(f.receiptPath).gracefulStop?.state === 'ipc-sent', 'IPC accepted')
    const duplicate = await publish(f.receipt)
    assert.equal(duplicate.accepted, false); assert.ok(duplicate.error.length)
    assert.doesNotThrow(() => process.kill(f.receipt.pid, 0))
    await until(() => fs.readFileSync(f.receipt.log, 'utf8').includes('IPC_SHUTDOWN'), 'child IPC receipt')
    assert.equal(fs.readFileSync(f.receipt.log, 'utf8').split('IPC_SHUTDOWN').length - 1, 1)
    fs.writeFileSync(f.release, 'release')
    assert.equal(await f.running, 0); f.complete()
    assert.equal(read(f.receiptPath).gracefulStop.clean, true)
    assert.equal(read(f.receiptPath).signal, null)
    assert.match(fs.readFileSync(f.receipt.log, 'utf8'), /drained-final-tail/)
})

test('a graceful deadline records timeout and never force-kills the still-draining child', { timeout: 10000 }, async t => {
    const f = await inProcess(t, 150)
    assert.equal((await publish(f.receipt)).accepted, true)
    await until(() => read(f.receiptPath).gracefulStop?.state === 'timed-out', 'timeout')
    assert.doesNotThrow(() => process.kill(f.receipt.pid, 0))
    assert.equal(read(f.receiptPath).exitedAt, undefined)
    fs.writeFileSync(f.release, 'release'); assert.equal(await f.running, 0); f.complete()
    assert.ok(read(f.receiptPath).gracefulStop.timedOutAt)
})

test('a superseding startup receipt cannot authorize an old logger stop', { timeout: 10000 }, async t => {
    const f = await inProcess(t), replacement = { pid: 77, loggerPid: 88, startedAt: 'replacement', stopToken: 'replacement' }
    fs.writeFileSync(f.receiptPath, JSON.stringify(replacement))
    const rejected = await publish(f.receipt)
    assert.equal(rejected.accepted, false); assert.ok(rejected.error.length)
    assert.deepEqual(read(f.receiptPath), replacement)
    assert.doesNotThrow(() => process.kill(f.receipt.pid, 0))
    // Re-establish the original fixture receipt before requesting its own drain.
    fs.writeFileSync(f.receiptPath, JSON.stringify(f.receipt))
    assert.equal((await publish(f.receipt)).accepted, true)
    await until(() => read(f.receiptPath).gracefulStop?.state === 'ipc-sent', 'owned request')
    fs.writeFileSync(f.release, 'release'); assert.equal(await f.running, 0); f.complete()
})

async function port() {
    for (let attempt = 0; attempt < 32; attempt++) {
        const probe = net.createServer(), selected = randomInt(25000, 60000)
        const available = await new Promise((resolve, reject) => { probe.once('error', error => ['EADDRINUSE', 'EACCES'].includes(error.code) ? resolve(false) : reject(error)); probe.listen(selected, '127.0.0.1', () => resolve(true)) })
        if (!available) continue
        await new Promise(resolve => probe.close(resolve)); return selected
    }
    throw Error('No free high synthetic port after 32 attempts')
}
async function externalFixture(t, hold = false) {
    const root = temporary(t), entry = path.join(root, 'out/cn-server.js'), selectedPort = await port()
    fs.mkdirSync(path.dirname(entry), { recursive: true })
    const release = path.join(root, 'release')
    fs.writeFileSync(entry, `const net=require('node:net'),fs=require('node:fs');const server=net.createServer();let closing=false;const close=()=>{if(closing)return;closing=true;clearInterval(releaseTimer);server.close(()=>process.disconnect())};const releaseTimer=setInterval(()=>{if(fs.existsSync(${JSON.stringify(release)}))close()},20);server.listen(Number(process.env.CN_LISTEN_PORT),'127.0.0.1',()=>console.log('fixture-ready'));process.on('message',m=>{if(m?.type==='starpoint:shutdown'){console.log('IPC_FIXTURE_DRAIN');${hold ? '' : 'setTimeout(close,200)'}}})`)
    const child = spawn(process.execPath, [loggerFile, '--root', root], { env: { ...process.env, CN_LISTEN_PORT: String(selectedPort) }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
    let output = ''; child.stdout.on('data', c => output += c); child.stderr.on('data', c => output += c)
    const exited = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })))
    const receiptPath = path.join(root, '.logs/cn-server-current.json')
    let receipt, complete = false
    t.after(async () => { if (!complete) { fs.writeFileSync(release, 'release'); if (receipt?.stopPipe) { fs.writeFileSync(receiptPath, JSON.stringify(receipt)); await publish(receipt).catch(() => {}) } await exited } fs.rmSync(root, { recursive: true, force: true }) })
    receipt = await until(() => { try { const r = read(receiptPath); return r.stopPipe && fs.readFileSync(r.log, 'utf8').includes('fixture-ready') && r } catch { return false } }, 'external ready')
    return { root, receipt, receiptPath, child, exited, release, complete: () => { complete = true }, output: () => output }
}
const powershell = process.platform === 'win32' ? path.join(process.env.SystemRoot || 'C:/Windows', 'System32/WindowsPowerShell/v1.0/powershell.exe') : 'powershell.exe'
const ps = (root, timeout = 10) => exec(powershell, ['-NoProfile', '-NonInteractive', '-File', stopScript, '-ProjectRoot', root, '-TimeoutSeconds', String(timeout)], { windowsHide: true, timeout: 20000 })

test('Windows stop command checks actual CIM identity and TCP ownership, then drains only its synthetic CN child', { skip: process.platform !== 'win32', timeout: 30000 }, async t => {
    const f = await externalFixture(t)
    const version = await exec(powershell, ['-NoProfile', '-NonInteractive', '-Command', '$PSVersionTable.PSVersion.ToString()'], { windowsHide: true, timeout: 5000 })
    assert.match(version.stdout.trim(), /^5\.1\./)
    const result = await ps(f.root)
    assert.match(result.stdout, /graceful shutdown completed/)
    assert.deepEqual(await f.exited, { code: 0, signal: null }); f.complete()
    const final = read(f.receiptPath)
    assert.equal(final.gracefulStop.clean, true)
    assert.match(fs.readFileSync(final.log, 'utf8'), /IPC_FIXTURE_DRAIN/)
})

test('Windows stop command rejects old capabilities, changed start time and foreign listener without sending a request', { skip: process.platform !== 'win32', timeout: 45000 }, async t => {
    const f = await externalFixture(t)
    for (const patch of [{ stopToken: null }, { startedAt: '2000-01-01T00:00:00Z' }, { httpPort: await port() }]) {
        fs.writeFileSync(f.receiptPath, JSON.stringify({ ...f.receipt, ...patch }))
        await assert.rejects(ps(f.root), error => /no verified|start time mismatch|listener does not belong/.test(error.stderr))
        assert.equal(read(f.receiptPath).gracefulStop, undefined)
        assert.doesNotMatch(fs.readFileSync(f.receipt.log, 'utf8'), /IPC_FIXTURE_DRAIN/)
        assert.doesNotThrow(() => process.kill(f.receipt.pid, 0))
    }
    fs.writeFileSync(f.receiptPath, JSON.stringify(f.receipt)); await ps(f.root)
    assert.deepEqual(await f.exited, { code: 0, signal: null }); f.complete()
})

test('Windows command timeout leaves its verified synthetic process alive for continued graceful drain', { skip: process.platform !== 'win32', timeout: 30000 }, async t => {
    const f = await externalFixture(t, true)
    await assert.rejects(ps(f.root, 1), error => /No process was force-killed/.test(error.stderr))
    assert.doesNotThrow(() => process.kill(f.receipt.pid, 0))
    assert.equal(read(f.receiptPath).gracefulStop.state, 'ipc-sent')
    fs.writeFileSync(f.release, 'release')
    assert.deepEqual(await f.exited, { code: 0, signal: null }); f.complete()
    assert.equal(read(f.receiptPath).gracefulStop.clean, true)
})
