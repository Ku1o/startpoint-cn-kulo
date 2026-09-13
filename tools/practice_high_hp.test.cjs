// Exercise the deployed accessor/route modules against an isolated database.
// No build or real player database is needed for this JSON/resource change.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { randomUUID } = require('node:crypto')
const { pack, unpack } = require('msgpackr')
const Fastify = require('fastify')

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'practice-high-hp-'))
process.env.DATA_DIR = dataDir
process.env.ADMIN_PANEL_PASSWORD = 'practice-high-hp-isolated-fixture'
const { getDb } = require('../out/data/db')
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const { getMergedPlayerDataSync } = require('../out/data/utils')
const { saveAccountDefaultPlayer } = require('../out/data/activeAccount')
const { getPlayerQuestProgressSync } = require('../out/data/domains/quest')
const assets = require('../out/lib/assets')
const snapshot = require('../out/data/snapshots/player-snapshot')
const battle = require('../out/routes/api/singleBattleQuest')
const db = getDb()
const game = Fastify({ logger: false })
const admin = Fastify({ logger: false })
const cases = [
    { id: 97, elapsed: 180000, damage: 1000479773 },
    { id: 87, elapsed: 180000, damage: 5001460385 },
    { id: 1101, elapsed: 600000, damage: 100047977312, name: '高血量木人·无' },
    { id: 1102, elapsed: 600000, damage: 500146038748, name: '高血量木人们·无' },
]
let apiCount = 0

function player(label) {
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'test', idpId: `${label}-${randomUUID()}`, status: 'normal' })
    const record = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, record.id)
    return { id: record.id, accountId: account.id }
}

function decode(response) {
    assert.equal(response.statusCode, 200, response.body)
    assert.match(response.headers['content-type'], /^application\/x-msgpack/)
    return unpack(Buffer.from(response.body, 'base64')).data
}

function progress(playerId, questId) {
    return getPlayerQuestProgressSync(playerId)['15']?.find(row => row.questId === questId)
}

async function main() {
    const audit = path.join(__dirname, '../assets/asset-patch/audit/practice-clones-100x-1.4.107')
    const receipt = JSON.parse(fs.readFileSync(path.join(audit, 'report.json'), 'utf8'))
    const beforeServer = JSON.parse(fs.readFileSync(path.join(audit, 'before/practice_quest.json'), 'utf8'))
    const server = require('../assets/practice_quest.json')
    assert.equal(Object.keys(server).length, Object.keys(beforeServer).length + 2)
    for (const [id, row] of Object.entries(beforeServer)) assert.deepEqual(server[id], row)
    for (const entry of receipt.hp.clones) {
        let total = 0
        for (const [kind, count] of [['boss', 1], ['funnel_each', entry.funnel_count]]) {
            if (!entry[kind]) continue
            const hp = Math.floor(entry[kind].factors.map(Number).reduce((a, b) => a * b, 1))
            assert.ok(Number.isSafeInteger(hp))
            assert.equal(hp, entry[kind].hp, `${kind}: native Number arithmetic`)
            total += hp * count
        }
        assert.equal(total, entry.initial_total)
    }
    for (const item of cases) {
        const actual = assets.getPracticeQuestSync(item.id)
        assert.ok(actual, `runtime accessor must resolve ${item.id}`)
        assert.deepEqual(assets.getQuestFromCategorySync(15, item.id), actual)
        for (const field of ['bRankTime', 'aRankTime', 'sRankTime', 'sPlusRankTime']) {
            assert.equal(actual[field], item.elapsed)
        }
        for (const field of ['rankPointReward', 'characterExpReward', 'manaReward', 'poolExpReward']) {
            assert.equal(actual[field], 0)
        }
        if (item.name) assert.equal(actual.name, item.name)
    }

    const source = player('practice-source')
    const target = player('practice-target')
    const legacyTarget = player('practice-legacy-target')
    const viewerId = 820000000 + source.id
    db.prepare('INSERT INTO sessions (token,account_id,expires,type) VALUES (?,?,?,2)')
        .run(String(viewerId), source.accountId, '2099-01-01T00:00:00.000Z')
    game.addHook('onSend', (_request, reply, payload, done) => {
        done(null, reply.getHeader('content-type') === 'application/x-msgpack' ? pack(payload).toString('base64') : payload)
    })
    await game.register(battle.default, { prefix: '/single_battle_quest' })
    await game.register(require('../out/routes/api/history').default, { prefix: '/history' })
    await game.ready()
    let oldV2
    let oldV1
    let originalProgress
    for (const [index, item] of cases.entries()) {
        decode(await game.inject({ method: 'POST', url: '/single_battle_quest/start', payload: {
            viewer_id: viewerId, category: 15, quest_id: item.id, party_id: 1,
            play_id: `high-hp-${item.id}`, use_boss_boost_point: false, use_boost_point: false,
            is_auto_start_mode: false, api_count: ++apiCount,
        } }))
        const result = decode(await game.inject({ method: 'POST', url: '/single_battle_quest/finish', payload: {
            viewer_id: viewerId, category: 15, quest_id: item.id, play_id: `high-hp-${item.id}`,
            continue_count: 0, elapsed_time_ms: item.elapsed, score: item.damage, add_mana: 0,
            is_accomplished: true, is_restored: false, api_count: ++apiCount,
            statistics: {
                clear_phase: 1,
                party: { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
                    equipments: [null, null, null], ability_soul_ids: [null, null, null] },
                zones: [{ damage_deal_total: item.damage, members: [{ origin_damage: item.damage }, null, null] }],
            },
        } }))
        assert.equal(result.category_id, 15)
        const history = decode(await game.inject({ method: 'POST', url: '/history/practice_battle', payload: { viewer_id: viewerId } })).history
        assert.equal(history.length, index + 1)
        assert.equal(history[0].quest_id, item.id)
        assert.equal(history[0].elapsed_time_ms, item.elapsed)
        assert.equal(history[0].total_damage, item.damage)
        assert.equal(history[0].character_1_total_damage, item.damage)
        assert.equal(history[0].clear_rank, 5, 'the ten-minute clear must retain the practice SS threshold')
        assert.ok(progress(source.id, item.id)?.finished)
        if (index === 1) {
            oldV2 = snapshot.createPlayerSaveSnapshotV2Sync(source.id)
            oldV1 = { schema: 'starpoint-cn-save', version: 1, playerId: source.id, exportedAt: new Date().toISOString(), data: getMergedPlayerDataSync(source.id) }
            originalProgress = [progress(source.id, 97), progress(source.id, 87)]
        }
    }
    assert.deepEqual([progress(source.id, 97), progress(source.id, 87)], originalProgress)
    const aborts = []
    for (const item of cases.filter(x => x.name)) {
        const playId = `high-hp-abort-${item.id}`
        decode(await game.inject({ method: 'POST', url: '/single_battle_quest/start', payload: {
            viewer_id: viewerId, category: 15, quest_id: item.id, party_id: 1, play_id: playId,
            use_boss_boost_point: false, use_boost_point: false, is_auto_start_mode: false, api_count: ++apiCount,
        } }))
        db.prepare('UPDATE players_active_quests SET started_at_ms=started_at_ms-420000 WHERE player_id=?').run(source.id)
        delete battle.activeQuests[source.id]
        const aborted = await game.inject({ method: 'POST', url: '/single_battle_quest/abort', payload: {
            viewer_id: viewerId, category: 15, quest_id: item.id, play_id: playId, finish_kind: 1, api_count: ++apiCount,
            statistics: {
                party: { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
                    equipments: [null, null, null], ability_soul_ids: [null, null, null] },
                zones: [{ damage_deal_total: item.damage, members: [{ origin_damage: item.damage }, null, null] }],
            },
        } })
        assert.equal(aborted.statusCode, 200, aborted.body)
        const latest = decode(await game.inject({ method: 'POST', url: '/history/practice_battle', payload: { viewer_id: viewerId } })).history[0]
        assert.equal(latest.quest_id, item.id)
        assert.equal(latest.finish_kind, 1)
        assert.equal(latest.clear_rank, null)
        assert.equal(latest.total_damage, item.damage)
        assert.ok(latest.elapsed_time_ms >= 420000 && latest.elapsed_time_ms <= 422000)
        aborts.push({ quest_id: item.id, elapsed_time_ms: latest.elapsed_time_ms, total_damage: latest.total_damage })
    }
    const badStart = await game.inject({ method: 'POST', url: '/single_battle_quest/start', payload: {
        viewer_id: viewerId, category: 15, quest_id: 1199, party_id: 1, play_id: 'missing-quest', api_count: ++apiCount,
    } })
    assert.equal(badStart.statusCode, 400)
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_active_quests WHERE player_id=?').get(source.id).n, 0)

    // Use real HTTP download/multipart import, including its automatic backup.
    require('../out/lib/management-auth').installManagementAuth(admin)
    await admin.register(require('../out/routes/web_api').default, { prefix: '/api' })
    const origin = await admin.listen({ host: '127.0.0.1', port: 0 })
    const login = await fetch(origin + '/admin-login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ password: process.env.ADMIN_PANEL_PASSWORD }) })
    assert.equal(login.status, 200)
    const cookie = login.headers.get('set-cookie').split(';')[0]
    const getSave = id => fetch(origin + `/api/player/save?id=${id}`, { headers: { cookie }, signal: AbortSignal.timeout(30000) })
    const putSave = (id, value) => {
        const form = new FormData()
        form.append('file', new Blob([typeof value === 'string' ? value : JSON.stringify(value)], { type: 'application/json' }), 'practice-save.json')
        return fetch(origin + `/api/player/save?id=${id}`, { method: 'POST', headers: { cookie, Accept: 'application/json' }, body: form, signal: AbortSignal.timeout(30000) })
    }
    const exported = await getSave(source.id)
    assert.equal(exported.status, 200, await exported.clone().text())
    const newV2 = await exported.json()
    assert.equal(newV2.schemaFingerprint, oldV2.schemaFingerprint, 'new content IDs do not change the save schema')
    const newV1 = { schema: 'starpoint-cn-save', version: 1, playerId: source.id, exportedAt: new Date().toISOString(), data: getMergedPlayerDataSync(source.id) }
    const imports = []
    for (const [value, recipient, expectedIds] of [
        [oldV2, legacyTarget, [97, 87]], [oldV1, legacyTarget, [97, 87]],
        [newV2, target, cases.map(x => x.id)], [newV1, legacyTarget, cases.map(x => x.id)],
    ]) {
        const before = snapshot.createPlayerSaveSnapshotV2Sync(recipient.id)
        const imported = await putSave(recipient.id, value)
        assert.equal(imported.status, 200, await imported.clone().text())
        const result = await imported.json()
        assert.equal(result.snapshotVersion, value.version)
        const backup = JSON.parse(fs.readFileSync(path.join(dataDir, 'admin-backups', path.basename(result.backup.replace(/\\/g, '/')), 'player-save.json'), 'utf8'))
        assert.deepEqual(backup.data.tables, before.data.tables, 'rollback backup must equal the untouched destination')
        for (const id of expectedIds) {
            assert.ok(progress(recipient.id, id)?.finished, `V${value.version} must retain quest ${id}`)
            assert.ok(assets.getPracticeQuestSync(id), `imported ID ${id} must resolve`)
        }
        assert.equal(db.prepare('SELECT account_id FROM players WHERE id=?').get(recipient.id).account_id, recipient.accountId)
        const reexported = await getSave(recipient.id)
        assert.equal(reexported.status, 200)
        if (value === newV2) {
            const restored = await reexported.json()
            const t = restored.data.tables.players_practice_battle_history
            assert.equal(t.rows.length, cases.length + aborts.length)
            const ids = [...new Set(t.rows.map(row => row[t.columns.indexOf('quest_id')]))].sort((a, b) => a - b)
            assert.deepEqual(ids, cases.map(x => x.id).sort((a, b) => a - b))
        }
        imports.push({ version: value.version, quest_ids: expectedIds, exact_pre_import_backup: true })
    }
    const beforeInvalid = snapshot.createPlayerSaveSnapshotV2Sync(target.id)
    assert.equal((await putSave(target.id, 'invalid-json')).status, 400)
    const invalidSchema = structuredClone(newV2)
    invalidSchema.schemaFingerprint = '0'.repeat(64)
    const rejectedSchema = await putSave(target.id, invalidSchema)
    // The existing import route reports validator errors as 500; the relevant
    // contract here is a clear rejection before any destination mutation.
    assert.equal(rejectedSchema.status, 500)
    assert.match((await rejectedSchema.json()).error, /存档数据库结构与当前服务器不一致/)
    assert.deepEqual(snapshot.createPlayerSaveSnapshotV2Sync(target.id).data.tables, beforeInvalid.data.tables)
    assert.equal(db.pragma('integrity_check', { simple: true }), 'ok')
    assert.deepEqual(db.pragma('foreign_key_check'), [])
    const report = { ok: true, winning_accessor: 'out/lib/assets.getQuestFromCategorySync',
        isolated_database: true, battle_start_finish_and_history: cases, ieee754_hp_parity: true,
        battle_abort_and_history: aborts,
        original_progress_preserved: true, imports, invalid_input_atomic: true,
        existing_server_rows_preserved: Object.keys(beforeServer).length, device_tested: false,
        runtime_mirror_tested: false, schema_changed: false }
    if (process.argv[2]) fs.writeFileSync(path.resolve(process.argv[2]), JSON.stringify(report, null, 2) + '\n')
    console.log('PASS: original/new practice starts, ten-minute finish/rank/history, seven-minute abort records, large damage, independent progress, old/new V1/V2 HTTP transfer and exact rollback backups')
}

main().catch(error => { console.error(error); process.exitCode = 1 }).finally(async () => {
    await game.close()
    await admin.close()
    await require('../out/multi/npc/player-party-pool').stopQuestNpcPartyPoolWorker()
    if (db.open) db.close()
    const resolved = path.resolve(dataDir)
    assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()))
    assert.ok(path.basename(resolved).startsWith('practice-high-hp-'))
    fs.rmSync(resolved, { recursive: true })
}).then(() => process.exit(process.exitCode || 0))
