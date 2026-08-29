const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-raid-reward-refresh-test-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const raidEventRoutes = require("../out/routes/api/raidEvent").default
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, getPlayerSync } = require("../out/data/domains/player")
const { getPlayerItemSync, insertPlayerItemsSync } = require("../out/data/domains/item")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const { getDb } = require("../out/data/db")

test("战阵全服奖励领取后立即返回最新资源，重复请求不重复发奖", async t => {
    const account = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "leiting", idpId: "", status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    insertPlayerItemsSync(player.id, { "100000": 10, "14040": 2 })

    const viewerId = 7720260829
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })

    getDb().prepare(`
        INSERT INTO raid_event_global_state
            (event_id, total_kill_count, weighted_kill_count, calculation_version, updated_at)
        VALUES (7, 200, 0, 5, ?)
    `).run(Date.now())
    getDb().prepare(`
        INSERT INTO players_raid_event_overall_rewards
            (player_id, event_id, received_up_to, updated_at)
        VALUES (?, 7, 199, ?)
    `).run(player.id, Date.now())

    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        done(null, contentType.startsWith("application/x-msgpack") && typeof payload === "object"
            ? JSON.stringify(payload)
            : payload)
    })
    await app.register(raidEventRoutes, { prefix: "/event/raid" })
    await app.ready()
    t.after(() => app.close())

    const summary = () => app.inject({
        method: "POST",
        url: "/event/raid/summary",
        headers: { "content-type": "application/json" },
        payload: {
            viewer_id: viewerId,
            event_id: 7,
            api_count: 1,
        },
    })

    const before = getPlayerSync(player.id)
    const first = await summary()
    assert.equal(first.statusCode, 200, first.payload)
    const firstData = JSON.parse(first.payload).data
    assert.equal(firstData.kill_count_reward_data.received_up_to, 200)
    assert.deepEqual(firstData.kill_count_reward_data.reward_list, [
        { kind: 8, kind_id: null, number: 500 },
        { kind: 1, kind_id: 100000, number: 25 },
        { kind: 3, kind_id: null, number: 600 },
        { kind: 1, kind_id: 14040, number: 1 },
    ])
    assert.equal(firstData.user_info.free_mana, before.freeMana + 500)
    assert.equal(firstData.user_info.free_vmoney, before.freeVmoney + 600)
    assert.equal(firstData.user_info.exp_pool, before.expPool)
    assert.equal(firstData.item_list["100000"], 35)
    assert.equal(firstData.item_list["14040"], 3)
    assert.equal(getPlayerSync(player.id).freeMana, before.freeMana + 500)
    assert.equal(getPlayerSync(player.id).freeVmoney, before.freeVmoney + 600)
    assert.equal(getPlayerItemSync(player.id, 100000), 35)
    assert.equal(getPlayerItemSync(player.id, 14040), 3)

    const repeated = await summary()
    assert.equal(repeated.statusCode, 200, repeated.payload)
    const repeatedData = JSON.parse(repeated.payload).data
    assert.deepEqual(repeatedData.kill_count_reward_data.reward_list, [])
    assert.equal("user_info" in repeatedData, false)
    assert.equal("item_list" in repeatedData, false)
    assert.equal(getPlayerSync(player.id).freeMana, before.freeMana + 500)
    assert.equal(getPlayerSync(player.id).freeVmoney, before.freeVmoney + 600)
    assert.equal(getPlayerItemSync(player.id, 100000), 35)
    assert.equal(getPlayerItemSync(player.id, 14040), 3)
})
