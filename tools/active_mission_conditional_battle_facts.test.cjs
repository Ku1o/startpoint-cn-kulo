require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const {
    collectActiveMissionConditionalBattleFacts,
    hasCompletedSecondManaBoardAbilities,
} = require("../src/lib/mission/active-conditional-battle-facts")
const { getCharacterManaNodesSync } = require("../src/lib/assets")
const { getActiveMissionMasterDefinition } = require("../src/lib/mission/active-master-data")

const characterId = 121033
const secondBoard = getCharacterManaNodesSync(characterId, 2)
assert.ok(secondBoard, "无情武神谢胧应当存在第二玛纳板")

const abilityNodeIds = Object.entries(secondBoard)
    .filter(([, node]) => ["4", "5", "6"].includes(node.field6))
    .map(([nodeId]) => Number(nodeId))
assert.equal(abilityNodeIds.length, 18)
assert.equal(hasCompletedSecondManaBoardAbilities(secondBoard, abilityNodeIds), true)
assert.equal(hasCompletedSecondManaBoardAbilities(secondBoard, abilityNodeIds.slice(0, -1)), false)

const mission = getActiveMissionMasterDefinition(20007)
assert.equal(mission.row[29], "71")
assert.equal(mission.row[32], "2")
assert.equal(mission.row[43], String(characterId))
assert.deepEqual(collectActiveMissionConditionalBattleFacts([mission], {
    questAccomplished: true,
    isMulti: true,
    questCategory: 2,
    questId: 1023001,
    partyCharacterIds: [characterId],
}, {
    [characterId]: {
        level: 100,
        secondBoardAbilitiesComplete: hasCompletedSecondManaBoardAbilities(secondBoard, abilityNodeIds),
    },
}), [{ pattern: 71, characterId }])

console.log("active mission conditional battle fact tests passed")
