'use strict'
const assert = require('node:assert/strict')
const test = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')
const root = path.resolve(__dirname, '../..')
const local = createRequire(path.join(root, 'package.json'))
const data = path.resolve(process.env.DATA_DIR || '')
const tmp = path.resolve(root, 'tmp') + path.sep
assert.ok(data.startsWith(tmp) && data.includes('cpu-check-'), 'Run only through the repository isolated-check launcher')
Object.assign(process.env, { CN_WRITER_THREAD: '0', GAME_ROUTINE_LOGS: 'off', GAME_VERBOSE_LOGS: 'false' })
local('ts-node/register/transpile-only')
const load = name => local(path.join(root, 'src', name))
const Fastify = local('fastify')
const { PartyCategory } = load('data/types')
const { QuestCategory } = load('lib/types')
const parties = load('data/domains/party')
const { captureBattleRosterSync, resolveBattlePartySync } = load('lib/quest/battle-roster')
const { partyCategoryForRushEvent } = load('lib/rush-party-categories')
const { getDb } = load('data/db')
const { saveAccountDefaultPlayer } = load('data/activeAccount')
const { insertAccountSync } = load('data/domains/account')
const { insertDefaultPlayerSync } = load('data/domains/player')
const { insertSessionWithTokenSync } = load('data/domains/session')
const { givePlayerCharacterSync } = load('lib/character')

test('source handlers preserve dedicated teams across migration, save, reread and start roster', async t => {
    const app = Fastify({ logger: false })
    t.after(async () => { await app.close(); getDb().close() })
    app.addHook('onSend', (_req, reply, payload, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof payload === 'object'
            ? JSON.stringify(payload) : payload))
    await app.register(load('routes/api/rushEvent').default, { prefix: '/rush' })
    await app.register(load('routes/api/party').default, { prefix: '/party' })
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'isolated-party-contract', idpId: 'isolated-party-contract', status: 'normal' })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    const viewer = 886010031
    insertSessionWithTokenSync({ token: String(viewer), accountId: account.id, type: 2, expires: new Date('2099-01-01T00:00:00Z') })
    const alternate = 243001
    const sub = Number(Object.keys(local(path.join(root, 'assets/character.json'))).find(id => !['1', String(alternate)].includes(id)))
    for (const id of [alternate, sub]) assert.ok(givePlayerCharacterSync(player.id, id))
    const party = (category, name, leader) => ({ category, name, characterIds: [leader, null, null], unisonCharacterIds: [null, null, null],
        equipmentIds: [null, null, null], abilitySoulIds: [null, null, null], edited: true, options: { allowOtherPlayersToHealMe: true } })
    parties.updatePlayerPartySync(player.id, 1, party(PartyCategory.RUSH, 'legacy sentinel', 1))
    parties.updatePlayerPartySync(player.id, 2, party(PartyCategory.RUSH, 'legacy second', 1))
    parties.updatePlayerPartySync(player.id, 1, party(PartyCategory.ABYSS_NORMAL, 'normal sentinel', sub))
    parties.updatePlayerPartySync(player.id, 1, party(PartyCategory.FANTASY, 'fantasy sentinel', 1))
    const db = getDb()
    const snapshot = () => db.prepare('SELECT * FROM players_parties WHERE player_id=? AND category<>? ORDER BY category,group_id,slot')
        .all(player.id, PartyCategory.ABYSS_EX)
    const protectedBefore = snapshot()
    const fetch = async eventId => {
        const r = await app.inject({ method: 'POST', url: '/rush/party', payload: { viewer_id: viewer, event_id: eventId } })
        assert.equal(r.statusCode, 200, r.body)
        assert.equal(r.json().data_headers.result_code, 1)
        return r.json().data.user_party_group_list
    }
    const first = await fetch(700100)
    assert.equal(first.find(g => g.party_group_id === 1).party_list.find(p => p.party_id === 1).party_name, 'legacy sentinel')
    assert.equal(parties.getPlayerPartyGroupListSync(player.id, PartyCategory.ABYSS_EX)['1'].list['2'].name, 'legacy second')
    assert.deepEqual(snapshot(), protectedBefore)
    const edit = await app.inject({ method: 'POST', url: '/party/edit', payload: {
        viewer_id: viewer, main_party_id: 1, party_info_list: [{ party_edited: true, party_category: 6,
            party_name: 'EX saved', party_id: 1, character_ids: [alternate, null, null], unison_character_ids: [null, null, null],
            equipment_ids: [null, null, null], ability_soul_ids: [null, null, null], options: { allow_other_players_to_heal_me: true } }],
    } })
    assert.equal(edit.statusCode, 200, edit.body)
    assert.equal(edit.json().data_headers.result_code, 1, edit.body)
    for (let i = 0; i < 2; i++) {
        const again = await fetch(700100)
        const ex = again.find(g => g.party_group_id === 1).party_list.find(p => p.party_id === 1)
        assert.equal(ex.party_name, 'EX saved')
        assert.deepEqual(ex.character_ids, [alternate, null, null])
        assert.deepEqual(snapshot(), protectedBefore)
    }
    const frozen = captureBattleRosterSync({ playerId: player.id, questCategory: QuestCategory.RUSH_EVENT,
        questId: 700100001, partyId: 1 })
    assert.equal(frozen.party.characters[0].id, alternate)
    parties.updatePlayerPartySync(player.id, 1, party(6, 'EX changed after start', sub))
    const reportedAfterEdit = { ...frozen.party, characters: [{ id: sub }, null, null] }
    assert.equal(resolveBattlePartySync(player.id, frozen, reportedAfterEdit, false).characters[0].id, alternate)
    assert.deepEqual(snapshot(), protectedBefore)
    for (const [eventId, category, leader] of [[700099, 5, sub], [700100, 6, sub], [700098, 7, 1], [700001, 4, 1], [799999, 4, 1]]) {
        assert.equal(partyCategoryForRushEvent(eventId), category)
        const roster = captureBattleRosterSync({ playerId: player.id, questCategory: QuestCategory.RUSH_EVENT,
            questId: eventId * 1000 + 1, partyId: 1 })
        assert.equal(roster.party.characters[0].id, leader)
    }
    // Missing EX is an error, even if a legacy Rush team exists: no category-4 fallback at battle start.
    db.prepare('DELETE FROM players_parties WHERE player_id=? AND category=6').run(player.id)
    assert.throws(() => captureBattleRosterSync({ playerId: player.id, questCategory: QuestCategory.RUSH_EVENT,
        questId: 700100001, partyId: 1 }), error => error.code === 'INVALID_BATTLE_PARTY')
    assert.deepEqual(snapshot(), protectedBefore)
})
