require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const {
    collectActiveMissionLoadoutBattleFacts,
    hasEnemyElementResistanceDownCapability,
} = require("../src/lib/mission/active-loadout-battle-facts")

function definition(missionId, characterElement, equipmentElement = "(None)", battleKind = 3) {
    const row = []
    row[29] = "89"
    row[32] = String(battleKind)
    row[34] = "(None)"
    row[69] = String(characterElement)
    row[70] = equipmentElement
    return { missionId, row }
}

function capabilityDefinition(missionId, category, battleKind = 3) {
    const row = []
    row[29] = "90"
    row[32] = String(battleKind)
    row[34] = "(None)"
    row[71] = category
    return { missionId, row }
}

const elementDefinitions = [
    definition(20011, 1),
    definition(20012, 1, "1"),
]
assert.deepEqual(collectActiveMissionLoadoutBattleFacts(elementDefinitions, {
    questAccomplished: true,
    isMulti: false,
    questCategory: 1,
    questId: 1001001,
    partyCharacterIds: [1],
    equipmentElements: [0],
}, {
    "1": { element: 0 },
}), [{ missionId: 20011 }, { missionId: 20012 }])

const resistanceDownDefinition = capabilityDefinition(20015, "ACToleranceOfElement_Down")
assert.deepEqual(collectActiveMissionLoadoutBattleFacts([resistanceDownDefinition], {
    questAccomplished: true,
    isMulti: false,
    questCategory: 1,
    questId: 1001001,
    partyCharacterIds: [10, 11],
}, {
    "10": { abilityCategories: new Set() },
    "11": { abilityCategories: new Set(["ACToleranceOfElement_Down"]) },
}), [{ missionId: 20015 }])

assert.deepEqual(collectActiveMissionLoadoutBattleFacts([resistanceDownDefinition], {
    questAccomplished: true,
    isMulti: false,
    questCategory: 1,
    questId: 1001001,
    partyCharacterIds: [10],
}, {
    "10": { abilityCategories: new Set() },
}), [])

assert.equal(hasEnemyElementResistanceDownCapability([
    "对敌人造成火属性伤害＋火属性抗性降低",
]), true)
assert.equal(hasEnemyElementResistanceDownCapability([
    "赋予队伍全体攻击力提升＋全属性抗性降低效果",
]), false)

console.log("active mission loadout battle fact tests passed")
