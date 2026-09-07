const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-quest-recommend-test-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, getPlayerSync } = require("../out/data/domains/player")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { insertPlayerQuestProgressSync } = require("../out/data/domains/quest")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const questRoutes = require("../out/routes/api/quest").default
const {
    getRecommendedQuestPartiesSync,
    recordQuestRecommendedPartySync,
} = require("../out/lib/quest/recommended-party-history")

const QUEST_CATEGORY = 1
const QUEST_ID = 1001001

function createPlayer(name) {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    getDb().prepare(`UPDATE players SET name = ?, party_slot = 1 WHERE id = ?`)
        .run(name, player.id)
    return { account, playerId: player.id }
}

function ensureCharacter(playerId, characterId, evolutionLevel) {
    getDb().prepare(`
        INSERT INTO players_characters (
            id, entry_count, evolution_level, over_limit_step, protection,
            join_time, update_time, exp, stack, mana_board_index, player_id,
            ex_boost_status_id, ex_boost_ability_id_list, illustration_settings
        ) VALUES (?, 1, ?, 0, 0, '2026-01-01', '2026-01-01', 0, 0, 1, ?, NULL, NULL, NULL)
        ON CONFLICT (id, player_id) DO UPDATE SET evolution_level = excluded.evolution_level
    `).run(characterId, evolutionLevel, playerId)
}

function saveParty(playerId, name, power, characterIds) {
    characterIds.forEach((characterId, index) => ensureCharacter(playerId, characterId, index))
    getDb().prepare(`
        INSERT INTO players_party_groups (id, color_id, player_id, category)
        VALUES (1, 15, ?, 1)
        ON CONFLICT (id, player_id, category) DO NOTHING
    `).run(playerId)
    getDb().prepare(`
        INSERT INTO players_parties (
            slot, name,
            character_id_1, character_id_2, character_id_3,
            unison_character_1, unison_character_2, unison_character_3,
            equipment_1, equipment_2, equipment_3,
            ability_soul_1, ability_soul_2, ability_soul_3,
            edited, current_battle_power, before_battle_power,
            player_id, group_id, category
        ) VALUES (
            1, ?, ?, ?, ?,
            NULL, NULL, NULL,
            NULL, NULL, NULL,
            NULL, NULL, NULL,
            1, ?, 0, ?, 1, 1
        )
        ON CONFLICT (slot, player_id, group_id, category) DO UPDATE SET
            name = excluded.name,
            character_id_1 = excluded.character_id_1,
            character_id_2 = excluded.character_id_2,
            character_id_3 = excluded.character_id_3,
            unison_character_1 = NULL,
            unison_character_2 = NULL,
            unison_character_3 = NULL,
            equipment_1 = NULL,
            equipment_2 = NULL,
            equipment_3 = NULL,
            ability_soul_1 = NULL,
            ability_soul_2 = NULL,
            ability_soul_3 = NULL,
            current_battle_power = excluded.current_battle_power
    `).run(name, ...characterIds, power, playerId)
}

function finishContext(playerId, clearTime, characterIds) {
    const party = {
        characters: characterIds.map(id => ({ id })),
        unison_characters: [null, null, null],
        equipments: [null, null, null],
        ability_soul_ids: [null, null, null],
    }
    return {
        playerId,
        questCategory: QUEST_CATEGORY,
        questId: QUEST_ID,
        questAccomplished: true,
        clearTime,
        clearRank: 5,
        party,
        statistics: { clear_phase: 1, party },
        player: getPlayerSync(playerId),
        questPreviouslyCompleted: false,
        questProgress: null,
        partySlot: 1,
    }
}

test("推荐配队只使用本关通关者，固定显示十条并只按通关战力排序", async () => {
    const viewer = createPlayer("Viewer")
    const highPower = createPlayer("Fast High Power")
    const lowPower = createPlayer("Fast Low Power")
    const legacy = createPlayer("Legacy Clear")
    const unrelated = createPlayer("Unrelated Whale")

    const highCharacters = [110001, 110002, 110003]
    const lowCharacters = [120001, 120002, 120003]
    const legacyCharacters = [130001, 130002, 130003]
    saveParty(highPower.playerId, "高速高战力", 20_000, highCharacters)
    saveParty(lowPower.playerId, "高速低战力", 10_000, lowCharacters)
    saveParty(legacy.playerId, "旧记录通关队", 15_000, legacyCharacters)
    saveParty(unrelated.playerId, "全服最高但没通关", 999_999, [140001, 140002, 140003])

    assert.equal(recordQuestRecommendedPartySync(
        finishContext(highPower.playerId, 8_000, highCharacters),
    ), true)
    assert.equal(recordQuestRecommendedPartySync(
        finishContext(lowPower.playerId, 8_000, lowCharacters),
    ), true)
    insertPlayerQuestProgressSync(legacy.playerId, QUEST_CATEGORY, {
        questId: QUEST_ID,
        finished: true,
        bestElapsedTimeMs: 7_000,
        clearRank: 5,
    })

    const first = getRecommendedQuestPartiesSync(
        viewer.playerId,
        QUEST_CATEGORY,
        QUEST_ID,
    )
    assert.equal(first.exactCandidateCount, 2)
    assert.equal(first.legacyCandidateCount, 1)
    assert.deepEqual(first.parties.map(party => [party.party_name, party.power]), [
        ["高速高战力", 20_000],
        ["旧记录通关队", 15_000],
        ["高速低战力", 10_000],
    ])
    assert.ok(!first.parties.some(party => party.party_name === "全服最高但没通关"))

    const replacementCharacters = [150001, 150002, 150003]
    saveParty(lowPower.playerId, "更快但低战力的新队伍", 9_000, replacementCharacters)
    assert.equal(recordQuestRecommendedPartySync(
        finishContext(lowPower.playerId, 6_000, replacementCharacters),
    ), false)
    const afterFasterLowPower = getRecommendedQuestPartiesSync(
        viewer.playerId,
        QUEST_CATEGORY,
        QUEST_ID,
    )
    assert.ok(afterFasterLowPower.parties.some(party => party.party_name === "高速低战力"))
    assert.ok(!afterFasterLowPower.parties.some(
        party => party.party_name === "更快但低战力的新队伍",
    ))

    saveParty(lowPower.playerId, "更慢但高战力的新队伍", 16_000, replacementCharacters)
    assert.equal(recordQuestRecommendedPartySync(
        finishContext(lowPower.playerId, 20_000, replacementCharacters),
    ), true)

    const viewerId = 223456789
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: viewer.account.id,
        type: 2,
        expires: new Date(Date.now() + 86_400_000),
    })
    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        if (reply.getHeader("content-type") === "application/x-msgpack"
            && typeof payload === "object") {
            done(null, JSON.stringify(payload))
            return
        }
        done(null, payload)
    })
    await app.register(questRoutes, { prefix: "/quest" })
    await app.ready()

    const response = await app.inject({
        method: "POST",
        url: "/quest/get_recent_other_player_party",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            category: QUEST_CATEGORY,
            quest_id: QUEST_ID,
        },
    })
    assert.equal(response.statusCode, 200)
    const body = JSON.parse(response.payload)
    assert.deepEqual(
        body.data.recent_other_player_party.map(party => [party.party_name, party.power]),
        [
            ["高速高战力", 20_000],
            ["更慢但高战力的新队伍", 16_000],
            ["旧记录通关队", 15_000],
        ],
    )

    for (let index = 0; index < 9; index += 1) {
        const candidate = createPlayer(`Power Candidate ${index}`)
        const characterBase = 160000 + index * 10
        const characterIds = [characterBase + 1, characterBase + 2, characterBase + 3]
        const power = 30_000 + index
        saveParty(candidate.playerId, `战力候选${index}`, power, characterIds)
        assert.equal(recordQuestRecommendedPartySync(
            finishContext(candidate.playerId, 100_000 - index * 1_000, characterIds),
        ), true)
    }
    const capped = getRecommendedQuestPartiesSync(
        viewer.playerId,
        QUEST_CATEGORY,
        QUEST_ID,
        99,
    )
    assert.equal(capped.parties.length, 10)
    assert.deepEqual(
        capped.parties.map(party => party.power),
        [...capped.parties.map(party => party.power)].sort((left, right) => right - left),
    )

    await app.close()
})
