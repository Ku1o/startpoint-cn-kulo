const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const assert = require('node:assert/strict')
const { createHash } = require('node:crypto')
const { spawnSync } = require('node:child_process')

const portable = path.resolve(process.argv[2] || '')
assert.ok(process.argv[2] && fs.existsSync(path.join(portable, 'manifest.json')), 'Provide the extracted portable directory')
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-portable-check-'))
process.env.DATA_DIR = fixture
const db = require('../out/data/db').getDb()
const api = require('../out/data/snapshots/player-snapshot')
const hash = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex')
const manifest = JSON.parse(fs.readFileSync(path.join(portable, 'manifest.json'), 'utf8'))
function verifyPackage() {
    for (const file of manifest.files) {
        assert.equal(hash(path.join(portable, file.path)), file.sha256, file.path)
    }
}
function request(options) {
    const child = spawnSync(path.join(portable, 'node.exe'), [path.join(portable, 'tools/extract_player_save_gui_worker.cjs')], {
        cwd: fixture, input: JSON.stringify(options), encoding: 'utf8', timeout: 30000, windowsHide: true,
        env: { ...process.env, PATH: '', NODE_PATH: '', NODE_OPTIONS: '', DATA_DIR: path.join(fixture, 'must-not-create') },
    })
    assert.equal(child.error, undefined)
    return { status: child.status, ...JSON.parse(child.stdout) }
}
try {
    const account = require('../out/data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'portable', idpId: 'portable-fixture', status: 'normal' })
    const player = require('../out/data/domains/player').insertDefaultPlayerSync(account.id)
    db.prepare('UPDATE players SET name=? WHERE id=?').run('便携包测试玩家', player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES (?,?,?,2)').run('123456789', account.id, '2099-01-01')
    db.prepare('INSERT INTO players_items(id,amount,player_id) VALUES (901,456,?)').run(player.id)
    const expected = api.createPlayerSaveSnapshotV2Sync(player.id, db)
    verifyPackage()
    const database = path.join(fixture, 'wdfp_data.db')
    for (const mode of ['ordinary', 'compact']) {
        if (mode === 'compact') require('../out/lib/storage-layout').migrateStorageLayout(db)
        db.pragma('wal_checkpoint(TRUNCATE)')
        const dbHash = hash(database)
        const before = fs.readdirSync(fixture).sort()
        const listed = request({ database, viewerId: 123456789, list: true })
        assert.equal(listed.ok, true, listed.error)
        assert.equal(listed.result.candidates[0].name, '便携包测试玩家')
        assert.deepEqual(fs.readdirSync(fixture).sort(), before)
        const output = path.join(fixture, `便携包 & 中文 ${mode}.json`)
        const exported = request({ database, viewerId: 123456789, playerId: player.id, output })
        assert.equal(exported.ok, true, exported.error)
        const actual = JSON.parse(fs.readFileSync(output, 'utf8'))
        assert.deepEqual(actual.data.tables, expected.data.tables)
        assert.equal(actual.schemaFingerprint, expected.schemaFingerprint)
        assert.deepEqual(fs.readdirSync(fixture).sort(), [...before, path.basename(output)].sort())
        assert.equal(hash(database), dbHash)
        const duplicate = request({ database, viewerId: 123456789, output })
        assert.equal(duplicate.ok, false)
        assert.match(duplicate.error, /拒绝覆盖/)
    }
    const missing = request({ database, viewerId: 87654321, list: true })
    assert.equal(missing.ok, false)
    assert.equal(fs.existsSync(path.join(fixture, 'must-not-create')), false)
    verifyPackage()
    console.log('PASS: extracted Windows package, bundled Node/native SQLite, empty PATH/NODE_PATH, ordinary + compact DB, Chinese paths, only requested JSON output, unchanged DB/package hashes, errors rejected')
} finally {
    if (db.open) db.close()
    const resolved = fs.realpathSync(fixture)
    assert.ok(resolved.startsWith(fs.realpathSync(os.tmpdir()) + path.sep))
    fs.rmSync(resolved, { recursive: true })
}
