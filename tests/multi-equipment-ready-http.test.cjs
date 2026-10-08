const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { EventEmitter } = require('node:events')
const Fastify = require('fastify')

const parent = path.resolve(__dirname, '../tmp')
fs.mkdirSync(parent, { recursive: true })
const directory = fs.mkdtempSync(path.join(parent, 'equipment-http-'))
process.env.DATA_DIR = directory
const originalInterval = global.setInterval
const intervals = []
global.setInterval = (...args) => {
    const timer = originalInterval(...args)
    intervals.push(timer)
    return timer
}
let db, rooms, manager, lobby, coordinator, battle, partyRoutes, accounts, players, sessions, parties, active
try {
    db = require('../out/data/db').getDb()
    accounts = require('../out/data/domains/account')
    players = require('../out/data/domains/player')
    sessions = require('../out/data/domains/session')
    parties = require('../out/data/domains/party')
    active = require('../out/data/domains/quest_active')
    rooms = require('../out/multi/room/manager')
    manager = require('../out/multi/state/SessionManager').sessionManager
    lobby = require('../out/multi/tcp/lobby')
    coordinator = require('../out/multi/coordinator/embedded').embeddedMultiCoordinator
    battle = require('../out/multi/http/battle')
    partyRoutes = require('../out/routes/api/party').default
} finally {
    global.setInterval = originalInterval
}
const equipment = require('../out/multi/room/equipment-ready')
let sequence = 0

class Socket extends EventEmitter {
    destroyed = false; readable = true; writable = true; frames = []
    write(frame) { this.frames.push(JSON.parse(frame.replace(/\0$/, ''))); return true }
    end() { this.writable = false }
    destroy() { this.destroyed = true; this.emit('close') }
}

function makePlayer() {
    const n = ++sequence
    const account = accounts.insertAccountSync({
        appId: 'wf_cn', idpAlias: '', idpCode: 'test', idpId: `equipment-${n}`, status: 'normal',
    })
    const player = players.insertDefaultPlayerSync(account.id)
    require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 880000000 + n
    sessions.insertSessionWithTokenSync({
        token: String(viewerId), accountId: account.id, type: 2,
        expires: new Date(Date.now() + 86400000),
    })
    return { ...player, viewerId }
}

function savedParty(soul = null) {
    return {
        category: 1, name: 'test', characterIds: [1, null, null],
        unisonCharacterIds: [null, null, null], equipmentIds: [null, null, null],
        abilitySoulIds: [soul, null, null], edited: true,
        options: { allowOtherPlayersToHealMe: true },
    }
}

async function setup(t) {
    const host = makePlayer(), guest = makePlayer()
    const room = rooms.createRoom(host.viewerId, host.id, 1, 1, 9001001, 0, 1)
    const clients = [host, guest].map(player => {
        const c = manager.createClient(new Socket(), player.viewerId, room.room_number, `cid-${player.id}`, player.id)
        c.enterData = {}
        c.isReady = true
        c.yourself = {
            viewerId: player.viewerId, playerId: player.id, connectionId: c.connectionId,
            comId: 0, currentPartyId: 1, state: [1],
            party: { equipments: [], abilitySoulIds: [] },
        }
        manager.addClientToRoom(c)
        rooms.addRoomMember(room.room_number, player.viewerId, player.id)
        parties.updatePlayerPartySync(player.id, 1, savedParty(), 1)
        players.updatePlayerSync({ id: player.id, partySlot: 1 })
        return c
    })
    for (const client of clients) client.mates = clients.map(c => c.yourself)
    const app = Fastify()
    app.addHook('onSend', (_req, reply, payload, done) => {
        done(null, reply.getHeader('content-type') === 'application/x-msgpack'
            ? JSON.stringify(payload) : payload)
    })
    t.after(async () => {
        manager.commitRoomDisband(room.room_number, 'test_cleanup')
        for (const client of clients) client.socket.destroy()
        await app.close()
        await new Promise(resolve => setImmediate(resolve))
    })
    await app.register(async instance => battle.registerBattleRoutes(instance), { prefix: '/multi' })
    await app.register(partyRoutes, { prefix: '/party' })
    await app.ready()
    const notify = async (index, data) => {
        lobby.handleMessage(clients[index].socket, [0, data])
        await coordinator.enqueueRoomCommand(room.room_number, () => {})
    }
    const start = (player = host, extra = {}) => app.inject({
        method: 'POST', url: '/multi/start', payload: {
            viewer_id: player.viewerId, category: 1, quest_id: 9001001,
            party_id: 1, room_number: room.room_number, play_id: `play-${player.id}`,
            use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: false,
            mate_player_ids: [], mate_party_ids: [], ...extra,
        },
    })
    const edit = (soul, slot = 1) => app.inject({
        method: 'POST', url: '/party/edit', payload: {
            viewer_id: guest.viewerId, main_party_id: 1, party_info_list: [{
                party_category: 1, party_name: 'test', party_id: slot, party_edited: true,
                character_ids: [1, null, null], unison_character_ids: [null, null, null],
                equipment_ids: [null, null, null], ability_soul_ids: [soul, null, null],
                options: { allow_other_players_to_heal_me: true },
            }],
        },
    })
    return { host, guest, room, clients, app, notify, start, edit }
}

test('HTTP-first start cannot bypass a restricted peer or allocate a partial battle', async t => {
    const x = await setup(t)
    parties.updatePlayerPartySync(x.guest.id, 1, savedParty(100013))
    const before = players.getPlayerSync(x.host.id)
    const denied = await x.start()
    assert.equal(denied.statusCode, 200)
    assert.equal(denied.json().data_headers.result_code, 4050)
    assert.equal(x.room.lifecycle.phase, 'LOBBY')
    assert.equal(x.room.lobby_generation, 0)
    assert.equal(active.getPlayerActiveQuestSync(x.host.id), null)
    assert.equal(active.getPlayerActiveQuestSync(x.guest.id), null)
    assert.equal(players.getPlayerSync(x.host.id).stamina, before.stamina)
    assert.equal(x.clients[1].isReady, false)
    assert.ok(x.clients.every(c => c.socket.frames.every(f => ![5, 6, 10].includes(f[1][0]))))

    parties.updatePlayerPartySync(x.guest.id, 1, savedParty())
    await x.notify(1, [3, [1]])
    const accepted = await x.start()
    assert.equal(accepted.json().data.play_id, `play-${x.host.id}`)
    const generation = x.room.lobby_generation
    await x.notify(0, [6])
    assert.equal(x.room.lobby_generation, generation, 'HTTP/TCP must share one generation')
    assert.ok(x.clients.every(c => c.socket.frames.filter(f => f[1][0] === 5).length === 1))
})

test('real party save blocks current gear, ignores other SETs/retries, and repairs without removing ownership', async t => {
    const x = await setup(t)
    assert.equal((await x.edit(100013)).json().data_headers.result_code, 1)
    assert.equal(x.clients[1].isReady, false)
    const firstBlock = x.clients[1].equipmentReadyBlock
    assert.ok(firstBlock)
    assert.equal((await x.edit(100013)).json().data_headers.result_code, 1)
    assert.equal(x.clients[1].equipmentReadyBlock, firstBlock, 'identical save is not user activity')
    await x.edit(100023, 2)
    assert.equal(x.clients[1].equipmentReadyBlock, firstBlock, 'other SET does not renew idle')
    assert.equal((await x.edit(null)).json().data_headers.result_code, 1)
    assert.equal(x.clients[1].equipmentReadyBlock, undefined)
    await x.notify(1, [3, [1]])
    assert.equal(x.clients[1].isReady, true)
    assert.equal(x.room.readyCountdownPending, true)
    assert.equal(equipment.hasRestrictedEquipment(x.room, x.clients[1]), false)
})

test('frozen selections tolerate later DB edits but reject a forged new request party', async t => {
    const x = await setup(t)
    await x.notify(0, [6])
    assert.equal(x.room.lifecycle.phase, 'BATTLE')
    parties.updatePlayerPartySync(x.guest.id, 1, savedParty(100013))
    const accepted = await x.start(x.guest)
    assert.equal(accepted.json().data.play_id, `play-${x.guest.id}`)
    const forged = await x.start(x.guest, {
        client_battle_party: { equipments: [{ equipment_id: 100013 }] },
    })
    assert.equal(forged.json().data_headers.result_code, 4050)
    const switched = await x.start(x.guest, { party_id: 2 })
    assert.equal(switched.json().data_headers.result_code, 4050)
})

test.after(() => {
    for (const timer of intervals) clearInterval(timer)
    if (db.open) db.close()
    fs.rmSync(directory, { recursive: true, force: true })
    try { fs.rmdirSync(parent) } catch {}
})
