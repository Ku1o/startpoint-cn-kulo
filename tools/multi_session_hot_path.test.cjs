const assert = require("node:assert/strict")
const { EventEmitter } = require("node:events")

const { SessionManager } = require("../out/multi/state/SessionManager.js")

class FakeSocket extends EventEmitter {
    constructor() {
        super()
        this.writable = true
        this.readable = true
        this.destroyed = false
        this.frames = []
    }

    write(frame) {
        this.frames.push(frame)
        return true
    }

    destroy() {
        if (this.destroyed) return
        this.destroyed = true
        this.writable = false
        this.readable = false
        this.emit("close")
    }
}

const manager = new SessionManager()
const socket = new FakeSocket()
const client = manager.createClient(socket, 81001, "654321", "hot-path-c1", 91001)
client.isBattle = true
client.roomGeneration = 4

manager.addBattleClient(client.connectionId, client)
assert.equal(manager.findClientBySocket(socket), client, "socket lookup should resolve the indexed battle client")

manager.setBattleExpectedCount(client.roomNumber, 1)
assert.equal(manager.markSceneReady(client.connectionId, client.roomNumber), true)
const activeTimer = manager.battleHeartbeatTimers.get(client.connectionId)
assert.ok(activeTimer, "SceneReady should arm one active heartbeat timer")

manager.noteBattleActivity(client.connectionId)
manager.noteBattleActivity(client.connectionId)
assert.equal(
    manager.battleHeartbeatTimers.get(client.connectionId),
    activeTimer,
    "battle traffic should refresh only the timestamp, not recreate the timer",
)

manager.removeBattleClient(client.connectionId)
assert.equal(manager.findClientBySocket(socket), undefined, "removing a battle client should clear its socket index")

console.log("multi_session_hot_path.test: ok")
process.exit(0)
