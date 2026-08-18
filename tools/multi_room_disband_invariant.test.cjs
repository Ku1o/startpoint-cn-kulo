const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const { EventEmitter } = require("node:events")
const { SessionManager } = require("../out/multi/state/SessionManager.js")
const { createRoom, getRoom } = require("../out/multi/room/manager.js")

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

const manager = new SessionManager()
const room = createRoom(101, 201, 1, 1, 2, 0, 1)
const socket = new FakeSocket()
const client = manager.createClient(socket, 101, room.room_number, "host", 201)
client.enterData = {}
client.roomGeneration = room.lobby_generation
manager.addClientToRoom(client)

assert.equal(manager.commitRoomDisband(room.room_number, "test_disband"), true)
assert.equal(getRoom(room.room_number), undefined,
    "room must be non-joinable before the dismissal frame is emitted")
assert.equal(socket.frames.some(frame => frame.includes("multibattle_room_dismissed")), true)

const productionFiles = [
    "src/multi/http/room.ts",
    "src/multi/tcp/lobby.ts",
    "src/multi/state/SessionManager.ts",
]
const occurrences = productionFiles.reduce((count, relative) => {
    const source = fs.readFileSync(path.join(__dirname, "..", relative), "utf8")
    return count + (source.match(/multibattle_room_dismissed/g) || []).length
}, 0)
assert.equal(occurrences, 1,
    "the room-dismissed UiString must only be emitted by the committed disband path")

console.log("multi room disband invariant test passed")
process.exit(0)
