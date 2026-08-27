const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-shop-deduction-test-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const shopRoutes = require("../out/routes/api/shop").default
const { computeFreeFirstDeduction } = require("../out/lib/free-first-deduction")
const {
    executeGenericShopPurchaseSync,
    ShopBalanceError,
} = require("../out/lib/event-shop-purchase")
const { insertAccountSync } = require("../out/data/domains/account")
const {
    getPlayerSync,
    insertDefaultPlayerSync,
    updatePlayerSync,
} = require("../out/data/domains/player")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const treasureShop = require("../assets/treasure_shop.json")

test("free-first deduction covers free, mixed, paid, and insufficient balances", () => {
    assert.deepEqual(computeFreeFirstDeduction(100, 50, 80), {
        freeBalance: 20,
        paidBalance: 50,
        freeSpent: 80,
        paidSpent: 0,
    })
    assert.deepEqual(computeFreeFirstDeduction(30, 70, 80), {
        freeBalance: 0,
        paidBalance: 20,
        freeSpent: 30,
        paidSpent: 50,
    })
    assert.deepEqual(computeFreeFirstDeduction(0, 100, 80), {
        freeBalance: 0,
        paidBalance: 20,
        freeSpent: 0,
        paidSpent: 80,
    })
    assert.equal(computeFreeFirstDeduction(30, 40, 80), null)
    assert.equal(computeFreeFirstDeduction(-1, 100, 50), null)
    assert.equal(computeFreeFirstDeduction(100, 100, 1.5), null)
})

function createGenericShopDependencies(initialPlayer) {
    let player = { ...initialPlayer }
    let manaSpent = 0
    let updateCount = 0
    return {
        dependencies: {
            transaction: operation => operation(),
            getPlayer: () => ({ ...player }),
            updatePlayer: nextPlayer => {
                player = { ...nextPlayer }
                updateCount++
            },
            getItem: () => 0,
            setItem: () => {},
            getPurchaseCount: () => 0,
            addPurchaseCount: (_playerId, _shopItemId, amount) => amount,
            recordManaSpent: (_playerId, amount) => {
                manaSpent += amount
            },
            grantRewards: () => ({
                user_info: { free_mana: 0, free_vmoney: 0, exp_pool: 0 },
                character_list: [],
                joined_character_id_list: [],
                equipment_list: [],
                items: {},
            }),
        },
        getPlayer: () => ({ ...player }),
        getManaSpent: () => manaSpent,
        getUpdateCount: () => updateCount,
    }
}

function genericShopItem(userCost) {
    return {
        costs: [],
        rewards: [],
        availableFrom: "2020-01-01 00:00:00",
        availableUntil: null,
        stock: 10,
        userCost,
    }
}

test("generic shop helper spends mixed mana and beads free-first", () => {
    const manaStore = createGenericShopDependencies({
        id: 1,
        freeMana: 20,
        paidMana: 40,
        freeVmoney: 0,
        vmoney: 0,
        bondToken: 0,
        expPool: 0,
    })
    executeGenericShopPurchaseSync({
        playerId: 1,
        shopItemId: 1,
        purchaseAmount: 1,
        shopItem: genericShopItem({ type: 1, amount: 50 }),
        nowMs: Date.now(),
        enforcePeriod: false,
    }, manaStore.dependencies)
    assert.equal(manaStore.getPlayer().freeMana, 0)
    assert.equal(manaStore.getPlayer().paidMana, 10)
    assert.equal(manaStore.getManaSpent(), 50)

    const beadStore = createGenericShopDependencies({
        id: 2,
        freeMana: 0,
        paidMana: 0,
        freeVmoney: 20,
        vmoney: 40,
        bondToken: 0,
        expPool: 0,
    })
    executeGenericShopPurchaseSync({
        playerId: 2,
        shopItemId: 2,
        purchaseAmount: 1,
        shopItem: genericShopItem({ type: 0, amount: 50 }),
        nowMs: Date.now(),
        enforcePeriod: false,
    }, beadStore.dependencies)
    assert.equal(beadStore.getPlayer().freeVmoney, 0)
    assert.equal(beadStore.getPlayer().vmoney, 10)

    const insufficientStore = createGenericShopDependencies({
        id: 3,
        freeMana: 20,
        paidMana: 20,
        freeVmoney: 0,
        vmoney: 0,
        bondToken: 0,
        expPool: 0,
    })
    assert.throws(() => executeGenericShopPurchaseSync({
        playerId: 3,
        shopItemId: 3,
        purchaseAmount: 1,
        shopItem: genericShopItem({ type: 1, amount: 50 }),
        nowMs: Date.now(),
        enforcePeriod: false,
    }, insufficientStore.dependencies), ShopBalanceError)
    assert.equal(insufficientStore.getUpdateCount(), 0)
})

test("shop routes use mixed balances without changing insufficient behavior", async t => {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 886326326
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

    const post = (url, payload) => app.inject({
        method: "POST",
        url: `/shop/${url}`,
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, api_count: 1, ...payload },
    })
    const body = response => JSON.parse(response.payload)

    await t.test("single mana purchase consumes paid overflow", async () => {
        updatePlayerSync({ id: player.id, freeMana: 260, paidMana: 3000 })
        const response = await post("buy", {
            shop_type: 2,
            shop_item_id: 200092,
            number: 1,
        })
        assert.equal(response.statusCode, 200)
        const current = getPlayerSync(player.id)
        assert.equal(current.freeMana, 0)
        assert.equal(current.paidMana, 260)
        assert.equal(body(response).data.user_info.free_mana, 0)
        assert.equal(body(response).data.user_info.paid_mana, 260)
    })

    await t.test("single bead purchase consumes paid overflow", async () => {
        const originalCost = treasureShop["200003"].userCost
        treasureShop["200003"].userCost = { type: 0, amount: 50 }
        try {
            updatePlayerSync({ id: player.id, freeVmoney: 20, vmoney: 30 })
            const response = await post("buy", {
                shop_type: 2,
                shop_item_id: 200003,
                number: 1,
            })
            assert.equal(response.statusCode, 200)
            const current = getPlayerSync(player.id)
            assert.equal(current.freeVmoney, 0)
            assert.equal(current.vmoney, 0)
            assert.equal(body(response).data.user_info.free_vmoney, 0)
            assert.equal(body(response).data.user_info.vmoney, 0)
        } finally {
            treasureShop["200003"].userCost = originalCost
        }
    })

    await t.test("bulk purchase calculates quantity from combined mana", async () => {
        updatePlayerSync({ id: player.id, freeMana: 500, paidMana: 1500 })
        const response = await post("bulk_buy", {
            shop_type: 2,
            buy_item_list: { "200091": 1 },
        })
        assert.equal(response.statusCode, 200)
        const current = getPlayerSync(player.id)
        assert.equal(current.freeMana, 0)
        assert.equal(current.paidMana, 0)
        assert.equal(body(response).data.user_info.free_mana, 0)
        assert.equal(body(response).data.user_info.paid_mana, 0)
    })

    await t.test("bulk purchase calculates quantity from combined beads", async () => {
        const originalCost = treasureShop["200004"].userCost
        treasureShop["200004"].userCost = { type: 0, amount: 50 }
        try {
            updatePlayerSync({ id: player.id, freeVmoney: 20, vmoney: 30 })
            const response = await post("bulk_buy", {
                shop_type: 2,
                buy_item_list: { "200004": 1 },
            })
            assert.equal(response.statusCode, 200)
            const current = getPlayerSync(player.id)
            assert.equal(current.freeVmoney, 0)
            assert.equal(current.vmoney, 0)
            assert.equal(body(response).data.user_info.free_vmoney, 0)
            assert.equal(body(response).data.user_info.vmoney, 0)
        } finally {
            treasureShop["200004"].userCost = originalCost
        }
    })

    await t.test("stamina recovery consumes paid bead overflow", async () => {
        updatePlayerSync({
            id: player.id,
            stamina: 10,
            staminaHealTime: new Date(),
            freeVmoney: 20,
            vmoney: 30,
        })
        const response = await post("recover_stamina", {})
        assert.equal(response.statusCode, 200)
        const current = getPlayerSync(player.id)
        assert.equal(current.freeVmoney, 0)
        assert.equal(current.vmoney, 0)
        assert.ok(current.stamina >= 100)
        assert.equal(body(response).data.user_info.stamina, current.stamina)
        assert.equal(body(response).data.user_info.free_vmoney, 0)
        assert.equal(body(response).data.user_info.vmoney, 0)
    })

    await t.test("combined insufficient mana still rejects without deduction", async () => {
        updatePlayerSync({ id: player.id, freeMana: 100, paidMana: 100 })
        const response = await post("buy", {
            shop_type: 2,
            shop_item_id: 200001,
            number: 1,
        })
        assert.equal(response.statusCode, 400)
        const current = getPlayerSync(player.id)
        assert.equal(current.freeMana, 100)
        assert.equal(current.paidMana, 100)
    })
})
