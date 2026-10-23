const { test, after } = require('node:test'), assert = require('node:assert/strict')
const f = require('./helpers/upstream-business-fixture.cjs').fixture('ranking-summary')
const players = [f.create(), f.create(), f.create()], chars = f.load('data/domains/character')
const leader = Number(Object.keys(f.load('lib/content-master').serverCharacters)[0])
for (const player of players) { if (!chars.getPlayerCharacterSync(player.id, leader)) chars.insertDefaultPlayerCharacterSync(player.id, leader) }
const summary = f.load('lib/ranking-summary').getRankingSummarySync, placement = f.load('lib/activity-degree-rewards').getRankingPlacementSync
function record(player, time, score, finished = true) { f.load('data/domains/quest').insertPlayerQuestProgressSync(player.id, 11,
    { questId: 1001, finished, bestElapsedTimeMs: time, highScore: score, leaderCharacterId: leader }) }
after(f.close)
test('empty and score-only records contain no synthetic first-place result', () => {
    assert.equal(summary(players[0].id, 99999), null)
    const empty = summary(players[0].id, 1)
    assert.deepEqual(empty, { best_record: null })
    record(players[0], null, 77, false)
    assert.equal(summary(players[0].id, 1).best_record.score, 77)
    assert.equal(summary(players[0].id, 1).best_record.is_accomplished, false)
})
test('actual top/leader/score and client percent projection agree with completed ranking including ties', () => {
    f.db.prepare('DELETE FROM players_quest_progress WHERE section=11 AND quest_id=1001').run()
    record(players[0], 1000, 100); record(players[1], 1000, 200); record(players[2], 2000, 300)
    const first = summary(players[0].id, 1), last = summary(players[2].id, 1)
    assert.equal(first.leader_character_id, leader)
    assert.equal(first.leader_character_evolution_img_level, chars.getPlayerCharacterSync(players[0].id, leader).illustrationSettings?.[0] ?? chars.getPlayerCharacterSync(players[0].id, leader).evolutionLevel)
    assert.deepEqual(first.rank_border_top, { elapsed_time_ms: 1000, is_accomplished: true, score: 200 })
    assert.equal(first.best_record.score, 100); assert.equal(last.rank_percentage, 100)
    assert.equal(first.rank_percentage, (1 / 3) * 100)
    assert.equal(placement(players[0].id, 1).percentile, 1 / 3, 'reward percentage remains a ratio')
    assert.ok(first.rank_percentage >= 0.5)
})
test('the production summary endpoint projects the same values without changing reward ratio', async () => {
    const app = require('fastify')({ logger: false }), { pack, unpack } = require('msgpackr')
    app.addHook('onSend', (_r, reply, body, done) => done(null, String(reply.getHeader('content-type')).startsWith('application/x-msgpack') ? pack(body).toString('base64') : body))
    await app.register(f.load('routes/api/rankingEvent').default); await app.ready()
    try {
        const response = await app.inject({ method: 'POST', url: '/get_summary', payload: { viewer_id: players[0].viewer, ranking_event_id: 1, quest_kind: 1 } })
        assert.equal(response.statusCode, 200)
        assert.deepEqual(unpack(Buffer.from(response.body, 'base64')).data, summary(players[0].id, 1))
        assert.equal(placement(players[0].id, 1).percentile, 1 / 3)
    } finally { await app.close() }
})
