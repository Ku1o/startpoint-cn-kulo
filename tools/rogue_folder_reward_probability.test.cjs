require("ts-node/register")

const assert = require("node:assert/strict")
const { shouldRollRogueFolderRandomReward } = require("../src/lib/quest/finish/rogue-drop-schedule.ts")

assert.equal(shouldRollRogueFolderRandomReward(undefined, () => 0.99), true)
assert.equal(shouldRollRogueFolderRandomReward(0.15, () => 0.149), true)
assert.equal(shouldRollRogueFolderRandomReward(0.15, () => 0.15), false)
assert.equal(shouldRollRogueFolderRandomReward(0.1, () => 0.11), false)
assert.equal(shouldRollRogueFolderRandomReward(1, () => 0.99), true)
assert.equal(shouldRollRogueFolderRandomReward(0, () => 0), false)

console.log("rogue folder reward probability checks passed")
