require("ts-node/register");

const assert = require("node:assert/strict");

const { resolveRogueRoundDrops } = require("../src/lib/quest/finish/rogue-drop-schedule.ts");
const config = require("../assets/rogue_event.json").events["700099"];
const folderRewards = require("../assets/rush_event_quest_folder.json")["700099"]["1"];
const tokenId = 2370099;

function tokenCount(round) {
  return resolveRogueRoundDrops(config, round)
    .filter((drop) => drop.type === "item" && Number(drop.id) === tokenId)
    .reduce((sum, drop) => sum + Number(drop.count), 0);
}

assert.equal(tokenCount(0), 0, "endless mode must not grant Deep Abyss tokens");
assert.equal(tokenCount(1), 1);
assert.equal(tokenCount(2), 5);
assert.equal(tokenCount(20), 5);
assert.equal(tokenCount(21), 6);
assert.equal(tokenCount(29), 6);
assert.equal(tokenCount(30), 0, "floor 30 uses only the folder-clear reward");

const floors2To29 = Array.from({ length: 28 }, (_, index) => tokenCount(index + 2));
assert.equal(floors2To29.reduce((sum, count) => sum + count, 0), 149);
const fixedReward = (id) => folderRewards.find((reward) => Number(reward.id) === id);
assert.equal(fixedReward(99)?.count, 1500, "Dream Emblems use the unified 1500 display/grant count");
assert.equal(fixedReward(tokenId)?.count, 50, "floor 30 fixed token reward is 50");
assert.equal(fixedReward(11003)?.count, 2, "the existing star fragment reward is preserved");
assert.equal(tokenCount(1) + floors2To29.reduce((sum, count) => sum + count, 0) + fixedReward(tokenId).count, 200);

console.log("rogue round drop schedule checks passed");
