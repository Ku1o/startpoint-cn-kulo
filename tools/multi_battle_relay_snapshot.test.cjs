const assert = require("node:assert/strict")
const { EventEmitter } = require("node:events")

const { sessionManager } = require("../out/multi/state/SessionManager.js")
const { relayToBattleRoom } = require("../out/multi/tcp/relay.js")
const { clearReliableSendState } = require("../out/multi/tcp/reliable-send.js")

class FakeSocket extends EventEmitter {
    constructor() {
        super()
        this.frames = []
        this.writable = true
        this.destroyed = false
    }
    write(frame) { this.frames.push(frame); return true }
    destroy() { this.destroyed = true; this.writable = false; this.emit("close") }
}

function makeClient(connectionId, generation) {
    return {
        connectionId,
        roomNumber: "765432",
        roomGeneration: generation,
        viewerId: Number(connectionId.replace(/\D/g, "")) || 1,
        isBattle: true,
        socket: new FakeSocket(),
    }
}

const source = makeClient("c1", 7)
const current = makeClient("c2", 7)
const oldGeneration = makeClient("c3", 6)
const detachedReplacement = makeClient("c4", 7)

sessionManager.battleClients.set(source.roomNumber,
    new Set([source.connectionId, current.connectionId, oldGeneration.connectionId, detachedReplacement.connectionId]))
sessionManager.cidToBattleClient.set(source.connectionId, source)
sessionManager.cidToBattleClient.set(current.connectionId, current)
sessionManager.cidToBattleClient.set(oldGeneration.connectionId, oldGeneration)
// Simulate a replaced connection: the set still briefly has c4 but the current
// connection map points somewhere else, so it must not receive this fan-out.
sessionManager.cidToBattleClient.set(detachedReplacement.connectionId, makeClient("c4", 8))

let serializationCalls = 0
const payload = [2, source.connectionId, [{
    toJSON() {
        serializationCalls += 1
        return 99
    },
}]]

relayToBattleRoom(source, payload, "broadcast", 1)

assert.equal(source.socket.frames.length, 0)
assert.equal(current.socket.frames.length, 1)
assert.equal(oldGeneration.socket.frames.length, 0)
assert.equal(detachedReplacement.socket.frames.length, 0)
assert.deepEqual(JSON.parse(current.socket.frames[0].slice(0, -1)), [2, source.connectionId, [99]])
assert.equal(serializationCalls, 1, "one logical relay should serialize its payload once")

for (const client of [source, current, oldGeneration, detachedReplacement]) {
    clearReliableSendState(client.socket)
}
sessionManager.battleClients.delete(source.roomNumber)
for (const id of ["c1", "c2", "c3", "c4"]) sessionManager.cidToBattleClient.delete(id)
console.log("multi_battle_relay_snapshot.test: ok")
