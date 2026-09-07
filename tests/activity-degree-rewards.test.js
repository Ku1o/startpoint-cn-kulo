const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-activity-degree-test-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const rushEventRoutes = require("../out/routes/api/rushEvent").default
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const { getDb } = require("../out/data/db")
const { hasPlayerDegreeSync } = require("../out/data/domains/degree")
const { getDefaultPlayerRushEventSync, insertPlayerRushEventSync } = require("../out/data/domains/rushEvent")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const {
    getEligibleRankingDegreeIdsSync,
    getEligibleRaidDegreeIdsSync,
    getEligibleRushDegreeIds,
    grantEligibleRankingEventDegreesSync,
    grantEligibleRaidEventDegreesSync,
    grantEligibleRushEventDegreesSync,
} = require("../out/lib/activity-degree-rewards")

const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "leiting",
    idpId: "",
    status: "normal",
})
const player = insertDefaultPlayerSync(account.id)

test("ranking time titles are restored from the persisted best clear", () => {
    getDb().prepare(`
        INSERT INTO players_quest_progress
            (section, quest_id, finished, best_elapsed_time_ms, player_id)
        VALUES (11, 3001, 1, 35000, ?)
    `).run(player.id)

    assert.deepEqual(getEligibleRankingDegreeIdsSync(player.id, 3), [54100, 54110, 54120, 54130])
    assert.deepEqual(grantEligibleRankingEventDegreesSync(player.id, 3), [54100, 54110, 54120, 54130])
    assert.equal(hasPlayerDegreeSync(player.id, 54130), true)
    assert.equal(hasPlayerDegreeSync(player.id, 54140), false)
})

test("raid titles use the player's deduplicated clear ledger by difficulty", () => {
    const insert = getDb().prepare(`
        INSERT INTO raid_event_global_kill_ledger
            (event_id, play_id, player_id, quest_id, created_at)
        VALUES (7, ?, ?, 7002, ?)
    `)
    for (let index = 0; index < 10; index++) {
        insert.run(`degree-test-${index}`, player.id, Date.now() + index)
    }

    assert.deepEqual(getEligibleRaidDegreeIdsSync(player.id, 7), [63081])
    assert.deepEqual(grantEligibleRaidEventDegreesSync(player.id, 7), [63081])
    assert.equal(hasPlayerDegreeSync(player.id, 63081), true)
})

test("rush title reward ranges are evaluated against endless round, not leaderboard rank", () => {
    assert.deepEqual(getEligibleRushDegreeIds(700001, 1), [])
    assert.deepEqual(getEligibleRushDegreeIds(700001, 3), [64000])
    assert.deepEqual(getEligibleRushDegreeIds(700001, 5), [64001])
    assert.deepEqual(getEligibleRushDegreeIds(700001, 6), [64002])

    assert.deepEqual(grantEligibleRushEventDegreesSync(player.id, 700001, 6), [64002])
    assert.equal(hasPlayerDegreeSync(player.id, 64002), true)
})

test("rush reruns reuse the original endless-round title milestones", () => {
    for (let index = 0; index < 7; index++) {
        const rerunEventId = 700011 + index
        const firstDegreeId = 64000 + index * 3
        assert.deepEqual(getEligibleRushDegreeIds(rerunEventId, 3), [firstDegreeId])
        assert.deepEqual(getEligibleRushDegreeIds(rerunEventId, 5), [firstDegreeId + 1])
        assert.deepEqual(getEligibleRushDegreeIds(rerunEventId, 6), [firstDegreeId + 2])
    }

    assert.deepEqual(grantEligibleRushEventDegreesSync(player.id, 700017, 6), [64020])
    assert.equal(hasPlayerDegreeSync(player.id, 64020), true)
})

test("rush rerun reward endpoint returns and grants the original event title", async t => {
    const rerunAccount = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const rerunPlayer = insertDefaultPlayerSync(rerunAccount.id)
    saveAccountDefaultPlayer(rerunAccount.id, rerunPlayer.id)

    const progress = getDefaultPlayerRushEventSync(700011)
    progress.endlessBattleMaxRound = 6
    progress.endlessBattleMaxRoundTime = 12_345
    insertPlayerRushEventSync(rerunPlayer.id, progress)

    const viewerId = 77119913
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: rerunAccount.id,
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
    await app.register(rushEventRoutes, { prefix: "/rush_event" })
    await app.ready()
    t.after(() => app.close())

    const response = await app.inject({
        method: "POST",
        url: "/rush_event/reward",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, api_count: 1, event_id: 700011 },
    })
    assert.equal(response.statusCode, 200, response.payload)
    const body = JSON.parse(response.payload)
    assert.deepEqual(body.data.ranking_reward.reward_list, [
        { kind: 7, kind_id: 64002, number: 1 },
    ])
    assert.deepEqual(body.data.degree_list, [
        { viewer_id: viewerId, degree_id: 64002 },
    ])
    assert.equal(hasPlayerDegreeSync(rerunPlayer.id, 64002), true)
})
