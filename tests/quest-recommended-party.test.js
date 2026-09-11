const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const { spawnSync } = require("node:child_process")

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

test("推荐配队只使用本关实际通关快照，最多十条且按通关战力排序", async () => {
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
    saveParty(legacy.playerId, "仅有通关标记的高战力现役队", 900_000, legacyCharacters)
    getDb().prepare('UPDATE players_parties SET equipment_1 = 100013 WHERE player_id = ? AND category = 1')
        .run(legacy.playerId)
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
    assert.deepEqual(first.parties.map(party => [party.party_name, party.power]), [
        ["高速高战力", 20_000],
        ["高速低战力", 10_000],
    ])
    assert.ok(!first.parties.some(party => party.party_name === "全服最高但没通关"))
    assert.ok(!first.parties.some(party => party.party_name === "仅有通关标记的高战力现役队"))
    // Editing a saved loadout after the clear never rewrites its frozen snapshot.
    getDb().prepare('UPDATE players_parties SET equipment_1 = 100013, name = ? WHERE player_id = ? AND category = 1')
        .run('通关后换上的幻想武器队', highPower.playerId)
    const frozen = getRecommendedQuestPartiesSync(viewer.playerId, QUEST_CATEGORY, QUEST_ID)
    assert.equal(frozen.parties[0].party_name, '高速高战力')
    assert.equal(frozen.parties[0].equipment_id_1, null)

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

test("没有本关快照时返回空列表，其他关卡和模式的快照不能补位", () => {
    const candidate = createPlayer('Old clear only')
    const ids = [180001, 180002, 180003]
    saveParty(candidate.playerId, '现在的最高战力编队', 999_999, ids)
    const targetQuest = 1002001
    insertPlayerQuestProgressSync(candidate.playerId, QUEST_CATEGORY, {
        questId: targetQuest, finished: true, bestElapsedTimeMs: 1000, clearRank: 5,
    })
    const context = finishContext(candidate.playerId, 1000, ids)
    assert.equal(recordQuestRecommendedPartySync(context), true)
    assert.deepEqual(getRecommendedQuestPartiesSync(-1, QUEST_CATEGORY, targetQuest).parties, [])
    assert.deepEqual(getRecommendedQuestPartiesSync(-1, 2, QUEST_ID).parties, [])
    context.questId = targetQuest
    context.questAccomplished = false
    assert.equal(recordQuestRecommendedPartySync(context), false)
    assert.deepEqual(getRecommendedQuestPartiesSync(-1, QUEST_CATEGORY, targetQuest).parties, [])
    context.questAccomplished = true
    assert.equal(recordQuestRecommendedPartySync(context), true)
    assert.equal(getRecommendedQuestPartiesSync(-1, QUEST_CATEGORY, targetQuest).parties.length, 1)
    assert.deepEqual(getRecommendedQuestPartiesSync(candidate.playerId, QUEST_CATEGORY, targetQuest).parties, [])
})

test("写入必须匹配结算的完整装备和魂珠以及实际模式，不能猜用当前编队", () => {
    const candidate = createPlayer('Incomplete clear')
    const ids = [190001, 190002, 190003]
    saveParty(candidate.playerId, '当前队伍', 20_000, ids)
    const context = finishContext(candidate.playerId, 1000, ids)
    for (const missing of ['unison_characters', 'equipments', 'ability_soul_ids']) {
        const party = { ...context.party }
        delete party[missing]
        assert.equal(recordQuestRecommendedPartySync({ ...context, party }), false, missing)
    }
    assert.equal(recordQuestRecommendedPartySync({
        ...context, party: { ...context.party, equipments: [] },
    }), false)
    assert.equal(recordQuestRecommendedPartySync({
        ...context, party: { ...context.party, equipments: [{ id: 123 }, null, null] },
    }), false)
    assert.equal(recordQuestRecommendedPartySync({
        ...context, party: { ...context.party, ability_soul_ids: [123, null, null] },
    }), false)
    // The same slot in NORMAL must not be used to manufacture a Carnival clear.
    assert.equal(recordQuestRecommendedPartySync({ ...context, questCategory: 22 }), false)
    assert.equal(recordQuestRecommendedPartySync(context), true)
})

test("幻想武器和魂珠在其他模式的历史记录被过滤，合法低战力通关能替换旧错误记录", () => {
    const candidate = createPlayer('Restricted history')
    const ids = [200001, 200002, 200003]
    saveParty(candidate.playerId, '合法通关', 10_000, ids)
    const context = { ...finishContext(candidate.playerId, 1000, ids), questId: 1003001 }
    assert.equal(recordQuestRecommendedPartySync(context), true)
    const original = getDb().prepare('SELECT party_payload FROM quest_npc_party_pool WHERE source_player_id = ?')
        .get(candidate.playerId)
    for (const field of ['equipment_id_1', 'ability_soul_id_2']) {
        const badParty = { ...JSON.parse(original.party_payload), [field]: 100013 }
        getDb().prepare('UPDATE quest_npc_party_pool SET battle_power = 999999, party_payload = ? WHERE source_player_id = ?')
            .run(JSON.stringify(badParty), candidate.playerId)
        assert.deepEqual(getRecommendedQuestPartiesSync(-1, 1, context.questId).parties, [])
        assert.equal(recordQuestRecommendedPartySync(context), true)
        const repaired = getRecommendedQuestPartiesSync(-1, 1, context.questId).parties
        assert.equal(repaired.length, 1)
        assert.equal(repaired[0].power, 10_000)
        assert.equal(repaired[0][field], null)
    }
    getDb().prepare('UPDATE players_parties SET equipment_1 = 100013 WHERE player_id = ? AND category = 1')
        .run(candidate.playerId)
    const restricted = { ...context, party: { ...context.party, equipments: [{ id: 100013 }, null, null] } }
    assert.equal(recordQuestRecommendedPartySync(restricted), false)
    // Fantasy Gauntlet's actual multiplayer quests keep their legitimate gear.
    assert.equal(recordQuestRecommendedPartySync({ ...restricted, questCategory: 7, questId: 300098001 }), true)
    assert.ok(getRecommendedQuestPartiesSync(-1, 7, 300098001).parties.some(p=>p.equipment_id_1===100013))
    // Rush's Fantasy practice quest is in the same equipment-allowed event.
    getDb().prepare('INSERT INTO players_party_groups (id,color_id,player_id,category) VALUES(1,15,?,4)')
        .run(candidate.playerId)
    const partyColumns = getDb().prepare('PRAGMA table_info(players_parties)').all().map(c=>c.name)
    getDb().prepare(`INSERT INTO players_parties (${partyColumns.join(',')})
        SELECT ${partyColumns.map(c=>c==='category'?'4':c).join(',')}
        FROM players_parties WHERE player_id=? AND category=1 AND group_id=1 AND slot=1`)
        .run(candidate.playerId)
    const { MODE15_PRACTICE_QUEST_ID } = require('../out/lib/mode15-optional')
    assert.equal(recordQuestRecommendedPartySync({ ...restricted, questCategory: 24, questId: MODE15_PRACTICE_QUEST_ID }), true)
    assert.equal(getRecommendedQuestPartiesSync(-1,24,MODE15_PRACTICE_QUEST_ID).parties[0].equipment_id_1,100013)
})

test("旧格式快照和重复队伍不占满第一页，后续页仍能找到真实通关队", () => {
    const targetQuest = 1004001
    for (let i = 0; i < 201; i++) {
        const candidate = createPlayer(`Legacy payload ${i}`)
        getDb().prepare(`INSERT INTO quest_npc_party_pool
            (quest_category, quest_id, source_player_id, party_slot, battle_power, party_payload, cleared_at)
            VALUES (1, ?, ?, 1, 999999, ?, 1000)`)
            .run(targetQuest, candidate.playerId, i % 2 ? '{bad json' : '{"characters":[{"id":1}]}')
    }
    const valid = createPlayer('Page two real clear')
    const ids = [210001, 210002, 210003]
    saveParty(valid.playerId, '第二页真实通关', 10_000, ids)
    assert.equal(recordQuestRecommendedPartySync({
        ...finishContext(valid.playerId, 1000, ids), questId: targetQuest,
    }), true)
    const duplicate = createPlayer('Duplicate real clear')
    saveParty(duplicate.playerId, '相同实际编队', 9_000, ids)
    assert.equal(recordQuestRecommendedPartySync({
        ...finishContext(duplicate.playerId, 1000, ids), questId: targetQuest,
    }), true)
    assert.deepEqual(getRecommendedQuestPartiesSync(-1, 1, targetQuest).parties.map(p=>p.party_name), ['第二页真实通关'])
})

test("通关快照持久化到数据库，新进程读取时仍不会混入现役队伍", () => {
    const candidate = createPlayer('Persistent clear')
    const ids = [220001, 220002, 220003]
    const targetQuest = 1005001
    saveParty(candidate.playerId, '持久化通关快照', 12345, ids)
    getDb().prepare('UPDATE players_parties SET equipment_1 = 123, ability_soul_2 = 234 WHERE player_id = ? AND category = 1')
        .run(candidate.playerId)
    const context = finishContext(candidate.playerId, 1000, ids)
    context.party.equipments[0] = { id: 123 }
    context.party.ability_soul_ids[1] = 234
    assert.equal(recordQuestRecommendedPartySync({
        ...context, questId: targetQuest,
    }), true)
    getDb().prepare('UPDATE players_parties SET name = ?, equipment_1 = 100013 WHERE player_id = ? AND category = 1')
        .run('后续改动', candidate.playerId)
    const reader = `
        const D = require('better-sqlite3');
        const db = new D(process.env.DATA_DIR + '/wdfp_data.db', {readonly:true,fileMustExist:true});
        db.pragma('query_only=ON');
        const cacheKey = require.resolve('./out/data/db');
        require.cache[cacheKey] = {id:cacheKey,filename:cacheKey,loaded:true,exports:{getDb:()=>db}};
        const {getRecommendedQuestPartiesSync} = require('./out/lib/quest/recommended-party-history');
        const result = getRecommendedQuestPartiesSync(-1,1,${targetQuest});
        console.log('RESULT='+JSON.stringify(result.parties));
        db.close();
    `
    const child = spawnSync(process.execPath, ['-e', reader], {cwd:path.resolve(__dirname,'..'),env:process.env,encoding:'utf8',timeout:20000})
    assert.equal(child.status, 0, child.stderr)
    const result = JSON.parse(child.stdout.split('\n').find(line=>line.startsWith('RESULT=')).slice(7))
    assert.equal(result.length, 1)
    assert.equal(result[0].party_name, '持久化通关快照')
    assert.equal(result[0].equipment_id_1, 123)
    assert.equal(result[0].ability_soul_id_2, 234)
})
