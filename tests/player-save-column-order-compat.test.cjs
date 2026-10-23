require('ts-node/register/transpile-only')

const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { createHash, randomUUID } = require('node:crypto')

const temporaryRoot = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(temporaryRoot, { recursive: true })
const directory = fs.mkdtempSync(path.join(temporaryRoot, 'save-column-order-'))
process.env.DATA_DIR = directory
process.env.TEMP = directory
process.env.TMP = directory
process.env.SQLITE_TMPDIR = directory
process.env.CN_WRITER_THREAD = '0'
process.env.GAME_VERBOSE_LOGS = 'false'
process.env.GAME_ROUTINE_LOGS = 'off'

const saves = require('../src/data/snapshots/player-snapshot')
const { getDb } = require('../src/data/db')
const { insertAccountSync } = require('../src/data/domains/account')
const { insertDefaultPlayerSync } = require('../src/data/domains/player')
const { getStorageSnapshotTableInfo } = require('../src/lib/storage-layout')
const db = getDb()
const reorderedTables = [
    'players', 'players_quest_progress', 'players_periodic_snapshots',
    'players_multi_special_exchange_campaigns',
]
const economyTables = [
    'players_shop_quotas', 'players_exchange_campaign_receipts',
    'players_special_exchange_campaigns',
]
let app, sourceArchive

function createPlayer(label) {
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'column-order', idpId: randomUUID(), status: 'normal' })
    const player = insertDefaultPlayerSync(account.id)
    db.prepare('UPDATE players SET name=?,free_vmoney=?,exp_pool=? WHERE id=?').run(label, 1234, 5678, player.id)
    return { id: player.id, accountId: account.id }
}

function seedProgress(playerId) {
    db.prepare(`INSERT OR REPLACE INTO players_quest_progress
        (section,quest_id,finished,host_finished,unlocked,high_score,clear_rank,best_elapsed_time_ms,leader_character_id,multi_clear_count,s_plus_reward_received,player_id)
        VALUES(2,1010001,1,1,1,4567,3,6789,111001,7,1,?)`).run(playerId)
    db.prepare(`INSERT OR REPLACE INTO players_periodic_snapshots
        (player_id,period_type,quest_clears,stamina_used,rank_ss,single_play_count,multi_clear_count,dash_count,login_days,updated_at)
        VALUES(?,'column-order-fixture',11,22,33,44,55,66,77,'2026-01-02T03:04:05.000Z')`).run(playerId)
    db.prepare(`INSERT OR REPLACE INTO players_multi_special_exchange_campaigns
        (campaign_id,status,ticket_item_id,player_id) VALUES(101,2,999002,?)`).run(playerId)
    db.prepare(`INSERT OR REPLACE INTO players_rush_events(player_id,event_id,tower_revision)
        VALUES(?,101,'column-order-fixture')`).run(playerId)
}

function seedEconomy(playerId) {
    db.prepare(`INSERT INTO players_shop_quotas VALUES(?,101,'month','2026-01',3)`).run(playerId)
    db.prepare(`INSERT INTO players_exchange_campaign_receipts VALUES('special',101,0,111001,?)`).run(playerId)
    db.prepare(`INSERT INTO players_special_exchange_campaigns VALUES(101,2,?)`).run(playerId)
}

function snapshot(playerId) { return saves.createPlayerSaveSnapshotV2Sync(playerId, db) }
function cloned(value) { return JSON.parse(JSON.stringify(value)) }

// Reconstruct the existing fingerprint contract from real target metadata,
// retaining every metadata field while following the archive's column order.
function fingerprint(archive, mutateMetadata = column => column) {
    const schema = saves.PLAYER_SNAPSHOT_V2_TABLES.filter(table => archive.data.tables[table]).map(table => {
        const info = getStorageSnapshotTableInfo(db, table) || db.prepare(`PRAGMA table_info("${table}")`).all()
        const byName = new Map(info.map(column => [column.name, column]))
        return { table, columns: archive.data.tables[table].columns.map(name => {
            const column = byName.get(name)
            assert.ok(column, 'fixture columns must resolve against the actual schema')
            return mutateMetadata({ name: column.name, type: column.type, notnull: column.notnull, defaultValue: column.dflt_value, pk: column.pk }, table)
        }) }
    })
    return createHash('sha256').update(JSON.stringify(schema)).digest('hex')
}

function archiveFor({ oldEconomy = false, oldTower = false } = {}) {
    const archive = cloned(sourceArchive)
    for (const table of reorderedTables) {
        const data = archive.data.tables[table]
        assert.ok(data.rows.length, `${table} must exercise nonempty rows`)
        data.columns.reverse()
        data.rows.forEach(row => row.reverse())
    }
    if (oldEconomy) economyTables.forEach(table => delete archive.data.tables[table])
    if (oldTower) {
        const data = archive.data.tables.players_rush_events
        const index = data.columns.indexOf('tower_revision')
        assert.ok(index >= 0)
        data.columns.splice(index, 1)
        data.rows.forEach(row => row.splice(index, 1))
    }
    archive.summary.includedTableCount = Object.keys(archive.data.tables).length
    archive.summary.rowCount = Object.values(archive.data.tables).reduce((total, table) => total + table.rows.length, 0)
    archive.schemaFingerprint = fingerprint(archive)
    return archive
}

function multipart(archive) {
    const boundary = `column-order-${randomUUID()}`
    return {
        headers: { accept: 'application/json', 'content-type': `multipart/form-data; boundary=${boundary}` },
        payload: Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic-save.json"\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(archive)}\r\n--${boundary}--\r\n`),
    }
}

function upload(targetId, archive) {
    return app.inject({ method: 'POST', url: `/api/player/save?id=${targetId}`, ...multipart(archive) })
}

function rowsByName(table) {
    return table.rows.map(row => Object.fromEntries(table.columns.map((column, index) => [column, row[index]])))
}

before(async () => {
    assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory) + path.sep))
    const source = createPlayer('synthetic-column-source')
    seedProgress(source.id)
    seedEconomy(source.id)
    sourceArchive = snapshot(source.id)
    app = require('fastify')({ logger: false, bodyLimit: 262144 })
    await app.register(require('@fastify/multipart'), { limits: { fileSize: 64 * 1024 * 1024, files: 1 } })
    await app.register(require('../src/routes/web_api/player').default, { prefix: '/api/player' })
    await app.ready()
})

after(async () => {
    if (app) await app.close()
    await require('../src/lib/seed-validator').default.close()
    if (db.open) db.close()
    assert.equal(path.dirname(directory), temporaryRoot)
    fs.rmSync(directory, { recursive: true })
})

test('HTTP import maps nonempty reordered columns by name for all four existing schema profiles', async () => {
    for (const oldEconomy of [false, true]) for (const oldTower of [false, true]) {
        const target = createPlayer('synthetic-column-target')
        seedEconomy(target.id)
        const before = snapshot(target.id)
        const archive = archiveFor({ oldEconomy, oldTower })
        const original = JSON.stringify(archive)
        const response = await upload(target.id, archive)
        assert.equal(response.statusCode, 200, response.body)
        assert.equal(JSON.stringify(archive), original, 'import must not rewrite the archive or its fingerprint')
        const result = response.json()
        const after = snapshot(target.id)
        const actualPlayer = rowsByName(after.data.tables.players)[0]
        const sourcePlayer = rowsByName(archive.data.tables.players)[0]
        for (const [column, value] of Object.entries(sourcePlayer)) {
            if (['id', 'account_id', 'time_offset', 'exp_pooled_time', 'last_login_time'].includes(column)) continue
            assert.equal(actualPlayer[column], value, `players.${column}`)
        }
        assert.equal(actualPlayer.id, target.id)
        assert.equal(actualPlayer.account_id, target.accountId)
        for (const table of reorderedTables.slice(1)) {
            const expected = rowsByName(archive.data.tables[table]).map(row => ({ ...row, player_id: target.id }))
            assert.deepEqual(rowsByName(after.data.tables[table]), expected, table)
        }
        assert.equal(rowsByName(after.data.tables.players_rush_events)[0].tower_revision, oldTower ? null : 'column-order-fixture')
        if (oldEconomy) for (const table of economyTables) {
            assert.deepEqual(after.data.tables[table], before.data.tables[table], `${table} target rights must survive old archives`)
        }
        const backup = JSON.parse(fs.readFileSync(path.join(directory, 'admin-backups', path.basename(result.backup), 'player-save.json'), 'utf8'))
        assert.deepEqual(backup.data.tables, before.data.tables, 'rollback backup must contain the target before replacement')
    }
})

test('metadata changes cannot be disguised as column ordering', () => {
    for (const field of ['type', 'notnull', 'defaultValue', 'pk']) {
        const archive = archiveFor()
        archive.schemaFingerprint = fingerprint(archive, (column, table) => {
            if (table !== 'players_quest_progress' || column.name !== 'high_score') return column
            return { ...column, [field]: { type: 'TEXT', notnull: 1, defaultValue: '913', pk: 8 }[field] }
        })
        assert.throws(() => saves.validatePlayerSaveSnapshotV2Sync(archive, db), /结构/, field)
    }
})

test('HTTP rejects duplicate, missing, extra columns and foreign player rows before changing the target', async () => {
    const target = createPlayer('synthetic-rejection-target')
    seedProgress(target.id)
    const before = snapshot(target.id).data.tables
    const mutations = [
        archive => { const data = archive.data.tables.players_quest_progress; data.columns[1] = data.columns[0] },
        archive => { const data = archive.data.tables.players_periodic_snapshots; data.columns.pop(); data.rows.forEach(row => row.pop()) },
        archive => { const data = archive.data.tables.players_multi_special_exchange_campaigns; data.columns.push('future_extra_column'); data.rows.forEach(row => row.push(1)) },
        archive => { const data = archive.data.tables.players_quest_progress; data.rows[0][data.columns.indexOf('player_id')] = target.id },
    ]
    for (const mutate of mutations) {
        const archive = archiveFor()
        mutate(archive)
        const response = await upload(target.id, archive)
        assert.notEqual(response.statusCode, 200)
        assert.deepEqual(snapshot(target.id).data.tables, before, 'invalid input must not change target progress')
    }
})

test('a late insert failure rolls back reordered player and progress writes', async () => {
    const target = createPlayer('synthetic-rollback-target')
    seedProgress(target.id)
    const before = snapshot(target.id).data.tables
    db.exec(`CREATE TEMP TRIGGER fail_column_order_import BEFORE INSERT ON players_multi_special_exchange_campaigns
        WHEN NEW.player_id=${target.id} BEGIN SELECT RAISE(ABORT,'synthetic column-order rollback'); END`)
    try {
        const response = await upload(target.id, archiveFor())
        assert.equal(response.statusCode, 500)
        assert.match(response.json().error, /synthetic column-order rollback/)
        assert.deepEqual(snapshot(target.id).data.tables, before, 'all earlier deletes and player/progress updates must roll back')
    } finally {
        db.exec('DROP TRIGGER fail_column_order_import')
    }
    assert.deepEqual(db.pragma('foreign_key_check'), [])
})
