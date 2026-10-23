'use strict'
// Explicit stopped-service migration. Never imports the server or opens its default DB.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), net = require('node:net')
const Sqlite = require('better-sqlite3')
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex')
const readJson = file => JSON.parse(fs.readFileSync(file, 'utf8'))
function saveJson(file, value) {
    const temporary = file + '.tmp-' + crypto.randomUUID()
    const fd = fs.openSync(temporary, 'wx')
    try { fs.writeFileSync(fd, JSON.stringify(value, null, 2) + '\n'); fs.fsyncSync(fd) } finally { fs.closeSync(fd) }
    fs.renameSync(temporary, file)
}
async function hashFile(file) { const hash = crypto.createHash('sha256'); for await (const chunk of fs.createReadStream(file)) hash.update(chunk); return hash.digest('hex') }
function inside(root, target) { const rel = path.relative(root, target); return rel && !path.isAbsolute(rel) && rel !== '..' && !rel.startsWith('..' + path.sep) }
function paths(project) {
    const root = fs.realpathSync(project), data = fs.realpathSync(process.env.DATA_DIR ? path.resolve(root, process.env.DATA_DIR) : path.join(root, '.database'))
    const database = fs.realpathSync(path.join(data, 'wdfp_data.db'))
    if (!inside(data, database) || fs.statSync(database).nlink !== 1) throw Error('数据库路径或硬链接不安全')
    const maintenance = path.join(root, '.storage-maintenance')
    return { root, data, database, maintenance, state: path.join(maintenance, 'time-content-state.json'),
        locks: [path.join(maintenance, 'active.lock'), path.join(data, 'storage-maintenance.lock')] }
}
function api() {
    return {
        ...require('../out/lib/deployment-maintenance-guard'),
        ...require('../out/lib/server-clock-state'),
        ...require('../out/lib/content-deployment'),
        ...require('../out/lib/content-operations'),
        ...require('../out/lib/content-operations-store'),
    }
}
function assertVersion(p) {
    if (Number(fs.readFileSync(p.database + '.version', 'utf8').trim()) !== require('../out/lib/storage-layout').WDFP_DATA_VERSION)
        throw Error('数据库版本不匹配；先使用对应版本的基础升级流程')
}
function legacyOffset(p, clock) {
    if (clock) return clock.snapshot.legacyBattleOffsetMs
    const file = path.join(p.data, 'active_account.json')
    if (!fs.existsSync(file)) throw Error('缺少原服务器时间记录，不能猜测旧对局的时间')
    const value = readJson(file).timeOffset
    if (!Number.isSafeInteger(value)) throw Error('旧时间偏移无效，必须核实后再迁移')
    return value
}
function validateInputs(p) {
    if (fs.realpathSync(path.resolve(__dirname, '..')) !== p.root) throw Error('迁移工具必须从目标服务目录运行，不能混用另一工作树的程序')
    const index = readJson(path.join(p.root, 'assets/content_discovery_runtime.json'))
    if (index.schemaVersion !== 2 || !index.sourceInputs || !Object.keys(index.sourceInputs).length) throw Error('关联资料索引缺失或无效')
    const mismatches = []
    for (const [relative, expected] of Object.entries(index.sourceInputs)) {
        const file = path.resolve(p.root, relative)
        if (!inside(p.root, file) || !fs.existsSync(file) || sha(fs.readFileSync(file)) !== expected) mismatches.push(relative)
    }
    if (mismatches.length) throw Error('程序与关联索引不匹配：' + mismatches.join(', '))
    return { discoveryInputs: Object.keys(index.sourceInputs).length,
        discovery: sha(fs.readFileSync(path.join(p.root, 'assets/content_discovery_runtime.json'))),
        contentPlan: sha(fs.readFileSync(path.join(p.root, 'assets/content_deployment_review_plan.json'))),
        boxExchangeReview: sha(fs.readFileSync(path.join(p.root, 'assets/content_box_exchange_review.json'))) }
}
function inspectDatabase(db, a) {
    const clock = a.readServerClockStateSync(db)
    const hasContent = !!db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_operations_meta'").get()
    const content = hasContent ? a.inspectContentDeploymentSync(a.createContentOperationsStore(db)) : { ready: false, reasons: ['尚未初始化内容运营表'] }
    return { ready: clock?.snapshot.mode === 'real' && content.ready, timeMode: clock?.snapshot.mode ?? 'legacy',
        clockPlanDigest: clock?.planDigest ?? null, content }
}
function inspect(options) {
    const p = paths(options.project); assertVersion(p)
    const inputs = validateInputs(p), a = api(), db = new Sqlite(p.database, { readonly: true, fileMustExist: true })
    try { return { database: p.database, ...inspectDatabase(db, a), inputs, maintenanceLocked: p.locks.some(file => fs.existsSync(file)) } }
    finally { db.close() }
}
function processAlive(pid) { if (!Number.isSafeInteger(pid) || pid <= 0) throw Error('服务进程记录无效'); try { process.kill(pid, 0); return true } catch (error) { if (error.code === 'ESRCH') return false; throw error } }
async function listening(port) {
    return new Promise((resolve, reject) => {
        const socket = net.connect({ host: '127.0.0.1', port })
        socket.setTimeout(1500)
        socket.once('connect', () => { socket.destroy(); resolve(true) })
        socket.once('timeout', () => { socket.destroy(); reject(Error('无法确认服务端口已停止')) })
        socket.once('error', error => { if (error.code === 'ECONNREFUSED') resolve(false); else reject(error) })
    })
}
async function assertStopped(p) {
    const logRoot = process.env.CN_LOG_DIR ? path.resolve(p.root, process.env.CN_LOG_DIR) : path.join(p.root, '.logs')
    for (const name of ['cn-server-current.json', 'cn-server-ready.json']) {
        const file = path.join(logRoot, name)
        if (fs.existsSync(file)) {
            const receipt = readJson(file)
            if (processAlive(receipt.pid)) throw Error('服务仍在运行，请先运行 scripts/stop-cn-logged.ps1 并等待完成')
        }
    }
    const ports = [Number(process.env.CN_LISTEN_PORT ?? 8001), Number(process.env.SESSION_PORT ?? 8003)]
    for (const port of ports) if (!Number.isInteger(port) || port < 1 || port > 65535 || await listening(port)) throw Error('服务或联机端口尚未停止')
}
function lockOwned(file, state) { const value = readJson(file); return value.kind === 'time-content-deployment' && value.runId === state.runId && value.database === state.database }
function assertOwned(p, state, missingAllowed = false) {
    if (state.format !== 1 || state.database !== p.database || !/^[a-f0-9-]{36}$/.test(state.runId)
        || !inside(path.join(p.data, 'time-content-backups'), state.backup)) throw Error('维护记录与目标数据库不一致')
    for (const file of p.locks) {
        if (!fs.existsSync(file) && missingAllowed) continue
        if (!fs.existsSync(file) || !lockOwned(file, state)) throw Error('维护锁不属于本批迁移，拒绝恢复或释放')
    }
}
function releaseLocks(p, state, checkpoint) {
    assertOwned(p, state, true)
    let deleted = 0
    for (const file of p.locks) if (fs.existsSync(file)) {
        fs.unlinkSync(file)
        if (++deleted === 1) checkpoint?.('after-release-first-lock')
    }
}
function loadState(p) {
    const journal = fs.existsSync(p.state) ? readJson(p.state) : null
    const firstLock = fs.existsSync(p.locks[0]) ? readJson(p.locks[0]) : null
    if (journal && (!firstLock || firstLock.runId === journal.runId)) return journal
    // A crash during initial lock acquisition, before the first journal/backup.
    const state = firstLock
    if (!state) throw Error('缺少可核实的维护记录')
    assertOwned(p, state, true)
    if (state.phase !== 'locking' || fs.existsSync(path.dirname(state.backup))) throw Error('维护记录缺失且无法证明尚未开始备份/迁移')
    for (const file of p.locks) if (!fs.existsSync(file)) fs.writeFileSync(file, JSON.stringify(state), { flag: 'wx' })
    return state
}
async function apply(options) {
    const p = paths(options.project); assertVersion(p)
    const inputs = validateInputs(p), a = api(); await assertStopped(p)
    fs.mkdirSync(p.maintenance, { recursive: true })
    const runId = crypto.randomUUID(), backupDir = path.join(p.data, 'time-content-backups', runId)
    const state = { format: 1, kind: 'time-content-deployment', runId, database: p.database, phase: 'locking',
        createdAt: new Date().toISOString(), backup: path.join(backupDir, 'wdfp_data.db'), inputs }
    const acquired = []
    try {
        for (const file of p.locks) { fs.writeFileSync(file, JSON.stringify(state), { flag: 'wx' }); acquired.push(file) }
    } catch (error) { for (const file of acquired) if (lockOwned(file, state)) fs.unlinkSync(file); throw error }
    saveJson(p.state, state)
    let db
    try {
        await assertStopped(p)
        db = new Sqlite(p.database, { fileMustExist: true, timeout: 1000 })
        db.pragma('locking_mode=EXCLUSIVE'); db.exec('BEGIN EXCLUSIVE; COMMIT')
        const before = inspectDatabase(db, a)
        // A repeat after later player progress or operator changes performs no writes.
        if (before.ready) {
            state.phase = 'already-ready'; state.result = before; saveJson(p.state, state)
            db.close(); db = null; releaseLocks(p, state); return state
        }
        state.beforeFingerprint = a.getDeploymentDatabaseFingerprintSync(db)
        saveJson(p.state, state)
        state.cutoverRealMs = Date.now(); state.legacyOffsetMs = legacyOffset(p, a.readServerClockStateSync(db))
        fs.mkdirSync(path.dirname(backupDir), { recursive: true })
        fs.mkdirSync(backupDir, { recursive: false })
        state.phase = 'backing-up'; saveJson(p.state, state)
        await db.backup(state.backup)
        state.backupSha256 = await hashFile(state.backup)
        for (const name of ['wdfp_data.db.version', 'active_account.json']) {
            const source = path.join(p.data, name)
            if (fs.existsSync(source)) fs.copyFileSync(source, path.join(backupDir, name), fs.constants.COPYFILE_EXCL)
        }
        state.phase = 'prepared'; saveJson(p.state, state)
        const guard = { kind: 'approved-stopped-database', databasePath: p.database, backupPath: state.backup,
            expectedDatabaseFingerprint: state.beforeFingerprint, expectedBackupSha256: state.backupSha256 }
        state.result = a.withDeploymentMaintenanceTransactionSync(db, guard, context => {
            a.initializeContentOperationsSchema(db)
            const store = a.createContentOperationsStore(db)
            const content = a.applyContentDeploymentMaintenanceSync(store, context, { nowMs: state.cutoverRealMs })
            if (options.faultAt === 'after-content') throw Error('Injected failure after content')
            let clock = a.readServerClockStateSync(db)
            if (!clock) {
                const coordinate = { cutoverRealMs: state.cutoverRealMs, legacyOffsetMs: state.legacyOffsetMs }
                const plan = a.planRealServerClockMaintenanceSync(db, coordinate, context)
                clock = a.activateRealServerClockMaintenanceSync(db, { ...coordinate, expectedPlanDigest: plan.digest }, context)
            }
            if (options.faultAt === 'after-clock') throw Error('Injected failure after clock')
            const actual = inspectDatabase(db, a)
            if (!actual.ready) throw Error('迁移后读回校验未通过')
            const result = { ...actual, contentMigration: content }
            // Durable intent BEFORE COMMIT closes the commit/report crash window.
            state.result = result; state.afterFingerprint = a.getDeploymentDatabaseFingerprintSync(db)
            state.phase = 'committing'; saveJson(p.state, state)
            options.checkpoint?.('before-commit')
            return result
        })
        options.checkpoint?.('after-commit')
        // This connection retains its EXCLUSIVE lock until close. Nothing writes
        // after the durable pre-commit fingerprint, so it is also the committed state.
        state.phase = 'applied'; saveJson(p.state, state); saveJson(path.join(backupDir, 'receipt.json'), state)
        return state
    } catch (error) {
        state.failedAt = state.phase; state.phase = 'failed'; state.error = error.message
        saveJson(p.state, state); throw error
    } finally { if (db?.open) db.close() }
}
async function release(options) {
    const p = paths(options.project), state = loadState(p)
    const completingRelease = ['released', 'released-without-migration', 'already-ready'].includes(state.phase)
    assertOwned(p, state, completingRelease); await assertStopped(p)
    if (['applied', 'released', 'already-ready'].includes(state.phase)) { if (!inspect(options).ready) throw Error('迁移验收尚未通过，保留维护锁') }
    else if (!['failed', 'rolled-back', 'released-without-migration'].includes(state.phase)) throw Error('该维护阶段不能释放；先检查备份和运行状态')
    else {
        const db = new Sqlite(p.database, { readonly: true, fileMustExist: true })
        try { if (api().getDeploymentDatabaseFingerprintSync(db) !== state.beforeFingerprint) throw Error('数据库变化，不能自动释放失败批次') }
        finally { db.close() }
    }
    state.phase = ['applied', 'released', 'already-ready'].includes(state.phase) ? 'released' : 'released-without-migration'
    saveJson(p.state, state); releaseLocks(p, state, options.checkpoint); return state
}
async function recover(options) {
    const p = paths(options.project), state = loadState(p)
    if (['released', 'released-without-migration', 'already-ready'].includes(state.phase)) return release(options)
    assertOwned(p, state); await assertStopped(p)
    const phase = state.phase === 'failed' ? state.failedAt : state.phase
    if (!['locking', 'backing-up', 'prepared', 'committing', 'applied'].includes(phase)) throw Error('该批次不需要中断恢复')
    const db = new Sqlite(p.database, { fileMustExist: true, timeout: 1000 })
    try {
        db.pragma('locking_mode=EXCLUSIVE'); db.exec('BEGIN EXCLUSIVE; COMMIT')
        const current = api().getDeploymentDatabaseFingerprintSync(db)
        if (['locking', 'backing-up'].includes(phase) && !state.beforeFingerprint) {
            // No mutation API can have been reached in these recorded phases.
            state.beforeFingerprint = current; state.phase = 'rolled-back'
        } else if (current === state.beforeFingerprint) state.phase = 'rolled-back'
        else if (state.afterFingerprint && current === state.afterFingerprint && inspectDatabase(db, api()).ready) {
            if (!state.backupSha256 || await hashFile(state.backup) !== state.backupSha256
                || JSON.stringify(validateInputs(p)) !== JSON.stringify(state.inputs)) throw Error('恢复所需备份或程序输入已变化')
            const backup = new Sqlite(state.backup, { readonly: true, fileMustExist: true })
            try { if (api().getDeploymentDatabaseFingerprintSync(backup) !== state.beforeFingerprint) throw Error('恢复备份与迁移前状态不符') }
            finally { backup.close() }
            state.phase = 'applied'
        }
        else throw Error('中断后的数据库不匹配迁移前后状态；保留维护锁，不覆盖数据')
        state.recoveredAt = new Date().toISOString(); saveJson(p.state, state); return state
    } finally { db.close() }
}
async function rollback(options) {
    const p = paths(options.project), state = readJson(p.state); assertOwned(p, state); await assertStopped(p)
    if (!['applied', 'failed'].includes(state.phase) || !state.backupSha256) throw Error('无可用的本批回退记录')
    if (await hashFile(state.backup) !== state.backupSha256) throw Error('备份完整性验证失败')
    const a = api(), db = new Sqlite(p.database, { fileMustExist: true, timeout: 1000 })
    let unchanged
    try {
        db.pragma('locking_mode=EXCLUSIVE'); db.exec('BEGIN EXCLUSIVE; COMMIT')
        const current = a.getDeploymentDatabaseFingerprintSync(db)
        unchanged = current === state.beforeFingerprint
        if (!unchanged && current !== state.afterFingerprint) throw Error('迁移后已有新的数据，拒绝用旧备份覆盖玩家进度')
        const backup = new Sqlite(state.backup, { readonly: true, fileMustExist: true })
        try { if (a.getDeploymentDatabaseFingerprintSync(backup) !== state.beforeFingerprint) throw Error('备份内容与迁移前记录不符') }
        finally { backup.close() }
        db.pragma('wal_checkpoint(TRUNCATE)')
    } finally { db.close() }
    if (!unchanged) {
        const temporary = p.database + '.restore-' + state.runId
        fs.copyFileSync(state.backup, temporary, fs.constants.COPYFILE_EXCL)
        // All application starts remain fenced by both owned maintenance locks.
        for (const suffix of ['-wal', '-shm']) {
            const sidecar = p.database + suffix
            if (fs.existsSync(sidecar)) {
                if (suffix === '-wal' && fs.statSync(sidecar).size !== 0) throw Error('WAL未排空，拒绝恢复')
                fs.unlinkSync(sidecar)
            }
        }
        fs.renameSync(temporary, p.database)
    }
    const restored = new Sqlite(p.database, { readonly: true, fileMustExist: true })
    try { if (a.getDeploymentDatabaseFingerprintSync(restored) !== state.beforeFingerprint) throw Error('回退读回失败，继续保持维护锁') }
    finally { restored.close() }
    state.phase = 'rolled-back'; saveJson(p.state, state); return state
}
async function main(args) {
    const command = args.shift(), options = { project: path.resolve(__dirname, '..') }
    while (args.length) { const key = args.shift(); if (key !== '--project' || !args[0]) throw Error('仅支持 --project <服务目录>'); options.project = path.resolve(args.shift()) }
    let result
    if (command === 'preview' || command === 'verify') { result = inspect(options); if (command === 'verify' && !result.ready) throw Error('时间或内容设置尚未迁移；请执行迁移工具，不要直接开服') }
    else if (command === 'apply') result = await apply(options)
    else if (command === 'release') result = await release(options)
    else if (command === 'rollback') result = await rollback(options)
    else if (command === 'recover') result = await recover(options)
    else throw Error('用法：node --env-file=.env scripts/time-content-deployment.cjs preview|apply|verify|release|rollback|recover')
    console.log(JSON.stringify(result, null, 2))
}
module.exports = { paths, inspect, apply, release, rollback, recover, validateInputs, assertStopped, main }
if (require.main === module) main(process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1 })
