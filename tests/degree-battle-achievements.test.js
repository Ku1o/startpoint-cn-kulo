const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-degree-battle-test-"))
process.env.DATA_DIR = temporaryDataDir

const { insertAccountSync } = require("../out/data/domains/account")
const { getDb } = require("../out/data/db")
const { insertDefaultPlayerSync, getPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const { getPlayerCategoryMissionsSync } = require("../out/data/domains/mission")
const { getGlobalPartyId } = require("../out/lib/special-event-parties")
const { recordBattleMissionDimensions } = require("../out/lib/mission/battle-dimensions")
const { recordMissionBattleFacts, buildBattleMissionSettlementScopes } = require("../out/lib/mission/battle-facts")
const { settleMissionCategories } = require("../out/lib/mission/settlement")

const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "leiting",
    idpId: "",
    status: "normal",
})
const player = insertDefaultPlayerSync(account.id)

function storedParty() {
    return getDb().prepare(`
        SELECT group_id, slot,
               character_id_1, character_id_2, character_id_3,
               unison_character_1, unison_character_2, unison_character_3,
               equipment_1, equipment_2, equipment_3
        FROM players_parties
        WHERE player_id = ? AND category = 1
        ORDER BY group_id, slot
        LIMIT 1
    `).get(player.id)
}

function battleParty(row) {
    const member = id => id === null ? null : { id }
    return {
        characters: [row.character_id_1, row.character_id_2, row.character_id_3].map(member),
        unison_characters: [
            row.unison_character_1,
            row.unison_character_2,
            row.unison_character_3,
        ].map(member),
        equipments: [row.equipment_1, row.equipment_2, row.equipment_3].map(member),
    }
}

test("a successful clear records party power and grants all reached power titles", () => {
    const row = storedParty()
    assert.ok(row)
    getDb().prepare(`
        UPDATE players_parties
        SET current_battle_power = 9000
        WHERE player_id = ? AND category = 1 AND group_id = ? AND slot = ?
    `).run(player.id, row.group_id, row.slot)
    const partySlot = getGlobalPartyId(row.group_id, row.slot)
    updatePlayerSync({ id: player.id, partySlot })

    const party = battleParty(row)
    const evaluationTime = new Date()
    const facts = recordMissionBattleFacts({
        playerId: player.id,
        questCategory: 1,
        questId: 1001001,
        questAccomplished: true,
        clearTime: 1000,
        clearRank: 5,
        party,
        partySlot,
        statistics: { clear_phase: 1, party },
        player: getPlayerSync(player.id),
        questPreviouslyCompleted: false,
        questProgress: null,
    }, evaluationTime)
    const degreeScope = buildBattleMissionSettlementScopes(facts)
        .find(scope => typeof scope !== "number" && scope.category === 5)
    assert.ok(degreeScope)
    settleMissionCategories(player.id, [degreeScope], evaluationTime)

    const progress = getPlayerCategoryMissionsSync(player.id, 5)
    assert.equal(progress["32000"].progress, 3000)
    assert.equal(progress["32010"].progress, 7500)
    assert.equal(progress["32020"].progress, 8500)
})

test("current decisive steam-robot quest ids grant the five matching titles", () => {
    const cases = [
        [1001001, 62330],
        [1004001, 62370],
        [1002001, 62410],
        [1005001, 62450],
        [1006001, 62530],
    ]
    for (const [questId] of cases) {
        recordBattleMissionDimensions({
            type: "battle_finish",
            playerId: player.id,
            questCategory: 26,
            questId,
            accomplished: true,
            mode: "multi",
            clearRank: 5,
            clearTimeMs: 1000,
            partyCharacterIds: [],
            unisonCharacterIds: [],
            statistics: {
                dashCount: 0,
                powerFlipCount: 0,
                powerFlipLv3Count: 0,
                skillCount: 0,
                maxComboCount: 0,
                maxSkillChainCount: 0,
                feverCount: 0,
                feverTimeMs: 0,
                weakenEnemyCount: 0,
                clearEnemyBuffCount: 0,
                clearSelfDebuffCount: 0,
                buffCompanionCount: 0,
                healCompanionCount: 0,
                emotionCount: 0,
                enemyKillCount: 0,
                weakPointDestroyCount: 0,
                coffinReduceCount: 0,
            },
        })
    }

    settleMissionCategories(player.id, [{
        category: 5,
        missionIds: cases.map(([, missionId]) => missionId),
    }], new Date())
    const progress = getPlayerCategoryMissionsSync(player.id, 5)
    for (const [, missionId] of cases) assert.equal(progress[String(missionId)].progress, 1)
})
