'use strict'
// Explicit opt-in LAN launcher. Merely preparing this candidate never binds a socket.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), net = require('node:net')
const assert = require('node:assert/strict'), { spawn } = require('node:child_process'), { createHash } = require('node:crypto')
const repo = path.resolve(__dirname, '..')
function privateHost(host, interfaces = os.networkInterfaces()) {
    assert.equal(net.isIP(host), 4, 'Explicit LAN IPv4 required')
    const [first, second] = host.split('.').map(Number)
    assert.ok(first === 10 || first === 172 && second >= 16 && second <= 31 || first === 192 && second === 168, 'Only RFC1918 LAN IPv4 may bind; public, wildcard and loopback addresses are rejected')
    assert.ok(Object.values(interfaces).flat().some(row => row && row.family === 'IPv4' && !row.internal && row.address === host), 'LAN IPv4 must belong to a current local interface')
    return host
}
function inside(root, target) {
    const relative = path.relative(root, path.resolve(target))
    assert.ok(relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative), 'LAN state path must stay in the dedicated run')
}
function prepare({ directory, host, pairFile }) {
    host = privateHost(host); directory = fs.realpathSync(directory)
    const baseEnv = JSON.parse(fs.readFileSync(path.join(directory, 'launch-env.json'), 'utf8'))
    assert.equal(fs.realpathSync(baseEnv.STARPOINT_ISOLATED_RUNTIME_ROOT), directory)
    assert.equal(fs.realpathSync(baseEnv.DATA_DIR), fs.realpathSync(path.join(directory, 'data')))
    const verification = JSON.parse(fs.readFileSync(path.join(directory, 'result.json'), 'utf8'))
    assert.equal(fs.realpathSync(verification.directory), directory)
    assert.equal(verification.fullVerificationPassed, true, 'Complete --verify before preparing a LAN candidate')
    assert.deepEqual(require('./isolated-content-runtime.cjs').inputs(), verification.inputIdentity, 'Prepare LAN only from the currently verified compiled runtime and plan')
    const normal = JSON.parse(fs.readFileSync(path.join(directory, 'normal-startup-smoke.json'), 'utf8'))
    assert.equal(normal.gracefulShutdownExitCode, 0); assert.equal(normal.actualLoad.resultCode, 1)
    const pair = JSON.parse(fs.readFileSync(pairFile, 'utf8')), build = pair.build
    assert.ok(build && typeof build.id === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(build.id))
    assert.equal(build.enabled, true); assert.equal(build.platform ?? 'android', 'android')
    assert.ok(build.allowUntil === null || typeof build.allowUntil === 'string' && Number.isFinite(Date.parse(build.allowUntil)) && Date.parse(build.allowUntil) > Date.now(), 'Selected existing build must be unexpired')
    assert.match(pair.key, /^[a-f0-9]{64}$/)
    assert.equal(pair.validatedExistingPair, true, 'Pair input must explicitly identify the already selected, verified existing build')
    const config = path.join(directory, 'config', 'lan-client-admission.json'), keys = path.join(directory, 'config', 'lan-client-admission.keys.json')
    const minimalBuild = { id: build.id, name: typeof build.name === 'string' ? build.name : 'Existing selected Android LAN build', enabled: true, platform: 'android', allowUntil: build.allowUntil }
    fs.writeFileSync(config, JSON.stringify({ enforce: true, updateMessage: '请使用本批隔离局域网测试包。', builds: [minimalBuild] }, null, 2))
    fs.writeFileSync(keys, JSON.stringify({ [build.id]: pair.key }, null, 2))
    const env = { ...baseEnv, CN_RUNTIME_IMPORT_ONLY: '0', CN_LISTEN_HOST: host, CN_LISTEN_PORT: '18001', SESSION_HOST: host, SESSION_PORT: '18003', CN_PUBLIC_HOST: host, SESSION_PUBLIC_HOST: host, CDN_BASE_URL: `http://${host}:8001/patch/cn`, CN_WRITER_THREAD: '1', CLIENT_ADMISSION_CONFIG: config, CLIENT_ADMISSION_KEYS: keys }
    for (const name of ['DATA_DIR', 'TMP', 'TEMP', 'TMPDIR', 'SQLITE_TMPDIR', 'GACHA_SEED_DIR', 'CN_LOG_DIR', 'NEWS_CONFIG_PATH', 'CLIENT_ADMISSION_CONFIG', 'CLIENT_ADMISSION_KEYS']) inside(directory, env[name])
    fs.writeFileSync(path.join(directory, 'launch-env-lan.private.json'), JSON.stringify(env, null, 2))
    const metadata = { schema: 1, directory, host, apiOrigin: `http://${host}:18001`, admissionOrigin: `http://${host}:18001`, session: { host, port: 18003 }, cdnBaseUrl: env.CDN_BASE_URL, database: path.join(env.DATA_DIR, 'wdfp_data.db'), config, keysFile: keys, inputIdentity: verification.inputIdentity, selectedBuild: minimalBuild, keySha256: createHash('sha256').update(pair.key).digest('hex'), reusedExistingPair: true, newIdAllocated: false, realSourceConfigChanged: false, preparedOnly: true, manualCommand: `node "${__filename}" --serve-lan --resume "${directory}" --host ${host}` }
    fs.writeFileSync(path.join(directory, 'lan-candidate.json'), JSON.stringify(metadata, null, 2))
    return metadata
}
async function reserve(host, port) {
    return new Promise((resolve, reject) => {
        const server = net.createServer(socket => socket.destroy())
        server.once('error', error => reject(Error(`LAN port ${port} is occupied or unavailable (${error.code}); no existing process was stopped`)))
        server.listen({ host, port, exclusive: true }, () => resolve(server))
    })
}
async function launch({ directory, host }) {
    host = privateHost(host); directory = fs.realpathSync(directory)
    const metadata = JSON.parse(fs.readFileSync(path.join(directory, 'lan-candidate.json'), 'utf8'))
    assert.equal(metadata.host, host, 'Prepared endpoint and APK host must match; prepare again deliberately when changing host')
    assert.deepEqual(require('./isolated-content-runtime.cjs').inputs(), metadata.inputIdentity, 'Prepared compiled runtime or plan changed; rerun isolated verification and prepare a fresh candidate')
    assert.equal(metadata.selectedBuild.enabled, true); assert.equal(metadata.selectedBuild.platform, 'android')
    assert.ok(metadata.selectedBuild.allowUntil === null || Date.parse(metadata.selectedBuild.allowUntil) > Date.now(), 'Prepared existing build has expired; refusing startup')
    const env = JSON.parse(fs.readFileSync(path.join(directory, 'launch-env-lan.private.json'), 'utf8'))
    assert.equal(env.CN_LISTEN_HOST, host); assert.equal(env.SESSION_HOST, host)
    assert.equal(env.CN_LISTEN_PORT, '18001'); assert.equal(env.SESSION_PORT, '18003')
    assert.equal(env.CN_RUNTIME_IMPORT_ONLY, '0'); assert.equal(env.STARPOINT_ISOLATED_RUNTIME_ROOT, directory)
    assert.equal(env.CDN_BASE_URL, `http://${host}:8001/patch/cn`)
    for (const name of ['DATA_DIR', 'TMP', 'TEMP', 'TMPDIR', 'SQLITE_TMPDIR', 'GACHA_SEED_DIR', 'CN_LOG_DIR', 'NEWS_CONFIG_PATH', 'CLIENT_ADMISSION_CONFIG', 'CLIENT_ADMISSION_KEYS']) inside(directory, env[name])
    const held = []
    try { for (const port of [18001, 18003]) held.push(await reserve(host, port)) }
    finally { await Promise.all(held.map(server => new Promise(resolve => server.close(resolve)))) }
    console.log(JSON.stringify({ status: 'starting-isolated-lan', apiOrigin: metadata.apiOrigin, session: metadata.session, cdnBaseUrl: metadata.cdnBaseUrl, selectedBuildId: metadata.selectedBuild.id, database: metadata.database, administratorPassword: env.ADMIN_PANEL_PASSWORD, warning: 'This is an independent synthetic player environment. Existing 8001/8003 services are unchanged.' }))
    const child = spawn(process.execPath, ['--require', path.join(__dirname, 'isolated-runtime-fs-guard.cjs'), path.join(repo, 'out/cn-server.js')], { cwd: directory, env, stdio: ['inherit', 'inherit', 'inherit', 'ipc'], windowsHide: true })
    const shutdown = () => { if (child.connected) child.send({ type: 'starpoint:shutdown' }) }
    process.once('SIGINT', shutdown); process.once('SIGTERM', shutdown); process.once('SIGBREAK', shutdown)
    child.once('exit', (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0) })
    return child
}
if (require.main === module) {
    const value = flag => { const index = process.argv.indexOf(flag); return index >= 0 ? process.argv[index + 1] : undefined }
    const options = { directory: value('--resume'), host: value('--host'), pairFile: value('--pair') }
    if (process.argv.includes('--prepare-lan')) console.log(JSON.stringify(prepare(options), null, 2))
    else if (process.argv.includes('--serve-lan')) launch(options).catch(error => { console.error(error.message); process.exitCode = 1 })
    else throw Error('Use --prepare-lan --resume <run> --host <local-private-IPv4> --pair <selected-pair-file>, or --serve-lan --resume <run> --host <local-private-IPv4>')
}
module.exports = { privateHost, prepare, reserve, launch }
