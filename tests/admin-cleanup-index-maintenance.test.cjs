'use strict'
require('ts-node/register/transpile-only')
const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { spawnSync } = require('node:child_process')
const Database = require('better-sqlite3')
const api = require('../src/cleanup-index-maintenance')
const { findMissingCascadeDeleteIndexes } = require('../src/lib/admin-account-cleanup')
const root = path.resolve(__dirname, '..')
const preload = require.resolve('ts-node/register/transpile-only')
const cli = path.join(root, 'src/cleanup-index-maintenance.ts')
const expectedIndexes = [
    'idx_cleanup_fk_players_exchange_campaign_receipts_0',
    'idx_cleanup_fk_players_special_exchange_campaigns_0',
]

function fixture() {
    const project = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'sp-cleanup-indexes-')))
    const data = path.join(project, '.database')
    fs.mkdirSync(data)
    const paths = { project, database: path.join(data, 'wdfp_data.db'),
        lock: path.join(data, 'storage-maintenance.lock'), state: path.join(data, 'storage-maintenance-state.json'),
        backups: path.join(data, 'maintenance-backups') }
    const db = new Database(paths.database)
    try {
        db.pragma('foreign_keys=ON')
        db.exec(`
            CREATE TABLE accounts(id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE players(id INTEGER PRIMARY KEY,account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE);
            CREATE INDEX idx_players_account ON players(account_id);
            CREATE TABLE players_exchange_campaign_receipts (
                campaign_type TEXT NOT NULL CHECK(campaign_type IN ('special','start_dash')),
                campaign_id INTEGER NOT NULL, reward_type INTEGER NOT NULL CHECK(reward_type IN (0,1)),
                reward_id INTEGER NOT NULL, player_id INTEGER NOT NULL,
                PRIMARY KEY (campaign_type,campaign_id,player_id),
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE);
            CREATE TABLE players_special_exchange_campaigns (
                campaign_id INTEGER NOT NULL,status INTEGER NOT NULL CHECK(status IN (1,2,3)),player_id INTEGER NOT NULL,
                PRIMARY KEY (campaign_id,player_id), FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE);
            CREATE TABLE players_receive_history(id INTEGER PRIMARY KEY,player_id INTEGER,content TEXT);
            INSERT INTO accounts VALUES(1,'kept'),(2,'another');
            INSERT INTO players VALUES(10,1),(20,2);
            INSERT INTO players_exchange_campaign_receipts VALUES('special',101,0,201,10),('start_dash',102,1,202,20);
            INSERT INTO players_special_exchange_campaigns VALUES(101,2,10),(102,3,20);
            INSERT INTO players_receive_history VALUES(1,10,'2020 history stays'),(2,20,'all progress stays');
        `)
    } finally { db.close() }
    fs.writeFileSync(paths.database + '.version', '9')
    return paths
}

function cleanup(paths) {
    const target = fs.realpathSync(paths.project)
    const temporary = fs.realpathSync(os.tmpdir())
    assert.equal(path.dirname(target), temporary)
    assert.match(path.basename(target), /^sp-cleanup-indexes-/)
    fs.rmSync(target, { recursive: true, force: true })
}

function inspect(paths) {
    const db = new Database(paths.database, { readonly: true, fileMustExist: true })
    try {
        const schema = db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").all()
        const tables = schema.filter(value => value.type === 'table')
        const rows = Object.fromEntries(tables.map(value => [value.name,
            db.prepare(`SELECT * FROM "${value.name.replace(/"/g, '""')}" ORDER BY rowid`).all()]))
        return { schema, rows, missing: findMissingCascadeDeleteIndexes(db) }
    } finally { db.close() }
}

function options(paths) {
    return { offline: true, confirm: api.CLEANUP_INDEX_CONFIRMATION, confirmDatabase: paths.database }
}

function readState(paths) {
    return JSON.parse(fs.readFileSync(path.join(path.dirname(paths.database), 'cleanup-index-maintenance-state.json'), 'utf8'))
}

function runCli(paths, args) {
    return spawnSync(process.execPath, ['-r', preload, cli, ...args, '--project', paths.project], {
        cwd: root, env: { ...process.env, DATA_DIR: path.dirname(paths.database) }, encoding: 'utf8', timeout: 20000,
    })
}

test('default preview only reads metadata and lists the two production-shaped missing indexes', () => {
    const p = fixture()
    try {
        const bytes = fs.readFileSync(p.database)
        const before = inspect(p)
        const files = fs.readdirSync(path.dirname(p.database)).sort()
        const preview = api.previewCleanupIndexes(p)
        assert.deepEqual(preview.missing.map(value => value.indexName), expectedIndexes)
        assert.equal(preview.locked, false)
        assert.deepEqual(inspect(p), before)
        assert.deepEqual(fs.readFileSync(p.database), bytes)
        assert.deepEqual(fs.readdirSync(path.dirname(p.database)).sort(), files)
        const result = runCli(p, [])
        assert.equal(result.status, 0, result.stderr)
        assert.deepEqual(JSON.parse(result.stdout).missing.map(value => value.indexName), expectedIndexes)
        assert.deepEqual(fs.readFileSync(p.database), bytes)
    } finally { cleanup(p) }
})

test('apply adds only two nonunique indexes, preserves all rows, and repeats without changes', async () => {
    const p = fixture()
    try {
        const before = inspect(p)
        fs.mkdirSync(path.join(p.project, '.storage-maintenance'))
        fs.writeFileSync(path.join(p.project, '.storage-maintenance', 'unrelated'), 'keep')
        const result = await api.applyCleanupIndexes(p, options(p), stage => {
            if (stage === 'indexes-created') {
                assert.ok(fs.existsSync(p.lock), 'startup remains blocked during maintenance')
            }
        })
        assert.equal(result.phase, 'completed')
        assert.equal(result.createdIndexes, 2)
        assert.equal(result.ddlCommitted, true)
        const after = inspect(p)
        assert.deepEqual(after.rows, before.rows)
        assert.deepEqual(after.missing, [])
        assert.deepEqual(after.schema.filter(value => !expectedIndexes.includes(value.name)), before.schema)
        const db = new Database(p.database, { readonly: true })
        try {
            for (const table of ['players_exchange_campaign_receipts', 'players_special_exchange_campaigns']) {
                const installed = db.pragma(`index_list(${table})`).filter(value => expectedIndexes.includes(value.name))
                assert.equal(installed.length, 1)
                assert.equal(installed[0].unique, 0)
                assert.equal(installed[0].partial, 0)
            }
            assert.deepEqual(db.pragma('foreign_key_check'), [])
        } finally { db.close() }
        assert.equal(fs.existsSync(p.lock), false)
        assert.equal(fs.readFileSync(path.join(p.project, '.storage-maintenance', 'unrelated'), 'utf8'), 'keep')
        const again = await api.applyCleanupIndexes(p, options(p))
        assert.equal(again.createdIndexes, 0)
        assert.deepEqual(inspect(p), after)
        assert.equal(fs.existsSync(p.backups), false)
    } finally { cleanup(p) }
})

test('apply requires explicit offline, confirmation, matching target, and correct version before writing', async () => {
    const p = fixture()
    try {
        const before = inspect(p)
        for (const option of [{ ...options(p), offline: false }, { ...options(p), confirm: 'wrong' },
            { ...options(p), confirmDatabase: p.database + '.version' }]) {
            await assert.rejects(api.applyCleanupIndexes(p, option))
            assert.equal(fs.existsSync(p.lock), false)
            assert.deepEqual(inspect(p), before)
        }
        fs.writeFileSync(p.database + '.version', '999')
        await assert.rejects(api.applyCleanupIndexes(p, options(p)), /基础数据库版本/)
        assert.equal(fs.existsSync(p.lock), false)
        assert.deepEqual(inspect(p), before)
    } finally { cleanup(p) }
})

test('an existing lock is never overwritten or released', async () => {
    const p = fixture()
    try {
        const lock = JSON.stringify({ pid: 1234, database: p.database, marker: 'not ours' })
        fs.writeFileSync(p.lock, lock)
        const before = inspect(p)
        await assert.rejects(api.applyCleanupIndexes(p, options(p)), /EEXIST/)
        assert.equal(fs.readFileSync(p.lock, 'utf8'), lock)
        assert.deepEqual(inspect(p), before)
    } finally { cleanup(p) }
})

test('unfinished or foreign maintenance records block apply without overwriting them', async () => {
    const p = fixture()
    try {
        const before = inspect(p)
        for (const state of [{ format: 1, database: p.database, phase: 'failed' },
            { format: 1, database: p.database, phase: 'ready' },
            { format: 1, database: p.database + '.other', phase: 'completed' }]) {
            const bytes = JSON.stringify(state)
            fs.writeFileSync(p.state, bytes)
            await assert.rejects(api.applyCleanupIndexes(p, options(p)), /维护记录/)
            assert.equal(fs.readFileSync(p.state, 'utf8'), bytes)
            assert.equal(fs.existsSync(p.lock), false)
            assert.deepEqual(inspect(p), before)
        }
        fs.writeFileSync(p.state, JSON.stringify({ format: 1, database: p.database, phase: 'completed' }))
        assert.equal((await api.applyCleanupIndexes(p, options(p))).createdIndexes, 2)
    } finally { cleanup(p) }
})

test('index repair never calls database backup or whole-database integrity scans', async () => {
    const p = fixture()
    const backup = Database.prototype.backup
    const pragma = Database.prototype.pragma
    try {
        const before = inspect(p)
        Database.prototype.backup = function () { throw new Error('database backup must not run') }
        Database.prototype.pragma = function (source, ...args) {
            if (/\b(?:quick_check|integrity_check)\b/i.test(source)) throw new Error('database integrity scan must not run')
            return pragma.call(this, source, ...args)
        }
        const result = await api.applyCleanupIndexes(p, options(p))
        assert.equal(result.createdIndexes, 2)
        assert.deepEqual(inspect(p).rows, before.rows)
        assert.deepEqual(inspect(p).missing, [])
        assert.equal(fs.existsSync(p.backups), false)
        assert.equal(fs.existsSync(p.lock), false)
    } finally { Database.prototype.backup = backup; Database.prototype.pragma = pragma; cleanup(p) }
})

test('CLI apply rejects missing offline confirmation and accepts the fully confirmed synthetic target', () => {
    const p = fixture()
    try {
        const before = inspect(p)
        const denied = runCli(p, ['apply'])
        assert.equal(denied.status, 1)
        assert.match(denied.stderr, /offline/)
        assert.deepEqual(inspect(p), before)
        const applied = runCli(p, ['apply', '--offline', '--confirm', api.CLEANUP_INDEX_CONFIRMATION,
            '--confirm-database', p.database])
        assert.equal(applied.status, 0, applied.stderr)
        assert.equal(JSON.parse(applied.stdout).createdIndexes, 2)
        assert.deepEqual(inspect(p).rows, before.rows)
        assert.deepEqual(inspect(p).missing, [])
    } finally { cleanup(p) }
})

test('an active or unfinished Windows maintenance controller is protected without any file changes', async () => {
    const p = fixture()
    try {
        const before = inspect(p)
        const directory = path.join(p.project, '.storage-maintenance')
        fs.mkdirSync(directory)
        const active = path.join(directory, 'active.lock')
        fs.writeFileSync(active, 'another controller')
        await assert.rejects(api.applyCleanupIndexes(p, options(p)), /Windows 存储维护控制器/)
        assert.equal(fs.readFileSync(active, 'utf8'), 'another controller')
        fs.unlinkSync(active)
        const controller = path.join(directory, 'controller.json')
        const bytes = JSON.stringify({ project: p.project, database: p.database, phase: 'service-starting' })
        fs.writeFileSync(controller, bytes)
        await assert.rejects(api.applyCleanupIndexes(p, options(p)), /Windows 存储维护控制器记录/)
        assert.equal(fs.readFileSync(controller, 'utf8'), bytes)
        assert.equal(fs.existsSync(p.lock), false)
        assert.deepEqual(inspect(p), before)
    } finally { cleanup(p) }
})

test('a conflicting second index name rolls back the first index and preserves all rows', async () => {
    const p = fixture()
    try {
        const db = new Database(p.database)
        try { db.exec(`CREATE INDEX ${expectedIndexes[1]} ON players_special_exchange_campaigns(campaign_id)`) }
        finally { db.close() }
        const before = inspect(p)
        await assert.rejects(api.applyCleanupIndexes(p, options(p)), /索引|index/i)
        assert.deepEqual(inspect(p), before)
        assert.equal(readState(p).createdIndexes, 0)
        assert.equal(readState(p).ddlCommitted, false)
        assert.equal(fs.existsSync(p.lock), false)
    } finally { cleanup(p) }
})

test('an error inside the DDL transaction rolls back every new index', async () => {
    const p = fixture()
    try {
        const before = inspect(p)
        await assert.rejects(api.applyCleanupIndexes(p, options(p), stage => {
            if (stage === 'indexes-created') throw new Error('synthetic failure before commit')
        }), /before commit/)
        assert.deepEqual(inspect(p), before)
        assert.equal(fs.existsSync(p.lock), false)
        assert.equal(readState(p).phase, 'failed')
    } finally { cleanup(p) }
})

test('an existing WAL reader prevents exclusive index maintenance', async () => {
    const p = fixture()
    let reader
    try {
        reader = new Database(p.database)
        reader.pragma('journal_mode=WAL')
        reader.exec('BEGIN; SELECT * FROM accounts')
        const before = inspect(p)
        await assert.rejects(api.applyCleanupIndexes(p, options(p)), /locked|busy/i)
        assert.deepEqual(inspect(p), before)
        assert.equal(fs.existsSync(p.lock), false)
    } finally { if (reader?.open) reader.close(); cleanup(p) }
})

test('post-commit failure retains its lock and records committed indexes for review', async () => {
    const p = fixture()
    try {
        const rows = inspect(p).rows
        await assert.rejects(api.applyCleanupIndexes(p, options(p), stage => {
            if (stage === 'indexes-committed') throw new Error('synthetic post-commit reporting failure')
        }), /post-commit/)
        assert.equal(readState(p).phase, 'failed')
        assert.equal(readState(p).ddlCommitted, true)
        assert.equal(fs.existsSync(p.lock), true)
        assert.deepEqual(inspect(p).missing, [])
        assert.deepEqual(inspect(p).rows, rows)
        await assert.rejects(api.applyCleanupIndexes(p, options(p)), /上次索引维护/)
    } finally { cleanup(p) }
})

test('the legacy unlock entry refuses a dead-process cleanup-index lock without changing its audit state', () => {
    const p = fixture()
    try {
        const child = spawnSync(process.execPath, ['-e', ''], { encoding: 'utf8', timeout: 10000 })
        assert.equal(child.status, 0, child.stderr)
        assert.throws(() => process.kill(child.pid, 0), error => error.code === 'ESRCH')
        const lock = JSON.stringify({ kind: 'cleanup-indexes', id: 'failed-index-task',
            pid: child.pid, database: p.database })
        const stateFile = path.join(path.dirname(p.database), 'cleanup-index-maintenance-state.json')
        const state = JSON.stringify({ format: 1, kind: 'cleanup-indexes', id: 'failed-index-task',
            database: p.database, phase: 'failed', ddlCommitted: true, error: 'post-commit reporting failure' })
        fs.writeFileSync(p.lock, lock)
        fs.writeFileSync(stateFile, state)
        const { unlockUnstartedMaintenance } = require('../src/storage-maintenance')
        assert.throws(() => unlockUnstartedMaintenance(p), /索引|cleanup-indexes/)
        assert.equal(fs.readFileSync(p.lock, 'utf8'), lock)
        assert.equal(fs.readFileSync(stateFile, 'utf8'), state)
    } finally { cleanup(p) }
})

test('the legacy unlock entry still releases an ordinary legacy lock after its process exits', () => {
    const p = fixture()
    try {
        const child = spawnSync(process.execPath, ['-e', ''], { encoding: 'utf8', timeout: 10000 })
        assert.equal(child.status, 0, child.stderr)
        assert.throws(() => process.kill(child.pid, 0), error => error.code === 'ESRCH')
        fs.writeFileSync(p.lock, JSON.stringify({ pid: child.pid, database: p.database }))
        const { unlockUnstartedMaintenance } = require('../src/storage-maintenance')
        unlockUnstartedMaintenance(p)
        assert.equal(fs.existsSync(p.lock), false)
    } finally { cleanup(p) }
})

test('another owner replacing the lock is never silently unlocked', async () => {
    const p = fixture()
    try {
        const replacement = JSON.stringify({ kind: 'another-owner', id: 'other', database: p.database, pid: process.pid })
        await assert.rejects(api.applyCleanupIndexes(p, options(p), stage => {
            if (stage === 'indexes-committed') fs.writeFileSync(p.lock, replacement)
        }), /维护锁身份已变化/)
        assert.equal(fs.readFileSync(p.lock, 'utf8'), replacement)
    } finally { cleanup(p) }
})

test('process exit during DDL leaves an audit record and lock, while SQLite rolls the DDL back', () => {
    const p = fixture()
    try {
        const before = inspect(p)
        const code = `const api=require(${JSON.stringify(cli)});const p=${JSON.stringify(p)};
            api.applyCleanupIndexes(p,{offline:true,confirm:api.CLEANUP_INDEX_CONFIRMATION,confirmDatabase:p.database},
            stage=>{if(stage==='indexes-created')process.exit(88)}).catch(e=>{console.error(e);process.exitCode=1})`
        const result = spawnSync(process.execPath, ['-r', preload, '-e', code], { cwd: root,
            env: { ...process.env, DATA_DIR: path.dirname(p.database) }, encoding: 'utf8', timeout: 20000 })
        assert.equal(result.status, 88, result.stderr)
        assert.equal(readState(p).phase, 'indexing')
        assert.equal(fs.existsSync(p.lock), true)
        assert.deepEqual(inspect(p), before)
        assert.equal(fs.existsSync(p.backups), false)
    } finally { cleanup(p) }
})
