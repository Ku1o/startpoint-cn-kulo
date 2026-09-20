const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'settlement-reliability-'))
process.env.DATA_DIR = directory
process.env.GAME_ROUTINE_LOGS = 'off'
const Fastify = require('fastify')
const { pack, unpack } = require('msgpackr')
// Own and close the room manager's existing import-time timer in this fixture.
const interval = global.setInterval
const roomTimers = []
let rushRoutes
try {
    global.setInterval = (callback, ...args) => {
        const timer = interval(callback, ...args)
        if (callback.name === 'cleanExpiredRooms') roomTimers.push(timer)
        return timer
    }
    rushRoutes = require('../out/routes/api/rushEvent').default
} finally { global.setInterval = interval }
const { getDb } = require('../out/data/db')
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const characters = require('../out/data/domains/character')
const missions = require('../out/data/domains/mission')
const awake = require('../out/data/domains/character_awake')
const { settleAwakeMissionRewards, settleAwakeMissionCandidates, getAwakeBattleMissionIds } = require('../out/lib/mission/awake-settlement')
const { reconcileAwakeUnlocksFromProgress } = require('../out/lib/mission/awake-unlock')
const rush = require('../out/data/domains/rushEvent')
const diagnostics = require('../out/lib/request-diagnostics')
const db = getDb()
const app = Fastify()
const monitor = diagnostics.installRequestDiagnostics(app)
app.addHook('onSend', (request, reply, payload) => diagnostics.measureResponseEncoding(request, async () =>
    reply.getHeader('content-type') === 'application/x-msgpack' ? pack(payload).toString('base64') : payload))
test.before(async () => { await app.register(rushRoutes, { prefix: '/rush' }); await app.ready() })
test.after(async () => {
    await app.close()
    roomTimers.forEach(clearInterval)
    db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory, { recursive: true })
})
let sequence = 0
function player() {
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'test', idpId: `reliability-${++sequence}`, status: 'normal' })
    const id = insertDefaultPlayerSync(account.id).id
    const viewer = 870200000 + id
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES (?,?,?,2)')
        .run(String(viewer), account.id, '2099-01-01T00:00:00.000Z')
    return { id, viewer }
}
function amounts(id) { return db.prepare('SELECT id,amount FROM players_items WHERE player_id=? ORDER BY id').all(id) }
function progress(characterId) {
    return [1, 2, 3, 4].map(n => ({ missionId: characterId * 10 + n, progress: 999 }))
}

test('unowned fixed-party progress stays pending while the outer battle transaction commits', () => {
    const p = player(), other = player(), characterId = 151045
    characters.insertDefaultPlayerCharacterSync(other.id, characterId) // Ownership must be player-scoped.
    missions.updatePlayerCategoryMissionSync(p.id, 9, 1510454, 3)
    const before = amounts(p.id)
    const mana = db.prepare('SELECT free_mana FROM players WHERE id=?').get(p.id).free_mana
    const result = db.transaction(() => {
        db.prepare('UPDATE players SET free_mana=free_mana+7 WHERE id=?').run(p.id)
        return settleAwakeMissionRewards(p.id, progress(characterId))
    })()
    assert.deepEqual(result.missionInfo, [])
    assert.deepEqual(result.characterList, [])
    assert.deepEqual(amounts(p.id), before)
    assert.equal(db.prepare('SELECT free_mana FROM players WHERE id=?').get(p.id).free_mana, mana + 7)
    assert.equal(awake.getPlayerCharacterAwakeUnlocksSync(p.id).size, 0)
    assert.equal(missions.getPlayerCategoryMissionsSync(p.id, 9)['1510454'].progress, 3)
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_category_mission_stages WHERE player_id=? AND category=9').get(p.id).n, 0)
    assert.equal(db.pragma('foreign_keys', { simple: true }), 1)
    assert.equal(characters.playerOwnsCharacterSync(p.id, characterId), false)

    characters.insertDefaultPlayerCharacterSync(p.id, characterId)
    const received = settleAwakeMissionRewards(p.id, progress(characterId))
    assert.equal(received.missionInfo.length, 4)
    assert.deepEqual(awake.getPlayerCharacterAwakeUnlocksSync(p.id).get(String(characterId)), { 1: 1 })
    const after = amounts(p.id)
    assert.deepEqual(settleAwakeMissionRewards(p.id, progress(characterId)).missionInfo, [])
    assert.deepEqual(amounts(p.id), after)
})

test('mixed owned and borrowed candidates settle only owned rewards; old unlock repair stays safe', () => {
    const p = player()
    characters.insertDefaultPlayerCharacterSync(p.id, 211002)
    const result = settleAwakeMissionRewards(p.id, [...progress(211002), ...progress(151045)])
    assert.equal(result.missionInfo.length, 4)
    assert.ok(result.missionInfo.every(row => Math.floor(row.mission_id / 10) === 211002))
    assert.equal(awake.getPlayerCharacterAwakeUnlocksSync(p.id).has('151045'), false)
    assert.doesNotThrow(() => reconcileAwakeUnlocksFromProgress(p.id, progress(151045)))
    missions.updatePlayerCategoryMissionSync(p.id, 9, 1510454, 3)
    const candidates = settleAwakeMissionCandidates(p.id, getAwakeBattleMissionIds([151045]), new Date('2025-01-01'))
    assert.deepEqual(candidates.characterList, [])
    assert.deepEqual(candidates.missionInfo, [])
    const skipped = diagnostics.drainAwakeDiagnostics()
    assert.ok(skipped.skippedUnownedMissions > 0)
    assert.ok(skipped.examples.length <= 3)
})

test('unexpected owned-character write failures still roll back the entire transaction', () => {
    const p = player()
    characters.insertDefaultPlayerCharacterSync(p.id, 151045)
    const before = amounts(p.id)
    const mana = db.prepare('SELECT free_mana FROM players WHERE id=?').get(p.id).free_mana
    db.exec("CREATE TRIGGER reject_awake_fixture BEFORE INSERT ON players_character_awake_unlocks BEGIN SELECT RAISE(ABORT,'awake fixture failure'); END")
    try {
        assert.throws(() => db.transaction(() => {
            db.prepare('UPDATE players SET free_mana=free_mana+7 WHERE id=?').run(p.id)
            settleAwakeMissionRewards(p.id, progress(151045))
        })(), /awake fixture failure/)
    } finally { db.exec('DROP TRIGGER reject_awake_fixture') }
    assert.deepEqual(amounts(p.id), before)
    assert.equal(db.prepare('SELECT free_mana FROM players WHERE id=?').get(p.id).free_mana, mana)
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_category_missions WHERE player_id=? AND category=9').get(p.id).n, 0)
})

async function select(p, eventId, folderId) {
    return app.inject({ method: 'POST', url: '/rush/select_folder', payload: { viewer_id: p.viewer, event_id: eventId, folder_id: folderId } })
}
test('same Rush selection is replayable without writes; a different folder remains rejected', async () => {
    const p = player(), eventId = 700001
    rush.insertPlayerRushEventSync(p.id, rush.getDefaultPlayerRushEventSync(eventId))
    assert.equal((await select(p, eventId, 1)).statusCode, 200)
    const before = db.prepare('SELECT * FROM players_rush_events WHERE player_id=?').all(p.id)
    const changes = db.prepare('SELECT total_changes() AS n').get().n
    const repeated = await Promise.all([select(p, eventId, 1), select(p, eventId, 1)])
    for (const response of repeated) {
        assert.equal(response.statusCode, 200)
        assert.deepEqual(unpack(Buffer.from(response.body, 'base64')).data, { folder_id: 1, event_id: eventId })
    }
    assert.equal(db.prepare('SELECT total_changes() AS n').get().n, changes)
    assert.equal((await select(p, eventId, 2)).statusCode, 400)
    assert.deepEqual(db.prepare('SELECT * FROM players_rush_events WHERE player_id=?').all(p.id), before)
    const summary = monitor.drain().summary
    assert.equal(summary.outcomes.rush_same_folder, 2)
    assert.equal(summary.outcomes.rush_different_folder, 1)
})

test('Rush failure reasons are distinct; invalid identities cannot mutate selection', async () => {
    const p = player()
    assert.equal((await select(p, 700001, 1)).statusCode, 400)
    assert.equal((await select({ viewer: 870999999 }, 700001, 1)).statusCode, 400)
    assert.equal((await select(p, 700001, null)).statusCode, 400)
    assert.equal((await app.inject({ method: 'POST', url: '/rush/select_folder', payload: {} })).statusCode, 400)
    const summary = monitor.drain().summary
    assert.equal(summary.outcomes.rush_missing_event, 1)
    assert.equal(summary.outcomes.rush_invalid_session, 1)
    assert.equal(summary.outcomes.rush_invalid_body, 2)
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_rush_events WHERE player_id=?').get(p.id).n, 0)
})

test('same-folder retries preserve the EX unlock gate and normal endless compatibility', async () => {
    const p = player()
    const { getAbyssTowerResetRevision } = require('../out/data/domains/abyss-tower-progress')
    for (const eventId of [700099, 700100]) rush.insertPlayerRushEventSync(p.id, {
        ...rush.getDefaultPlayerRushEventSync(eventId), activeRushBattleFolderId: 1,
        towerRevision: getAbyssTowerResetRevision(eventId),
    })
    const locked = await select(p, 700100, 1)
    assert.equal(locked.statusCode, 200)
    assert.equal(unpack(Buffer.from(locked.body, 'base64')).data_headers.result_code, 4050)
    const endless = await select(p, 700099, 2)
    assert.equal(endless.statusCode, 200)
    assert.equal(rush.getPlayerRushEventSync(p.id, 700099).activeRushBattleFolderId, 1)
    assert.equal((await select(p, 700099, 3)).statusCode, 400)
    assert.equal((await select(p, 700099, 1)).statusCode, 200)
    const summary = monitor.drain().summary
    assert.equal(summary.outcomes.rush_ex_locked, 1)
    assert.equal(summary.outcomes.rush_endless_compat, 1)
    assert.equal(summary.outcomes.rush_invalid_folder, 1)
    assert.equal(summary.outcomes.rush_same_folder, 1)
})
