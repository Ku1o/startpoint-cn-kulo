const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const Fastify = require("fastify")

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "mode15-disconnect-load-"))
process.env.DATA_DIR = dataDir
process.env.GACHA_SEED_DIR = path.join(dataDir, "seeds")

const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const { getPlayerItemSync } = require("../out/data/domains/item")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const { insertPlayerActiveQuestSync, getPlayerActiveQuestSync } =
    require("../out/data/domains/quest_active")
const { insertSessionWithToken } = require("../out/data/domains/session")
const mode15 = require("../out/lib/mode15")

const db = getDb()

function seedCompletedStage(playerId, stage) {
    db.prepare(`
        INSERT INTO players_rush_events_played_parties (
            player_id, event_id, round, battle_type
        ) VALUES (?, 700098, ?, 0)
    `).run(playerId, 700098000 + stage)
}

test("login cleanup after a disconnected Fantasy boundary keeps the same stage", async t => {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: "mode15-disconnect-load",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 890000000 + player.id
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })
    for (let stage = 1; stage < 10; stage += 1) seedCompletedStage(player.id, stage)
    insertPlayerActiveQuestSync(player.id, {
        playerId: player.id,
        playId: "disconnected-mode15-stage-10",
        questId: 300098002,
        category: 7,
        useBossBoostPoint: false,
        useBoostPoint: false,
        isAutoStartMode: false,
        isMulti: true,
        isMultiHost: true,
        roomNumber: "missing-mode15-room",
        continueCount: 0,
        startedAtMs: Date.now(),
    })
    assert.equal(mode15.getExpectedMode15StageSync(player.id), 10)
    const tokenBefore = getPlayerItemSync(player.id, 2370098) ?? 0

    const intervals = []
    const originalInterval = global.setInterval
    let loadRoutes
    try {
        global.setInterval = (...args) => {
            const timer = originalInterval(...args)
            intervals.push(timer)
            return timer
        }
        loadRoutes = require("../out/routes/cn/load").default
    } finally {
        global.setInterval = originalInterval
    }

    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        if (String(reply.getHeader("content-type") || "").startsWith("application/x-msgpack")
            && typeof payload === "object") {
            done(null, JSON.stringify(payload))
            return
        }
        done(null, payload)
    })
    await app.register(loadRoutes)
    await app.ready()
    t.after(async () => {
        await app.close()
        for (const timer of intervals) clearInterval(timer)
    })

    const response = await app.inject({
        method: "POST",
        url: "/load",
        payload: { viewer_id: viewerId },
        headers: { device: "android" },
    })
    assert.equal(response.statusCode, 200, response.body)
    const data = response.json().data
    assert.deepEqual(data.unfinished_multi_quest_list, [])
    assert.equal(getPlayerActiveQuestSync(player.id), null)
    assert.equal(mode15.getExpectedMode15StageSync(player.id), 10)
    assert.equal(mode15.canStartMode15QuestSync(player.id, 7, 300098002).allowed, true)
    assert.equal(mode15.canStartMode15QuestSync(player.id, 7, 300098001).allowed, false)
    assert.equal(getPlayerItemSync(player.id, 2370098) ?? 0, tokenBefore)
})

test("login clears a multiplayer active quest without room identity once and does not loop", async t => {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: "orphan-multi-load-loop",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 891000000 + player.id
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })
    insertPlayerActiveQuestSync(player.id, {
        playerId: player.id,
        playId: "orphan-without-room-number",
        questId: 1000101,
        category: 2,
        useBossBoostPoint: false,
        useBoostPoint: false,
        isAutoStartMode: false,
        isMulti: true,
        isMultiHost: false,
        roomNumber: null,
        continueCount: 0,
        startedAtMs: Date.now(),
    })

    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        if (String(reply.getHeader("content-type") || "").startsWith("application/x-msgpack")
            && typeof payload === "object") {
            done(null, JSON.stringify(payload))
            return
        }
        done(null, payload)
    })
    await app.register(require("../out/routes/cn/load").default)
    await app.ready()
    t.after(() => app.close())

    for (let attempt = 0; attempt < 2; attempt++) {
        const response = await app.inject({
            method: "POST",
            url: "/load",
            payload: { viewer_id: viewerId },
            headers: { device: "android" },
        })
        assert.equal(response.statusCode, 200, response.body)
        assert.deepEqual(response.json().data.unfinished_quest_list, [])
        assert.deepEqual(response.json().data.unfinished_multi_quest_list, [])
        assert.equal(getPlayerActiveQuestSync(player.id), null)
    }
})

test.after(() => {
    if (db.open) db.close()
    const resolved = path.resolve(dataDir)
    assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()))
    assert.ok(path.basename(resolved).startsWith("mode15-disconnect-load-"))
    fs.rmSync(resolved, { recursive: true, force: true })
})
