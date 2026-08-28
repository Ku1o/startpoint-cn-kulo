require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")

const dataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "character-awake-refresh-db-"))
const previousDataDirectory = process.env.DATA_DIR
process.env.DATA_DIR = dataDirectory
let db
let restoreTimeOffset = () => {}

function cleanup() {
    if (db?.open) db.close()
    restoreTimeOffset()
    fs.rmSync(dataDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
}

process.once("exit", cleanup)

const { initializeDatabase } = require("../src/data")
const { insertAccountSync } = require("../src/data/domains/account")
const {
    insertDefaultPlayerCharacterSync,
    insertPlayerCharacterManaNodesSync,
    updatePlayerCharacterSync,
} = require("../src/data/domains/character")
const { getPlayerCharacterAwakeUnlocksSync } = require("../src/data/domains/character_awake")
const { insertDefaultPlayerSync } = require("../src/data/domains/player")
const { getCharacterDataSync, getCharacterManaNodesSync } = require("../src/lib/assets")
const { characterExpCaps } = require("../src/lib/character")
const {
    getAwakeBattleMissionIds,
    mergeMissionSettlementResponse,
    settleAwakeMissionCandidates,
} = require("../src/lib/mission")
const missionRoutes = require("../src/routes/api/mission").default
const { getTimeOffset, setServerTimeOffset } = require("../src/utils")

const previousTimeOffset = getTimeOffset()
restoreTimeOffset = () => setServerTimeOffset(previousTimeOffset)
setServerTimeOffset(Date.parse("2025-01-01T12:00:00.000Z") - Date.now())

function decode(response) {
    assert.match(response.headers["content-type"], /^application\/x-msgpack/)
    return unpack(Buffer.from(response.body, "base64"))
}

async function main() {
    db = initializeDatabase()
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `character-awake-refresh-${randomUUID()}`,
        status: "normal",
    })
    const playerId = insertDefaultPlayerSync(account.id).id
    const characterId = 341005
    const incompleteCharacterId = 211002
    insertDefaultPlayerCharacterSync(playerId, characterId)
    insertDefaultPlayerCharacterSync(playerId, incompleteCharacterId)
    const rarity = getCharacterDataSync(characterId).rarity
    updatePlayerCharacterSync(playerId, characterId, { exp: characterExpCaps[rarity][0] })
    insertPlayerCharacterManaNodesSync(
        playerId,
        characterId,
        Object.keys(getCharacterManaNodesSync(characterId, 1)).map(Number),
    )
    db.prepare(`
        INSERT INTO players_character_quest_clears (
            player_id, character_id, clear_count, multi_count,
            leader_clear_count, leader_multi_count, leader_power_flip_count
        ) VALUES (?, ?, 5, 0, 0, 0, 0)
    `).run(playerId, characterId)

    const viewerId = 830000000 + playerId
    db.prepare(`
        INSERT INTO sessions (token, account_id, expires, type)
        VALUES (?, ?, ?, 2)
    `).run(String(viewerId), account.id, new Date("2099-01-01T00:00:00.000Z").toISOString())

    const evaluationTime = new Date("2025-01-01T12:00:00.000Z")
    const battleMissionIds = getAwakeBattleMissionIds([
        characterId,
        incompleteCharacterId,
    ])
    const firstBattleSettlement = settleAwakeMissionCandidates(
        playerId,
        battleMissionIds,
        evaluationTime,
    )
    assert.ok(firstBattleSettlement.missionInfo.length > 0)
    assert.deepEqual(getPlayerCharacterAwakeUnlocksSync(playerId).get(String(characterId)), { 1: 1 })

    const battleResponse = {
        character_list: [{ character_id: characterId, preserved_field: "keep" }],
        item_list: {},
        equipment_list: [],
    }
    mergeMissionSettlementResponse(battleResponse, firstBattleSettlement, viewerId)
    assert.equal(battleResponse.character_list.length, 1)
    assert.equal(battleResponse.character_list[0].preserved_field, "keep")
    assert.deepEqual(
        battleResponse.character_list.find(entry => entry.character_id === characterId)?.mana_board_awake,
        { 1: 1 },
    )
    assert.equal(
        getPlayerCharacterAwakeUnlocksSync(playerId).get(String(incompleteCharacterId)),
        undefined,
    )

    const itemAmountsAfterFirstBattle = Object.fromEntries(
        [13, 14, 15, 16].map(itemId => [itemId, db.prepare(`
            SELECT amount FROM players_items WHERE player_id = ? AND id = ?
        `).get(playerId, itemId)?.amount ?? 0]),
    )
    const repeatedBattleSettlement = settleAwakeMissionCandidates(
        playerId,
        battleMissionIds,
        evaluationTime,
    )
    assert.deepEqual(repeatedBattleSettlement.missionInfo, [])
    assert.deepEqual(
        repeatedBattleSettlement.characterList.find(
            entry => entry.character_id === characterId,
        )?.mana_board_awake,
        { 1: 1 },
    )
    assert.deepEqual(
        Object.fromEntries([13, 14, 15, 16].map(itemId => [itemId, db.prepare(`
            SELECT amount FROM players_items WHERE player_id = ? AND id = ?
        `).get(playerId, itemId)?.amount ?? 0])),
        itemAmountsAfterFirstBattle,
    )

    const app = Fastify()
    app.addHook("onSend", (_request, reply, payload, done) => {
        if (reply.getHeader("content-type") === "application/x-msgpack") {
            done(null, pack(payload).toString("base64"))
            return
        }
        done(null, payload)
    })
    await app.register(missionRoutes, { prefix: "/mission" })
    await app.ready()

    const requestAwakePage = apiCount => app.inject({
        method: "POST",
        url: "/mission/get_mission_progress",
        payload: {
            viewer_id: viewerId,
            api_count: apiCount,
            category_list: [{ category: 9, character_id: characterId }],
        },
    })

    const first = await requestAwakePage(1)
    assert.equal(first.statusCode, 200, first.body)
    const firstData = decode(first).data
    assert.deepEqual(firstData.mission_progress_list.map(entry => entry.mission_id), [
        3410051, 3410052, 3410053, 3410054,
    ])
    assert.deepEqual(
        firstData.character_list.find(entry => entry.character_id === characterId)?.mana_board_awake,
        { 1: 1 },
    )
    // CN 1.8.1 filters common-response active_mission_list through the
    // ordinary ActiveMissionRepository. Category 9 IDs are rejected there,
    // so the recovery response updates the saved character state. A scene
    // that was already prepared must be left and entered again to read it.
    assert.equal(firstData.active_mission_list, undefined)

    const itemAmountsAfterFirst = Object.fromEntries(
        [13, 14, 15, 16].map(itemId => [itemId, db.prepare(`
            SELECT amount FROM players_items WHERE player_id = ? AND id = ?
        `).get(playerId, itemId)?.amount ?? 0]),
    )
    const repeated = await requestAwakePage(2)
    assert.equal(repeated.statusCode, 200, repeated.body)
    const repeatedData = decode(repeated).data
    assert.deepEqual(repeatedData.mission_info, [])
    assert.deepEqual(
        repeatedData.character_list.find(entry => entry.character_id === characterId)?.mana_board_awake,
        { 1: 1 },
    )
    assert.equal(repeatedData.active_mission_list, undefined)
    assert.deepEqual(
        Object.fromEntries([13, 14, 15, 16].map(itemId => [itemId, db.prepare(`
            SELECT amount FROM players_items WHERE player_id = ? AND id = ?
        `).get(playerId, itemId)?.amount ?? 0])),
        itemAmountsAfterFirst,
    )

    await app.close()
    cleanup()
    process.removeListener("exit", cleanup)
}

main().then(
    () => console.log("character awake immediate refresh tests passed"),
    error => {
        console.error(error)
        process.exitCode = 1
    },
)
