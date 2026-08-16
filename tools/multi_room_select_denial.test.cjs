require("ts-node/register")

const assert = require("node:assert/strict")
const {
    SELECT_ROOM_BATTLE_STATE,
    SELECT_ROOM_DISBANDED_STATE,
    SELECT_ROOM_FILLED_STATE,
    getSelectRoomDenialRaisingState,
} = require("../src/multi/room/select-denial.ts")

assert.equal(
    getSelectRoomDenialRaisingState({ battleStarted: false, roomFull: true }),
    SELECT_ROOM_FILLED_STATE,
    "a full room must use the client's Filled dialog instead of Disbanded",
)
assert.equal(
    getSelectRoomDenialRaisingState({ battleStarted: true, roomFull: false }),
    SELECT_ROOM_BATTLE_STATE,
    "a room already in battle must use the client's Battle dialog",
)
assert.equal(
    getSelectRoomDenialRaisingState({ battleStarted: true, roomFull: true }),
    SELECT_ROOM_BATTLE_STATE,
    "battle state is more specific when capacity and battle checks overlap",
)
assert.equal(
    getSelectRoomDenialRaisingState({ battleStarted: false, roomFull: false }),
    SELECT_ROOM_DISBANDED_STATE,
    "missing and unrelated unavailable rooms keep the existing fallback",
)

console.log("multi_room_select_denial tests passed")
