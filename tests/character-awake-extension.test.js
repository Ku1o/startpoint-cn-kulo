const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-awake-extension-test-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const manaRoutes = require("../out/routes/api/character/mana").default
const { insertAccountSync } = require("../out/data/domains/account")
const { getPlayerSync, insertDefaultPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const {
    getPlayerCharacterSync,
    getPlayerCharacterManaNodesSync,
    getPlayerCharactersManaNodeAwakeLevelsSync,
    insertDefaultPlayerCharacterSync,
    insertPlayerCharacterManaNodesSync,
    updatePlayerCharacterManaNodeAwakeLevelSync,
    updatePlayerCharacterBondTokenSync,
    updatePlayerCharacterSync,
} = require("../out/data/domains/character")
const { upsertPlayerCharacterAwakeUnlockSync } = require("../out/data/domains/character_awake")
const { getPlayerItemSync, insertPlayerItemsSync } = require("../out/data/domains/item")
const { getCharacterDataSync, getCharacterManaNodesSync, getManaNodeAwakeCost } = require("../out/lib/assets")
const { getClientSerializedData } = require("../out/data/utils/player-data")
const {
    collectLinkedManaNodeAwakeUpdates,
    deferLinkedManaBoardAwakeLevels,
    resolveLinkedManaNodeBoardIndex,
} = require("../out/lib/character-awake-extension")

const CHARACTER_ID = 151045

function createApp() {
    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        if (contentType.startsWith("application/x-msgpack") && typeof payload === "object") {
            done(null, JSON.stringify(payload))
            return
        }
        done(null, payload)
    })
    app.register(manaRoutes, { prefix: "/character" })
    return app
}

function createSubject(viewerId) {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    insertDefaultPlayerCharacterSync(player.id, CHARACTER_ID)
    updatePlayerCharacterSync(player.id, CHARACTER_ID, {
        evolutionLevel: 1,
        manaBoardIndex: 1,
    })
    return insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    }).then(() => ({ player }))
}

test("夏日莉莉丝二板未点满时保持普通态，点满后整板同步觉醒", async t => {
    const app = createApp()
    await app.ready()
    t.after(() => app.close())

    const viewerId = 1510452026083001
    const { player } = await createSubject(viewerId)
    const board1 = getCharacterManaNodesSync(CHARACTER_ID, 1)
    const board2 = getCharacterManaNodesSync(CHARACTER_ID, 2)
    assert.ok(board1)
    assert.ok(board2)

    const skillEvolutionNodeId = Number(Object.entries(board1).find(([, node]) => (
        node.field5 === "2" && node.field6 === ""
    ))[0])
    const slot6NodeIds = Object.entries(board2)
        .filter(([, node]) => node.field6 === "6")
        .map(([nodeId]) => Number(nodeId))
    assert.ok(slot6NodeIds.length > 1)
    const lateNodeId = slot6NodeIds.at(-1)
    const learnedSlot6NodeIds = slot6NodeIds.slice(0, -1)
    const remainingBoard2NodeIds = Object.keys(board2).map(Number)
        .filter(nodeId => !learnedSlot6NodeIds.includes(nodeId))

    insertPlayerCharacterManaNodesSync(
        player.id,
        CHARACTER_ID,
        [...Object.keys(board1).map(Number), ...learnedSlot6NodeIds],
    )
    upsertPlayerCharacterAwakeUnlockSync(player.id, CHARACTER_ID, 1, 1)

    const rarity = getCharacterDataSync(CHARACTER_ID).rarity
    const awakeCost = getManaNodeAwakeCost(CHARACTER_ID, skillEvolutionNodeId, rarity)
    assert.ok(awakeCost)
    const requiredItems = { ...awakeCost.items }
    let remainingBoard2Mana = 0
    for (const nodeId of remainingBoard2NodeIds) {
        const node = board2[String(nodeId)]
        remainingBoard2Mana += node.manaCost
        for (const [itemId, amount] of Object.entries(node.items)) {
            requiredItems[itemId] = (requiredItems[itemId] ?? 0) + amount
        }
    }
    insertPlayerItemsSync(player.id, Object.fromEntries(
        Object.entries(requiredItems).map(([itemId, amount]) => [itemId, amount + 10]),
    ))
    updatePlayerSync({
        id: player.id,
        freeMana: awakeCost.manaAmount + remainingBoard2Mana + 100,
        paidMana: 0,
    })

    const awakened = await app.inject({
        method: "POST",
        url: "/character/awake_mana_node",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            character_id: CHARACTER_ID,
            api_count: 1,
            mana_node_multiplied_id_list: [skillEvolutionNodeId],
            awake_level: 1,
        },
    })
    assert.equal(awakened.statusCode, 200, awakened.payload)
    const awakenedNodeList = awakened.json().data.user_character_mana_node_list[String(CHARACTER_ID)]
    assert.deepEqual(
        new Set(awakenedNodeList.map(node => node.multiplied_id)),
        new Set([...Object.keys(board1).map(Number), ...learnedSlot6NodeIds]),
    )
    for (const nodeId of learnedSlot6NodeIds) {
        assert.equal(awakenedNodeList.find(node => node.multiplied_id === nodeId).awake_level, 0)
    }
    assert.equal(awakenedNodeList.some(node => node.multiplied_id === lateNodeId), false)
    assert.equal(getPlayerCharacterSync(player.id, CHARACTER_ID).evolutionLevel, 2)
    const levelsAfterAwake = getPlayerCharactersManaNodeAwakeLevelsSync(player.id)[String(CHARACTER_ID)]
    for (const nodeId of learnedSlot6NodeIds) assert.equal(levelsAfterAwake[nodeId], 0)
    assert.equal(levelsAfterAwake[lateNodeId], undefined)

    assert.equal(getPlayerCharacterSync(player.id, CHARACTER_ID).manaBoardIndex, 1)
    const replayedNodeId = learnedSlot6NodeIds[0]
    const manaBeforeReplay = getPlayerSync(player.id).freeMana
    const nodeCountBeforeReplay = getPlayerCharacterManaNodesSync(player.id, CHARACTER_ID).length
    const replayedItemId = Number(Object.keys(board2[String(replayedNodeId)].items)[0])
    const itemBeforeReplay = getPlayerItemSync(player.id, replayedItemId)
    const replayed = await app.inject({
        method: "POST",
        url: "/character/learn_mana_node",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            character_id: CHARACTER_ID,
            api_count: 2,
            mana_node_multiplied_id_list: [replayedNodeId],
        },
    })
    assert.equal(replayed.statusCode, 200, replayed.payload)
    assert.equal(getPlayerSync(player.id).freeMana, manaBeforeReplay)
    assert.equal(getPlayerCharacterManaNodesSync(player.id, CHARACTER_ID).length, nodeCountBeforeReplay)
    assert.equal(getPlayerItemSync(player.id, replayedItemId), itemBeforeReplay)
    assert.deepEqual(replayed.json().data.item_list, {})
    const replayedNodeList = replayed.json().data.user_character_mana_node_list[String(CHARACTER_ID)]
    assert.deepEqual(
        new Set(replayedNodeList.map(node => node.multiplied_id)),
        new Set([...Object.keys(board1).map(Number), ...learnedSlot6NodeIds]),
    )
    const replayedResponse = replayedNodeList
        .find(node => node.multiplied_id === replayedNodeId)
    assert.equal(replayedResponse.awake_level, 0)
    assert.equal(replayed.json().data.character_list[0].mana_board_awake?.[2], undefined)
    assert.equal(replayed.json().data.character_list[0].mana_board_index, 1)
    assert.equal(getPlayerCharacterSync(player.id, CHARACTER_ID).manaBoardIndex, 1)

    const learned = await app.inject({
        method: "POST",
        url: "/character/learn_mana_node",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            character_id: CHARACTER_ID,
            api_count: 2,
            mana_node_multiplied_id_list: remainingBoard2NodeIds,
        },
    })
    assert.equal(learned.statusCode, 200, learned.payload)
    const learnedData = learned.json().data
    const finalNodeList = learnedData.user_character_mana_node_list[String(CHARACTER_ID)]
    assert.deepEqual(
        new Set(finalNodeList.map(node => node.multiplied_id)),
        new Set([...Object.keys(board1).map(Number), ...Object.keys(board2).map(Number)]),
    )
    for (const nodeId of Object.keys(board2).map(Number)) {
        assert.equal(finalNodeList.find(node => node.multiplied_id === nodeId).awake_level, 1)
    }
    // Incremental common responses cannot update unsolicited mana-node levels
    // in the 1.8.1 client. Keep board 2 out of Awake mode until the next full
    // load initializes both structures together.
    assert.equal(learnedData.character_list[0].mana_board_awake?.[2], undefined)
    const finalLevels = getPlayerCharactersManaNodeAwakeLevelsSync(player.id)[String(CHARACTER_ID)]
    for (const nodeId of Object.keys(board2).map(Number)) assert.equal(finalLevels[nodeId], 1)
    assert.equal(getPlayerCharacterSync(player.id, CHARACTER_ID).manaBoardIndex, 2)
    const loadedAfterCompletion = getClientSerializedData(player.id, {})
    assert.equal(
        loadedAfterCompletion.user_character_list[String(CHARACTER_ID)].mana_board_awake[2],
        1,
    )
})

test("已完成二板的角色觉醒后保留板位与羁绊完成状态", async t => {
    const app = createApp()
    await app.ready()
    t.after(() => app.close())

    const viewerId = 1510452026083101
    const { player } = await createSubject(viewerId)
    const board1 = getCharacterManaNodesSync(CHARACTER_ID, 1)
    const board2 = getCharacterManaNodesSync(CHARACTER_ID, 2)
    assert.ok(board1)
    assert.ok(board2)

    const learnedNodeIds = [
        ...Object.keys(board1).map(Number),
        ...Object.keys(board2).map(Number),
    ]
    insertPlayerCharacterManaNodesSync(player.id, CHARACTER_ID, learnedNodeIds)
    updatePlayerCharacterSync(player.id, CHARACTER_ID, { manaBoardIndex: 2 })
    updatePlayerCharacterBondTokenSync(player.id, CHARACTER_ID, {
        manaBoardIndex: 1,
        status: 2,
    })
    updatePlayerCharacterBondTokenSync(player.id, CHARACTER_ID, {
        manaBoardIndex: 2,
        status: 2,
    })
    upsertPlayerCharacterAwakeUnlockSync(player.id, CHARACTER_ID, 1, 1)

    const skillEvolutionNodeId = Number(Object.entries(board1).find(([, node]) => (
        node.field5 === "2" && node.field6 === ""
    ))[0])
    const rarity = getCharacterDataSync(CHARACTER_ID).rarity
    const awakeCost = getManaNodeAwakeCost(CHARACTER_ID, skillEvolutionNodeId, rarity)
    assert.ok(awakeCost)
    insertPlayerItemsSync(player.id, Object.fromEntries(
        Object.entries(awakeCost.items).map(([itemId, amount]) => [itemId, amount + 10]),
    ))
    updatePlayerSync({
        id: player.id,
        freeMana: awakeCost.manaAmount + 100,
        paidMana: 0,
    })

    const awakened = await app.inject({
        method: "POST",
        url: "/character/awake_mana_node",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            character_id: CHARACTER_ID,
            api_count: 1,
            mana_node_multiplied_id_list: [skillEvolutionNodeId],
            awake_level: 1,
        },
    })
    assert.equal(awakened.statusCode, 200, awakened.payload)

    const data = awakened.json().data
    assert.equal(data.character_list[0].mana_board_index, 2)
    assert.deepEqual(data.character_list[0].bond_token_list, [
        { mana_board_index: 1, status: 2 },
        { mana_board_index: 2, status: 2 },
    ])
    assert.deepEqual(
        new Set(data.user_character_mana_node_list[String(CHARACTER_ID)]
            .map(node => node.multiplied_id)),
        new Set(learnedNodeIds),
    )
    assert.equal(data.character_list[0].mana_board_awake?.[2], undefined)
    for (const nodeId of Object.keys(board2).map(Number)) {
        assert.equal(
            data.user_character_mana_node_list[String(CHARACTER_ID)]
                .find(node => node.multiplied_id === nodeId).awake_level,
            1,
        )
    }

    const storedCharacter = getPlayerCharacterSync(player.id, CHARACTER_ID)
    assert.equal(storedCharacter.manaBoardIndex, 2)
    assert.deepEqual(storedCharacter.bondTokenList, [
        { manaBoardIndex: 1, status: 2 },
        { manaBoardIndex: 2, status: 2 },
    ])
    const loadedAfterAwakening = getClientSerializedData(player.id, {})
    assert.equal(
        loadedAfterAwakening.user_character_list[String(CHARACTER_ID)].mana_board_awake[2],
        1,
    )
})

test("扩展板只在整板完成后统一产生觉醒更新", () => {
    const board2 = getCharacterManaNodesSync(CHARACTER_ID, 2)
    const slot5Entry = Object.entries(board2).find(([, node]) => node.field6 === "5")
    const slot6Entry = Object.entries(board2).find(([, node]) => node.field6 === "6")
    const slot5Node = slot5Entry[1]
    const slot6Node = slot6Entry[1]
    const rarity = getCharacterDataSync(CHARACTER_ID).rarity
    assert.ok(getManaNodeAwakeCost(CHARACTER_ID, Number(slot5Entry[0]), rarity))
    assert.ok(getManaNodeAwakeCost(CHARACTER_ID, Number(slot6Entry[0]), rarity))
    assert.equal(resolveLinkedManaNodeBoardIndex(CHARACTER_ID, [Number(
        Object.entries(board2).find(([, node]) => node === slot6Node)[0],
    )], 2), 2)
    assert.equal(resolveLinkedManaNodeBoardIndex(CHARACTER_ID, [Number(
        Object.entries(board2).find(([, node]) => node === slot5Node)[0],
    )], 2), 2)

    const board2NodeIds = Object.keys(board2).map(Number)
    const incompleteUpdates = collectLinkedManaNodeAwakeUpdates(
        CHARACTER_ID,
        new Set(board2NodeIds.slice(0, -1)),
        new Map(),
        1,
    )
    assert.deepEqual(incompleteUpdates, [])

    const updates = collectLinkedManaNodeAwakeUpdates(
        CHARACTER_ID,
        new Set(board2NodeIds),
        new Map(),
        1,
    )
    assert.deepEqual(
        new Set(updates.map(update => update.nodeId)),
        new Set(board2NodeIds),
    )
    assert.deepEqual(
        deferLinkedManaBoardAwakeLevels(CHARACTER_ID, { 1: 1, 2: 1 }),
        { 1: 1 },
    )
})

test("加载旧存档时把已点满扩展板的局部觉醒修复为整板觉醒", async () => {
    const viewerId = 1510452026083102
    const { player } = await createSubject(viewerId)
    const board1 = getCharacterManaNodesSync(CHARACTER_ID, 1)
    const board2 = getCharacterManaNodesSync(CHARACTER_ID, 2)
    const board1NodeIds = Object.keys(board1).map(Number)
    const board2NodeIds = Object.keys(board2).map(Number)
    insertPlayerCharacterManaNodesSync(
        player.id,
        CHARACTER_ID,
        [...board1NodeIds, ...board2NodeIds],
    )
    updatePlayerCharacterSync(player.id, CHARACTER_ID, {
        evolutionLevel: 2,
        manaBoardIndex: 2,
    })
    for (const [nodeIdText, node] of Object.entries(board2)) {
        if (node.field6 !== "6") continue
        updatePlayerCharacterManaNodeAwakeLevelSync(
            player.id,
            CHARACTER_ID,
            Number(nodeIdText),
            1,
        )
    }

    const data = getClientSerializedData(player.id, {})
    assert.ok(data)
    assert.equal(data.user_character_list[String(CHARACTER_ID)].mana_board_awake[2], 1)
    const responseNodeList = data.user_character_mana_node_list[String(CHARACTER_ID)]
    for (const nodeId of board2NodeIds) {
        assert.equal(responseNodeList.find(node => node.multiplied_id === nodeId).awake_level, 1)
    }
    const storedLevels = getPlayerCharactersManaNodeAwakeLevelsSync(player.id)[String(CHARACTER_ID)]
    for (const nodeId of board2NodeIds) assert.equal(storedLevels[nodeId], 1)
})
