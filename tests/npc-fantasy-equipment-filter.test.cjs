const assert = require("node:assert/strict")
const test = require("node:test")

const {
    isNpcPartyAllowedInRoom,
} = require("../out/multi/npc/equipment-policy")
const { buildNpcMates } = require("../out/multi/npc/builder")
const { NPC_TEMPLATES } = require("../out/multi/npc/types")

test("ordinary rooms reject encoded AI parties carrying Fantasy equipment", () => {
    const source = {
        characters: [[0, { id: 111001 }]],
        equipments: [
            [0, { equipmentId: 100013, level: 5 }],
            [0, { equipmentId: 300101, level: 5 }],
            [1],
        ],
        abilitySoulIds: [[0, 100023], [0, 300201], [1]],
        marker: "player-history",
    }
    assert.equal(isNpcPartyAllowedInRoom(2, 1099001, source), false)
    assert.equal(source.equipments[0][0], 0)
    assert.deepEqual(source.abilitySoulIds[0], [0, 100023])
})

test("ordinary rooms reject plain AI item fields containing Fantasy equipment", () => {
    const source = {
        equipmentIds: [100020, 400101, null],
        equipment_ids: [400102, 100021, null],
        ability_soul_ids: [100022, 400103, null],
    }
    assert.equal(isNpcPartyAllowedInRoom(1, 1001001, source), false)
    assert.deepEqual(source.equipmentIds, [100020, 400101, null])
})

test("ordinary rooms accept a complete legal AI party unchanged", () => {
    const source = {
        equipments: [[0, { equipmentId: 300101 }], [1], [1]],
        abilitySoulIds: [[0, 300201], [1], [1]],
    }
    assert.equal(isNpcPartyAllowedInRoom(2, 1099001, source), true)
    assert.deepEqual(source.equipments[0], [0, { equipmentId: 300101 }])
})

for (const [category, questId] of [
    [7, 300098001],
    [7, 300098002],
    [7, 300098003],
]) {
    test(`Fantasy room ${questId} keeps AI Fantasy equipment`, () => {
        const source = {
            equipments: [[0, { equipmentId: 100013 }]],
            abilitySoulIds: [[0, 100023]],
        }
        assert.equal(isNpcPartyAllowedInRoom(category, questId, source), true)
    })
}

test("unknown room context rejects server-owned AI Fantasy equipment", () => {
    const source = {
        equipments: [[0, { equipmentId: 100013 }]],
        abilitySoulIds: [[0, 100023]],
    }
    assert.equal(isNpcPartyAllowedInRoom(undefined, undefined, source), false)
})

test("fixed AI templates are rejected as whole parties outside Fantasy", () => {
    const originalEquipment = NPC_TEMPLATES[0].equipments
    const originalSouls = NPC_TEMPLATES[0].ability_soul_ids
    try {
        NPC_TEMPLATES[0].equipments = [100013, 300101]
        NPC_TEMPLATES[0].ability_soul_ids = [100023, 300201]

        const ordinary = buildNpcMates(1099001, 2)
        assert.equal(ordinary.mate1, null)

        const fantasy = buildNpcMates(300098003, 7).mate1.party
        assert.equal(fantasy.equipments[0].equipment_id, 100013)
        assert.equal(fantasy.ability_soul_ids[0], 100023)
    } finally {
        NPC_TEMPLATES[0].equipments = originalEquipment
        NPC_TEMPLATES[0].ability_soul_ids = originalSouls
    }
})
