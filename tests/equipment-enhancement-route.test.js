const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-enhancement-route-test-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const shopRoutes = require("../out/routes/api/shop").default
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const {
    getPlayerEquipmentSync,
    insertPlayerEquipmentSync,
} = require("../out/data/domains/equipment")
const {
    getPlayerItemSync,
    insertPlayerItemsSync,
} = require("../out/data/domains/item")

const CAPS = [1, 12, 23, 34, 45, 56, 69, 70, 77, 84, 91, 98, 99]
const WEAPONS = [
    { equipmentId: 5010070, shopItemIds: [1001, ...Array.from({ length: 12 }, (_, i) => 1003 + i)] },
    { equipmentId: 5020043, shopItemIds: [1002, ...Array.from({ length: 12 }, (_, i) => 1015 + i)] },
]

test("Liberator and Terminator each require 13 ordered one-crystal purchases", async t => {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    insertPlayerItemsSync(player.id, { "40313": 26 })
    for (const weapon of WEAPONS) {
        insertPlayerEquipmentSync(player.id, weapon.equipmentId, {
            level: 1,
            enhancementLevel: 0,
            protection: false,
            stack: 1,
        })
    }

    const viewerId = 886326327
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })

    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        if (contentType.startsWith("application/x-msgpack") && typeof payload === "object") {
            done(null, JSON.stringify(payload))
            return
        }
        done(null, payload)
    })
    await app.register(shopRoutes, { prefix: "/shop" })
    await app.ready()
    t.after(() => app.close())

    const buy = (shopItemId, number = 1) => app.inject({
        method: "POST",
        url: "/shop/buy",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            api_count: 1,
            shop_type: 10,
            shop_item_id: shopItemId,
            number,
        },
    })

    const skipped = await buy(1003, 11)
    assert.equal(skipped.statusCode, 400)
    assert.equal(getPlayerItemSync(player.id, 40313), 26)
    assert.equal(getPlayerEquipmentSync(player.id, 5010070).enhancementLevel, 0)

    let expectedCrystals = 26
    for (const weapon of WEAPONS) {
        let previousCap = 0
        for (const [index, shopItemId] of weapon.shopItemIds.entries()) {
            const cap = CAPS[index]
            const response = await buy(shopItemId, cap - previousCap)
            assert.equal(response.statusCode, 200, response.payload)
            expectedCrystals -= 1
            assert.equal(getPlayerItemSync(player.id, 40313), expectedCrystals)
            assert.equal(
                getPlayerEquipmentSync(player.id, weapon.equipmentId).enhancementLevel,
                cap,
            )
            previousCap = cap
        }
        const repeatedFinalStage = await buy(weapon.shopItemIds.at(-1), 1)
        assert.equal(repeatedFinalStage.statusCode, 400)
        assert.equal(getPlayerItemSync(player.id, 40313), expectedCrystals)
    }

    assert.equal(getPlayerItemSync(player.id, 40313), 0)
    assert.equal(getPlayerEquipmentSync(player.id, 5010070).enhancementLevel, 99)
    assert.equal(getPlayerEquipmentSync(player.id, 5020043).enhancementLevel, 99)
})
