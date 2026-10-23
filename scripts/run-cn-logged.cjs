// Keep log I/O outside the game process. Buckets use real time, not the game clock.
const fs = require('node:fs')
const path = require('node:path')
const net = require('node:net')
const os = require('node:os')
const { spawn } = require('node:child_process')
const { Writable } = require('node:stream')
const { pipeline, finished } = require('node:stream/promises')
const { StringDecoder } = require('node:string_decoder')
const { randomUUID } = require('node:crypto')

const FOUR_HOURS_MS = 4 * 60 * 60 * 1000
const LOG_SYNC_INTERVAL_MS = 100
const PARTIAL_LINE_FLUSH_MS = 100
const MAX_LINE_CHARS = 64 * 1024
const STOP_REQUEST_MAX_AGE_MS = 30_000
const GRACEFUL_STOP_WAIT_MS = 180_000

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
    constructor({
        directory,
        retentionDays = 30,
        debug = false,
        now = Date.now,
        onRotate = () => {},
        syncIntervalMs = LOG_SYNC_INTERVAL_MS,
    }) {
        super({ objectMode: true, highWaterMark: 16 })
        if (!Number.isInteger(retentionDays) || retentionDays < 1 || retentionDays > 3650) {
            throw new RangeError('Retention days must be an integer from 1 to 3650.')
        }
        if (!Number.isInteger(syncIntervalMs) || syncIntervalMs < 1 || syncIntervalMs > 60_000) {
            throw new RangeError('Log sync interval must be an integer from 1 to 60000 milliseconds.')
        }
        this.directory = path.resolve(directory)
        this.retentionDays = retentionDays
        this.debug = debug
        this.now = now
        this.onRotate = onRotate
        this.syncIntervalMs = syncIntervalMs
        this.file = null
        this.bucket = null
        this.dirty = false
        this.syncTimer = null
        this.syncChain = Promise.resolve()
    }

    async rotate(timeMs) {
        const bucket = logBucket(timeMs, this.debug)
        if (this.bucket?.start === bucket.start) return
        await fs.promises.mkdir(this.directory, { recursive: true })
        await this.closeFile()
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
        this.dirty = true
        this.scheduleSync()
    }

    _final(callback) {
        this.closeFile().then(() => callback(), callback)
    }

    _destroy(error, callback) {
        this.closeFile().then(() => callback(error), closeError => callback(error || closeError))
    }

    scheduleSync() {
        if (this.syncTimer) return
        this.syncTimer = setTimeout(() => {
            this.syncTimer = null
            this.syncCurrentFile().catch(error => this.destroy(error))
        }, this.syncIntervalMs)
        this.syncTimer.unref()
    }

    async syncCurrentFile() {
        const file = this.file
        if (!file || !this.dirty) {
            await this.syncChain
            return
        }
        this.dirty = false
        this.syncChain = this.syncChain.then(() => file.datasync())
        await this.syncChain
    }

    async closeFile() {
        if (this.syncTimer) {
            clearTimeout(this.syncTimer)
            this.syncTimer = null
        }
        const file = this.file
        if (!file) {
            await this.syncChain
            return
        }
        let failure
        try {
            await this.syncCurrentFile()
        } catch (error) {
            failure = error
        }
        this.file = null
        try {
            await file.close()
        } catch (error) {
            failure ??= error
        }
        if (failure) throw failure
    }
}

function writeLines(writer, channel, lines) {
    return new Promise((resolve, reject) => {
        writer.write({ channel, lines }, error => error ? reject(error) : resolve())
    })
}

function logChannel(writer, channel, mirror, partialLineFlushMs = PARTIAL_LINE_FLUSH_MS) {
    if (!Number.isInteger(partialLineFlushMs)
        || partialLineFlushMs < 1 || partialLineFlushMs > 60_000) {
        throw new RangeError('Partial line flush interval must be an integer from 1 to 60000 milliseconds.')
    }
    const decoder = new StringDecoder('utf8')
    let pending = ''
    let partialTimer = null
    let skipLeadingTerminator = false
    let operation = Promise.resolve()
    let stream

    function clearPartialTimer() {
        if (!partialTimer) return
        clearTimeout(partialTimer)
        partialTimer = null
    }

    function enqueue(action) {
        operation = operation.then(action)
        return operation
    }

    async function flushPartialLine() {
        if (!pending) return
        const text = pending
        pending = ''
        skipLeadingTerminator = true
        await writeLines(writer, channel, [text])
    }

    function schedulePartialFlush() {
        if (partialTimer || !pending) return
        partialTimer = setTimeout(() => {
            partialTimer = null
            enqueue(flushPartialLine).catch(error => stream.destroy(error))
        }, partialLineFlushMs)
        partialTimer.unref()
    }

    async function consume(text, final = false) {
        if (mirror && text) {
            await new Promise((resolve, reject) =>
                mirror.write(text, error => error ? reject(error) : resolve()))
        }
        if (skipLeadingTerminator && text) {
            if (text === '\r') return
            if (text.startsWith('\r\n')) text = text.slice(2)
            else if (text.startsWith('\n') || text.startsWith('\r')) text = text.slice(1)
            skipLeadingTerminator = false
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
        if (final) clearPartialTimer()
        else if (pending) schedulePartialFlush()
        else clearPartialTimer()
    }
    stream = new Writable({
        write(chunk, _encoding, callback) {
            enqueue(() => consume(decoder.write(chunk))).then(() => callback(), callback)
        },
        final(callback) {
            clearPartialTimer()
            enqueue(() => consume(decoder.end(), true)).then(() => callback(), callback)
        },
        destroy(error, callback) {
            clearPartialTimer()
            callback(error)
        },
    })
    return stream
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

function validStopRequest(request, receipt, now = Date.now()) {
    const requestedAt = typeof request?.requestedAt === 'string' ? Date.parse(request.requestedAt) : NaN
    return request?.version === 1 && request.pid === receipt.pid && request.loggerPid === receipt.loggerPid
        && request.startedAt === receipt.startedAt && request.stopToken === receipt.stopToken
        && Number.isFinite(requestedAt) && requestedAt >= Date.parse(receipt.startedAt)
        && requestedAt <= now + 5_000 && now - requestedAt <= STOP_REQUEST_MAX_AGE_MS
}

async function listenForStopRequests(receiptPath, receipt, getChild, waitMs = GRACEFUL_STOP_WAIT_MS) {
    let consumed = false, deadline, closed = false
    const sockets = new Set(), pending = new Set()
    const update = state => {
        receipt.gracefulStop = { ...receipt.gracefulStop, ...state }
        saveReceipt(receiptPath, receipt, true)
    }
    async function consume(request) {
        let sending = false
        try {
            const child = getChild()
            const current = JSON.parse(fs.readFileSync(receiptPath, 'utf8'))
            if (consumed || !validStopRequest(request, receipt)
                || current.pid !== receipt.pid || current.loggerPid !== receipt.loggerPid || current.startedAt !== receipt.startedAt
                || current.stopToken !== receipt.stopToken || current.stopPipe !== receipt.stopPipe)
                throw new Error('Foreign, expired or already consumed stop request')
            if (!child?.connected || child.exitCode !== null || child.signalCode !== null) throw new Error('Server IPC is unavailable')
            consumed = true
            sending = true
            update({ state: 'ipc-sent', requestedAt: request.requestedAt, acceptedAt: new Date().toISOString() })
            await new Promise((resolve, reject) => child.send({ type: 'starpoint:shutdown' }, error => error ? reject(error) : resolve()))
            deadline = setTimeout(() => {
                if (child.exitCode === null && child.signalCode === null) {
                    try { update({ state: 'timed-out', timedOutAt: new Date().toISOString() }) }
                    catch (error) { console.error('[LOG-CAPTURE] stop receipt:', error.message) }
                    console.error('[LOG-CAPTURE] Graceful stop timed out; server was not force-killed.')
                }
            }, waitMs)
            deadline.unref()
            return { accepted: true }
        } catch (error) {
            if (sending) update({ state: 'ipc-failed', ipcError: error.message })
            receipt.stopRequestRejection = { at: new Date().toISOString(), reason: error.message }
            saveReceipt(receiptPath, receipt, true)
            console.error('[LOG-CAPTURE] Stop request rejected:', error.message)
            return { accepted: false, error: error.message }
        }
    }
    // Local IPC wakes only when a client connects; no periodic file checks.
    const server = net.createServer(socket => {
        sockets.add(socket)
        socket.on('close', () => sockets.delete(socket))
        socket.on('error', () => socket.destroy())
        socket.setTimeout(5_000, () => socket.destroy())
        let data = '', bytes = 0, handled = false
        socket.setEncoding('utf8')
        socket.on('data', chunk => {
            if (handled) return
            bytes += Buffer.byteLength(chunk)
            if (bytes > 16_384) { handled = true; socket.destroy(); return }
            data += chunk
            const newline = data.indexOf('\n')
            if (newline < 0) return
            handled = true
            const task = (async () => {
                let response
                try { response = await consume(JSON.parse(data.slice(0, newline))) }
                catch { response = { accepted: false, error: 'Invalid stop request' } }
                if (!socket.destroyed) await new Promise(resolve => socket.end(JSON.stringify(response) + '\n', resolve))
            })()
            pending.add(task)
            task.finally(() => pending.delete(task))
        })
    })
    await new Promise((resolve, reject) => {
        server.once('error', reject)
        server.listen(receipt.stopPipe, () => { server.removeListener('error', reject); resolve() })
    })
    server.on('error', error => console.error('[LOG-CAPTURE] stop pipe:', error.message))
    return async () => {
        if (closed) return
        closed = true
        await Promise.all(pending)
        clearTimeout(deadline)
        for (const socket of sockets) socket.destroy()
        await new Promise(resolve => server.close(resolve))
    }
}

async function runLoggedServer({
    root = path.resolve(__dirname, '..'),
    directory = path.join(root, '.logs'),
    args = [path.join(root, 'out/cn-server.js')],
    retentionDays = 30,
    debug = false,
    consoleOutput = false,
    gracefulStopWaitMs = GRACEFUL_STOP_WAIT_MS,
} = {}) {
    root = fs.realpathSync(root)
    directory = path.resolve(directory)
    const receiptPath = path.join(directory, `cn-server-${debug ? 'debug-' : ''}current.json`)
    const receipt = {
        pid: null,
        loggerPid: process.pid,
        startedAt: null,
        loggerStartedAt: new Date(Date.now() - process.uptime() * 1000).toISOString(),
        projectRoot: root,
        executable: process.execPath,
        loggerEntry: __filename,
        serverEntry: args[0]?.startsWith('-') ? null : path.resolve(root, args[0]),
        httpPort: Number(process.env.CN_LISTEN_PORT || 8001),
        stopToken: randomUUID(),
        stopPipe: process.platform === 'win32'
            ? `\\\\.\\pipe\\starpoint-cn-stop-${process.pid}-${randomUUID()}`
            : path.join(os.tmpdir(), `sp-cn-${process.pid}-${randomUUID()}.sock`),
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
    let stopWatching = async () => {}
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
        // Fail before starting the game if its local stop channel cannot be opened.
        stopWatching = await listenForStopRequests(receiptPath, receipt, () => child, gracefulStopWaitMs)
        receipt.startedAt = new Date().toISOString()
        child = spawn(process.execPath, args, {
            cwd: root,
            windowsHide: true,
            stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
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
        await stopWatching()
        await Promise.all([stdout, stderr])
        if (!writer.destroyed) {
            await new Promise((resolve, reject) =>
                writer.end(error => error ? reject(error) : resolve()))
        }
        Object.assign(receipt, {
            exitedAt: new Date().toISOString(),
            exitCode: failure ? 1 : result.code,
            signal: result.signal,
            ...(receipt.gracefulStop ? { gracefulStop: { ...receipt.gracefulStop, state: 'exited',
                completedAt: new Date().toISOString(), clean: !failure && !receipt.gracefulStop.ipcError && result.code === 0 && result.signal === null } } : {}),
            ...(failure ? { error: failure.message } : {}),
        })
        saveReceipt(receiptPath, receipt, true)
        if (failure) throw failure
        return result.code ?? (result.signal === 'SIGINT' ? 130 : 143)
    } finally {
        await stopWatching()
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
            else if (argv[i] === '--root') options.root = path.resolve(argv[++i])
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

module.exports = {
    FOUR_HOURS_MS, LOG_SYNC_INTERVAL_MS, PARTIAL_LINE_FLUSH_MS,
    logBucket, RotatingLogWriter, logChannel, runLoggedServer,
    validStopRequest, STOP_REQUEST_MAX_AGE_MS, GRACEFUL_STOP_WAIT_MS,
}
