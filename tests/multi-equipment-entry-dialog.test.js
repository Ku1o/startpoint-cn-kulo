const test = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

// Any incidental storage initialization must stay away from player saves.
process.env.DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'multi-entry-dialog-'))
const originalInterval = global.setInterval
global.setInterval = (...args) => { const timer = originalInterval(...args); timer.unref(); return timer }
const rooms = require('../out/multi/room/manager')
const { sessionManager: manager } = require('../out/multi/state/SessionManager')
const { embeddedMultiCoordinator: coordinator } = require('../out/multi/coordinator/embedded')
const mode15 = require('../out/lib/mode15-optional')
const players = require('../out/data/domains/player')
const { handleMessage } = require('../out/multi/tcp/lobby')
global.setInterval = originalInterval

class Socket extends EventEmitter {
    destroyed = false; writable = true; readable = true
    frames = []; endCalls = 0; destroyCalls = 0
    write(frame) { this.frames.push(JSON.parse(frame.replace(/\0$/, ''))); return true }
    end() { this.endCalls++; this.writable = false }
    destroy() { this.destroyCalls++; this.destroyed = true; this.emit('close') }
}

function setup(t, rejected = [], fantasy = false, count = 3) {
    const room = rooms.createRoom(101, 201, 1, 2, 1001, 0, 1)
    const clients = Array.from({ length: count }, (_, i) => {
        const socket = new Socket()
        const client = manager.createClient(socket, 101 + i, room.room_number, `cid-${i}`, 201 + i)
        client.roomGeneration = 0
        client.yourself = { viewerId: client.viewerId, playerId: client.playerId,
            connectionId: client.connectionId, currentPartyId: 1, state: [1], comId: 0 }
        const address = `${client.viewerId}@${room.room_number}`
        manager.clients.set(address, client)
        if (!manager.roomClients.has(room.room_number)) manager.roomClients.set(room.room_number, new Set())
        manager.roomClients.get(room.room_number).add(address)
        manager.socketClients.set(socket, client)
        rooms.addRoomMember(room.room_number, client.viewerId, client.playerId)
        return client
    })
    const roster = clients.map(c => c.yourself)
    for (const c of clients) c.mates = roster
    const lookups = []
    t.mock.method(players, 'getPlayerSync', () => ({ partySlot: 7 }))
    t.mock.method(mode15, 'isMode15Quest', () => fantasy)
    t.mock.method(mode15, 'getMode15ExclusiveGlobalPartyItemsSync', (playerId, category, slot) => {
        lookups.push({ playerId, category, slot })
        return rejected.includes(playerId) ? [5900001] : []
    })
    t.after(() => {
        if (rooms.getRoom(room.room_number)) manager.commitRoomDisband(room.room_number, 'test_cleanup')
        for (const c of clients) c.socket.destroy()
    })
    const start = async (sender = 0) => {
        handleMessage(clients[sender].socket, [0, [6]])
        await coordinator.enqueueRoomCommand(room.room_number, () => {})
    }
    return { room, clients, lookups, start }
}

for (const [name, rejected, count, sender] of [
    ['host rejected in three-player room', [201], 3, 0],
    ['guest rejected in three-player room', [202], 3, 0],
    ['guest sends StartBattle before host', [202], 3, 1],
    ['multiple restricted players', [201, 203], 3, 0],
    ['two-player room', [202], 2, 0],
]) {
    test(`${name}: all peers get entry dialog before any battle or FIN`, async t => {
        const x = setup(t, rejected, false, count)
        await x.start(sender)
        assert.equal(rooms.getRoom(x.room.room_number), undefined)
        assert.equal(x.room.lifecycle.phase, 'DISBANDED')
        assert.equal(manager.battleExpectedCount.has(x.room.room_number), false)
        assert.equal(manager.getClientsInRoom(x.room.room_number).length, 0)
        assert.ok(x.lookups.length >= count)
        assert.ok(x.lookups.every(q => q.category === 1 && q.slot === 7), 'persisted selected party overrides stale lobby slot')
        for (const c of x.clients) {
            assert.deepEqual(c.socket.frames, [[1, [6, 'quest_start_out_of_period_error']]])
            assert.equal(c.socket.endCalls, 0)
            assert.equal(c.socket.destroyCalls, 0)
            assert.equal(manager.isRetiredLobbySocket(c.socket), true)
        }
        // Queued StartBattle / Bye from the old room cannot create a battle
        // or cause a second response while clients process the dialog.
        await x.start(sender)
        handleMessage(x.clients[0].socket, [0, [1]])
        for (const c of x.clients) assert.equal(c.socket.frames.length, 1)
    })
}

for (const fantasy of [false, true]) {
    test(`${fantasy ? 'fantasy quest with exclusive gear' : 'ordinary quest with legal gear'} still starts`, async t => {
        const x = setup(t, fantasy ? [201, 202, 203] : [], fantasy)
        await x.start()
        assert.equal(x.room.lifecycle.phase, 'BATTLE')
        assert.equal(manager.battleExpectedCount.get(x.room.room_number), 3)
        for (const c of x.clients) {
            assert.equal(c.socket.frames.length, 1)
            assert.equal(c.socket.frames[0][1][0], 5)
            assert.equal(c.socket.frames[0][1][1].length, 3)
            assert.equal(c.socket.endCalls, 0)
        }
        if (fantasy) assert.deepEqual(x.lookups, [])
    })
}

test('ordinary room disband keeps its original message', t => {
    const x = setup(t)
    assert.equal(manager.commitRoomDisband(x.room.room_number, 'normal_disband'), true)
    for (const c of x.clients) assert.deepEqual(c.socket.frames, [[1, [6, 'multibattle_room_dismissed']]])
})
