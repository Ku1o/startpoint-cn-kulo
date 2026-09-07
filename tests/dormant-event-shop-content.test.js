const test = require("node:test")
const assert = require("node:assert/strict")

const baseEventShops = require("../assets/event_item_shop.json")
const baseEventShopIdMap = require("../assets/event_item_shop_id_map.json")
const rankEventShops = require("../assets/event_item_shop_rank_p5b.json")
const rankEventShopIdMap = require("../assets/event_item_shop_id_map_rank_p5b.json")
const {
    serverEventShops,
    serverEventShopIdMap,
} = require("../out/lib/content-master")
const {
    getEventShopItemsSync,
    getShopItemSync,
} = require("../out/lib/assets")

const DEATH_BRINGER_SHOP_ITEM_ID = "59001010"

test("Five Boss 关闭时不暴露死亡使者兑换，但保留原始备用定义", () => {
    const rawDeathBringer = baseEventShops["2"]["59001"][DEATH_BRINGER_SHOP_ITEM_ID]
    assert.deepEqual(rawDeathBringer.rewards, [{ type: 4, id: 5900101, count: 1 }])
    assert.deepEqual(baseEventShopIdMap[DEATH_BRINGER_SHOP_ITEM_ID], {
        eventType: 2,
        eventId: 59001,
    })

    assert.equal(serverEventShops["2"]["59001"][DEATH_BRINGER_SHOP_ITEM_ID], undefined)
    assert.equal(serverEventShopIdMap[DEATH_BRINGER_SHOP_ITEM_ID], undefined)
    assert.equal(
        getEventShopItemsSync(2, 59001)[DEATH_BRINGER_SHOP_ITEM_ID],
        undefined,
    )
    assert.equal(getShopItemSync(4, DEATH_BRINGER_SHOP_ITEM_ID), null)

    const expectedShops = structuredClone(baseEventShops)
    expectedShops["11"] = {
        ...expectedShops["11"],
        "700099": {
            ...expectedShops["11"]?.["700099"],
            ...rankEventShops["11"]?.["700099"],
        },
    }
    delete expectedShops["2"]["59001"][DEATH_BRINGER_SHOP_ITEM_ID]
    assert.deepEqual(serverEventShops, expectedShops)

    const expectedIdMap = {
        ...baseEventShopIdMap,
        ...rankEventShopIdMap,
    }
    delete expectedIdMap[DEATH_BRINGER_SHOP_ITEM_ID]
    assert.deepEqual(serverEventShopIdMap, expectedIdMap)
})
