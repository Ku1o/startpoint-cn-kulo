const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-clear-count-"))
process.env.DATA_DIR = dataDir
const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const {
    getLeaderboardRankPageSync, getLeaderboardPlayerRankSync,
} = require("../out/data/domains/leaderboard")
const {
    getLeaderboardCompetition, getLeaderboardCompetitionSeasonSync,
} = require("../out/lib/leaderboard/competition")
const { setLeaderboardAvailabilitySync } = require("../out/lib/leaderboard/availability")
const {
    startLeaderboardQuestSync, finishLeaderboardQuestSync, resetLeaderboardCompetitionSync,
} = require("../out/lib/leaderboard/service")
const {
    buildNativeLeaderboardPayload, getOfficialLeaderboardPageSync,
} = require("../out/lib/leaderboard/presentation")
const {
    settleLeaderboardSeasonSync, rolloverLeaderboardSeasonSync,
} = require("../out/lib/leaderboard/settlement")

const competition = getLeaderboardCompetition("rush:700099:1")
const party = Object.fromEntries([
    "characterIds", "unisonCharacterIds", "equipmentIds", "abilitySoulIds",
    "evolutionImgLevels", "unisonEvolutionImgLevels",
].map(key => [key, [null, null, null]]))
let clock = 1_000_000

function player() {
    const account = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "leiting", idpId: "", status: "normal",
    })
    return insertDefaultPlayerSync(account.id).id
}

function round(playerId, number, time = 1000, accomplished = true) {
    const quest = {
        category: competition.category, eventId: competition.eventId,
        folderId: competition.folderId, round: number,
        questId: 700099000 + number, totalRounds: 2,
    }
    const runId = startLeaderboardQuestSync(playerId, quest, clock)
    clock += 10_000
    const result = { playerId, quest, accomplished, clientBattleMs: time, party, finishedAtMs: clock }
    finishLeaderboardQuestSync(result)
    // A retried finish request must not count the same completion twice.
    finishLeaderboardQuestSync(result)
    return runId
}

function clear(playerId, time = 1000) {
    round(playerId, 1, time)
    return round(playerId, 2, time)
}

test("通关次数按榜单赛季累计有效整轮，最佳用时排序不变，结算保留计数", async t => {
    const db = getDb()
    t.after(() => {
        db.close()
        fs.rmSync(dataDir, { recursive: true, force: true })
    })
    const a = player()
    const b = player()
    const outsider = player()
    const season = getLeaderboardCompetitionSeasonSync(competition.key)
    clear(a, 1000)
    clear(a, 2000) // Slower clears still count.
    clear(b, 500)
    const rank = (id, filter = {}) => getLeaderboardPlayerRankSync(competition.key, season, id, filter)
    assert.equal(rank(a).clearCount, 2)
    assert.equal(rank(a).clientBattleMs, 2000)
    assert.equal(rank(a).rankNumber, 2)
    assert.equal(rank(b).clearCount, 1)

    round(a, 1, 100, false) // Failed battle, then abandon.
    resetLeaderboardCompetitionSync(a, competition, clock)
    round(a, 2, 100) // A completed run tracked only from round 2 is ineligible.
    round(a, 1, 100) // An active partial run is also ineligible.
    resetLeaderboardCompetitionSync(a, competition, clock)
    const missingRound = clear(a, 100)
    db.prepare("DELETE FROM leaderboard_run_rounds WHERE run_id = ? AND round_number = 1").run(missingRound)
    const zeroTime = clear(a, 100)
    db.prepare("UPDATE leaderboard_runs SET client_battle_ms = 0 WHERE id = ?").run(zeroTime)
    const otherSeason = clear(a)
    db.prepare("UPDATE leaderboard_runs SET season = ? WHERE id = ?").run(season + 10, otherSeason)
    const otherCompetition = clear(a)
    db.prepare("UPDATE leaderboard_runs SET competition_key = 'other' WHERE id = ?").run(otherCompetition)
    assert.equal(rank(a).clearCount, 2)
    assert.equal(rank(a).clientBattleMs, 2000)

    const page = getLeaderboardRankPageSync({ competitionKey: competition.key, season, offset: 1, limit: 1 })
    assert.deepEqual(page.map(row => [row.playerId, row.clearCount]), [[a, 2]])
    const native = buildNativeLeaderboardPayload(competition, a)
    assert.deepEqual(native.rows.map(row => row.count), ["通关次数：1次", "通关次数：2次"])
    assert.equal(native.item.count, "通关次数：2次")
    assert.equal(native.item.time, "TIME: 00:02.00")
    assert.equal(buildNativeLeaderboardPayload(competition, outsider).item.count, "通关次数：0次")
    const limited = buildNativeLeaderboardPayload({ ...competition, displayLimit: 1 }, a)
    assert.equal(limited.rows.length, 1)
    assert.equal(limited.item.count, "通关次数：2次")
    const official = getOfficialLeaderboardPageSync({ competition, playerId: a, page: 0 })
    assert.equal(official.myData.clear_count, 2)
    assert.deepEqual(official.rows.map(row => row.clear_count), [1, 2])
    const app = require("fastify")()
    await app.register(require("../out/routes/web_api/leaderboards").default, { prefix: "/leaderboards" })
    try {
        const response = await app.inject({ method: "GET", url: `/leaderboards/${encodeURIComponent(competition.key)}` })
        assert.equal(response.statusCode, 200)
        assert.deepEqual(response.json().rows.map(row => row.clearCount), [1, 2])
    } finally { await app.close() }

    const settlement = settleLeaderboardSeasonSync(competition.key, "clear-count-test", clock)
    assert.equal(settlement.ok, true)
    assert.equal(rank(a, { settled: true }).clearCount, 2)
    assert.equal(settleLeaderboardSeasonSync(competition.key, "repeat", clock).reason, "already-settled")

    // Simulate a pre-upgrade snapshot: reconstruct only clears before settlement.
    db.prepare("UPDATE leaderboard_settlement_results SET clear_count = NULL WHERE player_id = ?").run(a)
    assert.equal(rank(a, { settled: true }).clearCount, 2)
    db.prepare("UPDATE leaderboard_runs SET season = ?, finished_at_ms = ? WHERE id = ?")
        .run(season, clock + 1000, otherSeason)
    assert.equal(rank(a, { settled: true }).clearCount, 2)
    db.prepare("UPDATE leaderboard_settlement_results SET clear_count = 2 WHERE player_id = ?").run(a)
    db.prepare("DELETE FROM players WHERE id = ?").run(a)
    assert.equal(db.prepare("SELECT COUNT(*) n FROM leaderboard_runs WHERE player_id = ?").get(a).n, 0)
    assert.equal(rank(a, { settled: true }).clearCount, 2)
    assert.equal(buildNativeLeaderboardPayload(competition, null).rows[1].count, "通关次数：2次")

    // Missing legacy history must not be fabricated as zero or one clear.
    db.prepare("UPDATE leaderboard_settlement_results SET clear_count = NULL WHERE player_id = ?").run(a)
    assert.equal(rank(a, { settled: true }).clearCount, null)
    assert.equal(buildNativeLeaderboardPayload(competition, null).rows[1].count, "通关次数：未记录")

    const rollover = rolloverLeaderboardSeasonSync(competition.key, "clear-count-test", clock)
    assert.equal(rollover.ok, true)
    setLeaderboardAvailabilitySync(competition.key, true, clock)
    assert.equal(buildNativeLeaderboardPayload(competition, b).item.count, "通关次数：0次")
    clear(b)
    assert.equal(buildNativeLeaderboardPayload(competition, b).item.count, "通关次数：1次")
    assert.equal(rank(b, { settled: true }).clearCount, 1)
})
