const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { Writable, Readable } = require('node:stream')
const { pipeline, finished } = require('node:stream/promises')
const { spawn, execFileSync } = require('node:child_process')
const { once } = require('node:events')
const {
    FOUR_HOURS_MS, logBucket, RotatingLogWriter, logChannel, runLoggedServer,
} = require('../scripts/run-cn-logged.cjs')

const root = path.resolve(__dirname, '..')
const tempRoot = path.join(root, 'tmp')

function temporary(t) {
    fs.mkdirSync(tempRoot, { recursive: true })
    const directory = fs.mkdtempSync(path.join(tempRoot, 'log-rotation-'))
    t.after(() => {
        fs.rmSync(directory, { recursive: true, force: true })
        try { fs.rmdirSync(tempRoot) } catch {}
    })
    return directory
}

function write(writer, channel, text) {
    return new Promise((resolve, reject) => {
        writer.write({ channel, text }, error => error ? reject(error) : resolve())
    })
}

async function close(writer) {
    const ended = finished(writer)
    writer.end()
    await ended
}

test('four-hour buckets use Beijing wall clock including exact boundaries and midnight', () => {
    for (let hour = 0; hour < 24; hour++) {
        const time = Date.parse(`2026-10-05T${String(hour).padStart(2, '0')}:59:59.999+08:00`)
        const bucket = logBucket(time)
        assert.equal(bucket.name, `cn-server-20261005-${String(Math.floor(hour / 4) * 4).padStart(2, '0')}00.log`)
        assert.ok(time >= bucket.start && time < bucket.end)
        assert.equal(bucket.end - bucket.start, FOUR_HOURS_MS)
    }
    const midnight = Date.parse('2026-10-06T00:00:00+08:00')
    assert.equal(logBucket(midnight - 1).name, 'cn-server-20261005-2000.log')
    assert.equal(logBucket(midnight).name, 'cn-server-20261006-0000.log')
    assert.equal(logBucket(midnight, true).name, 'cn-server-debug-20261006-0000.log')
})

test('stdout and stderr share buckets; restart appends; idle time creates no empty files', async t => {
    const directory = temporary(t)
    let clock = Date.parse('2026-10-05T03:59:59+08:00')
    const rotations = []
    const options = { directory, now: () => clock, onRotate: bucket => rotations.push(bucket.name) }
    const first = new RotatingLogWriter(options)
    await write(first, 'stdout', 'before-boundary')
    clock += 1000
    await write(first, 'stderr', 'after-boundary')
    await close(first)
    const second = new RotatingLogWriter(options)
    await write(second, 'stdout', 'after-restart')
    clock = Date.parse('2026-10-06T00:00:00+08:00')
    await write(second, 'stdout', 'next-day')
    await close(second)
    assert.deepEqual(fs.readdirSync(directory).sort(), [
        'cn-server-20261005-0000.log', 'cn-server-20261005-0400.log',
        'cn-server-20261006-0000.log',
    ])
    const content = fs.readFileSync(path.join(directory, 'cn-server-20261005-0400.log'), 'utf8')
    assert.match(content, /\[stderr\] after-boundary/)
    assert.match(content, /\[stdout\] after-restart/)
    assert.equal(rotations.length, 4)
})

test('line capture preserves split UTF-8, stderr, CRLF and final partial output with bounded lines', async t => {
    const directory = temporary(t)
    const writer = new RotatingLogWriter({ directory })
    let mirrored = ''
    const mirror = new Writable({ write(chunk, _encoding, callback) { mirrored += chunk.toString(); callback() } })
    const text = '\u5e7b\u60f3\u8fde\u6218'
    const bytes = Buffer.from(text + '\r\npartial')
    const longLine = 'x'.repeat(65_535) + '\uD840\uDC00' + 'x'.repeat(140_000)
    await Promise.all([
        pipeline(Readable.from([bytes.subarray(0, 2), bytes.subarray(2, 5), bytes.subarray(5)]),
            logChannel(writer, 'stdout', mirror)),
        pipeline(Readable.from([Buffer.from(longLine)]), logChannel(writer, 'stderr')),
    ])
    await close(writer)
    const content = fs.readFileSync(path.join(directory, fs.readdirSync(directory)[0]), 'utf8')
    assert.equal(mirrored, text + '\r\npartial')
    assert.match(content, new RegExp(`\\[stdout\\] ${text}\\n`))
    assert.match(content, /\[stdout\] partial\n/)
    const stderr = content.split('\n').filter(line => line.includes('[stderr] '))
    assert.equal(stderr.map(line => line.split('[stderr] ')[1]).join(''), longLine)
    assert.ok(stderr.every(line => line.length < 66_000))
})

test('many short lines are batched rather than written once per line', async t => {
    const directory = temporary(t)
    const writer = new RotatingLogWriter({ directory })
    await writer.rotate(Date.now())
    const original = writer.file.write.bind(writer.file)
    let writes = 0
    writer.file.write = (...args) => { writes++; return original(...args) }
    await pipeline(Readable.from([Buffer.from('sample\n'.repeat(5000))]), logChannel(writer, 'stdout'))
    await close(writer)
    assert.ok(writes < 10, `unexpected writes: ${writes}`)
    const content = fs.readFileSync(path.join(directory, fs.readdirSync(directory)[0]), 'utf8')
    assert.equal(content.split('[stdout] sample').length - 1, 5000)
})

test('new prefixed combined logs remain readable by both analysis tools', async t => {
    const directory = temporary(t)
    const writer = new RotatingLogWriter({ directory })
    await write(writer, 'stderr', '[MEM] ' + JSON.stringify({
        pid: 42, uptimeSeconds: 60, rss: 100, main: { heapUsed: 50 },
    }))
    await write(writer, 'stderr', '[PERF] requests=2 cpu=10 elu=5 loopP99=1 loopMax=2')
    await write(writer, 'stdout', '[CRASH] sample')
    await close(writer)
    const file = path.join(directory, fs.readdirSync(directory)[0])
    const report = JSON.parse(execFileSync(process.execPath, [
        'tools/analyze-runtime-log.cjs', file,
    ], { cwd: root, encoding: 'utf8', timeout: 5000 }))
    assert.equal(report.samples.memory, 1)
    assert.equal(report.samples.perf, 1)
    assert.equal(report.crashes.lines, 1)
    assert.equal(report.loop.requestsTotal, 2)
    const memory = await require('../tools/analyze-memory-log.cjs').analyzeFiles([file])
    assert.equal(memory.runs[0].samples, 1)
    assert.equal(memory.invalidSamples, 0)
})

test('retention only prunes old owned log names and keeps debug, diagnostics and receipts', async t => {
    const directory = temporary(t)
    const clock = Date.parse('2026-10-05T12:00:00+08:00')
    const names = [
        'cn-server-20260901-0000.log',
        'cn-server-20260901-123456.stdout.log',
        'cn-server-20260901-123456.stderr.log',
        'cn-server-debug-20260901-0000.log',
        'multi-chain-example.jsonl',
        'cn-server-current.json',
        'unrelated.log',
        'cn-server-20261005-1200.log',
    ]
    for (const name of names) {
        const file = path.join(directory, name)
        fs.writeFileSync(file, 'keep\n')
        fs.utimesSync(file, new Date('2026-09-01'), new Date('2026-09-01'))
    }
    const writer = new RotatingLogWriter({ directory, now: () => clock, retentionDays: 7 })
    await write(writer, 'stdout', 'now')
    await close(writer)
    assert.deepEqual(fs.readdirSync(directory).sort(), names.slice(3).sort())
    assert.match(fs.readFileSync(path.join(directory, names[7]), 'utf8'), /^keep\n/)
})

test('collector drains real child output, preserves exit code and records the real game PID', async t => {
    const directory = temporary(t)
    const code = await runLoggedServer({
        root, directory,
        args: ['-e', `
            console.log('GAME_PID=' + process.pid);
            process.stdout.write('stdout-tail');
            process.stderr.write('stderr-tail');
            process.exitCode = 7;
        `],
    })
    assert.equal(code, 7)
    const receipt = JSON.parse(fs.readFileSync(path.join(directory, 'cn-server-current.json')))
    assert.equal(receipt.loggerPid, process.pid)
    assert.notEqual(receipt.pid, process.pid)
    assert.equal(receipt.intervalHours, 4)
    assert.equal(receipt.stdout, receipt.stderr)
    assert.equal(receipt.stdout, receipt.log)
    assert.equal(receipt.exitCode, 7)
    assert.ok(receipt.exitedAt)
    const content = fs.readFileSync(receipt.log, 'utf8')
    assert.match(content, new RegExp(`GAME_PID=${receipt.pid}`))
    assert.match(content, /\[stdout\] stdout-tail/)
    assert.match(content, /\[stderr\] stderr-tail/)
    assert.equal(fs.readdirSync(directory).filter(name => name.endsWith('.log')).length, 1)
})

test('unwritable destination fails before launching a child', async t => {
    const directory = temporary(t)
    const file = path.join(directory, 'not-a-directory')
    fs.writeFileSync(file, 'original')
    await assert.rejects(runLoggedServer({ directory: file, args: ['-e', 'process.exit(0)'] }))
    assert.equal(fs.readFileSync(file, 'utf8'), 'original')
})

test('an exiting collector preserves a receipt already replaced by the next startup', async t => {
    const directory = temporary(t)
    const receiptPath = path.join(directory, 'cn-server-current.json')
    const replacement = { pid: 123, loggerPid: 456, startedAt: 'replacement-start' }
    const code = await runLoggedServer({
        root, directory,
        args: ['-e', `
            require('node:fs').writeFileSync(
                ${JSON.stringify(receiptPath)},
                ${JSON.stringify(JSON.stringify(replacement))}
            );
            console.log('old-game-exit');
        `],
    })
    assert.equal(code, 0)
    assert.deepEqual(JSON.parse(fs.readFileSync(receiptPath, 'utf8')), replacement)
})

test('writer errors are propagated without leaving an open handle', async t => {
    const directory = temporary(t)
    const writer = new RotatingLogWriter({ directory })
    await write(writer, 'stdout', 'before-error')
    await writer.file.close()
    const ended = finished(writer)
    writer.write({ channel: 'stderr', text: 'failure' })
    await assert.rejects(ended)
    assert.equal(writer.destroyed, true)
    assert.equal(writer.file, null)
})

test('collector forwards SIGTERM, drains final logs and does not restart the child', {
    skip: process.platform === 'win32',
    timeout: 15_000,
}, async t => {
    const directory = temporary(t)
    const modulePath = path.join(root, 'scripts/run-cn-logged.cjs')
    const source = `
        const { runLoggedServer } = require(${JSON.stringify(modulePath)});
        runLoggedServer({
            directory: ${JSON.stringify(directory)},
            consoleOutput: true,
            args: ['-e', ${JSON.stringify(`
                process.on('SIGTERM', () => { console.error('shutdown-tail'); process.exit(0); });
                console.log('child-ready');
                setInterval(() => {}, 1000);
            `)}]
        }).then(code => process.exitCode = code, () => process.exitCode = 1);
    `
    const child = spawn(process.execPath, ['-e', source], { stdio: ['ignore', 'pipe', 'pipe'] })
    const exited = once(child, 'exit')
    t.after(async () => {
        if (child.exitCode === null && child.signalCode === null) {
            child.kill('SIGKILL')
            await exited
        }
    })
    await new Promise((resolve, reject) => {
        child.on('error', reject)
        child.stdout.on('data', data => { if (data.toString().includes('child-ready')) resolve() })
        child.once('exit', () => reject(new Error('Collector exited before child-ready')))
    })
    child.kill('SIGTERM')
    assert.deepEqual(await exited, [0, null])
    const receipt = JSON.parse(fs.readFileSync(path.join(directory, 'cn-server-current.json')))
    assert.match(fs.readFileSync(receipt.log, 'utf8'), /\[stderr\] shutdown-tail/)
    assert.equal(receipt.exitCode, 0)
})

test('startup scripts use the collector without fixed stdout/stderr redirection', () => {
    const logged = fs.readFileSync(path.join(root, 'scripts/start-cn-logged.ps1'), 'utf8')
    const debug = fs.readFileSync(path.join(root, 'scripts/start-cn-debug.ps1'), 'utf8')
    const posix = fs.readFileSync(path.join(root, 'scripts/start-cn.sh'), 'utf8')
    assert.match(logged, /scripts\/run-cn-logged\.cjs/)
    assert.doesNotMatch(logged, /-RedirectStandard(?:Output|Error)/)
    assert.match(logged, /candidate\.loggerPid -eq \$process\.Id/)
    assert.match(debug, /"--debug" "--console"/)
    assert.match(posix, /nohup node --env-file=\.env scripts\/run-cn-logged\.cjs/)
})
