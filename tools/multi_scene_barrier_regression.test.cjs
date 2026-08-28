const assert = require("node:assert/strict")
const { EventEmitter } = require("node:events")
const { SessionManager } = require("../out/multi/state/SessionManager")

class FakeSocket extends EventEmitter {
    constructor() {
        super()
        this.destroyed = false
        this.writable = true
        this.readable = true
        this.writes = []
    }
    write(value) { this.writes.push(String(value)); return true }
    end() { this.destroy() }
    destroy() {
        if (this.destroyed) return
        this.destroyed = true
        this.writable = false
        this.readable = false
        this.emit("close")
    }
}

function client(manager, viewerId, room, connectionId, battle = false) {
    const value = manager.createClient(new FakeSocket(), viewerId, room, connectionId, viewerId)
    value.isBattle = battle
    return value
}

const manager = new SessionManager()
const hostLobby = client(manager, 101, "123456", "host-cid")
const guestLobby = client(manager, 202, "123456", "guest-cid")
manager.addClientToRoom(hostLobby)
manager.addClientToRoom(guestLobby)

assert.equal(manager.getRoomClientByConnectionId("123456", "host-cid"), hostLobby)
assert.equal(manager.getRoomClientByConnectionId("123456", "guest-cid"), guestLobby)

const hostBattle = client(manager, 101, "123456", "host-cid", true)
const guestBattle = client(manager, 202, "123456", "guest-cid", true)
manager.addBattleClient(hostBattle.connectionId, hostBattle)
manager.addBattleClient(guestBattle.connectionId, guestBattle)
assert.equal(manager.battleClients.get("123456").size, 2, "host and guest must not replace each other")
assert.equal(hostBattle.socket.destroyed, false)

manager.setBattleExpectedCount("123456", 2)
assert.equal(manager.markSceneReady(hostBattle.connectionId, "123456"), false)
manager.removeClient(guestBattle)
assert.equal(manager.battleExpectedCount.get("123456"), 2, "two-player loading must not fall back to solo")
assert.equal(hostBattle.socket.writes.some(line => line.includes('[0,"guest-cid"]')), false,
    "loading disconnect must not publish a teammate Leave packet")

const unknownManager = new SessionManager()
const unknownA = client(unknownManager, 0, "654321", "a", true)
const unknownB = client(unknownManager, 0, "654321", "b", true)
unknownManager.addBattleClient("a", unknownA)
unknownManager.addBattleClient("b", unknownB)
assert.equal(unknownManager.battleClients.get("654321").size, 2,
    "unknown viewerId=0 sockets must never be deduplicated as one player")

const reconnectManager = new SessionManager()
const oldBattle = client(reconnectManager, 303, "777777", "same-cid", true)
const newBattle = client(reconnectManager, 303, "777777", "same-cid", true)
reconnectManager.addBattleClient("same-cid", oldBattle)
reconnectManager.addBattleClient("same-cid", newBattle)
reconnectManager.removeClient(oldBattle)
assert.equal(reconnectManager.getBattleClient("same-cid"), newBattle,
    "late close from a superseded socket must not delete its replacement")

const trioManager = new SessionManager()
const trioA = client(trioManager, 401, "888888", "trio-a", true)
const trioB = client(trioManager, 402, "888888", "trio-b", true)
const trioC = client(trioManager, 403, "888888", "trio-c", true)
trioManager.addBattleClient(trioA.connectionId, trioA)
trioManager.addBattleClient(trioB.connectionId, trioB)
trioManager.addBattleClient(trioC.connectionId, trioC)
trioManager.setBattleExpectedCount("888888", 3)

assert.equal(trioManager.markSceneReady(trioA.connectionId, "888888"), false)
assert.equal(trioManager.battleConnectionPhase.get(trioA.connectionId), "ready",
    "SceneReady must not activate one player before the room barrier releases")
trioManager.removeClient(trioA)
assert.deepEqual(trioB.socket.writes, [], "a pre-start disconnect must remain deferred")
assert.deepEqual(trioC.socket.writes, [], "all survivors must remain on the same loading barrier")
assert.equal(trioManager.battleExpectedCount.get("888888"), 2,
    "a three-player barrier may fall back to the two surviving real players")

assert.equal(trioManager.markSceneReady(trioB.connectionId, "888888"), false)
assert.equal(trioManager.markSceneReady(trioC.connectionId, "888888"), true)
for (const survivor of [trioB, trioC]) {
    assert.deepEqual(survivor.socket.writes, [
        '[1,[1]]\0',
        '[1,[0,"trio-a"]]\0',
    ], "survivors must receive BattleStart before the deferred AI takeover")
    assert.equal(trioManager.battleConnectionPhase.get(survivor.connectionId), "active")
}

trioB.socket.writes.length = 0
trioManager.removeClient(trioC)
assert.deepEqual(trioB.socket.writes, ['[1,[0,"trio-c"]]\0'],
    "an active-scene disconnect must still publish Leave immediately")

console.log("multi scene barrier regression: ok")
process.exit(0)
