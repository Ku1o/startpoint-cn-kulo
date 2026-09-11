const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
process.env.DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'startpoint-how-to-get-'))
const Fastify = require('fastify')
const howRoutes = require('../out/routes/api/howToGet').default
const shopRoutes = require('../out/routes/api/shop').default
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const { insertSessionWithToken } = require('../out/data/domains/session')
const { saveAccountDefaultPlayer } = require('../out/data/activeAccount')
const { addPlayerShopPurchaseCountSync } = require('../out/data/domains/shopPurchase')
const { setServerTime } = require('../out/utils')
const { getShopItemSync } = require('../out/lib/assets')
const { getShopPurchaseKey } = require('../out/lib/shop-sales')
const { getHowToGetSources } = require('../out/lib/how-to-get-sources')

test('入手方式沿用真实商店期限和库存，静态索引不缓存玩家状态', async t => {
    const app = Fastify({ logger: false })
    app.addHook('onSend', (_request, reply, payload, done) => {
        done(null, String(reply.getHeader('content-type') ?? '').startsWith('application/x-msgpack')
            && typeof payload === 'object' ? JSON.stringify(payload) : payload)
    })
    await app.register(howRoutes, { prefix: '/how_to_get' })
    await app.register(shopRoutes, { prefix: '/shop' })
    await app.ready()
    t.after(async () => { setServerTime(null); await app.close() })
    async function player(viewer) {
        const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'leiting', idpId: '', status: 'normal' })
        const p = insertDefaultPlayerSync(account.id)
        saveAccountDefaultPlayer(account.id, p.id)
        await insertSessionWithToken({ token: String(viewer), accountId: account.id,
            expires: new Date(Date.now() + 86400000), type: 2 })
        return p
    }
    const p1 = await player(77119051)
    await player(77119052)
    async function post(url, payload, viewer = 77119051) {
        const res = await app.inject({ method: 'POST', url,
            payload: { viewer_id: viewer, api_count: 1, ...payload } })
        assert.equal(res.statusCode, 200, res.payload)
        return JSON.parse(res.payload).data
    }
    const how = (payload, viewer) => post('/how_to_get/get_list', payload, viewer)
    const sale = (id, list) => list.find(r => r.shop_item_id === id)

    await t.test('过期来源隐藏，原期和复刻期间恢复；索引初始化后时间变化仍生效', async () => {
        setServerTime(new Date('2024-01-01T00:00:00Z'))
        assert.equal(sale(700000, (await how({ item_id: 49100 })).shop_sales_list), undefined)
        setServerTime(new Date('2023-11-24T00:00:00Z'))
        assert.ok(sale(700000, (await how({ item_id: 49100 })).shop_sales_list))
        setServerTime(new Date('2025-07-26T00:00:00Z'))
        const source = sale(700000, (await how({ item_id: 49100 })).shop_sales_list)
        const actual = sale(700000, (await post('/shop/get_sales_list', {
            shop_types: [], boss_coin_shop_category_ids: [], event_list: [{ event_type: 11, event_ids: [700011] }],
        })).sales_list)
        assert.deepEqual(source, actual)
        setServerTime(new Date('2025-08-15T00:00:00Z'))
        assert.equal(sale(700000, (await how({ item_id: 49100 })).shop_sales_list), undefined)
    })
    await t.test('12 对幻想商品沿用已存共享购买键，另一玩家不受影响', async () => {
        setServerTime(new Date('2025-07-26T00:00:00Z'))
        for (let i = 0; i < 12; i++) {
            const ids = [9700201 + i, 9700301 + i]
            const item = getShopItemSync(4, ids[0])
            const reward = item.rewards[0]
            const query = { [reward.type === 4 ? 'equipment_id' : 'item_id']: reward.id }
            assert.equal(sale(ids[0], (await how(query)).shop_sales_list).stock_quantity, item.stock)
            assert.equal(getShopPurchaseKey(4, ids[0]), -9702001 - i)
            addPlayerShopPurchaseCountSync(p1.id, -9702001 - i, item.stock)
            const sources = (await how(query)).shop_sales_list
            const actual = (await post('/shop/get_sales_list', {
                shop_types: [], boss_coin_shop_category_ids: [],
                event_list: [{ event_type: 11, event_ids: [700098] }, { event_type: 0, event_ids: [300098] }],
            })).sales_list
            for (const id of ids) {
                assert.equal(sale(id, sources).stock_quantity, 0)
                assert.deepEqual(sale(id, sources), sale(id, actual))
            }
            assert.equal(sale(ids[0], (await how(query, 77119052)).shop_sales_list).stock_quantity, item.stock)
        }
    })
    await t.test('普通商店与星粒同号商品的购买计数隔离', async () => {
        for (const id of [100008, 110005, 110006]) {
            assert.equal(getShopPurchaseKey(8, id), -8000000 - id)
            assert.equal(getShopPurchaseKey(9, id), id)
            const item = getShopItemSync(8, id)
            const reward = item.rewards.find(r => r.id)
            const query = { [reward.type === 4 ? 'equipment_id' : 'item_id']: reward.id }
            addPlayerShopPurchaseCountSync(p1.id, id, 1)
            const source = (await how(query)).shop_sales_list.find(r => r.shop_type === 8 && r.shop_item_id === id)
            assert.equal(source.total_purchase_num, 0)
            addPlayerShopPurchaseCountSync(p1.id, getShopPurchaseKey(8, id), 1)
            const updated = (await how(query)).shop_sales_list.find(r => r.shop_type === 8 && r.shop_item_id === id)
            assert.equal(updated.total_purchase_num, 1)
        }
    })
    await t.test('保留现用五重来源和普通箱池，旧死亡使者商品不返回', async () => {
        const weapon = await how({ equipment_id: 5900101 })
        assert.ok(sale(990099001, weapon.shop_sales_list))
        assert.equal(sale(59001010, weapon.shop_sales_list), undefined)
        const ticket = await how({ equipment_id: 0, item_id: 10000143 })
        assert.ok(sale(990099002, ticket.shop_sales_list))
        assert.ok(getHowToGetSources(false, 2).boxes.length > 0)
        assert.ok((await how({ item_id: 2 })).box_gacha_id_list.includes(1))
        assert.ok((await how({ equipment_id: 5100001 })).box_gacha_id_list.includes(1))
        assert.deepEqual((await how({ item_id: 5100001 })).box_gacha_id_list, [])
        assert.deepEqual((await how({ item_id: -1 })).shop_sales_list, [])
        assert.deepEqual((await how({ item_id: 10000143 }, 99999999)).shop_sales_list, [])
    })
})
