const test = require("node:test")
const assert = require("node:assert/strict")

const {
    RoomAdmissionRegistry,
    drainRoomAdmissionPerformanceSummary,
} = require("../out/multi/room/admission")

test("claimed admission returns to the reservation when TCP closes before Enter", () => {
    const registry = new RoomAdmissionRegistry(15_000)
    assert.equal(registry.reserve("100001", 4, 20, [10], 3, 1_000), true)
    assert.deepEqual(registry.claim("100001", 4, 20, "connection-a", 1_100), {
        ok: true,
        kind: "claimed",
    })
    assert.equal(registry.releaseClaim("100001", 4, 20, "connection-a", 1_200), true)
    assert.deepEqual(registry.claim("100001", 4, 20, "connection-b", 1_300), {
        ok: true,
        kind: "claimed",
    })
    assert.equal(registry.commit("100001", 4, 20, "connection-b"), true)
    assert.equal(registry.getOccupancy("100001", 4, [10], 1_400), 1)
})

test("a replacement TCP connection owns the claim and the old socket cannot release it", () => {
    const registry = new RoomAdmissionRegistry(15_000)
    assert.equal(registry.reserve("100002", 8, 30, [10], 3, 2_000), true)
    assert.equal(registry.claim("100002", 8, 30, "old", 2_100).ok, true)
    assert.deepEqual(registry.claim("100002", 8, 30, "replacement", 2_200), {
        ok: true,
        kind: "reclaimed",
    })
    assert.equal(registry.releaseClaim("100002", 8, 30, "old", 2_300), false)
    assert.equal(registry.commit("100002", 8, 30, "replacement"), true)
})

test("a repeated HTTP selection cannot steal a live TCP claim", () => {
    const registry = new RoomAdmissionRegistry(15_000)
    assert.equal(registry.reserve("100006", 5, 30, [10], 3, 7_000), true)
    assert.equal(registry.claim("100006", 5, 30, "current", 7_100).ok, true)
    assert.equal(registry.reserve("100006", 5, 30, [10], 3, 7_200), true)
    assert.equal(registry.releaseClaim("100006", 5, 30, "other", 7_300), false)
    assert.equal(registry.commit("100006", 5, 30, "current"), true)
})

test("capacity counts reservations and claims without double-counting viewers", () => {
    const registry = new RoomAdmissionRegistry(15_000)
    assert.equal(registry.reserve("100003", 1, 20, [10], 3, 3_000), true)
    assert.equal(registry.claim("100003", 1, 20, "a", 3_100).ok, true)
    assert.equal(registry.reserve("100003", 1, 30, [10, 20], 3, 3_200), true)
    assert.equal(registry.getOccupancy("100003", 1, [10, 20], 3_300), 3)
    assert.equal(registry.reserve("100003", 1, 40, [10, 20], 3, 3_400), false)
})

test("expired and previous-generation reservations are never claimed", () => {
    const registry = new RoomAdmissionRegistry(1_000)
    assert.equal(registry.reserve("100004", 2, 20, [10], 3, 4_000), true)
    assert.deepEqual(registry.claim("100004", 2, 20, "late", 5_001), {
        ok: false,
        reason: "expired",
    })

    assert.equal(registry.reserve("100005", 2, 20, [10], 3, 6_000), true)
    assert.deepEqual(registry.claim("100005", 3, 20, "stale", 6_100), {
        ok: false,
        reason: "generation_mismatch",
    })
})

test("admission diagnostics are aggregated instead of logged per success", () => {
    const summary = drainRoomAdmissionPerformanceSummary()
    assert.match(summary, /reserve=/)
    assert.match(summary, /claim=/)
    assert.match(summary, /select_to_tcp\{n=/)
    assert.equal(drainRoomAdmissionPerformanceSummary(), "none")
})
