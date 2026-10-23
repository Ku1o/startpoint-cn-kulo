const { test, after } = require('node:test'), assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const f = require('./helpers/upstream-business-fixture.cjs').fixture('multi-party-fallback')
const players = f.load('data/domains/player'), chars = f.load('data/domains/character'), parties = f.load('data/domains/party')
const snapshots = f.load('multi/party-snapshot'), { PartyCategory } = f.load('data/types')
const player = f.create(), other = f.create()
const ids = Object.keys(f.load('lib/content-master').serverCharacters).slice(0, 3).map(Number)
for (const p of [player, other]) for (const id of ids) if (!chars.getPlayerCharacterSync(p.id, id)) chars.insertDefaultPlayerCharacterSync(p.id, id)
function party(name, id, unison = null) { return { name, category: PartyCategory.NORMAL, characterIds: [id, null, null], unisonCharacterIds: [unison, null, null],
    equipmentIds: [null, null, null], abilitySoulIds: [null, null, null], edited: true, options: { allowOtherPlayersToHealMe: true }, currentBattlePower: 10000, beforeBattlePower: 10000 } }
const selected = party('selected A', ids[0], ids[1]), npc = party('NPC B', ids[2])
parties.updatePlayerPartySync(player.id, 2, selected, 2)
parties.updatePlayerPartySync(player.id, 1, npc, 1)
parties.updatePlayerPartySync(other.id, 2, party('other selected', ids[2]), 2)
players.updatePlayerSync({ id: player.id, partySlot: 12 }); players.updatePlayerSync({ id: other.id, partySlot: 12 })
chars.insertPlayerCharacterManaNodesSync(player.id, ids[0], [101, 102])
chars.insertPlayerCharacterManaNodesSync(player.id, ids[1], [201])
chars.updatePlayerCharacterManaNodeAwakeLevelSync(player.id, ids[0], 102, 2)
chars.updatePlayerCharacterManaNodeAwakeLevelSync(player.id, ids[1], 201, 1)
after(f.close)

test('DB fallback selects the requested global SET and preserves both positions awake levels', () => {
    const a = snapshots.getRealPartySnapshot(player.id, 12)
    assert.equal(a.characters[0][1].id, ids[0]); assert.equal(a.unison_characters[0][1].id, ids[1])
    assert.deepEqual(a.characters[0][1].mana_node_ids, { 101: 0, 102: 2 })
    assert.deepEqual(a.unison_characters[0][1].mana_node_ids, { 201: 1 })
    assert.equal(snapshots.getRealPartySnapshot(player.id, 1).characters[0][1].id, ids[2])
    assert.equal(snapshots.getRealPartySnapshot(other.id, 12).characters[0][1].id, ids[2])
    a.characters[0][1].mana_node_ids[102] = 99
    assert.equal(snapshots.getRealPartySnapshot(player.id, 12).characters[0][1].mana_node_ids[102], 2)
    assert.equal(snapshots.buildRealParty(player.id, npc).characters[0][1].id, ids[2], 'explicit NPC source remains separate')
})
test('selected wire cache is scoped to the SET, and awakening invalidates only future fallback reads', () => {
    const frozen = snapshots.getRealPartySnapshot(player.id, 12), wire = structuredClone(frozen)
    wire.characters[0][1].id = ids[2]
    snapshots.setRealPartySnapshot(player.id, wire, 1)
    assert.equal(snapshots.getRealPartySnapshot(player.id, 12).characters[0][1].id, ids[0])
    chars.updatePlayerCharacterManaNodeAwakeLevelSync(player.id, ids[0], 102, 3)
    assert.equal(snapshots.getRealPartySnapshot(player.id, 12).characters[0][1].mana_node_ids[102], 3)
    assert.equal(frozen.characters[0][1].mana_node_ids[102], 2, 'accepted battle snapshot is unchanged')
    assert.equal(snapshots.getRealPartySnapshot(player.id, 121).characters[0][0], 1, 'invalid selected SET never inherits NPC')
})
test('parent business facts preserve the requested SET and the explicitly frozen wire party', async () => {
    const handlers = f.load('multi/coordinator/business-handlers')
    const scope = { playerId: player.id, category: 2, questId: 1033004, partyId: 12 }
    const facts = await handlers.handleRealtimeBusiness('player.facts', scope)
    assert.equal(facts.partyId, 12); assert.equal(facts.party.characters[0][1].id, ids[0])
    assert.equal(facts.party.characters[0][1].mana_node_ids[102], 3)
    const accepted = snapshots.buildRealParty(player.id, npc)
    const frozenFacts = await handlers.handleRealtimeBusiness('player.facts', { ...scope, wireParty: accepted })
    assert.deepEqual(frozenFacts.party, accepted, 'a DB refresh does not replace the accepted original play party')
})
test('Welcome uses the DB fallback when Enter omits party; a supplied party stays authoritative', async t => {
    const rooms = f.load('multi/room/manager'), manager = f.load('multi/state/SessionManager').sessionManager
    const lobby = f.load('multi/tcp/lobby')
    class Socket extends EventEmitter { destroyed = false; writable = true; readable = true; frames = []
        write(frame) { this.frames.push(JSON.parse(frame.replace(/\0$/, ''))); return true }
        destroy() { this.destroyed = true; this.writable = false } end() { this.destroy() } }
    for (const supplied of [false, true]) {
        const room = rooms.createRoom(player.viewer, player.id, 12, 2, 1033004, 1, ids[0])
        const socket = new Socket(), client = manager.createClient(socket, player.viewer, room.room_number, `fallback-${supplied}`, player.id)
        client.roomGeneration = room.lobby_generation
        client.yourself = { viewerId: player.viewer, playerId: player.id, connectionId: client.connectionId, currentPartyId: 12, state: [0], party: snapshots.getRealPartySnapshot(player.id, 12) }
        manager.addClientToRoom(client); rooms.addRoomMember(room.room_number, player.viewer, player.id)
        const replacement = snapshots.buildRealParty(player.id, npc)
        await lobby.handleMessage(socket, [0, [0, supplied ? { party: replacement, currentPartyId: 12 } : {}, 12]])
        const welcome = socket.frames.find(frame => frame[0] === 1 && frame[1]?.[0] === 0)
        assert.ok(welcome, JSON.stringify(socket.frames)); assert.equal(welcome[1][1].party.characters[0][1].id, supplied ? ids[2] : ids[0])
        rooms.disbandRoom(room.room_number, 'fixture_complete')
    }
})
