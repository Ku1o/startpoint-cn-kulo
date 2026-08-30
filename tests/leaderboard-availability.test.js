const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-leaderboard-switch-"))
process.env.DATA_DIR = temporaryDataDir

const outDir = process.env.STARPOINT_TEST_OUT_DIR
    ? path.resolve(process.env.STARPOINT_TEST_OUT_DIR)
    : path.resolve(__dirname, "../out")
const fromOut = modulePath => require(path.join(outDir, modulePath))

const Fastify = require("fastify")
const rushEventRoutes = fromOut("routes/api/rushEvent").default
const leaderboardAdminRoutes = fromOut("routes/web_api/leaderboards").default
const { insertAccountSync } = fromOut("data/domains/account")
const { saveAccountDefaultPlayer } = fromOut("data/activeAccount")
const {
    insertDefaultPlayerSync,
    updatePlayerSync,
} = fromOut("data/domains/player")
const { insertSessionWithToken } = fromOut("data/domains/session")
const {
    countLeaderboardRanksSync,
    getActiveLeaderboardRunSync,
    getLeaderboardSeasonSync,
} = fromOut("data/domains/leaderboard")
const { getLeaderboardCompetition } = fromOut("lib/leaderboard/competition")
const {
    getLeaderboardAvailabilitySync,
    isLeaderboardEnabledSync,
} = fromOut("lib/leaderboard/availability")
const {
    finishLeaderboardQuestSync,
    startLeaderboardQuestSync,
} = fromOut("lib/leaderboard/service")
const {
    getLeaderboardSettlementConfigSync,
    putLeaderboardSettlementConfigSync,
    runDueLeaderboardSettlementsSync,
} = fromOut("lib/leaderboard/settlement")

const competition = getLeaderboardCompetition("rush:700099:1")
assert.ok(competition)

const party = {
    characterIds: [169980, 169994, 169995],
    unisonCharacterIds: [null, null, null],
    equipmentIds: [null, null, null],
    abilitySoulIds: [null, null, null],
    evolutionImgLevels: [1, 0, 1],
    unisonEvolutionImgLevels: [null, null, null],
}

function createPlayer(name) {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    updatePlayerSync({ id: player.id, name, rankPoint: 100000 })
    return { account, player }
}

function quest(round, totalRounds = 2) {
    return {
        category: competition.category,
        eventId: competition.eventId,
        folderId: competition.folderId,
        round,
        questId: 700099000 + round,
        totalRounds,
    }
}

function completeRun(playerId, startedAtMs) {
    for (let round = 1; round <= 2; round++) {
        const currentQuest = quest(round)
        assert.ok(startLeaderboardQuestSync(playerId, currentQuest, startedAtMs + round * 10_000))
        finishLeaderboardQuestSync({
            playerId,
            quest: currentQuest,
            accomplished: true,
            clientBattleMs: 1_000 + round,
            party,
            finishedAtMs: startedAtMs + round * 10_000 + 1_000 + round,
        })
    }
}

test("排行榜冻结后保留名次，手动换季需先结算，自动结算只关闭不换季", async t => {
    assert.equal(getLeaderboardAvailabilitySync(competition.key).enabled, true)
    const ranked = createPlayer("Ranked")
    const interrupted = createPlayer("Interrupted")
    completeRun(ranked.player.id, 1_000_000)
    const season = getLeaderboardSeasonSync(competition.key)
    assert.equal(countLeaderboardRanksSync(competition.key, season), 1)
    assert.ok(startLeaderboardQuestSync(interrupted.player.id, quest(1), 2_000_000))

    const admin = Fastify({ logger: false })
    await admin.register(leaderboardAdminRoutes, { prefix: "/api/leaderboards" })
    await admin.ready()
    t.after(() => admin.close())

    const closeResponse = await admin.inject({
        method: "PATCH",
        url: `/api/leaderboards/${encodeURIComponent(competition.key)}/availability`,
        payload: { enabled: false },
    })
    assert.equal(closeResponse.statusCode, 200, closeResponse.payload)
    const closeBody = closeResponse.json()
    assert.equal(closeBody.availability.enabled, false)
    assert.equal(closeBody.abandonedRuns, 1)
    assert.equal(isLeaderboardEnabledSync(competition.key), false)
    assert.equal(getActiveLeaderboardRunSync(interrupted.player.id, competition.key), null)
    assert.equal(countLeaderboardRanksSync(competition.key, season), 1)
    assert.equal(startLeaderboardQuestSync(interrupted.player.id, quest(1), 3_000_000), null)
    const detailResponse = await admin.inject({
        method: "GET",
        url: `/api/leaderboards/${encodeURIComponent(competition.key)}`,
    })
    assert.equal(detailResponse.statusCode, 200, detailResponse.payload)
    assert.equal(detailResponse.json().availability.enabled, false)

    saveAccountDefaultPlayer(ranked.account.id, ranked.player.id)
    const viewerId = 77119913
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: ranked.account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })
    const game = Fastify({ logger: false })
    game.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        done(null, contentType.startsWith("application/x-msgpack") && typeof payload === "object"
            ? JSON.stringify(payload)
            : payload)
    })
    await game.register(rushEventRoutes, { prefix: "/event/rush" })
    await game.ready()
    t.after(() => game.close())

    const frozenLeaderboardResponse = await game.inject({
        method: "POST",
        url: "/event/rush/leaderboard",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: competition.eventId },
    })
    assert.equal(frozenLeaderboardResponse.statusCode, 200, frozenLeaderboardResponse.payload)
    const frozenPayload = JSON.parse(frozenLeaderboardResponse.payload).data
    assert.equal(frozenPayload.enabled, true)
    assert.equal(frozenPayload.time, "排行榜已冻结")
    assert.equal(frozenPayload.total, 1)
    assert.equal(frozenPayload.rows.length, 1)

    const officialResponse = await game.inject({
        method: "POST",
        url: "/event/rush/ranking",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: competition.eventId, page: 0 },
    })
    assert.equal(officialResponse.statusCode, 200, officialResponse.payload)
    const officialPayload = JSON.parse(officialResponse.payload).data
    assert.equal(officialPayload.total, 1)
    assert.equal(officialPayload.ranking_data.length, 1)

    const prematureRolloverResponse = await admin.inject({
        method: "POST",
        url: `/api/leaderboards/${encodeURIComponent(competition.key)}/rollover`,
    })
    assert.equal(prematureRolloverResponse.statusCode, 409, prematureRolloverResponse.payload)
    assert.equal(prematureRolloverResponse.json().reason, "season-not-settled")
    assert.equal(getLeaderboardSeasonSync(competition.key), season)

    const settleResponse = await admin.inject({
        method: "POST",
        url: `/api/leaderboards/${encodeURIComponent(competition.key)}/settle`,
    })
    assert.equal(settleResponse.statusCode, 200, settleResponse.payload)
    assert.equal(isLeaderboardEnabledSync(competition.key), false)
    assert.equal(getLeaderboardSeasonSync(competition.key), season)
    assert.equal(countLeaderboardRanksSync(competition.key, season), 1)

    const settledFrozenResponse = await game.inject({
        method: "POST",
        url: "/event/rush/leaderboard",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: competition.eventId },
    })
    assert.equal(settledFrozenResponse.statusCode, 200, settledFrozenResponse.payload)
    assert.equal(JSON.parse(settledFrozenResponse.payload).data.total, 1)

    const rolloverResponse = await admin.inject({
        method: "POST",
        url: `/api/leaderboards/${encodeURIComponent(competition.key)}/rollover`,
    })
    assert.equal(rolloverResponse.statusCode, 200, rolloverResponse.payload)
    const rolloverBody = rolloverResponse.json()
    assert.equal(rolloverBody.rolled, true)
    assert.equal(rolloverBody.nextSeason, season + 1)
    assert.equal(isLeaderboardEnabledSync(competition.key), false)
    assert.equal(countLeaderboardRanksSync(competition.key, season + 1), 0)

    const rolledDetailResponse = await admin.inject({
        method: "GET",
        url: `/api/leaderboards/${encodeURIComponent(competition.key)}`,
    })
    assert.equal(rolledDetailResponse.statusCode, 200, rolledDetailResponse.payload)
    assert.equal(rolledDetailResponse.json().overview.season, season + 1)
    assert.equal(rolledDetailResponse.json().availability.enabled, false)

    const rolledFrozenResponse = await game.inject({
        method: "POST",
        url: "/event/rush/leaderboard",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: competition.eventId },
    })
    assert.equal(rolledFrozenResponse.statusCode, 200, rolledFrozenResponse.payload)
    const rolledFrozenPayload = JSON.parse(rolledFrozenResponse.payload).data
    assert.equal(rolledFrozenPayload.enabled, true)
    assert.equal(rolledFrozenPayload.time, "排行榜已冻结")
    assert.equal(rolledFrozenPayload.total, 1)
    assert.equal(rolledFrozenPayload.rows.length, 1)

    const rolledOfficialResponse = await game.inject({
        method: "POST",
        url: "/event/rush/ranking",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: competition.eventId, page: 0 },
    })
    assert.equal(rolledOfficialResponse.statusCode, 200, rolledOfficialResponse.payload)
    const rolledOfficialPayload = JSON.parse(rolledOfficialResponse.payload).data
    assert.equal(rolledOfficialPayload.total, 1)
    assert.equal(rolledOfficialPayload.ranking_data.length, 1)

    const openResponse = await admin.inject({
        method: "PATCH",
        url: `/api/leaderboards/${encodeURIComponent(competition.key)}/availability`,
        payload: { enabled: true },
    })
    assert.equal(openResponse.statusCode, 200, openResponse.payload)
    assert.equal(openResponse.json().availability.enabled, true)

    const reopenedResponse = await game.inject({
        method: "POST",
        url: "/event/rush/leaderboard",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: competition.eventId },
    })
    assert.equal(reopenedResponse.statusCode, 200, reopenedResponse.payload)
    const reopenedPayload = JSON.parse(reopenedResponse.payload).data
    assert.equal(reopenedPayload.enabled, true)
    assert.equal(reopenedPayload.total, 0)
    assert.equal(reopenedPayload.rows.length, 0)
    completeRun(interrupted.player.id, 4_000_000)
    assert.equal(countLeaderboardRanksSync(competition.key, season + 1), 1)

    const config = getLeaderboardSettlementConfigSync(competition.key)
    putLeaderboardSettlementConfigSync({
        ...config,
        autoEnabled: true,
        settleAtMs: 5_000_000,
        repeatIntervalMs: null,
        updatedAtMs: 4_900_000,
    })
    runDueLeaderboardSettlementsSync(5_000_000)

    assert.equal(getLeaderboardSeasonSync(competition.key), season + 1)
    assert.equal(isLeaderboardEnabledSync(competition.key), false)
    assert.equal(countLeaderboardRanksSync(competition.key, season + 1), 1)
    const scheduledConfig = getLeaderboardSettlementConfigSync(competition.key)
    assert.equal(scheduledConfig.autoEnabled, false)
    assert.equal(scheduledConfig.settleAtMs, null)

    const autoFrozenResponse = await game.inject({
        method: "POST",
        url: "/event/rush/leaderboard",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: competition.eventId },
    })
    assert.equal(autoFrozenResponse.statusCode, 200, autoFrozenResponse.payload)
    const autoFrozenPayload = JSON.parse(autoFrozenResponse.payload).data
    assert.equal(autoFrozenPayload.enabled, true)
    assert.equal(autoFrozenPayload.time, "排行榜已冻结")
    assert.equal(autoFrozenPayload.total, 1)
    assert.equal(autoFrozenPayload.rows.length, 1)
    assert.equal(startLeaderboardQuestSync(ranked.player.id, quest(1), 6_000_000), null)
})
