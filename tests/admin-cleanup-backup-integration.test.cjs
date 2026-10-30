'use strict'
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { spawn } = require('node:child_process'), { test } = require('node:test')
const out = process.env.STARPOINT_TEST_OUT_DIR
if (!out) throw Error('Use STARPOINT_TEST_OUT_DIR for the current build')
const load = name => require(path.join(out, name))
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

async function scenario(name) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-cleanup-backup-'))
    process.env.DATA_DIR = directory
    process.env.MULTI_REALTIME_PROCESS = '0'
    let app, db
    try {
        db = load('data/db').getDb()
        const accounts = load('data/domains/account'), players = load('data/domains/player')
        const account = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'fixture', idpId: name, status: 'normal' })
        players.insertDefaultPlayerSync(account.id)
        const backupRoot = path.join(directory, 'admin-backups')
        const old = path.join(backupRoot, 'unnoted-accounts-20200101-000000-000')
        fs.mkdirSync(old, { recursive: true })
        fs.writeFileSync(path.join(old, 'evidence.txt'), 'must survive failure or cancellation')
        const backups = load('lib/admin-database-backup'), original = backups.createFullDatabaseBackup
        let pendingCancel, closing
        if (name === 'cancel' || name === 'close') {
            backups.createFullDatabaseBackup = (prefix, metadata, options = {}) => original(prefix, metadata, {
                ...options,
                onProgress(progress) {
                    options.onProgress?.(progress)
                    if (pendingCancel || closing) return
                    if (name === 'cancel') pendingCancel = app.inject({ method: 'POST', url: '/server/deleteUnnotedAccounts/cancel', payload: { jobId: currentJobId } })
                    else closing = app.close()
                },
            })
        }
        if (name === 'failure') backups.createFullDatabaseBackup = () => Promise.reject(new Error('synthetic backup failure'))
        if (name === 'missing-index') {
            const indices = db.prepare('PRAGMA index_list(players)').all()
            const index = indices.find(row => db.prepare(`PRAGMA index_info("${row.name}")`).all()[0]?.name === 'account_id')
            assert.ok(index)
            db.exec(`DROP INDEX "${index.name}"`)
        }
        app = require('fastify')({ logger: false })
        await app.register(load('routes/web_api/server').default, { prefix: '/server' })
        await app.ready()
        if (name === 'retention') {
            for (let index = 0; index < 5; index++) {
                const valid = path.join(backupRoot, `manual-full-20200101-00000${index}-000`)
                fs.mkdirSync(valid)
                fs.writeFileSync(path.join(valid, 'backup-info.json'), JSON.stringify(index ? { status: 'completed' } : {}))
                fs.writeFileSync(path.join(valid, 'wdfp_data.db'), 'synthetic historical backup')
                fs.writeFileSync(path.join(valid, 'wdfp_data.db.version'), '9')
                const failed = path.join(backupRoot, `manual-full-20250101-00000${index}-000`)
                fs.mkdirSync(failed)
                fs.writeFileSync(path.join(failed, 'backup-info.json'), JSON.stringify({ status: 'failed' }))
                fs.writeFileSync(path.join(failed, 'wdfp_data.db'), 'synthetic incomplete target')
                fs.writeFileSync(path.join(failed, 'wdfp_data.db.version'), '9')
            }
            const response = await app.inject({ method: 'POST', url: '/server/databaseBackup' })
            assert.equal(response.statusCode, 200, response.body)
            assert.equal(response.json().removedBackups, 1, 'only oldest of six successful backups expires')
            assert.equal(fs.existsSync(path.join(backupRoot, 'manual-full-20200101-000000-000')), false)
            for (let index = 1; index < 5; index++) assert.ok(fs.existsSync(path.join(backupRoot, `manual-full-20200101-00000${index}-000`)))
            for (let index = 0; index < 5; index++) assert.ok(fs.existsSync(path.join(backupRoot, `manual-full-20250101-00000${index}-000`)))
            return
        }
        const wrong = await app.inject({ method: 'POST', url: '/server/deleteUnnotedAccounts/cancel', payload: { jobId: 'stale-job' } })
        assert.equal(wrong.statusCode, 409)
        const started = await app.inject({ method: 'POST', url: '/server/deleteUnnotedAccounts', payload: { confirm: 'DELETE_UNNOTED_ACCOUNTS' } })
        assert.equal(started.statusCode, 202, started.body)
        currentJobId = started.json().jobId
        let job
        const end = Date.now() + 15000
        if (name === 'close') {
            while (!closing && Date.now() < end) await sleep(5)
            assert.ok(closing)
            await closing
            const failedDirectories = fs.readdirSync(backupRoot).filter(entry => entry !== path.basename(old))
            assert.equal(failedDirectories.length, 1)
            const info = JSON.parse(fs.readFileSync(path.join(backupRoot, failedDirectories[0], 'backup-info.json')))
            assert.equal(info.status, 'failed')
        } else {
            do {
                job = (await app.inject({ url: '/server/deleteUnnotedAccounts/status' })).json()
                if (job.status !== 'running') break
                await sleep(5)
            } while (Date.now() < end)
            assert.equal(job.status, 'failed', JSON.stringify(job))
            assert.equal(job.deletedAccounts, 0)
            assert.equal(job.deletedSaves, 0)
            assert.match(job.error, /未执行删除|未删除任何账号/)
            if (name === 'cancel') assert.equal((await pendingCancel).statusCode, 202)
            if (name === 'missing-index') assert.match(job.error, /删除索引/)
        }
        assert.ok(db.prepare('SELECT id FROM accounts WHERE id=?').get(account.id))
        assert.equal(db.prepare('SELECT COUNT(*) n FROM players WHERE account_id=?').get(account.id).n, 1)
        assert.equal(fs.readFileSync(path.join(old, 'evidence.txt'), 'utf8'), 'must survive failure or cancellation')
        assert.equal(db.pragma('quick_check', { simple: true }), 'ok')
        assert.deepEqual(db.pragma('foreign_key_check'), [])
    } finally {
        if (app) await app.close()
        if (db) { await load('multi/npc/player-party-pool').stopQuestNpcPartyPoolWorker(); db.close() }
        assert.equal(path.dirname(directory), path.resolve(os.tmpdir()))
        assert.ok(path.basename(directory).startsWith('sp-cleanup-backup-'))
        fs.rmSync(directory, { recursive: true, force: true })
    }
}
let currentJobId
if (process.argv[2] === '--scenario') scenario(process.argv[3]).catch(error => { console.error(error); process.exitCode = 1 })
else for (const name of ['cancel', 'close', 'failure', 'missing-index', 'retention']) {
    test(`cleanup backup protection: ${name}`, { timeout: 25000 }, async () => {
        const child = spawn(process.execPath, [__filename, '--scenario', name], { env: process.env, stdio: ['ignore', 'pipe', 'pipe'] })
        let output = ''
        child.stdout.on('data', value => { output += value }); child.stderr.on('data', value => { output += value })
        assert.equal(await new Promise(resolve => child.once('exit', resolve)), 0, output)
    })
}
