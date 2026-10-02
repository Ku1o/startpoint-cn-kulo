const assert = require("node:assert/strict")
const { EventEmitter } = require("node:events")

const {
    clearReliableSendState,
    getReliableSendQueueStats,
    sendFrameReliably,
} = require("../out/multi/tcp/reliable-send.js")
const {
    finishTcpDisconnect,
} = require("../out/multi/tcp/disconnect-diagnostics.js")

class FakeSocket extends EventEmitter {
    constructor(writeResults = []) {
        super()
        this.writeResults = [...writeResults]
        this.frames = []
        this.writable = true
        this.destroyed = false
    }

    write(frame) {
        if (this.destroyed) throw new Error("write after destroy")
        this.frames.push(frame)
        return this.writeResults.length > 0 ? this.writeResults.shift() : true
    }

    destroy() {
        if (this.destroyed) return
        this.destroyed = true
        this.writable = false
        this.emit("close")
    }
}

const slow = new FakeSocket([false, true])
const fast = new FakeSocket([true, true])

assert.equal(sendFrameReliably(slow, "one\0", { connectionId: "slow" }), "sent")
assert.equal(sendFrameReliably(slow, "two\0", { connectionId: "slow" }), "queued")
assert.deepEqual(getReliableSendQueueStats(slow), { messages: 1, bytes: 4, blocked: true })

assert.equal(sendFrameReliably(fast, "alpha\0", { connectionId: "fast" }), "sent")
assert.equal(sendFrameReliably(fast, "beta\0", { connectionId: "fast" }), "sent")
assert.deepEqual(fast.frames, ["alpha\0", "beta\0"])

slow.emit("drain")
assert.deepEqual(slow.frames, ["one\0", "two\0"])
assert.deepEqual(getReliableSendQueueStats(slow), { messages: 0, bytes: 0, blocked: false })

clearReliableSendState(slow)
clearReliableSendState(fast)

const saturated = new FakeSocket([false])
assert.equal(sendFrameReliably(saturated, "head\0", { connectionId: "saturated" }), "sent")
for (let index = 0; index < 512; index++) {
    assert.equal(
        sendFrameReliably(saturated, `queued-${index}\0`, { connectionId: "saturated" }),
        "queued",
    )
}
assert.equal(getReliableSendQueueStats(saturated).messages, 512)
assert.equal(
    sendFrameReliably(saturated, "overflow\0", { connectionId: "saturated" }),
    "closed",
)
assert.equal(saturated.destroyed, true)
assert.equal(finishTcpDisconnect(saturated, false), "send_queue_limit")
assert.deepEqual(saturated.frames, ["head\0"], "write(false) already accepted the head frame")

console.log("multi_chain_reliable_send.test: ok")
