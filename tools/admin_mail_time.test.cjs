const assert = require("node:assert/strict")

const { buildAdminMailTimestamps } = require("../out/lib/admin-mail-time.js")

const timestamps = buildAdminMailTimestamps(new Date("2026-08-27T11:04:54.000Z"))
assert.deepEqual(timestamps, {
    databaseTime: "2026-08-27 11:04:54",
    chinaDisplayTime: "2026-08-27 19:04:54",
})

const nextDay = buildAdminMailTimestamps(new Date("2026-08-27T20:30:00.000Z"))
assert.deepEqual(nextDay, {
    databaseTime: "2026-08-27 20:30:00",
    chinaDisplayTime: "2026-08-28 04:30:00",
})

console.log("admin mail China-time formatting tests passed")
