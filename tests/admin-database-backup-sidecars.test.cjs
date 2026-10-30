'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const crypto = require('node:crypto')
const { test } = require('node:test')
const Database = require('better-sqlite3')

const out = process.env.STARPOINT_TEST_OUT_DIR
if (!out) throw new Error('Use the current isolated build via STARPOINT_TEST_OUT_DIR')
const { createFullDatabaseBackup } = require(path.join(out, 'lib/admin-database-backup'))
const { drainDatabaseBackups } = require(path.join(out, 'lib/admin-database-backup-worker'))
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex')

async function fixture(t, stateOverride = {}) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-backup-sidecars-'))
    const previousDataDir = process.env.DATA_DIR
    process.env.DATA_DIR = directory
    const databasePath = path.join(directory, 'wdfp_data.db')
    const versionPath = path.join(directory, 'wdfp_data.db.version')
    const statePath = path.join(directory, 'active_account.json')
    const db = new Database(databasePath)
    db.pragma('journal_mode = WAL')
    db.exec(`CREATE TABLE accounts(id INTEGER PRIMARY KEY);
        CREATE TABLE players(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id));
        CREATE TABLE payload(id INTEGER PRIMARY KEY, value BLOB NOT NULL);
        INSERT INTO accounts VALUES(1),(2);
        INSERT INTO players VALUES(11,1),(22,2);`)
    const insert = db.prepare('INSERT INTO payload VALUES(?,?)')
    db.transaction(() => { for (let id = 0; id < 512; id++) insert.run(id, Buffer.alloc(3800, id % 251)) })()
    const state = {
        activePlayerId: 11, selectedAccountId: 1, defaultPlayers: { 1: 11, 2: 22 },
        timeOffset: null, lastSetTime: null, ...stateOverride,
    }
    const stateBytes = Buffer.from(JSON.stringify(state, null, 4) + '\r\n')
    const versionBytes = Buffer.from('175\n')
    fs.writeFileSync(statePath, stateBytes)
    fs.writeFileSync(versionPath, versionBytes)
    t.after(async () => {
        await drainDatabaseBackups()
        db.close()
        if (previousDataDir === undefined) delete process.env.DATA_DIR
        else process.env.DATA_DIR = previousDataDir
        // run-isolated-check.cjs owns removal of its disposable test root.
    })
    return { directory, databasePath, versionPath, statePath, state, stateBytes, versionBytes, db }
}

async function rejectedBackup(fixture, options) {
    let failure
    await assert.rejects(createFullDatabaseBackup('manual-full', {}, options), error => {
        failure = error
        return error.code === 'failed' && typeof error.backupDirectory === 'string'
    })
    const backupRoot = path.join(fixture.directory, 'admin-backups')
    assert.equal(path.dirname(failure.backupDirectory), backupRoot)
    const info = JSON.parse(fs.readFileSync(path.join(failure.backupDirectory, 'backup-info.json'), 'utf8'))
    assert.equal(info.status, 'failed')
    assert.equal(info.errorCode, 'failed')
    assert.ok(info.error)
    assert.equal(info.verification, undefined, 'failure metadata cannot claim verified completion')
    assert.deepEqual(fixture.db.prepare('SELECT id,account_id FROM players ORDER BY id').all(), [
        { id: 11, account_id: 1 }, { id: 22, account_id: 2 },
    ])
    return { failure, info }
}

test('full wrapper keeps captured sidecar bytes and records verified snapshot provenance', { timeout: 15000 }, async t => {
    const f = await fixture(t)
    let changed = false
    const result = await createFullDatabaseBackup('manual-full', { purpose: 'synthetic-sidecar-regression' }, {
        onProgress(progress) {
            if (progress.phase === 'copying' && !changed) {
                fs.writeFileSync(f.statePath, JSON.stringify({ ...f.state, activePlayerId: 22, selectedAccountId: 2 }))
                changed = true
            }
        },
    })
    assert.equal(changed, true)
    assert.deepEqual(fs.readFileSync(path.join(result.directory, 'active_account.json')), f.stateBytes)
    assert.deepEqual(fs.readFileSync(path.join(result.directory, 'wdfp_data.db.version')), f.versionBytes)
    assert.notDeepEqual(fs.readFileSync(f.statePath), f.stateBytes, 'source sidecar changed before wrapper completion')
    const info = JSON.parse(fs.readFileSync(path.join(result.directory, 'backup-info.json'), 'utf8'))
    assert.equal(info.status, 'completed')
    assert.equal(info.verification.quickCheck, 'ok')
    assert.equal(info.verification.snapshot, true)
    assert.equal(info.verification.sidecarValidated, true)
    assert.equal(info.sidecars.versionSha256, sha256(f.versionBytes))
    assert.equal(info.sidecars.activeAccountSha256, sha256(f.stateBytes))
    assert.ok(Date.parse(info.sidecars.capturedAt) <= Date.parse(info.verification.snapshotPinnedAt))
    const target = new Database(path.join(result.directory, 'wdfp_data.db'), { readonly: true, fileMustExist: true })
    try {
        assert.equal(target.pragma('quick_check', { simple: true }), 'ok')
        assert.equal(target.prepare('SELECT account_id FROM players WHERE id=11').pluck().get(), 1)
        assert.equal(target.prepare('SELECT COUNT(*) FROM payload').pluck().get(), 512)
    } finally { target.close() }
})

for (const [name, override] of [
    ['missing active player', { activePlayerId: 999 }],
    ['missing selected account', { selectedAccountId: 999 }],
    ['wrong default-player ownership', { defaultPlayers: { 1: 22 } }],
    ['unsafe time offset', { timeOffset: 1.5 }],
    ['invalid last-set date', { lastSetTime: 'not-a-date' }],
]) {
    test(`full wrapper rejects ${name} without changing source state`, { timeout: 15000 }, async t => {
        const f = await fixture(t, override)
        await rejectedBackup(f)
        assert.deepEqual(fs.readFileSync(f.statePath), f.stateBytes)
        assert.deepEqual(fs.readFileSync(f.versionPath), f.versionBytes)
    })
}

test('version changed immediately after byte capture is rejected by the real worker', { timeout: 15000 }, async t => {
    const f = await fixture(t)
    const readFile = fs.readFileSync
    let changed = false
    // Deterministic boundary seam: the wrapper receives the original bytes,
    // then the on-disk version changes before its real worker can pin a read.
    fs.readFileSync = function (filename, ...args) {
        const bytes = readFile.call(this, filename, ...args)
        if (filename === f.versionPath && !changed) {
            changed = true
            fs.writeFileSync(f.versionPath, '176\n')
        }
        return bytes
    }
    try {
        const { info } = await rejectedBackup(f)
        assert.equal(changed, true)
        assert.equal(info.sidecars.versionSha256, sha256(f.versionBytes))
        assert.match(info.error, /版本文件/)
    } finally { fs.readFileSync = readFile }
})
