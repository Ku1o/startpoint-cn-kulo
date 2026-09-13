const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const directory = fs.mkdtempSync(path.join(os.tmpdir(), "degree-query-scope-"))
process.env.DATA_DIR = directory
process.env.GAME_VERBOSE_LOGS = "false"
const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const character = require("../out/data/domains/character")
const missionData = require("../out/data/domains/mission")
const degreeData = require("../out/data/domains/degree")
const assets = require("../out/lib/assets")
const { serverManaNodes, serverCharacters } = require("../out/lib/content-master")
const { characterExpCaps } = require("../out/lib/character")
const mission = require("../out/lib/mission")
const { getCategoryMissionRewardStageDefinition } = require("../out/lib/mission/rewards")
const { setServerTimeOffset } = require("../out/utils")
const time = new Date("2025-01-01T12:00:00Z")
setServerTimeOffset(time.getTime() - Date.now())
const db = getDb()
const prepare = db.prepare.bind(db)
let capture = null
db.prepare = function (sql) {
    const statement = prepare(sql)
    return new Proxy(statement, { get(target, property) {
        const value = Reflect.get(target, property, target)
        if (typeof value !== "function") return value
        if (!["all", "get", "run"].includes(property)) return value.bind(target)
        return (...args) => {
            const result = value.apply(target, args)
            if (capture) capture.push({ sql: sql.replace(/\s+/g, " ").trim(), args, operation: property,
                rows: property === "all" ? result.length : property === "get" ? Number(result !== undefined) : 0 })
            return result
        }
    } })
}
test.after(() => {
    db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory, { recursive: true })
})
let sequence = 0
function seed(ids = [211002, 341005, 151045]) {
    const account = insertAccountSync({ appId: "wf_cn", idpAlias: "", idpCode: "test", idpId: `degree-scope-${++sequence}`, status: "normal" })
    const playerId = insertDefaultPlayerSync(account.id).id
    for (const id of ids) if (!character.playerOwnsCharacterSync(playerId, id)) {
        character.insertDefaultPlayerCharacterSync(playerId, id)
    }
    return playerId
}
function learn(playerId, id, nodes) {
    const existing = new Set(character.getPlayerCharacterManaNodesSync(playerId, id))
    character.insertPlayerCharacterManaNodesSync(playerId, id, [...new Set(nodes)].filter(node => !existing.has(node)))
}
function board(id, index = 2) { return Object.keys(assets.getCharacterManaNodesSync(id, index) ?? {}).map(Number) }
const allBoards = Object.fromEntries(Object.keys(serverManaNodes).map(id => [id, board(id)]))
function reference(playerId) {
    const characters = character.getPlayerCharactersSync(playerId)
    const nodes = character.getPlayerCharactersManaNodesSync(playerId)
    return {
        nodes: Object.values(nodes).reduce((total, values) => total + values.length, 0),
        bonds: Object.values(characters).reduce((total, row) => total + row.bondTokenList.filter(t => t.status >= 2).length, 0),
        completed: new Set(Object.keys(characters).map(Number).filter(id => {
            const required = board(id)
            const learned = new Set(nodes[id] ?? [])
            return required.length > 0 && required.every(node => learned.has(node))
        })),
    }
}
async function trace(action) {
    capture = []
    try { return { result: await action(), queries: capture } } finally { capture = null }
}
function inventory(playerId) {
    return prepare("SELECT id, amount FROM players_items WHERE player_id = ? ORDER BY id").all(playerId)
}
function settle(playerId, ids, at = time) {
    return mission.settleMissionCategoriesWithProgress(playerId, [{ category: 5, missionIds: ids }], at)
}
function noCharacterFactReads(queries) {
    assert.equal(queries.some(q => q.operation !== "run" && /\bplayers_characters(?:_mana_nodes|_bond_tokens)?\b/.test(q.sql)), false)
}

test("aggregate counts and exact board membership match the old full-row calculation", async () => {
    const playerId = seed(Object.keys(serverCharacters).map(Number))
    const ids = Object.keys(character.getPlayerCharactersSync(playerId)).map(Number)
    for (const [index, id] of ids.entries()) {
        learn(playerId, id, board(id, 1).slice(0, index % 7))
        const required = board(id)
        if (index % 3 === 0) learn(playerId, id, required)
        if (index % 3 === 1 && required.length) learn(playerId, id, [...required.slice(0, -1), 999990001])
        character.updatePlayerCharacterBondTokenSync(playerId, id, { manaBoardIndex: 1, status: index % 4 })
    }
    const other = seed()
    learn(other, 211002, board(211002))
    const expected = reference(playerId)
    assert.ok(expected.completed.size > 50)
    const { result, queries } = await trace(() => ({
        nodes: character.countPlayerCharacterManaNodesSync(playerId),
        bonds: character.countPlayerReceivedBondTokensSync(playerId),
        completed: character.getPlayerCompletedManaBoardCharacterIdsSync(playerId, allBoards),
    }))
    assert.deepEqual(result, expected)
    assert.equal(queries.length, 4)
    assert.equal(queries.reduce((total, q) => total + q.rows, 0), expected.completed.size + 3)
    const boardQuery = queries.find(q => q.sql.includes("json_each"))
    const planRows = prepare("EXPLAIN QUERY PLAN " + boardQuery.sql).all(...boardQuery.args).map(row => row.detail)
    assert.match(planRows[0], /SCAN board VIRTUAL TABLE/)
    const plan = planRows.join("\n")
    assert.match(plan, /SEARCH owned USING .*INDEX.*id=\?.*player_id=\?/)
    assert.match(plan, /SEARCH learned USING .*INDEX.*value=\?.*character_id=\?.*player_id=\?/)
})

test("wrong extra nodes, empty layouts and unowned characters cannot complete a board", () => {
    const playerId = seed()
    const required = board(211002)
    assert.ok(required.length > 1)
    learn(playerId, 211002, [...required.slice(0, -1), 999990001])
    assert.equal(character.getPlayerCharacterManaNodesSync(playerId, 211002).length, required.length)
    assert.deepEqual(character.getPlayerCompletedManaBoardCharacterIdsSync(playerId, {
        211002: required, 341005: [], 111001: board(111001),
    }), new Set())
    learn(playerId, 211002, required.slice(-1))
    // Completion is learned membership, irrespective of awakening/evolution levels.
    assert.deepEqual(character.getPlayerCompletedManaBoardCharacterIdsSync(playerId, { 211002: required }), new Set([211002]))
})

test("reused query plans see fresh progress and remain isolated between players", () => {
    const first = seed()
    const second = seed()
    const needs = { manaNodes: true, bondTokens: true, ownedCharacterIds: true }
    const initial = character.getPlayerCharacterMissionStatsSync(first, needs)
    const other = character.getPlayerCharacterMissionStatsSync(second, needs)
    const required = board(211002)
    const initialNodes = new Set(character.getPlayerCharacterManaNodesSync(first, 211002))
    learn(first, 211002, required)
    character.updatePlayerCharacterBondTokenSync(first, 211002, { manaBoardIndex: 1, status: 2 })
    const updated = character.getPlayerCharacterMissionStatsSync(first, needs)
    assert.equal(updated.manaNodeCount, initial.manaNodeCount + required.filter(id => !initialNodes.has(id)).length)
    assert.equal(updated.bondTokenCount, initial.bondTokenCount + 1)
    assert.deepEqual(character.getPlayerCharacterMissionStatsSync(second, needs), other)
    assert.equal(character.getPlayerCharacterFavorFactsSync(first, [211002])[211002].hasReceivedBondToken, true)
    assert.equal(character.getPlayerCharacterFavorFactsSync(second, [211002])[211002].hasReceivedBondToken, false)
    assert.deepEqual(character.getPlayerCompletedManaBoardCharacterIdsSync(first, { 211002: required }), new Set([211002]))
    assert.deepEqual(character.getPlayerCompletedManaBoardCharacterIdsSync(second, { 211002: required }), new Set())
})

test("count-only title conditions return scalar rows and scoped title calculations agree with full context", async () => {
    const playerId = seed()
    learn(playerId, 211002, [...board(211002, 1), ...board(211002)])
    character.updatePlayerCharacterBondTokenSync(playerId, 341005, { manaBoardIndex: 1, status: 3 })
    const computer = mission.getComputer(5)
    const { result: counts, queries } = await trace(() => computer.buildContext(playerId, 5, time, [5000, 6000]))
    assert.equal(queries.some(q => q.operation === "all"), false)
    assert.equal(queries.reduce((total, q) => total + q.rows, 0), 2)
    const expected = reference(playerId)
    assert.equal(computer.compute(5000, counts, 0), expected.nodes)
    assert.equal(computer.compute(6000, counts, 0), expected.bonds)
    const full = computer.buildContext(playerId, 5, time)
    const ids = mission.getDegreeMissionIdsForConditionTypes([7, 8, 44, 48])
    for (const id of ids) {
        const scoped = computer.buildContext(playerId, 5, time, [id])
        for (const progress of [0, 1, 9999]) assert.equal(computer.compute(id, scoped, progress), computer.compute(id, full, progress), String(id))
    }
})

test("completed titles skip fact reads while repairing missing ownership without duplicate rewards", async () => {
    const playerId = seed()
    const target = mission.getMissionFinalTargetProgress(5, 5000)
    const stages = mission.getMissionStageIds(5, 5000)
    missionData.updatePlayerCategoryMissionSync(playerId, 5, 5000, target)
    for (const stage of stages) missionData.updatePlayerCategoryMissionStageSync(playerId, 5, stage, 5000, true)
    const expectedDegrees = stages.flatMap(stage => getCategoryMissionRewardStageDefinition(5, 5000, stage).rewards)
        .filter(reward => reward.kind === 6).map(reward => reward.degreeId)
    assert.ok(expectedDegrees.length > 0)
    const before = inventory(playerId)
    const { result, queries } = await trace(() => settle(playerId, [5000]))
    noCharacterFactReads(queries)
    assert.deepEqual(result.evaluatedProgress, [{ category: 5, missionId: 5000, progress: target }])
    assert.deepEqual(result.settlement.missionInfo, [])
    for (const id of expectedDegrees) assert.equal(degreeData.hasPlayerDegreeSync(playerId, id), true)
    assert.deepEqual(inventory(playerId), before)
    const repeated = await trace(() => mission.settleMissionCategoriesAsync(playerId, [{ category: 5, missionIds: [5000] }], time))
    noCharacterFactReads(repeated.queries)
    assert.equal(repeated.queries.some(q => q.operation === "run"), false)
    assert.deepEqual(repeated.result.degreeIds, [])
})

test("unreceived completed stages grant once, retain old caps and respect future availability", async () => {
    const playerId = seed()
    missionData.updatePlayerCategoryMissionSync(playerId, 5, 5000, 1000)
    const first = await trace(() => settle(playerId, [5000]))
    noCharacterFactReads(first.queries)
    assert.equal(first.result.settlement.missionInfo.length, 1)
    assert.equal(first.result.evaluatedProgress[0].progress, 100)
    const before = inventory(playerId)
    assert.deepEqual(settle(playerId, [5000]).settlement.missionInfo, [])
    assert.deepEqual(inventory(playerId), before)
    missionData.updatePlayerCategoryMissionSync(playerId, 5, 5020, 3000)
    const closed = await trace(() => settle(playerId, [5020]))
    assert.deepEqual(closed.result.evaluatedProgress, [])
    noCharacterFactReads(closed.queries)
    const opened = await trace(() => settle(playerId, [5020], new Date("2051-01-01T00:00:00Z")))
    assert.equal(opened.result.settlement.missionInfo.length, 1)
    noCharacterFactReads(opened.queries)
})

test("mixed completed and pending titles scan only pending conditions and partial favor stages still advance", async () => {
    const playerId = seed()
    missionData.updatePlayerCategoryMissionSync(playerId, 5, 5000, 100)
    missionData.updatePlayerCategoryMissionStageSync(playerId, 5, 1, 5000, true)
    const mixed = await trace(() => settle(playerId, [5000, 6000]))
    assert.equal(mixed.queries.some(q => q.sql.includes("players_characters_mana_nodes")), false)
    assert.equal(mixed.queries.filter(q => q.sql.includes("token.status >= 2")).length, 1)
    character.updatePlayerCharacterBondTokenSync(playerId, 211002, { manaBoardIndex: 1, status: 2 })
    const first = settle(playerId, [211002])
    assert.equal(first.evaluatedProgress[0].progress, 1)
    const rarity = assets.getCharacterDataSync(211002).rarity
    character.updatePlayerCharacterSync(playerId, 211002, { exp: characterExpCaps[rarity].at(-1) })
    const advanced = settle(playerId, [211002])
    assert.equal(advanced.evaluatedProgress[0].progress, 2)
    assert.equal(advanced.settlement.missionInfo.length, 1)
    const repeated = await trace(() => settle(playerId, [211002]))
    noCharacterFactReads(repeated.queries)
    assert.deepEqual(repeated.result.settlement.missionInfo, [])
})
