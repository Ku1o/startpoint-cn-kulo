// Run checks with all disposable state under this repository, including children.
const fs = require('node:fs')
const path = require('node:path')
const { spawn } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const parent = path.join(root, 'tmp')
fs.mkdirSync(parent, { recursive: true })
const args = process.argv.slice(2)
if (!args.length) args.push('--test', 'tests/multicore-snapshot.test.cjs')
const commands = args[0] === '--test' && args.length > 2
    && args.slice(1).every(argument => !argument.startsWith('-'))
    ? args.slice(1).map(file => ['--test', file])
    : [args]
let child = null
let directory = null
let interruptedSignal = null
function cleanupDirectory() {
    if (!directory) return
    fs.rmSync(directory, { recursive: true, force: true })
    directory = null
}
function cleanup() {
    cleanupDirectory()
    try { fs.rmdirSync(parent) } catch {}
    console.log('[check] temporary state removed')
}
for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => {
        interruptedSignal = signal
        if (!child) return
        try {
            if (process.platform === 'win32') child.kill(signal)
            else process.kill(-child.pid, signal)
        } catch {}
    })
}

async function run(command) {
    directory = fs.mkdtempSync(path.join(parent, 'cpu-check-'))
    const environment = {
        ...process.env,
        TMPDIR: directory, TMP: directory, TEMP: directory,
        DATA_DIR: path.join(directory, 'database'),
        GACHA_SEED_DIR: path.join(directory, 'seeds'),
        npm_config_cache: path.join(directory, 'npm-cache'),
        PROCESS_MEMORY_DIAGNOSTICS: 'false',
    }
    for (const key of ['CN_LOAD_CAPTURE_PATH', 'PERF_STATE_OUTPUT']) delete environment[key]
    const code = await new Promise((resolve, reject) => {
        child = spawn(process.execPath, command, {
            cwd: root,
            stdio: 'inherit',
            env: environment,
            detached: process.platform !== 'win32',
        })
        child.once('error', reject)
        child.once('exit', (exitCode, signal) => resolve(exitCode ?? (signal ? 1 : 0)))
    })
    child = null
    cleanupDirectory()
    return code
}

async function main() {
    try {
        for (const command of commands) {
            const code = await run(command)
            if (interruptedSignal) {
                process.exitCode = interruptedSignal === 'SIGINT' ? 130 : 143
                return
            }
            if (code !== 0) {
                process.exitCode = code
                return
            }
        }
    } catch (error) {
        console.error(error)
        process.exitCode = 1
    } finally {
        cleanup()
    }
}

void main()
