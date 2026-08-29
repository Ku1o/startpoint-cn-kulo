const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-shop-degree-test-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const shopRoutes = require("../out/routes/api/shop").default
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, getPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const { hasPlayerDegreeSync } = require("../out/data/domains/degree")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")

test("深渊商店称号按一次性库存原子购买，并阻止重复扣款", async t => {
    const account = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "leiting", idpId: "", status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    updatePlayerSync({ id: player.id, freeVmoney: 5_000_000, vmoney: 0 })
    saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 77119911
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })

    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        done(null, contentType.startsWith("application/x-msgpack") && typeof payload === "object"
            ? JSON.stringify(payload)
            : payload)
    })
    await app.register(shopRoutes, { prefix: "/shop" })
    await app.ready()
    t.after(() => app.close())

    const buy = () => app.inject({
        method: "POST",
        url: "/shop/buy",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            api_count: 1,
            shop_type: 4,
            shop_item_id: 9700118,
            number: 1,
        },
    })

    const first = await buy()
    assert.equal(first.statusCode, 200, first.payload)
    const firstBody = JSON.parse(first.payload)
    assert.equal(getPlayerSync(player.id).freeVmoney, 0)
    assert.equal(hasPlayerDegreeSync(player.id, 9900006), true)
    assert.deepEqual(firstBody.data.degree_list, [{ viewer_id: viewerId, degree_id: 9900006 }])

    const repeated = await buy()
    assert.equal(repeated.statusCode, 400)
    assert.equal(getPlayerSync(player.id).freeVmoney, 0)

    const sales = await app.inject({
        method: "POST",
        url: "/shop/get_sales_list",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            shop_types: [],
            boss_coin_shop_category_ids: [],
            equipment_enhancement_shop_category_ids: [],
            browse_treasure_flag: false,
            event_list: [{ event_type: 11, event_ids: [700099] }],
        },
    })
    assert.equal(sales.statusCode, 200, sales.payload)
    const titleSale = JSON.parse(sales.payload).data.sales_list
        .find(row => row.shop_item_id === 9700118)
    assert.equal(titleSale.stock_quantity, 0)
    assert.equal(titleSale.total_purchase_num, 1)
})
