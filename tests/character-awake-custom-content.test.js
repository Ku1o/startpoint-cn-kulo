const test = require("node:test")
const assert = require("node:assert/strict")

const definitionsExtension = require("../assets/mission_char_awake_cnmod.json")
const rewardsExtension = require("../assets/mission_char_awake_reward_cnmod.json")
const baseDefinitions = require("../assets/mission_char_awake.json")
const baseRewards = require("../assets/mission_char_awake_reward.json")
const awakeExtension = require("../assets/character_awake_extension.json")
const { getMissionMasterDefinition } = require("../out/lib/mission/master-data")
const { getAwakeMissionRewardStageDefinition } = require("../out/lib/mission/rewards")
const { getMissionIdsByCategory } = require("../out/lib/mission/stages")
const { getCharacterDataSync } = require("../out/lib/assets")

const CHARACTER_IDS = [151045, 151027, 151021, 151015, 251017, 251053, 151159, 261089, 131020]
const BOARD2_LINKS = {
    151045: [6],
    151027: [5],
    151021: [4, 5],
    251017: [6],
    251053: [4, 6],
    151159: [4, 5, 6],
    261089: [4, 5, 6],
}

test("九名角色的觉醒任务与奖励扩展不覆盖官方ID", () => {
    assert.equal(Object.keys(definitionsExtension).length, CHARACTER_IDS.length * 4)
    assert.equal(Object.keys(rewardsExtension).length, CHARACTER_IDS.length * 4)
    for (const key of Object.keys(definitionsExtension)) assert.equal(baseDefinitions[key], undefined)
    for (const key of Object.keys(rewardsExtension)) assert.equal(baseRewards[key], undefined)

    const categoryIds = new Set(getMissionIdsByCategory(9))
    for (const characterId of CHARACTER_IDS) {
        for (let suffix = 1; suffix <= 4; suffix++) {
            const missionId = characterId * 10 + suffix
            assert.ok(categoryIds.has(missionId))
            const definition = getMissionMasterDefinition(9, missionId)
            assert.ok(definition)
            assert.equal(definition.enableStart, "2020-01-01 00:00:00")
            assert.equal(definition.enableEnd, "2099-04-13 11:59:59")
            const reward = getAwakeMissionRewardStageDefinition(missionId, 1)
            assert.ok(reward)
            if (suffix === 4) {
                assert.deepEqual(reward.specialReward, {
                    characterId,
                    boardIndex: 1,
                    awakeLevel: 1,
                })
            }
        }
    }
})

test("二板觉醒联动只包含实际改动的能力槽", () => {
    assert.deepEqual(Object.keys(awakeExtension).map(Number).sort((a, b) => a - b),
        Object.keys(BOARD2_LINKS).map(Number).sort((a, b) => a - b))
    for (const [characterId, slots] of Object.entries(BOARD2_LINKS)) {
        assert.deepEqual(
            awakeExtension[characterId].linked_mana_node_slots.map(link => link.ability_slot),
            slots,
        )
        for (const link of awakeExtension[characterId].linked_mana_node_slots) {
            assert.equal(link.board_index, 2)
            assert.equal(link.awake_level, 1)
        }
    }
})

test("暗龙服务端身份继续保持五星", () => {
    assert.equal(getCharacterDataSync(261089).rarity, 5)
})
