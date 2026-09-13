const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const directory = fs.mkdtempSync(path.join(os.tmpdir(), "awake-query-scope-"))
process.env.DATA_DIR = directory
process.env.GAME_VERBOSE_LOGS = "false"
const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")
const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const character = require("../out/data/domains/character")
const missions = require("../out/data/domains/mission")
const unlock = require("../out/data/domains/character_awake")
const assets = require("../out/lib/assets")
const mission = require("../out/lib/mission")
const routes = require("../out/routes/api/mission").default
const { setServerTimeOffset } = require("../out/utils")
const db = getDb()
const prepare = db.prepare.bind(db)
let capture = null
db.prepare = function (sql) {
    const statement = prepare(sql)
    return new Proxy(statement, {
        get(target, property) {
            const value = Reflect.get(target, property, target)
            if (typeof value !== "function") return value
            if (!["all", "get", "run"].includes(property)) return value.bind(target)
            return (...args) => {
                const result = value.apply(target, args)
                if (capture) capture.push({ sql: sql.replace(/\s+/g, " ").trim(), operation: property,
                    rows: property === "all" ? result.length : property === "get" ? Number(result !== undefined) : 0 })
                return result
            }
        },
    })
}
const time = new Date("2025-01-01T12:00:00.000Z")
setServerTimeOffset(time.getTime() - Date.now())
const app = Fastify()
app.addHook("onSend", (_request, reply, payload, done) => {
    done(null, reply.getHeader("content-type") === "application/x-msgpack" ? pack(payload).toString("base64") : payload)
})
test.before(async () => { await app.register(routes, { prefix: "/mission" }); await app.ready() })
test.after(async () => {
    await app.close()
    db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory, { recursive: true })
})

let sequence = 0
function seed(ids = [211002], count = 5) {
    const account = insertAccountSync({ appId: "wf_cn", idpAlias: "", idpCode: "test", idpId: `awake-scope-${++sequence}`, status: "normal" })
    const playerId = insertDefaultPlayerSync(account.id).id
    for (const id of ids) {
        if (!character.playerOwnsCharacterSync(playerId, id)) character.insertDefaultPlayerCharacterSync(playerId, id)
        const learned = new Set(character.getPlayerCharacterManaNodesSync(playerId, id))
        character.insertPlayerCharacterManaNodesSync(playerId, id,
            Object.keys(assets.getCharacterManaNodesSync(id, 1) || {}).map(Number).filter(node => !learned.has(node)))
        prepare(`INSERT INTO players_character_quest_clears (player_id, character_id, clear_count,
            multi_count, leader_clear_count, leader_multi_count, leader_power_flip_count)
            VALUES (?, ?, ?, 0, 0, 0, 0)`).run(playerId, id, count)
    }
    const viewerId = 870100000 + playerId
    prepare("INSERT INTO sessions (token, account_id, expires, type) VALUES (?, ?, ?, 2)")
        .run(String(viewerId), account.id, "2099-01-01T00:00:00.000Z")
    return { playerId, viewerId }
}
async function page(player, ids = [211002]) {
    const response = await app.inject({ method: "POST", url: "/mission/get_mission_progress", payload: {
        viewer_id: player.viewerId, api_count: ++sequence, category_list: ids.map(id => ({ category: 9, character_id: id })),
    } })
    assert.equal(response.statusCode, 200, response.body)
    return unpack(Buffer.from(response.body, "base64")).data
}
function inventory(playerId) {
    return prepare("SELECT id, amount FROM players_items WHERE player_id = ? ORDER BY id").all(playerId)
}
async function trace(action) {
    capture = []
    try { return { result: await action(), queries: capture } } finally { capture = null }
}

test("scoped mission reads preserve category isolation and include only requested stages", () => {
    const { playerId } = seed()
    for (const [category, id, progress] of [[9, 2110021, 1], [9, 3410051, 5], [1, 2110021, 99]]) {
        missions.updatePlayerCategoryMissionSync(playerId, category, id, progress)
        missions.updatePlayerCategoryMissionStageSync(playerId, category, 1, id, true)
    }
    assert.deepEqual(missions.getPlayerCategoryMissionsSync(playerId, 9, [2110021, 2110021]), {
        2110021: { progress: 1, stages: { 1: true } },
    })
    assert.deepEqual(missions.getPlayerCategoryMissionsSync(playerId, 9, []), {})
    assert.equal(Object.keys(missions.getPlayerCategoryMissionsSync(playerId, 9)).length, 2)
})

test("completed page retries publish authority with one scoped mission snapshot and no writes", async () => {
    const player = seed([211002, 341005])
    const first = await page(player)
    assert.equal(first.mission_info.length, 4)
    const before = inventory(player.playerId)
    missions.updatePlayerCategoryMissionSync(player.playerId, 9, 3410051, 5)
    const { result, queries } = await trace(() => page(player))
    assert.deepEqual(result.mission_info, [])
    assert.equal(result.character_list.find(row => row.character_id === 211002).mana_board_awake[1], 1)
    assert.deepEqual(inventory(player.playerId), before)
    assert.equal(queries.filter(q => q.operation === "run").length, 0)
    for (const table of ["players_category_missions", "players_category_mission_stages"]) {
        const reads = queries.filter(q => q.sql.includes(`FROM ${table} `))
        assert.equal(reads.length, 1, table)
        assert.equal(reads[0].rows, 4, table)
        assert.match(reads[0].sql, /IN \(/)
    }
    assert.equal(queries.filter(q => q.sql.includes("FROM players_characters_mana_nodes ")).length, 1)
})

test("duplicate and multi-character page scopes grant once and preserve existing higher authority", async () => {
    const player = seed([211002, 341005])
    const result = await page(player, [211002, 341005, 211002])
    assert.equal(result.mission_info.length, 8)
    assert.equal(new Set(result.mission_info.map(row => row.mission_id)).size, 8)
    const before = inventory(player.playerId)
    unlock.upsertPlayerCharacterAwakeUnlockSync(player.playerId, 211002, 1, 2)
    const repeated = await page(player, [211002, 341005])
    assert.equal(repeated.character_list.find(row => row.character_id === 211002).mana_board_awake[1], 2)
    assert.deepEqual(inventory(player.playerId), before)
})

test("received old saves repair missing unlocks without repeating rewards", async () => {
    const player = seed()
    await page(player)
    const before = inventory(player.playerId)
    prepare("DELETE FROM players_character_awake_unlocks WHERE player_id = ? AND character_id = ?")
        .run(player.playerId, 211002)
    const result = await page(player)
    assert.deepEqual(result.mission_info, [])
    assert.equal(result.character_list[0].mana_board_awake[1], 1)
    assert.deepEqual(inventory(player.playerId), before)
    const incomplete = seed([211002], 4)
    assert.equal((await page(incomplete)).character_list.length, 0)
})

test("all configured unlocks converge to one read with no fact scans or writes", async () => {
    const ids = [...new Set(mission.getMissionIdsByCategory(9).map(mission.getCharacterIdFromMission).map(Number))]
    const player = seed(ids)
    for (const id of mission.getMissionIdsByCategory(9)) for (const stage of mission.getMissionStageIds(9, id)) {
        const reward = mission.getAwakeMissionRewardStageDefinition(id, stage)?.specialReward
        if (reward) unlock.upsertPlayerCharacterAwakeUnlockSync(player.playerId, reward.characterId, reward.boardIndex, reward.awakeLevel)
    }
    const { result, queries } = await trace(() => mission.reconcileAwakeUnlocks(player.playerId))
    assert.equal(result.changed.size, 0)
    assert.equal(queries.length, 1)
    assert.match(queries[0].sql, /FROM players_character_awake_unlocks/)
})

test("candidate reconciliation leaves unrelated characters pending and avoids full quest reads", async () => {
    const player = seed([211002, 341005])
    const { result, queries } = await trace(() => mission.reconcileAwakeUnlocks(player.playerId, [211002]))
    assert.deepEqual(result.changed.get("211002"), { 1: 1 })
    assert.equal(result.all.has("341005"), false)
    assert.equal(queries.some(q => q.sql.includes("FROM players_quest_progress")), false)
    const repeated = await trace(() => mission.reconcileAwakeUnlocks(player.playerId, [211002]))
    assert.equal(repeated.queries.length, 1)
})

test("bounded legacy co-clear reads preserve both pair orientations and ignore unrelated history", async () => {
    const player = seed([211001, 231001])
    const insert = prepare("INSERT INTO players_party_member_co_clears (player_id, char_id_a, char_id_b, co_clear_count) VALUES (?, ?, ?, ?)")
    insert.run(player.playerId, 211001, 231001, 3)
    insert.run(player.playerId, 231001, 211001, 4)
    insert.run(player.playerId, 10, 211001, 999)
    const computer = mission.getComputer(9)
    const { result: context, queries } = await trace(() => computer.buildContext(player.playerId, 9, time, [2110012]))
    assert.equal(computer.compute(2110012, context, 0), 7)
    const pairs = queries.filter(q => q.sql.includes("FROM players_party_member_co_clears"))
    assert.equal(pairs.length, 1)
    assert.equal(pairs[0].rows, 2)
    const full = computer.buildContext(player.playerId, 9, time)
    assert.equal(computer.compute(2110012, full, 0), 7)
})

test("scoped facts and final-mission dependency expansion agree with full evaluation for every configured mission", () => {
    const allIds = mission.getMissionIdsByCategory(9)
    const characterIds = [...new Set(allIds.map(mission.getCharacterIdFromMission).map(Number))]
    const { playerId } = seed(characterIds, 17)
    const computer = mission.getComputer(9)
    const assertEquivalent = () => {
        const full = computer.buildContext(playerId, 9, time)
        for (const characterId of characterIds) {
            const ids = allIds.filter(id => Number(mission.getCharacterIdFromMission(id)) === characterId)
            // Reconciliation now requests only the special-reward mission; its
            // context must still carry all three child missions and their facts.
            const scoped = computer.buildContext(playerId, 9, time, [characterId * 10 + 4])
            for (const id of ids) for (const previous of [0, 2, 999]) {
                assert.equal(computer.compute(id, scoped, previous), computer.compute(id, full, previous),
                    `mission ${id}, previous ${previous}`)
            }
        }
    }
    assertEquivalent()
    prepare("UPDATE players SET total_mana_obtained = 7654321, total_powerflips = 321, max_combo_achieved = 654 WHERE id = ?")
        .run(playerId)
    prepare("UPDATE players_characters_bond_tokens SET status = 2 WHERE player_id = ?").run(playerId)
    prepare(`UPDATE players_character_quest_clears SET leader_clear_count = 11,
        leader_multi_count = 7, leader_power_flip_count = 43 WHERE player_id = ?`).run(playerId)
    const insertQuest = prepare(`INSERT INTO players_quest_progress
        (player_id, section, quest_id, finished, clear_rank, best_elapsed_time_ms, leader_character_id)
        VALUES (?, ?, ?, 1, 5, ?, ?)`)
    for (const questId of new Set(characterIds.flatMap(mission.getCharacterStoryQuestIds))) {
        insertQuest.run(playerId, 3, questId, null, null)
    }
    for (const [section, questId, elapsed, leader] of [
        [2, 1028004, 10000, 111001], [2, 1020003, 30000, 141003],
        [2, 1010004, 80000, 231001], [21, 1006, 91000, 231001],
        [13, 1020, 120000, 251003], [18, 400001104, 40000, 151006],
    ]) insertQuest.run(playerId, section, questId, elapsed, leader)
    for (const id of allIds.filter(id => id % 10 !== 4)) {
        missions.updatePlayerCategoryMissionSync(playerId, 9, id, id % 3)
    }
    const insertPair = prepare("INSERT INTO players_party_member_co_clears (player_id, char_id_a, char_id_b, co_clear_count) VALUES (?, ?, ?, ?)")
    for (const [a, b, count] of [[211001, 231001, 8], [221004, 10, 5], [243007, 241063, 9],
        [241063, 361009, 6], [361009, 243007, 7], [251004, 1, 4]]) insertPair.run(playerId, a, b, count)
    assertEquivalent()
    const scoped = computer.buildContext(playerId, 9, time, [2630024, 2410634, 1410034])
    assert.equal(computer.compute(2630022, scoped, 0), 7654321)
    assert.equal(computer.compute(2410633, scoped, 0), 6)
    assert.equal(computer.compute(1410033, scoped, 0), 1)
})

test("batched quest facts keep exact sections and player scope, deduplicate and bound parameters", async () => {
    const quests = require("../out/data/domains/quest")
    const player = seed()
    const other = seed()
    const ids = Array.from({ length: 805 }, (_, i) => 9100000 + i)
    const insert = prepare("INSERT INTO players_quest_progress (player_id, section, quest_id, finished, clear_rank) VALUES (?, ?, ?, 1, ?)")
    db.transaction(() => {
        for (const id of ids) insert.run(player.playerId, 2, id, 5)
        insert.run(player.playerId, 3, ids[0], 2)
        insert.run(other.playerId, 2, ids[0], 3)
    })()
    const { result, queries } = await trace(() => quests.getPlayerQuestProgressBySectionAndIdsSync(player.playerId, "2", [...ids, ids[0], NaN]))
    assert.equal(result.length, 805)
    assert.equal(result.every(row => row.finished && row.clearRank === 5), true)
    assert.deepEqual(result[0], quests.getPlayerSingleQuestProgressSync(player.playerId, 2, ids[0]))
    assert.equal(queries.length, 3)
    assert.equal(queries.every(q => q.operation === "all" && /section = \? AND quest_id IN/.test(q.sql)), true)
    assert.deepEqual((await trace(() => quests.getPlayerQuestProgressBySectionAndIdsSync(player.playerId, 2, []))).queries, [])
})

test("batched character clear facts match single reads, omit missing rows and never read other players", async () => {
    const clears = require("../out/data/domains/character_clear")
    const { serverCharacters } = require("../out/lib/content-master")
    const ids = Object.keys(serverCharacters).map(Number)
    assert.ok(ids.length > 400)
    const player = seed(ids, 17)
    const other = seed([ids[0]], 99)
    const { result, queries } = await trace(() => clears.getPlayerCharacterClearsSync(player.playerId, [...ids, ids[0], 999999999]))
    assert.equal(Object.keys(result).length, ids.length)
    for (const id of ids) assert.deepEqual(result[id], clears.getPlayerCharacterClearSync(player.playerId, id))
    assert.equal(result[ids[0]].clear_count, 17)
    assert.equal(clears.getPlayerCharacterClearSync(other.playerId, ids[0]).clear_count, 99)
    assert.equal(result[999999999], undefined)
    assert.equal(queries.length, Math.ceil((ids.length + 1) / 400))
    assert.deepEqual((await trace(() => clears.getPlayerCharacterClearsSync(player.playerId, []))).queries, [])
})

test("batched finite-abyss reads retain time-revision repair and do it only once per batch", async () => {
    const quests = require("../out/data/domains/quest")
    const { QuestCategory } = require("../out/lib/types/quest")
    const { getAbyssTimeRevision, ABYSS_FIRST_QUEST_ID } = require("../out/lib/abyss-time-revision")
    const revision = getAbyssTimeRevision()
    assert.ok(revision)
    const player = seed()
    const section = QuestCategory.RUSH_EVENT
    const insert = prepare(`INSERT INTO players_quest_progress
        (player_id, section, quest_id, finished, best_elapsed_time_ms, best_time_revision)
        VALUES (?, ?, ?, 1, 1234, 'older-tower')`)
    for (const id of [ABYSS_FIRST_QUEST_ID, ABYSS_FIRST_QUEST_ID + 1, 700099999]) insert.run(player.playerId, section, id)
    insert.run(player.playerId, 2, ABYSS_FIRST_QUEST_ID)
    const unrelated = await trace(() => quests.getPlayerQuestProgressBySectionAndIdsSync(player.playerId, 2, [ABYSS_FIRST_QUEST_ID]))
    assert.equal(unrelated.result[0].bestElapsedTimeMs, 1234)
    assert.equal(unrelated.queries.some(q => q.operation === "run"), false)
    const { result, queries } = await trace(() => quests.getPlayerQuestProgressBySectionAndIdsSync(player.playerId, section,
        [ABYSS_FIRST_QUEST_ID, ABYSS_FIRST_QUEST_ID + 1, ABYSS_FIRST_QUEST_ID]))
    assert.equal(result.length, 2)
    assert.equal(result.every(row => row.bestElapsedTimeMs === null), true)
    assert.equal(queries.filter(q => q.operation === "run").length, 1)
    assert.equal(quests.getPlayerSingleQuestProgressSync(player.playerId, section, 700099999).bestElapsedTimeMs, 1234)
    assert.equal(prepare("SELECT best_time_revision FROM players_quest_progress WHERE player_id = ? AND section = ? AND quest_id = ?")
        .get(player.playerId, section, ABYSS_FIRST_QUEST_ID).best_time_revision, revision)
})
