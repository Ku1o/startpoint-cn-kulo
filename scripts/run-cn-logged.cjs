// Keep log I/O outside the game process. Buckets use real time, not the game clock.
const fs = require('node:fs')
const path = require('node:path')
const { spawn } = require('node:child_process')
const { Writable } = require('node:stream')
const { pipeline, finished } = require('node:stream/promises')
const { StringDecoder } = require('node:string_decoder')

const FOUR_HOURS_MS = 4 * 60 * 60 * 1000
const MAX_LINE_CHARS = 64 * 1024

function logBucket(timeMs, debug = false) {
    const start = Math.floor(timeMs / FOUR_HOURS_MS) * FOUR_HOURS_MS
    const date = new Date(start + 8 * 60 * 60 * 1000)
    const pad = value => String(value).padStart(2, '0')
    const stamp = `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}`
        + `${pad(date.getUTCDate())}-${pad(date.getUTCHours())}00`
    return {
        start,
        end: start + FOUR_HOURS_MS,
        name: `cn-server-${debug ? 'debug-' : ''}${stamp}.log`,
    }
}

async function pruneLogs(directory, retentionDays, timeMs, debug, currentPath) {
    // Preserve diagnostics, receipts, unrelated files and the other logging mode.
    const pattern = debug
        ? /^cn-server-debug-\d{8}-\d{4,6}\.log$/
        : /^cn-server-\d{8}-\d{4,6}(?:\.(?:stdout|stderr))?\.log$/
    const cutoff = timeMs - retentionDays * 24 * 60 * 60 * 1000
    for (const entry of await fs.promises.readdir(directory, { withFileTypes: true })) {
        if (!entry.isFile() || !pattern.test(entry.name)) continue
        const file = path.join(directory, entry.name)
        if (file === currentPath) continue
        try {
            if ((await fs.promises.stat(file)).mtimeMs < cutoff) {
                await fs.promises.unlink(file)
            }
        } catch (error) {
            if (error.code !== 'ENOENT') throw error
        }
    }
}

class RotatingLogWriter extends Writable {
    constructor({ directory, retentionDays = 30, debug = false, now = Date.now, onRotate = () => {} }) {
        super({ objectMode: true, highWaterMark: 16 })
        if (!Number.isInteger(retentionDays) || retentionDays < 1 || retentionDays > 3650) {
            throw new RangeError('Retention days must be an integer from 1 to 3650.')
        }
        this.directory = path.resolve(directory)
        this.retentionDays = retentionDays
        this.debug = debug
        this.now = now
        this.onRotate = onRotate
        this.file = null
        this.bucket = null
    }

    async rotate(timeMs) {
        const bucket = logBucket(timeMs, this.debug)
        if (this.bucket?.start === bucket.start) return
        await fs.promises.mkdir(this.directory, { recursive: true })
        await this.file?.close()
        this.file = null
        const filePath = path.join(this.directory, bucket.name)
        // Append across restarts within the same four-hour bucket.
        this.file = await fs.promises.open(filePath, 'a')
        this.bucket = bucket
        await this.onRotate({ ...bucket, path: filePath })
        await pruneLogs(this.directory, this.retentionDays, timeMs, this.debug, filePath)
    }

    _write(record, _encoding, callback) {
        const timeMs = this.now()
        this.writeRecord(record, timeMs).then(() => callback(), callback)
    }

    async writeRecord(record, timeMs) {
        await this.rotate(timeMs)
        const prefix = `[${new Date(timeMs).toISOString()}] [${record.channel}] `
        const data = Buffer.from((record.lines ?? [record.text]).map(text => `${prefix}${text}\n`).join(''))
        // Handle partial writes without dropping the remainder.
        let offset = 0
        while (offset < data.length) {
            const { bytesWritten } = await this.file.write(data, offset, data.length - offset)
            if (!bytesWritten) throw new Error('Log file write made no progress.')
            offset += bytesWritten
        }
    }

    _final(callback) {
        this.closeFile().then(() => callback(), callback)
    }

    _destroy(error, callback) {
        this.closeFile().then(() => callback(error), closeError => callback(error || closeError))
    }

    async closeFile() {
        const file = this.file
        this.file = null
        await file?.close()
    }
}

function writeLines(writer, channel, lines) {
    return new Promise((resolve, reject) => {
        writer.write({ channel, lines }, error => error ? reject(error) : resolve())
    })
}

function logChannel(writer, channel, mirror) {
    const decoder = new StringDecoder('utf8')
    let pending = ''
    async function consume(text, final = false) {
        if (mirror && text) {
            await new Promise((resolve, reject) =>
                mirror.write(text, error => error ? reject(error) : resolve()))
        }
        pending += text
        let lines = []
        let size = 0
        while (pending.length > 0) {
            const newline = pending.indexOf('\n')
            if (newline >= 0 && newline <= MAX_LINE_CHARS) {
                const line = pending.slice(0, newline).replace(/\r$/, '')
                pending = pending.slice(newline + 1)
                lines.push(line)
                size += line.length + 1
            } else if (pending.length >= MAX_LINE_CHARS) {
                // Do not cut an astral character's UTF-16 surrogate pair.
                const lastCode = pending.charCodeAt(MAX_LINE_CHARS - 1)
                const length = lastCode >= 0xD800 && lastCode <= 0xDBFF
                    ? MAX_LINE_CHARS - 1 : MAX_LINE_CHARS
                lines.push(pending.slice(0, length))
                size += length
                pending = pending.slice(length)
            } else if (final) {
                lines.push(pending)
                size += pending.length
                pending = ''
            } else {
                break
            }
            if (size >= MAX_LINE_CHARS) {
                await writeLines(writer, channel, lines)
                lines = []
                size = 0
            }
        }
        if (lines.length) await writeLines(writer, channel, lines)
    }
    return new Writable({
        write(chunk, _encoding, callback) {
            consume(decoder.write(chunk)).then(() => callback(), callback)
        },
        final(callback) {
            consume(decoder.end(), true).then(() => callback(), callback)
        },
    })
}

function saveReceipt(file, receipt, onlyIfOwned = false) {
    const temporary = `${file}.${process.pid}.tmp`
    try {
        if (onlyIfOwned) {
            let current
            try { current = JSON.parse(fs.readFileSync(file, 'utf8')) }
            catch (error) {
                if (error.code === 'ENOENT') return
                throw error
            }
            if (current.loggerPid !== receipt.loggerPid || current.pid !== receipt.pid
                || current.startedAt !== receipt.startedAt) return
        }
        fs.writeFileSync(temporary, JSON.stringify(receipt, null, 2) + '\n')
        fs.renameSync(temporary, file)
    } finally {
        if (fs.existsSync(temporary)) fs.unlinkSync(temporary)
    }
}

async function runLoggedServer({
    root = path.resolve(__dirname, '..'),
    directory = path.join(root, '.logs'),
    args = ['out/cn-server.js'],
    retentionDays = 30,
    debug = false,
    consoleOutput = false,
} = {}) {
    directory = path.resolve(directory)
    const receiptPath = path.join(directory, `cn-server-${debug ? 'debug-' : ''}current.json`)
    const receipt = {
        pid: null,
        loggerPid: process.pid,
        startedAt: null,
        timezone: 'UTC+08:00',
        intervalHours: 4,
        retentionDays,
        temp: process.env.TMPDIR || process.env.TEMP || process.env.TMP || null,
    }
    const writer = new RotatingLogWriter({
        directory, retentionDays, debug,
        onRotate(bucket) {
            Object.assign(receipt, {
                log: bucket.path,
                // Maintenance tooling still uses stdout to check project ownership.
                stdout: bucket.path,
                stderr: bucket.path,
                bucketStart: new Date(bucket.start).toISOString(),
                bucketEnd: new Date(bucket.end).toISOString(),
            })
            if (receipt.pid) saveReceipt(receiptPath, receipt, true)
        },
    })
    let child
    let forcedStop
    let failure
    function stop(signal = 'SIGTERM') {
        if (!child || child.exitCode !== null || child.signalCode !== null) return
        child.kill(signal)
        if (!forcedStop) {
            forcedStop = setTimeout(() => child.kill('SIGKILL'), 10_000)
            forcedStop.unref()
        }
    }
    function fail(error) {
        failure ??= error
        stop()
    }
    writer.on('error', fail)
    const writerClosed = finished(writer).catch(fail)
    const interrupt = () => stop('SIGINT')
    const terminate = () => stop('SIGTERM')
    process.on('SIGINT', interrupt)
    process.on('SIGTERM', terminate)
    try {
        await writer.rotate(Date.now())
        receipt.startedAt = new Date().toISOString()
        child = spawn(process.execPath, args, {
            cwd: root,
            windowsHide: true,
            stdio: ['ignore', 'pipe', 'pipe'],
        })
        const closed = new Promise(resolve => {
            child.on('error', fail)
            child.on('close', (code, signal) => resolve({ code, signal }))
        })
        receipt.pid = child.pid
        try {
            saveReceipt(receiptPath, receipt)
        } catch (error) {
            fail(error)
        }
        const capture = (source, channel, mirror) =>
            pipeline(source, logChannel(writer, channel, mirror)).catch(fail)
        const stdout = capture(child.stdout, 'stdout', consoleOutput ? process.stdout : null)
        const stderr = capture(child.stderr, 'stderr', consoleOutput ? process.stderr : null)
        const result = await closed
        await Promise.all([stdout, stderr])
        if (!writer.destroyed) {
            await new Promise((resolve, reject) =>
                writer.end(error => error ? reject(error) : resolve()))
        }
        Object.assign(receipt, {
            exitedAt: new Date().toISOString(),
            exitCode: failure ? 1 : result.code,
            signal: result.signal,
            ...(failure ? { error: failure.message } : {}),
        })
        saveReceipt(receiptPath, receipt, true)
        if (failure) throw failure
        return result.code ?? (result.signal === 'SIGINT' ? 130 : 143)
    } finally {
        if (forcedStop) clearTimeout(forcedStop)
        process.removeListener('SIGINT', interrupt)
        process.removeListener('SIGTERM', terminate)
        writer.destroy()
        await writerClosed
    }
}

if (require.main === module) {
    const options = {}
    const argv = process.argv.slice(2)
    try {
        for (let i = 0; i < argv.length; i++) {
            if (argv[i] === '--') { options.args = argv.slice(i + 1); break }
            if (argv[i] === '--retention-days') options.retentionDays = Number(argv[++i])
            else if (argv[i] === '--debug') options.debug = true
            else if (argv[i] === '--console') options.consoleOutput = true
            else throw new Error(`Unknown argument: ${argv[i]}`)
        }
        runLoggedServer(options).then(
            code => { process.exitCode = code },
            error => { console.error('[LOG-CAPTURE]', error); process.exitCode = 1 },
        )
    } catch (error) {
        console.error('[LOG-CAPTURE]', error)
        process.exitCode = 1
    }
}

module.exports = { FOUR_HOURS_MS, logBucket, RotatingLogWriter, logChannel, runLoggedServer }
