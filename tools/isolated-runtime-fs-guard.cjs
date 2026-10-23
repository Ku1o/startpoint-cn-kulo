'use strict'
// Harness-only confinement, inherited by actual SQLite worker threads via --require.
const fs = require('node:fs'), path = require('node:path'), Module = require('node:module')
const { fileURLToPath } = require('node:url')
const root = process.env.STARPOINT_ISOLATED_RUNTIME_ROOT
if (!root) throw Error('Explicit STARPOINT_ISOLATED_RUNTIME_ROOT required')
const realpath = fs.realpathSync, rawOpen = fs.openSync, rawWrite = fs.writeSync, rawClose = fs.closeSync
const writableDescriptors = new Map()
const canonical = value => {
    let target = path.resolve(value instanceof URL ? fileURLToPath(value) : String(value)), suffix = []
    while (!fs.existsSync(target)) { suffix.unshift(path.basename(target)); const parent = path.dirname(target); if (target === parent) throw Error('Unresolvable path'); target = parent }
    return path.join(realpath(target), ...suffix)
}
const allowedRoot = canonical(root)
function check(value) {
    if (typeof value === 'number') {
        if (!writableDescriptors.has(value)) throw Error('Isolated guard rejects untracked descriptor writes')
        value = writableDescriptors.get(value)
    }
    const resolved = canonical(value), relative = path.relative(allowedRoot, resolved)
    if (relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) throw Error('ISOLATED_WRITE_OUTSIDE_ROOT: ' + resolved)
    return resolved
}
const audit = (kind, value) => {
    const line = JSON.stringify({ pid: process.pid, threadId: require('node:worker_threads').threadId, kind, path: check(value) }) + '\n'
    const fd = rawOpen(path.join(allowedRoot, 'path-audit.jsonl'), 'a')
    try { rawWrite(fd, line) } finally { rawClose(fd) }
}
for (const name of ['writeFile', 'appendFile', 'mkdir', 'mkdtemp', 'rm', 'rmdir', 'unlink', 'truncate', 'chmod', 'chown', 'utimes']) {
    for (const suffix of ['', 'Sync']) if (typeof fs[name + suffix] === 'function') {
        const original = fs[name + suffix]
        fs[name + suffix] = function (target, ...args) { audit(name, target); return original.call(this, target, ...args) }
    }
    if (typeof fs.promises[name] === 'function') {
        const original = fs.promises[name]
        fs.promises[name] = function (target, ...args) { audit(name, target); return original.call(this, target, ...args) }
    }
}
for (const name of ['rename', 'copyFile', 'link', 'symlink']) for (const suffix of ['', 'Sync']) if (fs[name + suffix]) {
    const original = fs[name + suffix]
    fs[name + suffix] = function (source, destination, ...args) { audit(name, source); audit(name, destination); return original.call(this, source, destination, ...args) }
}
for (const suffix of ['', 'Sync']) {
    const original = fs['open' + suffix]
    fs['open' + suffix] = function (target, flags, ...args) {
        const writable = typeof flags === 'number' ? (flags & (fs.constants.O_WRONLY | fs.constants.O_RDWR | fs.constants.O_CREAT | fs.constants.O_TRUNC | fs.constants.O_APPEND)) !== 0 : /[wa+]/.test(flags)
        if (writable) audit('open-write', target)
        if (suffix === 'Sync') {
            const fd = original.call(this, target, flags, ...args)
            if (writable) writableDescriptors.set(fd, check(target))
            return fd
        }
        const callback = args.pop()
        return original.call(this, target, flags, ...args, (error, fd) => {
            if (!error && writable) writableDescriptors.set(fd, check(target))
            callback(error, fd)
        })
    }
}
for (const suffix of ['', 'Sync']) {
    const original = fs['close' + suffix]
    fs['close' + suffix] = function (fd, ...args) { writableDescriptors.delete(fd); return original.call(this, fd, ...args) }
}
const originalLoad = Module._load
let wrappedSqlite
Module._load = function (name, ...args) {
    const loaded = originalLoad.call(this, name, ...args)
    if (name !== 'better-sqlite3') return loaded
    if (!wrappedSqlite) wrappedSqlite = new Proxy(loaded, { construct(target, values) { if (values[0] !== ':memory:') audit('sqlite-open', values[0]); return Reflect.construct(target, values) } })
    return wrappedSqlite
}
globalThis.__isolatedRuntimeCheckPath = check
