'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), net = require('node:net')
const { spawnSync } = require('node:child_process')
const { randomInt } = require('node:crypto')
const wrapper = path.resolve(__dirname, '../scripts/migrate-time-content.ps1')
const realCli = path.resolve(__dirname, '../scripts/time-content-deployment.cjs')
async function freePort() {
    for (let attempt = 0; attempt < 32; attempt++) {
        const probe = net.createServer()
        const port = randomInt(25000, 60000)
        const available = await new Promise((resolve, reject) => {
            probe.once('error', error => ['EADDRINUSE', 'EACCES'].includes(error.code) ? resolve(false) : reject(error))
            probe.listen(port, '127.0.0.1', () => resolve(true))
        })
        if (!available) continue
        await new Promise(resolve => probe.close(resolve)); return port
    }
    throw Error('No free synthetic high loopback port after 32 attempts')
}
async function fixture(t, config = {}) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'time-content-wrapper-'))
    fs.mkdirSync(path.join(root, 'scripts')); fs.mkdirSync(path.join(root, '.logs'))
    fs.writeFileSync(path.join(root, '.env'), '')
    fs.writeFileSync(path.join(root, 'config.json'), JSON.stringify(config))
    // The expensive migration is a fixture; its stopped assertion is the actual
    // production CLI guard against only this fixture's receipts and high ports.
    fs.writeFileSync(path.join(root, 'scripts/time-content-deployment.cjs'), `
const fs=require('node:fs'),path=require('node:path'),real=require(${JSON.stringify(realCli)});
const root=path.resolve(__dirname,'..'),events=path.join(root,'events.jsonl');
const event=name=>fs.appendFileSync(events,JSON.stringify(name)+'\\n');
exports.paths=project=>({root:project});
exports.assertStopped=async p=>{event('guard');return real.assertStopped(p)};
if(require.main===module){const action=process.argv[2];event(action);Promise.resolve().then(async()=>{
 if(action==='apply') { if(JSON.parse(fs.readFileSync(path.join(root,'config.json'))).race)fs.writeFileSync(path.join(root,'.logs/cn-server-current.json'),JSON.stringify({pid:process.pid}));await exports.assertStopped({root}); }
}).catch(e=>{console.error(e.message);process.exitCode=1})}
`)
    fs.writeFileSync(path.join(root, 'scripts/stop-cn-logged.ps1'), `param([string]$ProjectRoot)
Add-Content -LiteralPath (Join-Path $ProjectRoot 'events.jsonl') -Value '"stop"'
$config=Get-Content -Raw -LiteralPath (Join-Path $ProjectRoot 'config.json') | ConvertFrom-Json
if (!$config.acceptStop) { throw 'UNVERIFIED_STOP: do not stop a foreign or old-capability instance' }
Remove-Item -LiteralPath (Join-Path $ProjectRoot '.logs/cn-server-current.json')
`)
    fs.writeFileSync(path.join(root, 'scripts/start-cn-logged.ps1'), `Add-Content -LiteralPath (Join-Path $PSScriptRoot '../events.jsonl') -Value '"start"'`)
    const http = await freePort(); let tcp = await freePort(); while (tcp === http) tcp = await freePort()
    const env = { ...process.env, CN_LOG_DIR: path.join(root, '.logs'), CN_LISTEN_PORT: String(http), SESSION_PORT: String(tcp) }
    t.after(() => fs.rmSync(root, { recursive: true, force: true }))
    return { root, http, tcp, env,
        run: (mode = 'Apply') => spawnSync('pwsh.exe', ['-NoProfile', '-NonInteractive', '-File', wrapper, '-Mode', mode, '-ProjectRoot', root], { env, windowsHide: true, encoding: 'utf8', timeout: 20000 }),
        receipt: data => fs.writeFileSync(path.join(root, '.logs/cn-server-current.json'), JSON.stringify(data)),
        events: () => fs.readFileSync(path.join(root, 'events.jsonl'), 'utf8').trim().split(/\r?\n/).map(JSON.parse),
    }
}
const output = result => result.stdout + '\n' + result.stderr

test('already-stopped legacy startup skips unsupported stop and preserves apply/verify/release/start order', { skip: process.platform !== 'win32' }, async t => {
    const f = await fixture(t)
    const ended = spawnSync(process.execPath, ['-e', 'process.exit(0)'])
    assert.equal(ended.status, 0)
    f.receipt({ pid: ended.pid, loggerPid: ended.pid, startedAt: 'legacy-receipt-without-IPC' })
    const result = f.run()
    assert.equal(result.status, 0, output(result)); assert.match(result.stdout, /already stopped/)
    assert.deepEqual(f.events(), ['guard', 'apply', 'guard', 'verify', 'release', 'start'])
})

test('a missing startup receipt is skipped only after the actual both-port guard proves stopped', { skip: process.platform !== 'win32' }, async t => {
    const f = await fixture(t), result = f.run()
    assert.equal(result.status, 0, output(result))
    assert.deepEqual(f.events(), ['guard', 'apply', 'guard', 'verify', 'release', 'start'])
})

test('a live or malformed receipt cannot reach migration when the verified stop entry rejects it', { skip: process.platform !== 'win32' }, async t => {
    for (const receipt of [{ pid: process.pid }, { pid: 'unknown-pid' }]) {
        const f = await fixture(t); f.receipt(receipt)
        const result = f.run()
        assert.notEqual(result.status, 0); assert.match(result.stderr, /UNVERIFIED_STOP/)
        assert.deepEqual(f.events(), ['guard', 'stop'])
    }
})

test('a foreign high-port listener is never treated as stopped even without a receipt', { skip: process.platform !== 'win32' }, async t => {
    const f = await fixture(t), server = net.createServer(socket => socket.destroy())
    await new Promise(resolve => server.listen(f.tcp, '127.0.0.1', resolve))
    t.after(() => new Promise(resolve => server.close(resolve)))
    const result = f.run()
    assert.notEqual(result.status, 0); assert.match(result.stderr, /UNVERIFIED_STOP/)
    assert.deepEqual(f.events(), ['guard', 'stop'])
})

test('a running startup uses the existing stop entry and migration still repeats its own stopped check', { skip: process.platform !== 'win32' }, async t => {
    const f = await fixture(t, { acceptStop: true }); f.receipt({ pid: process.pid })
    const result = f.run()
    assert.equal(result.status, 0, output(result))
    assert.deepEqual(f.events(), ['guard', 'stop', 'apply', 'guard', 'verify', 'release', 'start'])
})

test('a new live process appearing after preflight is rejected by apply and cannot release or restart', { skip: process.platform !== 'win32' }, async t => {
    const f = await fixture(t, { race: true }), result = f.run()
    assert.notEqual(result.status, 0); assert.match(result.stderr, /command 'apply' failed/)
    assert.deepEqual(f.events(), ['guard', 'apply', 'guard'])
})

test('non-Apply modes keep the original command-only behavior', { skip: process.platform !== 'win32' }, async t => {
    const f = await fixture(t), result = f.run('Preview')
    assert.equal(result.status, 0, output(result)); assert.deepEqual(f.events(), ['preview'])
})
