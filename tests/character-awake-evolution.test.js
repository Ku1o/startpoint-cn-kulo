const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-awake-evolution-test-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const manaRoutes = require("../out/routes/api/character/mana").default
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, getPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const {
    getPlayerCharacterSync,
    insertDefaultPlayerCharacterSync,
    insertPlayerCharacterManaNodesSync,
    updatePlayerCharacterManaNodeAwakeLevelSync,
    updatePlayerCharacterSync,
} = require("../out/data/domains/character")
const { upsertPlayerCharacterAwakeUnlockSync } = require("../out/data/domains/character_awake")
const { insertPlayerItemsSync } = require("../out/data/domains/item")
const { getCharacterDataSync, getCharacterManaNodesSync, getManaNodeAwakeCost } = require("../out/lib/assets")

// Existing retail-awakenable character used only as a stable schema fixture.
const CHARACTER_ID = 341005

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

async function createSubject(viewerId) {
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

    const board1 = getCharacterManaNodesSync(CHARACTER_ID, 1)
    assert.ok(board1)
    insertPlayerCharacterManaNodesSync(player.id, CHARACTER_ID, Object.keys(board1).map(Number))
    upsertPlayerCharacterAwakeUnlockSync(player.id, CHARACTER_ID, 1, 1)

    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })
    return { board1, player }
}

function getSkillEvolutionNodeId(board1) {
    const entry = Object.entries(board1).find(([, node]) => node.field5 === "2" && node.field6 === "")
    assert.ok(entry, "official awake board should contain a skill-evolution node")
    return Number(entry[0])
}

function awakeRequest(app, viewerId, skillEvolutionNodeId) {
    return app.inject({
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
}

test("官方觉醒角色的技能节点会持久化进化等级，并可幂等修复旧存档", async t => {
    const app = createApp()
    await app.ready()
    t.after(() => app.close())

    const freshViewerId = 3410052026082901
    const fresh = await createSubject(freshViewerId)
    const skillEvolutionNodeId = getSkillEvolutionNodeId(fresh.board1)
    const rarity = getCharacterDataSync(CHARACTER_ID).rarity
    const cost = getManaNodeAwakeCost(CHARACTER_ID, skillEvolutionNodeId, rarity)
    assert.ok(cost)
    insertPlayerItemsSync(fresh.player.id, Object.fromEntries(
        Object.entries(cost.items).map(([itemId, amount]) => [itemId, amount + 10]),
    ))
    updatePlayerSync({
        id: fresh.player.id,
        freeMana: cost.manaAmount + 100,
        paidMana: 0,
    })

    const awakened = await awakeRequest(app, freshViewerId, skillEvolutionNodeId)
    assert.equal(awakened.statusCode, 200, awakened.payload)
    const awakenedData = awakened.json().data
    assert.equal(awakenedData.character_list[0].evolution_level, 2)
    assert.equal(awakenedData.character_list[0].evolution_img_level, 2)
    assert.deepEqual(awakenedData.evolution, {
        character_id: CHARACTER_ID,
        level: 2,
        img_level: 2,
    })
    assert.equal(getPlayerCharacterSync(fresh.player.id, CHARACTER_ID).evolutionLevel, 2)

    const legacyViewerId = 3410052026082902
    const legacy = await createSubject(legacyViewerId)
    const legacySkillNodeId = getSkillEvolutionNodeId(legacy.board1)
    updatePlayerCharacterManaNodeAwakeLevelSync(
        legacy.player.id,
        CHARACTER_ID,
        legacySkillNodeId,
        1,
    )
    updatePlayerSync({ id: legacy.player.id, freeMana: 7777, paidMana: 0 })

    const repaired = await awakeRequest(app, legacyViewerId, legacySkillNodeId)
    assert.equal(repaired.statusCode, 200, repaired.payload)
    assert.equal(repaired.json().data.character_list[0].evolution_level, 2)
    assert.equal(getPlayerCharacterSync(legacy.player.id, CHARACTER_ID).evolutionLevel, 2)
    assert.equal(getPlayerSync(legacy.player.id).freeMana, 7777)

    const repeated = await awakeRequest(app, legacyViewerId, legacySkillNodeId)
    assert.equal(repeated.statusCode, 200, repeated.payload)
    assert.deepEqual(repeated.json().data.evolution, [])
    assert.equal(getPlayerSync(legacy.player.id).freeMana, 7777)
})
