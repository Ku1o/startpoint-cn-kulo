const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { createHash } = require('node:crypto')
const { spawnSync } = require('node:child_process')
const Database = require('better-sqlite3')
const { extractPlayerSave, parseArgs } = require('../tools/extract_player_save.cjs')

test('备份 viewer id 提取及恢复的隔离集成验证', async t => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-extract-save-'))
    const targetDir = path.join(root, 'target')
    fs.mkdirSync(targetDir)
    process.env.DATA_DIR = targetDir
    const db = require('../out/data/db').getDb()
    const snapshots = require('../out/data/snapshots/player-snapshot')
    const { insertAccountSync } = require('../out/data/domains/account')
    const { insertDefaultPlayerSync } = require('../out/data/domains/player')
    const make = name => {
        const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'fixture', idpId: name, status: 'normal' })
        const player = insertDefaultPlayerSync(account.id)
        db.prepare('UPDATE players SET name = ? WHERE id = ?').run(name, player.id)
        return { account, player }
    }
    const source = make('备份来源')
    const target = make('恢复目标')
    const other = make('其他玩家')
    const username = 'Source_Account'
    db.prepare('UPDATE accounts SET username = ? WHERE id = ?').run(username, source.account.id)
    const viewerId = 123456789
    db.prepare('INSERT INTO sessions(token, account_id, expires, type) VALUES (?, ?, ?, 2)')
        .run(String(viewerId), source.account.id, '2000-01-01') // Viewer tokens do not expire.
    db.prepare('INSERT INTO sessions(token, account_id, expires, type) VALUES (?, ?, ?, 1)')
        .run('234567891', other.account.id, '2099-01-01')
    db.prepare('INSERT INTO players_items(id, amount, player_id) VALUES (901, ?, ?)').run(456, source.player.id)
    db.prepare('INSERT INTO players_items(id, amount, player_id) VALUES (901, ?, ?)').run(999, other.player.id)
    db.prepare('INSERT INTO players_active_missions(id, progress, player_id) VALUES (98001, 6, ?)').run(source.player.id)
    db.prepare('INSERT INTO players_active_missions_stages(id, status, player_id, mission_id) VALUES (1, 2, ?, 98001)').run(source.player.id)
    db.prepare('INSERT INTO players_receive_history(player_id, type, type_id, number, reason_id, create_time) VALUES (?, 1, 901, 456, 0, ?)')
        .run(source.player.id, '2026-09-15 01:00:00')
    const beforeSource = snapshots.createPlayerSaveSnapshotV2Sync(source.player.id, db)
    const backupDir = path.join(root, 'backup')
    fs.mkdirSync(backupDir)
    const backup = path.join(backupDir, 'wdfp_data.db')
    await db.backup(backup)
    const digest = filename => createHash('sha256').update(fs.readFileSync(filename)).digest('hex')
    const backupHash = digest(backup)
    const output = path.join(root, 'recovered.json')
    const options = { database: backup, viewerId, output }
    let app
    t.after(async () => {
        if (app) await app.close()
        if (db.open) db.close()
        const resolved = fs.realpathSync(root)
        assert.ok(resolved.startsWith(fs.realpathSync(os.tmpdir()) + path.sep))
        fs.rmSync(resolved, { recursive: true })
    })

    await t.test('CLI 通过 viewer 映射导出；忽略 DATA_DIR；备份及其他玩家不变', () => {
        const forbidden = path.join(root, 'must-not-open')
        const child = spawnSync(process.execPath, [path.resolve(__dirname, '../tools/extract_player_save.cjs'),
            '--database', backupDir, '--viewer-id', String(viewerId), '--output', output], {
            cwd: root, encoding: 'utf8', env: { ...process.env, DATA_DIR: forbidden }, timeout: 30000,
        })
        assert.equal(child.status, 0, child.stdout + child.stderr)
        assert.equal(fs.existsSync(forbidden), false)
        const snapshot = JSON.parse(fs.readFileSync(output, 'utf8'))
        assert.notEqual(viewerId, source.player.id)
        assert.equal(snapshot.playerId, source.player.id)
        assert.deepEqual(snapshot.data.tables, beforeSource.data.tables)
        assert.equal(snapshot.data.tables.accounts, undefined)
        assert.equal(snapshot.data.tables.sessions, undefined)
        assert.equal(snapshot.data.tables.device_bindings, undefined)
        assert.equal(digest(backup), backupHash)
    })

    await t.test('CLI 通过登录账号名定位同一账号；大小写不敏感且不读取密码', () => {
        const accountOutput = path.join(root, 'recovered-by-account.json')
        const child = spawnSync(process.execPath, [path.resolve(__dirname, '../tools/extract_player_save.cjs'),
            '--database', backup, '--username', username.toLowerCase(), '--output', accountOutput], {
            cwd: root, encoding: 'utf8', env: { ...process.env, DATA_DIR: path.join(root, 'must-not-open-account') }, timeout: 30000,
        })
        assert.equal(child.status, 0, child.stdout + child.stderr)
        const directOutput = path.join(root, 'recovered-by-account-direct.json')
        const result = extractPlayerSave({ database: backup, username, output: directOutput })
        assert.equal(result.username, username.toLowerCase())
        assert.equal(result.playerId, source.player.id)
        assert.deepEqual(JSON.parse(fs.readFileSync(accountOutput, 'utf8')).data.tables, beforeSource.data.tables)
        assert.deepEqual(JSON.parse(fs.readFileSync(directOutput, 'utf8')).data.tables, beforeSource.data.tables)
        assert.equal(fs.existsSync(path.join(root, 'must-not-open-account')), false)
        assert.throws(() => extractPlayerSave({ database: backup, username, viewerId, output: path.join(root, 'both.json') }), /必须且只能指定/)
        assert.throws(() => extractPlayerSave({ database: backup, username: 'missing_account', output: path.join(root, 'missing-account.json') }), /找不到登录账号/)
        assert.equal(digest(backup), backupHash)
    })

    await t.test('窗口进程协议支持中文路径，只生成指定 JSON；查询和错误均不创建备份', () => {
        const guiOutput = path.join(root, '中文 存档 & 测试.json')
        const run = request => {
            const child = spawnSync(process.execPath, [path.resolve(__dirname, '../tools/extract_player_save_gui_worker.cjs')], {
                input: JSON.stringify(request), encoding: 'utf8', timeout: 30000,
            })
            const response = JSON.parse(child.stdout)
            return { child, response }
        }
        const beforeFiles = fs.readdirSync(root).sort()
        const listed = run({ database: backup, viewerId, list: true })
        assert.equal(listed.child.status, 0, listed.child.stderr)
        assert.equal(listed.response.ok, true)
        assert.equal(listed.response.result.candidates[0].name, '备份来源')
        assert.deepEqual(fs.readdirSync(root).sort(), beforeFiles)
        const extracted = run({ database: backup, viewerId, playerId: source.player.id, output: guiOutput })
        assert.equal(extracted.child.status, 0, extracted.child.stderr)
        assert.equal(extracted.response.ok, true)
        assert.equal(extracted.response.result.output, guiOutput)
        assert.deepEqual(JSON.parse(fs.readFileSync(guiOutput, 'utf8')).data.tables, beforeSource.data.tables)
        assert.deepEqual(fs.readdirSync(root).sort(), [...beforeFiles, path.basename(guiOutput)].sort())
        const duplicate = run({ database: backup, viewerId, output: guiOutput })
        assert.equal(duplicate.child.status, 1)
        assert.match(duplicate.response.error, /拒绝覆盖/)
        const missingOutput = run({ database: backup, viewerId })
        assert.equal(missingOutput.response.ok, false)
        assert.match(missingOutput.response.error, /输出文件/)
        assert.equal(digest(backup), backupHash)
    })

    await t.test('错误 viewer、登录 token、跨账号选择、已有输出和缺失文件拒绝', () => {
        const failOutput = path.join(root, 'failure.json')
        for (const [changes, pattern] of [
            [{ viewerId: 111111111 }, /找不到 viewer/],
            [{ viewerId: 234567891 }, /找不到 viewer/],
            [{ viewerId: '1 OR 1=1' }, /正整数/],
            [{ viewerId: '9007199254740992' }, /正整数/],
            [{ username: 'bad name' }, /登录账号/],
            [{ username: 'a' }, /登录账号/],
            [{ playerId: other.player.id }, /不属于/],
            [{ database: path.join(root, 'missing.db') }, /ENOENT/],
        ]) {
            assert.throws(() => extractPlayerSave({ ...options, output: failOutput, ...changes }), pattern)
            assert.equal(fs.existsSync(failOutput), false)
        }
        const outputHash = digest(output)
        assert.throws(() => extractPlayerSave(options), /拒绝覆盖/)
        assert.equal(digest(output), outputHash)
        assert.throws(() => extractPlayerSave({ ...options, output: backup }), /json/)
        assert.throws(() => parseArgs(['--viewer-id']), /缺少值/)
        assert.throws(() => parseArgs(['--viewer-id', '1', '--viewer-id', '2']), /重复/)
        assert.equal(digest(backup), backupHash)
    })

    await t.test('多存档必须选择，列举仅显示该账号；已删存档和未知表拒绝', () => {
        const second = insertDefaultPlayerSync(source.account.id)
        const multiple = path.join(root, 'multiple.db')
        db.pragma('wal_checkpoint(TRUNCATE)')
        fs.copyFileSync(path.join(targetDir, 'wdfp_data.db'), multiple)
        const opts = { ...options, database: multiple, output: path.join(root, 'second.json') }
        assert.throws(() => extractPlayerSave(opts), /多个存档/)
        assert.deepEqual(extractPlayerSave({ ...opts, list: true }).candidates.map(p => p.id), [source.player.id, second.id])
        assert.equal(fs.existsSync(opts.output), false)
        assert.equal(extractPlayerSave({ ...opts, playerId: second.id }).playerId, second.id)
        const scratch = new Database(multiple)
        try {
            scratch.exec('CREATE TABLE future_player_state(player_id INTEGER REFERENCES players(id), progress INTEGER)')
            scratch.prepare('INSERT INTO future_player_state VALUES (?, 77)').run(source.player.id)
            assert.throws(() => extractPlayerSave({ ...opts, playerId: source.player.id }), /尚未登记.*future_player_state/)
            scratch.exec('DROP TABLE future_player_state')
            scratch.prepare('DELETE FROM players WHERE account_id = ?').run(source.account.id)
            assert.throws(() => extractPlayerSave(opts), /已没有存档/)
        } finally { scratch.close() }
    })

    await t.test('缺表备份不自动初始化；压缩存储沿用 V2 逻辑结构', () => {
        const old = path.join(root, 'missing-table.db')
        fs.copyFileSync(backup, old)
        const oldDb = new Database(old)
        oldDb.exec('DROP TABLE players_character_awake_unlocks')
        oldDb.close()
        const oldHash = digest(old)
        assert.throws(() => extractPlayerSave({ ...options, database: old }), /存档表不存在/)
        assert.equal(digest(old), oldHash)

        const compact = path.join(root, 'compact.db')
        fs.copyFileSync(backup, compact)
        const compactDb = new Database(compact)
        require('../out/lib/storage-layout').migrateStorageLayout(compactDb)
        compactDb.close()
        const compactHash = digest(compact)
        const compactOutput = path.join(root, 'compact.json')
        extractPlayerSave({ ...options, database: compact, output: compactOutput })
        const recovered = JSON.parse(fs.readFileSync(compactOutput, 'utf8'))
        assert.equal(recovered.schemaFingerprint, beforeSource.schemaFingerprint)
        assert.deepEqual(recovered.data.tables, beforeSource.data.tables)
        assert.equal(digest(compact), compactHash)
    })

    await t.test('读取配套 WAL 中的进度，拒绝损坏数据库及 CDN 输出', () => {
        const walPath = path.join(root, 'with-wal.db')
        fs.copyFileSync(backup, walPath)
        const writer = new Database(walPath)
        try {
            writer.pragma('journal_mode = WAL')
            writer.pragma('wal_autocheckpoint = 0')
            writer.prepare('UPDATE players_items SET amount=789 WHERE player_id=? AND id=901').run(source.player.id)
            assert.ok(fs.statSync(`${walPath}-wal`).size > 0)
            const mainHash = digest(walPath)
            const walHash = digest(`${walPath}-wal`)
            const walOutput = path.join(root, 'wal.json')
            extractPlayerSave({ ...options, database: walPath, output: walOutput })
            const items = JSON.parse(fs.readFileSync(walOutput, 'utf8')).data.tables.players_items
            assert.equal(items.rows.find(row => row[items.columns.indexOf('id')] === 901)[items.columns.indexOf('amount')], 789)
            assert.equal(digest(walPath), mainHash)
            assert.equal(digest(`${walPath}-wal`), walHash)
        } finally { writer.close() }
        const corrupt = path.join(root, 'corrupt.db')
        fs.writeFileSync(corrupt, 'not a SQLite database')
        assert.throws(() => extractPlayerSave({ ...options, database: corrupt }), /not a database/)
        const protectedDir = path.join(root, '.cdn')
        fs.mkdirSync(protectedDir)
        assert.throws(() => extractPlayerSave({ ...options, output: path.join(protectedDir, 'save.json') }), /只读 .cdn/)
        const alias = path.join(root, 'cdn-alias')
        fs.symlinkSync(protectedDir, alias, process.platform === 'win32' ? 'junction' : 'dir')
        assert.throws(() => extractPlayerSave({ ...options, output: path.join(alias, 'save.json') }), /只读 .cdn/)
        assert.deepEqual(fs.readdirSync(protectedDir), [])
    })

    await t.test('实际下载/上传路由恢复误删进度；回滚备份为目标原进度；不影响其他玩家', async () => {
        // Simulate deletion only in the isolated destination; the backup remains intact.
        db.prepare('DELETE FROM players WHERE id = ?').run(source.player.id)
        const targetBefore = snapshots.createPlayerSaveSnapshotV2Sync(target.player.id, db)
        const otherBefore = snapshots.createPlayerSaveSnapshotV2Sync(other.player.id, db)
        app = require('fastify')({ logger: false })
        await app.register(require('@fastify/multipart'), { limits: { fileSize: 64 * 1024 * 1024 } })
        await app.register(require('../out/routes/web_api/player').default, { prefix: '/api/player' })
        const boundary = 'extract-save-fixture-boundary'
        const payload = Buffer.concat([
            Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="save.json"\r\nContent-Type: application/json\r\n\r\n`),
            fs.readFileSync(output), Buffer.from(`\r\n--${boundary}--\r\n`),
        ])
        const response = await app.inject({ method: 'POST', url: `/api/player/save?id=${target.player.id}`,
            headers: { accept: 'application/json', 'content-type': `multipart/form-data; boundary=${boundary}` }, payload })
        assert.equal(response.statusCode, 200, response.body)
        const backupName = path.basename(response.json().backup)
        const rollback = JSON.parse(fs.readFileSync(path.join(targetDir, 'admin-backups', backupName, 'player-save.json'), 'utf8'))
        assert.deepEqual(rollback.data.tables, targetBefore.data.tables)
        const downloaded = await app.inject({ method: 'GET', url: `/api/player/save?id=${target.player.id}` })
        assert.equal(downloaded.statusCode, 200)
        const restored = downloaded.json()
        assert.equal(restored.summary.playerName, '备份来源')
        assert.equal(restored.playerId, target.player.id)
        assert.equal(db.prepare('SELECT account_id FROM players WHERE id=?').get(target.player.id).account_id, target.account.id)
        assert.equal(db.prepare('SELECT amount FROM players_items WHERE player_id=? AND id=901').get(target.player.id).amount, 456)
        assert.equal(restored.data.tables.players_active_missions_stages.rows.length, 1)
        assert.equal(restored.data.tables.players_receive_history.rows.length, 1)
        assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(other.player.id, db).data.tables, otherBefore.data.tables)
        assert.equal(digest(backup), backupHash)
        assert.deepEqual(db.pragma('foreign_key_check'), [])
    })
})
