const moduleRoot = process.argv.includes('--compiled') ? '../out' : '../src'
if (moduleRoot === '../src') require('ts-node/register/transpile-only')

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { randomUUID } = require('node:crypto')
const Fastify = require('fastify')
const { pack, unpack } = require('msgpackr')

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'practice-real-time-'))
process.env.DATA_DIR = dataDir
const NativeDate = Date
let realNow = NativeDate.parse('2026-09-13T15:59:00.000Z')
global.Date = class extends NativeDate {
    constructor(...args) { super(...(args.length ? args : [realNow])) }
    static now() { return realNow }
}
const { getDb } = require(`${moduleRoot}/data/db`)
const { insertAccountSync } = require(`${moduleRoot}/data/domains/account`)
const { insertDefaultPlayerSync } = require(`${moduleRoot}/data/domains/player`)
const { saveAccountDefaultPlayer } = require(`${moduleRoot}/data/activeAccount`)
const { setServerTime, getServerTime, getTimeOffset } = require(`${moduleRoot}/utils`)
const { insertPlayerPracticeBattleHistorySync } = require(`${moduleRoot}/data/domains/practice-battle-history`)
const { buildBattleHistoryProtocolRecord } = require(`${moduleRoot}/lib/quest/battle-history`)
const db = getDb()
const app = Fastify({ logger: false })

async function main() {
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'test', idpId: randomUUID(), status: 'normal' })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 830000000 + player.id
    db.prepare('INSERT INTO sessions (token, account_id, expires, type) VALUES (?, ?, ?, 2)')
        .run(String(viewerId), account.id, '2099-01-01T00:00:00.000Z')
    const party = { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
        equipments: [null, null, null], ability_soul_ids: [null, null, null] }
    const statistics = { clear_phase: 1, party,
        zones: [{ damage_deal_total: 123456789012, members: [{ origin_damage: 123456789012 }, null, null] }] }
    const legacy = { playerId: player.id, playId: 'imported-virtual-date',
        ...buildBattleHistoryProtocolRecord({ categoryId: 15, questId: 91, finishKind: 0,
            createdAt: new Date('2025-08-05T01:26:35Z'), elapsedTimeMs: 2397, score: 100,
            clearRank: 5, party, statistics, equipmentList: {} }, 15, 'Legacy fixture') }
    insertPlayerPracticeBattleHistorySync(legacy)
    const readLegacy = () => db.prepare('SELECT * FROM players_practice_battle_history WHERE player_id=? AND play_id=?')
        .get(player.id, legacy.playId)
    const legacyBefore = readLegacy()

    app.addHook('onSend', (_request, reply, payload, done) => {
        done(null, reply.getHeader('content-type') === 'application/x-msgpack' ? pack(payload).toString('base64') : payload)
    })
    await app.register(require(`${moduleRoot}/routes/api/singleBattleQuest`).default, { prefix: '/api/index.php/single_battle_quest' })
    await app.register(require(`${moduleRoot}/routes/api/history`).default, { prefix: '/api/index.php/history' })
    await app.ready()
    let count = 0
    const post = (url, payload) => app.inject({ method: 'POST', url: `/api/index.php/${url}`, payload })
    const decode = response => unpack(Buffer.from(response.body, 'base64'))
    const readHistory = async () => {
        const response = await post('history/practice_battle', { viewer_id: viewerId })
        assert.equal(response.statusCode, 200, response.body)
        return decode(response)
    }
    const cases = [
        { questId: 97, kind: 'finish', elapsed: 31195, virtual: '2025-08-06T00:00:00Z', expected: '2026-09-13 23:59:31' },
        { questId: 1101, kind: 'abort', elapsed: 38000, virtual: '2025-07-19T00:00:00Z', expected: '2026-09-14 00:00:09' },
        { questId: 1102, kind: 'finish', elapsed: 600000, virtual: '2035-01-01T00:00:00Z', expected: '2026-09-14 00:10:09' },
    ]
    for (const item of cases) {
        setServerTime(new Date(item.virtual))
        const offsetBefore = getTimeOffset()
        const playId = `real-time-${item.questId}`
        const start = await post('single_battle_quest/start', {
            viewer_id: viewerId, category: 15, quest_id: item.questId, party_id: 1, play_id: playId,
            use_boss_boost_point: false, use_boost_point: false, is_auto_start_mode: false, api_count: ++count,
        })
        assert.equal(start.statusCode, 200, start.body)
        realNow += item.elapsed
        const common = { viewer_id: viewerId, category: 15, quest_id: item.questId, play_id: playId, api_count: ++count, statistics }
        const response = item.kind === 'abort'
            ? await post('single_battle_quest/abort', { ...common, finish_kind: 1 })
            : await post('single_battle_quest/finish', { ...common, continue_count: 0, elapsed_time_ms: item.elapsed,
                score: 123456789012, add_mana: 0, is_accomplished: true, is_restored: false })
        assert.equal(response.statusCode, 200, response.body)
        const data = await readHistory()
        const record = data.data.history[0]
        assert.equal(record.quest_id, item.questId)
        assert.equal(record.create_time, item.expected, `${item.kind} must use real Beijing time despite the virtual clock`)
        assert.equal(record.elapsed_time_ms, item.elapsed, 'changing the display clock must not change battle duration')
        assert.equal(record.total_damage, 123456789012)
        assert.equal(record.character_1_total_damage, 123456789012)
        assert.equal(Object.keys(record).length, 29, 'client protocol shape stays compatible')
        assert.equal(getTimeOffset(), offsetBefore, 'recording history must not change the event clock')
        assert.equal(data.data_headers.servertime, getServerTime())
    }
    const response = await readHistory()
    // Match PracticeHistoryListScene.historySort: the client sorts again by
    // create_time, even though the server already returns newest insertions.
    const clientOrder = [...response.data.history].sort((a, b) => b.create_time.localeCompare(a.create_time))
    assert.deepEqual(clientOrder.map(row => row.quest_id), [1102, 1101, 97, 91])
    assert.deepEqual(readLegacy(), legacyBefore, 'unknown old real dates must not be guessed or rewritten')
    const datesBefore = response.data.history.map(row => row.create_time)
    setServerTime(new Date('2024-01-01T00:00:00Z'))
    assert.deepEqual((await readHistory()).data.history.map(row => row.create_time), datesBefore,
        'reading an archive after another clock change must not retime its records')
    console.log(JSON.stringify({ passed: true, mode: moduleRoot, completion_and_abort_real_time: true,
        beijing_midnight: true, virtual_clock_backward_and_forward: true, client_date_sort: true,
        damage_and_duration_preserved: true, legacy_row_unchanged: true, protocol_fields: 29 }))
}

main().catch(error => { console.error(error); process.exitCode = 1 }).finally(async () => {
    await app.close()
    await require(`${moduleRoot}/multi/npc/player-party-pool`).stopQuestNpcPartyPoolWorker()
    if (db.open) db.close()
    global.Date = NativeDate
    const resolved = path.resolve(dataDir)
    assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()))
    assert.ok(path.basename(resolved).startsWith('practice-real-time-'))
    fs.rmSync(resolved, { recursive: true })
    process.exit(process.exitCode ?? 0)
})
