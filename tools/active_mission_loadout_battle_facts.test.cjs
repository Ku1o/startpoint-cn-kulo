require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const {
    collectActiveMissionLoadoutBattleFacts,
    getCharacterCapabilityCategories,
    hasDirectHealCapability,
    hasEnemyElementResistanceDownCapability,
    hasRegenerationCapability,
} = require("../src/lib/mission/active-loadout-battle-facts")
const { getActiveMissionMasterDefinition } = require("../src/lib/mission/active-master-data")
const { computeActiveMissionFactProgress } = require("../src/lib/mission/active-reconciliation")
const { getBattleActiveMissionPatterns } = require("../src/lib/mission/battle-facts")

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

function ignoredCapabilityDefinition(missionId, category, ignoredCharacterStringId) {
    const definition = capabilityDefinition(missionId, category)
    definition.row[72] = ignoredCharacterStringId
    return definition
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
const resistanceDownMasterDefinition = getActiveMissionMasterDefinition(20015)
assert.equal(resistanceDownMasterDefinition.row[29], "90")
assert.equal(resistanceDownMasterDefinition.row[71], "ACToleranceOfElement_Down")
const healingMasterDefinition = getActiveMissionMasterDefinition(20016)
assert.equal(healingMasterDefinition.row[29], "90")
assert.equal(healingMasterDefinition.row[71], "CreateNormalHeal,CreateRatioHeal,ACRegeneration")
assert.equal(healingMasterDefinition.row[72], "compliment_oiran")
const fullSkillStartMasterDefinition = getActiveMissionMasterDefinition(20017)
assert.equal(fullSkillStartMasterDefinition.row[29], "91")
assert.equal(fullSkillStartMasterDefinition.row[32], "3")
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

const characterText = require("../assets/cdndata/character_text.json")
assert.equal(hasDirectHealCapability(characterText[151027]), true)
assert.equal(hasRegenerationCapability(characterText[161069]), true)
assert.equal(hasDirectHealCapability(characterText[161039]), false, "回复无效不属于治疗能力")
assert.equal(hasRegenerationCapability(characterText[161039]), false)
assert.equal(getCharacterCapabilityCategories(151027).has("CreateNormalHeal"), true)
assert.equal(getCharacterCapabilityCategories(151027).has("CreateRatioHeal"), true)
assert.equal(getCharacterCapabilityCategories(161069).has("ACRegeneration"), true)
assert.equal(getCharacterCapabilityCategories(161039).size, 0)

assert.deepEqual(collectActiveMissionLoadoutBattleFacts([healingMasterDefinition], {
    questAccomplished: true,
    isMulti: false,
    questCategory: 1,
    questId: 1001001,
    partyCharacterIds: [161069],
}, {
    "161069": {
        stringId: "blackflower_wiz",
        abilityCategories: new Set(["ACRegeneration"]),
    },
}), [{ missionId: 20016 }])
assert.deepEqual(collectActiveMissionLoadoutBattleFacts([
    ignoredCapabilityDefinition(20016, "CreateRatioHeal", "compliment_oiran"),
], {
    questAccomplished: true,
    isMulti: false,
    questCategory: 1,
    questId: 1001001,
    partyCharacterIds: [111006],
}, {
    "111006": {
        stringId: "compliment_oiran",
        abilityCategories: new Set(["CreateRatioHeal", "ACRegeneration"]),
    },
}), [])

assert.deepEqual(collectActiveMissionLoadoutBattleFacts([fullSkillStartMasterDefinition], {
    questAccomplished: true,
    isMulti: false,
    questCategory: 1,
    questId: 1001001,
    partyCharacterIds: [],
    zones: [{ skill_point_over_on_start: 1 }, { skill_point_over_on_start: 2 }],
}, {}), [{ missionId: 20017 }])
for (const zones of [
    undefined,
    [],
    [{ skill_point_over_on_start: 2 }],
    [{ skill_point_over_on_start: 4 }],
    [{ skill_point_over_on_start: 2 }, { skill_point_over_on_start: 2 }],
    [{ skill_point_over_on_start: -1 }, { skill_point_over_on_start: 4 }],
    [{ skill_point_over_on_start: 1.5 }, { skill_point_over_on_start: 1.5 }],
    [{}],
]) {
    assert.deepEqual(collectActiveMissionLoadoutBattleFacts([fullSkillStartMasterDefinition], {
        questAccomplished: true,
        isMulti: false,
        questCategory: 1,
        questId: 1001001,
        partyCharacterIds: [],
        zones,
    }, {}), [])
}
assert.deepEqual(collectActiveMissionLoadoutBattleFacts([fullSkillStartMasterDefinition], {
    questAccomplished: false,
    isMulti: false,
    questCategory: 1,
    questId: 1001001,
    partyCharacterIds: [],
    zones: [{ skill_point_over_on_start: 3 }],
}, {}), [])

assert.equal(computeActiveMissionFactProgress(90, resistanceDownMasterDefinition.row, {
    characters: {},
    loadoutBattleFacts: { "20015": 5 },
}, 20015), 5)
assert.equal(getBattleActiveMissionPatterns(1).includes(90), true)
assert.equal(computeActiveMissionFactProgress(91, fullSkillStartMasterDefinition.row, {
    characters: {},
    loadoutBattleFacts: { "20017": 1 },
}, 20017), 1)
assert.equal(getBattleActiveMissionPatterns(1).includes(91), true)

console.log("active mission loadout battle fact tests passed")
