const assert = require("node:assert/strict")

const { selectStableNpcSlots } = require("../out/multi/npc/controller.js")

const candidates = [
    { viewer_id: 900000002, com_id: 2 },
    { viewer_id: 900000001, com_id: 1 },
]

assert.deepEqual(
    selectStableNpcSlots(candidates, 2).map(mate => mate.com_id),
    [1, 2],
    "one-real/two-COM rooms should use both stable COM slots",
)
assert.deepEqual(
    selectStableNpcSlots(candidates, 1).map(mate => mate.com_id),
    [2],
    "two-real/one-COM rooms should preserve the surviving tail slot COM2",
)
assert.deepEqual(selectStableNpcSlots(candidates, 0), [])
assert.deepEqual(candidates.map(mate => mate.com_id), [2, 1], "selection must not mutate provider data")

console.log("multi_npc_slot_stability.test: ok")
