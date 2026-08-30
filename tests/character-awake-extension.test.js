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
const { insertDefaultPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const {
    getPlayerCharacterSync,
    getPlayerCharactersManaNodeAwakeLevelsSync,
    insertDefaultPlayerCharacterSync,
    insertPlayerCharacterManaNodesSync,
    updatePlayerCharacterSync,
} = require("../out/data/domains/character")
const { upsertPlayerCharacterAwakeUnlockSync } = require("../out/data/domains/character_awake")
const { insertPlayerItemsSync } = require("../out/data/domains/item")
const { getCharacterDataSync, getCharacterManaNodesSync, getManaNodeAwakeCost } = require("../out/lib/assets")
const {
    collectLinkedManaNodeAwakeUpdates,
    getInheritedLinkedManaNodeAwakeLevel,
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

test("夏日莉莉丝二板能力6只联动已学习节点，后学习节点继承觉醒等级", async t => {
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

    insertPlayerCharacterManaNodesSync(
        player.id,
        CHARACTER_ID,
        [...Object.keys(board1).map(Number), ...learnedSlot6NodeIds],
    )
    upsertPlayerCharacterAwakeUnlockSync(player.id, CHARACTER_ID, 1, 1)

    const rarity = getCharacterDataSync(CHARACTER_ID).rarity
    const awakeCost = getManaNodeAwakeCost(CHARACTER_ID, skillEvolutionNodeId, rarity)
    assert.ok(awakeCost)
    const lateNode = board2[String(lateNodeId)]
    const requiredItems = { ...awakeCost.items }
    for (const [itemId, amount] of Object.entries(lateNode.items)) {
        requiredItems[itemId] = (requiredItems[itemId] ?? 0) + amount
    }
    insertPlayerItemsSync(player.id, Object.fromEntries(
        Object.entries(requiredItems).map(([itemId, amount]) => [itemId, amount + 10]),
    ))
    updatePlayerSync({
        id: player.id,
        freeMana: awakeCost.manaAmount + lateNode.manaCost + 100,
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
    assert.equal(getPlayerCharacterSync(player.id, CHARACTER_ID).evolutionLevel, 2)
    const levelsAfterAwake = getPlayerCharactersManaNodeAwakeLevelsSync(player.id)[String(CHARACTER_ID)]
    for (const nodeId of learnedSlot6NodeIds) assert.equal(levelsAfterAwake[nodeId], 1)
    assert.equal(levelsAfterAwake[lateNodeId], undefined)

    updatePlayerCharacterSync(player.id, CHARACTER_ID, { manaBoardIndex: 2 })
    const learned = await app.inject({
        method: "POST",
        url: "/character/learn_mana_node",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            character_id: CHARACTER_ID,
            api_count: 2,
            mana_node_multiplied_id_list: [lateNodeId],
        },
    })
    assert.equal(learned.statusCode, 200, learned.payload)
    const lateResponse = learned.json().data.user_character_mana_node_list[String(CHARACTER_ID)]
        .find(node => node.multiplied_id === lateNodeId)
    assert.equal(lateResponse.awake_level, 1)
    const finalLevels = getPlayerCharactersManaNodeAwakeLevelsSync(player.id)[String(CHARACTER_ID)]
    assert.equal(finalLevels[lateNodeId], 1)
})

test("非配置槽位和未觉醒角色不会继承二板觉醒等级", () => {
    const board2 = getCharacterManaNodesSync(CHARACTER_ID, 2)
    const slot5Node = Object.values(board2).find(node => node.field6 === "5")
    const slot6Node = Object.values(board2).find(node => node.field6 === "6")
    assert.equal(getInheritedLinkedManaNodeAwakeLevel(CHARACTER_ID, 2, slot5Node, 2), 0)
    assert.equal(getInheritedLinkedManaNodeAwakeLevel(CHARACTER_ID, 2, slot6Node, 1), 0)
    assert.equal(getInheritedLinkedManaNodeAwakeLevel(CHARACTER_ID, 2, slot6Node, 2), 1)

    const learnedIds = new Set(Object.keys(board2).map(Number))
    const updates = collectLinkedManaNodeAwakeUpdates(
        CHARACTER_ID,
        learnedIds,
        new Map(),
        1,
    )
    assert.deepEqual(
        new Set(updates.map(update => String(board2[String(update.nodeId)].field6))),
        new Set(["6"]),
    )
})
