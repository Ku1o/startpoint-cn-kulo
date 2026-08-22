const test = require("node:test")
const assert = require("node:assert/strict")
const Module = require("node:module")
const { EventEmitter } = require("node:events")

const { SessionManager } = require("../out/multi/state/SessionManager")

class FakeSocket extends EventEmitter {
    constructor(name) {
        super()
        this.name = name
        this.destroyed = false
        this.readable = true
        this.writable = true
        this.endCalls = 0
        this.destroyCalls = 0
    }

    end() {
        this.endCalls += 1
        this.writable = false
    }

    destroy() {
        this.destroyCalls += 1
        this.destroyed = true
        this.readable = false
        this.writable = false
    }
}

test("room disband sends the meeting frame only to lobby sockets", t => {
    const manager = new SessionManager()
    const roomNumber = "654321"
    const viewerId = 101
    const lobbySocket = new FakeSocket("lobby")
    const battleSocket = new FakeSocket("battle")
    const lobbyClient = manager.createClient(
        lobbySocket,
        viewerId,
        roomNumber,
        "lobby-connection",
        201,
    )
    const battleClient = manager.createClient(
        battleSocket,
        viewerId,
        roomNumber,
        "battle-connection",
        201,
    )
    lobbyClient.roomGeneration = 1
    battleClient.roomGeneration = 1
    battleClient.isBattle = true

    const lobbyAddress = `${viewerId}@${roomNumber}`
    manager.clients.set(lobbyAddress, lobbyClient)
    manager.roomClients.set(roomNumber, new Set([lobbyAddress]))
    manager.battleClients.set(roomNumber, new Set([battleClient.connectionId]))
    manager.cidToBattleClient.set(battleClient.connectionId, battleClient)
    manager.socketClients.set(lobbySocket, lobbyClient)
    manager.socketClients.set(battleSocket, battleClient)

    const sent = []
    manager.sendJson = (socket, data, context) => {
        sent.push({ socket, data, context })
        return "sent"
    }

    let disbandCall = null
    const originalLoad = Module._load
    Module._load = function (request, parent, isMain) {
        if (request === "../room/manager"
            && parent?.filename.endsWith("SessionManager.js")) {
            return {
                disbandRoom(actualRoomNumber, reason) {
                    disbandCall = { roomNumber: actualRoomNumber, reason }
                    return true
                },
            }
        }
        return originalLoad.call(this, request, parent, isMain)
    }
    t.after(() => {
        Module._load = originalLoad
    })

    assert.equal(manager.commitRoomDisband(roomNumber, "test_disband"), true)
    assert.deepEqual(disbandCall, { roomNumber, reason: "test_disband" })
    assert.equal(sent.length, 1)
    assert.equal(sent[0].socket, lobbySocket)
    assert.deepEqual(sent[0].data, [1, [6, "multibattle_room_dismissed"]])
    assert.equal(sent[0].context.channel, "room_disband")

    assert.equal(lobbySocket.endCalls, 1)
    assert.equal(battleSocket.endCalls, 1)
    assert.equal(manager.getClientsInRoom(roomNumber).length, 0)
    assert.equal(manager.battleClients.has(roomNumber), false)
    assert.equal(manager.cidToBattleClient.has(battleClient.connectionId), false)
})
