const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

process.env.DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-shop-period-test-"))

const Fastify = require("fastify")
const shopRoutes = require("../out/routes/api/shop").default
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const { getPlayerItemSync, givePlayerItemSync } = require("../out/data/domains/item")
const { getPlayerShopPurchaseCountSync } = require("../out/data/domains/shopPurchase")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const { setServerTime } = require("../out/utils")

test("活动商品的单买和批量购买都执行兑换期校验", async t => {
    const account = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "leiting", idpId: "", status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    givePlayerItemSync(player.id, 2370001, 600)

    const viewerId = 77119912
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
    t.after(async () => {
        setServerTime(null)
        await app.close()
    })

    const post = (url, payload) => app.inject({
        method: "POST",
        url: `/shop/${url}`,
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, api_count: 1, ...payload },
    })

    setServerTime(new Date("2024-01-01T00:00:00.000Z"))
    const expiredSingle = await post("buy", {
        shop_type: 4,
        shop_item_id: 700000,
        number: 1,
    })
    assert.equal(expiredSingle.statusCode, 400)
    assert.equal(getPlayerItemSync(player.id, 2370001), 600)
    assert.equal(getPlayerItemSync(player.id, 49100), null)
    assert.equal(getPlayerShopPurchaseCountSync(player.id, 700000), 0)

    setServerTime(new Date("2023-11-24T00:00:00.000Z"))
    const activeSingle = await post("buy", {
        shop_type: 4,
        shop_item_id: 700000,
        number: 1,
    })
    assert.equal(activeSingle.statusCode, 200, activeSingle.payload)
    assert.equal(getPlayerItemSync(player.id, 2370001), 400)
    assert.equal(getPlayerItemSync(player.id, 49100), 1)
    assert.equal(getPlayerShopPurchaseCountSync(player.id, 700000), 1)

    setServerTime(new Date("2025-07-26T00:00:00.000Z"))
    const rerunSales = await post("get_sales_list", {
        shop_types: [],
        boss_coin_shop_category_ids: [],
        event_list: [{ event_type: 11, event_ids: [700011] }],
    })
    assert.equal(rerunSales.statusCode, 200, rerunSales.payload)
    const rerunSalesList = JSON.parse(rerunSales.payload).data.sales_list
    assert.equal(rerunSalesList.length, 33)
    assert.ok(rerunSalesList.some(item => item.shop_type === 4 && item.shop_item_id === 700000))

    const rerunSingle = await post("buy", {
        shop_type: 4,
        shop_item_id: 700000,
        number: 1,
    })
    assert.equal(rerunSingle.statusCode, 200, rerunSingle.payload)
    assert.equal(getPlayerItemSync(player.id, 2370001), 200)
    assert.equal(getPlayerItemSync(player.id, 49100), 2)
    assert.equal(getPlayerShopPurchaseCountSync(player.id, 700000), 2)

    setServerTime(new Date("2025-08-15T00:00:00.000Z"))
    const expiredBulk = await post("bulk_buy", {
        shop_type: 4,
        buy_item_list: { "700000": 1 },
    })
    assert.equal(expiredBulk.statusCode, 200, expiredBulk.payload)
    assert.equal(getPlayerItemSync(player.id, 2370001), 200)
    assert.equal(getPlayerItemSync(player.id, 49100), 2)
    assert.equal(getPlayerShopPurchaseCountSync(player.id, 700000), 2)
})
