const assert = require("node:assert/strict")
const { EventEmitter } = require("node:events")
const { SessionManager } = require("../out/multi/state/SessionManager.js")

class FakeSocket extends EventEmitter {
    constructor() {
        super()
        this.destroyed = false
        this.readable = true
        this.writable = true
        this.frames = []
    }
    write(frame) { this.frames.push(String(frame)); return true }
    end() { this.writable = false }
    destroy() {
        this.destroyed = true
        this.readable = false
        this.writable = false
    }
}

function client(manager, socket, connectionId) {
    const value = manager.createClient(socket, 101, "654321", connectionId, 201)
    value.enterData = {}
    value.roomGeneration = 3
    return value
}

const manager = new SessionManager()
process.env.MULTI_MAX_SUPERSEDED_CONNECTIONS_PER_VIEWER = "2"
const oldSocket = new FakeSocket()
const newSocket = new FakeSocket()
const oldClient = client(manager, oldSocket, "old")
const newClient = client(manager, newSocket, "new")
const abandonedBattleTimer = setTimeout(() => {}, 60_000)
manager.abandonedBattleTimers.set("654321", abandonedBattleTimer)

manager.addClientToRoom(oldClient)
manager.addClientToRoom(newClient)

assert.equal(oldClient.superseded, true)
assert.equal(oldSocket.destroyed, false, "superseding a lobby socket must not destroy it immediately")
assert.equal(manager.isSupersededSocket(oldSocket), true,
    "superseded sockets must be recognizable for benign late-message handling")
assert.equal(manager.findClientBySocket(oldSocket), undefined, "superseded sockets must stop producing room commands")
assert.equal(manager.findClientBySocket(newSocket), newClient)
assert.equal(newClient.connectionGeneration, oldClient.connectionGeneration + 1)
assert.equal(manager.abandonedBattleTimers.get("654321"), abandonedBattleTimer,
    "a lobby reconnect must not cancel the abandoned-battle watchdog")

manager.removeClient(oldClient)
assert.equal(manager.getClient(101, "654321"), newClient,
    "a late close from the superseded socket must not remove its replacement")

manager.broadcastToRoom("654321", [1, [2, "cid", [1]]], undefined, 3)
assert.equal(oldSocket.frames.length, 0, "superseded sockets must not receive new room broadcasts")
assert.equal(newSocket.frames.length, 1)

const thirdSocket = new FakeSocket()
const fourthSocket = new FakeSocket()
manager.addClientToRoom(client(manager, thirdSocket, "third"))
manager.addClientToRoom(client(manager, fourthSocket, "fourth"))
assert.equal(oldSocket.destroyed, true,
    "excess superseded sockets must be closed to bound reconnect resource usage")
assert.equal(newSocket.destroyed, false,
    "the configured quarantine capacity should retain the most recent stale sockets")

clearTimeout(abandonedBattleTimer)
console.log("multi room connection generation test passed")
process.exit(0)
