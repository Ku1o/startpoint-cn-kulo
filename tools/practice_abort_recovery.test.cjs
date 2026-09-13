const moduleRoot = process.argv.includes('--compiled') ? '../out' : '../src'
if (moduleRoot === '../src') require('ts-node/register/transpile-only')

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { randomUUID } = require('node:crypto')
const Fastify = require('fastify')
const { pack, unpack } = require('msgpackr')

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'practice-abort-recovery-'))
process.env.DATA_DIR = dataDir
const { getDb } = require(`${moduleRoot}/data/db`)
const { insertAccountSync } = require(`${moduleRoot}/data/domains/account`)
const { insertDefaultPlayerSync } = require(`${moduleRoot}/data/domains/player`)
const { saveAccountDefaultPlayer } = require(`${moduleRoot}/data/activeAccount`)
const battle = require(`${moduleRoot}/routes/api/singleBattleQuest`)
const db = getDb()
const app = Fastify({ logger: false })

async function main() {
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'test', idpId: randomUUID(), status: 'normal' })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 820000000 + player.id
    db.prepare('INSERT INTO sessions (token, account_id, expires, type) VALUES (?, ?, ?, 2)')
        .run(String(viewerId), account.id, '2099-01-01T00:00:00.000Z')
    app.addHook('onSend', (_request, reply, payload, done) => {
        done(null, reply.getHeader('content-type') === 'application/x-msgpack' ? pack(payload).toString('base64') : payload)
    })
    await app.register(battle.default, { prefix: '/single_battle_quest' })
    await app.register(require(`${moduleRoot}/routes/cn/load`).default, { prefix: '/cn' })
    await app.ready()
    let apiCount = 0
    const post = (url, payload) => app.inject({ method: 'POST', url, payload })
    const activeCount = () => db.prepare('SELECT COUNT(*) AS n FROM players_active_quests WHERE player_id=?').get(player.id).n
    const historyCount = () => db.prepare('SELECT COUNT(*) AS n FROM players_practice_battle_history WHERE player_id=?').get(player.id).n
    const progressBefore = db.prepare('SELECT * FROM players_quest_progress WHERE player_id=?').all(player.id)
    const checks = []

    // Crash/relogin abandonment has no live battle statistics. Also accept null
    // and unusable telemetry without manufacturing a zero-damage history row.
    for (const questId of [97, 87, 1101, 1102]) {
        for (const [label, statistics] of [
            ['omitted', undefined], ['null', null], ['empty', {}],
            ['invalid-damage', { party: {}, zones: [{ damage_deal_total: -1 }] }],
        ]) {
            const playId = `recovery-${questId}-${label}`
            const started = await post('/single_battle_quest/start', {
                viewer_id: viewerId, category: 15, quest_id: questId, party_id: 1, play_id: playId,
                use_boss_boost_point: false, use_boost_point: false, is_auto_start_mode: false, api_count: ++apiCount,
            })
            assert.equal(started.statusCode, 200, started.body)
            delete battle.activeQuests[player.id] // Reconstruct from persisted state after restart.
            if (questId === 1101 && label === 'omitted') {
                const loaded = await post('/cn/load', { viewer_id: viewerId })
                assert.equal(loaded.statusCode, 200, loaded.body)
                assert.equal(unpack(Buffer.from(loaded.body, 'base64')).data.unfinished_quest_list[0].play_id, playId)
            }
            const payload = { viewer_id: viewerId, category: 15, quest_id: questId, play_id: playId, finish_kind: 3, api_count: ++apiCount }
            if (statistics !== undefined) payload.statistics = statistics
            for (const mismatch of [{ play_id: 'older-play' }, { quest_id: 1199 }, { category: 1 }]) {
                const refused = await post('/single_battle_quest/abort', { ...payload, ...mismatch })
                assert.equal(refused.statusCode, 400, refused.body)
                assert.equal(activeCount(), 1, 'unrelated abort must preserve the active battle')
            }
            const aborted = await post('/single_battle_quest/abort', payload)
            assert.equal(aborted.statusCode, 200, `${questId}/${label}: ${aborted.body}`)
            assert.equal(aborted.json().data.category_id, 15)
            assert.equal(activeCount(), 0)
            assert.equal(battle.activeQuests[player.id], undefined)
            assert.equal(historyCount(), 0, 'missing/invalid telemetry must not fabricate battle history')
            if (questId === 1101 && label === 'omitted') {
                const loaded = await post('/cn/load', { viewer_id: viewerId })
                assert.equal(loaded.statusCode, 200, loaded.body)
                assert.deepEqual(unpack(Buffer.from(loaded.body, 'base64')).data.unfinished_quest_list, [])
            }
            assert.equal((await post('/single_battle_quest/abort', payload)).statusCode, 200, 'retry must be idempotent')
            checks.push(`${questId}/${label}`)
        }
    }
    // Failure to commit the cancellation must preserve the recoverable battle,
    // even when no history row is being written.
    const rollbackPlayId = 'recovery-delete-rollback'
    assert.equal((await post('/single_battle_quest/start', {
        viewer_id: viewerId, category: 15, quest_id: 1101, party_id: 1, play_id: rollbackPlayId,
        use_boss_boost_point: false, use_boost_point: false, is_auto_start_mode: false, api_count: ++apiCount,
    })).statusCode, 200)
    db.exec(`CREATE TRIGGER reject_recovery_delete BEFORE DELETE ON players_active_quests
        BEGIN SELECT RAISE(ABORT, 'recovery rollback fixture'); END`)
    const rollbackPayload = { viewer_id: viewerId, category: 15, quest_id: 1101,
        play_id: rollbackPlayId, finish_kind: 3, api_count: ++apiCount }
    assert.equal((await post('/single_battle_quest/abort', rollbackPayload)).statusCode, 500)
    assert.equal(activeCount(), 1)
    assert.equal(battle.activeQuests[player.id].playId, rollbackPlayId)
    assert.equal(historyCount(), 0)
    db.exec('DROP TRIGGER reject_recovery_delete')
    assert.equal((await post('/single_battle_quest/abort', rollbackPayload)).statusCode, 200)
    assert.equal(activeCount(), 0)
    assert.deepEqual(db.prepare('SELECT * FROM players_quest_progress WHERE player_id=?').all(player.id), progressBefore)
    console.log(JSON.stringify({ passed: true, recovery_cases: checks, mismatched_requests: checks.length * 3,
        no_fabricated_history: true, quest_progress_unchanged: true, cancellation_rollback: true,
        database: 'isolated temporary database' }))
}

main().catch(error => { console.error(error); process.exitCode = 1 }).finally(async () => {
    await app.close()
    await require(`${moduleRoot}/multi/npc/player-party-pool`).stopQuestNpcPartyPoolWorker()
    if (db.open) db.close()
    const resolved = path.resolve(dataDir)
    assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()))
    assert.ok(path.basename(resolved).startsWith('practice-abort-recovery-'))
    fs.rmSync(resolved, { recursive: true })
    process.exit(process.exitCode ?? 0)
})
