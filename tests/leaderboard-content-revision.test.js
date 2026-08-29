const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-leaderboard-revision-"))
process.env.DATA_DIR = temporaryDataDir

const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const {
    countLeaderboardRanksSync,
    getLeaderboardPlayerRankSync,
    getLeaderboardSeasonSync,
} = require("../out/data/domains/leaderboard")
const {
    getDefaultPlayerRushEventSync,
    getPlayerRushEventPlayedPartiesSync,
    getPlayerRushEventSync,
    insertPlayerRushEventPlayedPartySync,
    insertPlayerRushEventSync,
} = require("../out/data/domains/rushEvent")
const {
    getLeaderboardCompetition,
    getLeaderboardCompetitionSeasonSync,
} = require("../out/lib/leaderboard/competition")
const {
    finishLeaderboardQuestSync,
    startLeaderboardQuestSync,
} = require("../out/lib/leaderboard/service")

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

function quest(round) {
    return {
        category: competition.category,
        eventId: competition.eventId,
        folderId: competition.folderId,
        round,
        questId: 700099000 + round,
        totalRounds: 30,
    }
}

function finishRound(playerId, round, startedAtMs) {
    const identity = quest(round)
    assert.ok(startLeaderboardQuestSync(playerId, identity, startedAtMs))
    finishLeaderboardQuestSync({
        playerId,
        quest: identity,
        accomplished: true,
        clientBattleMs: 1_000 + round,
        party,
        finishedAtMs: startedAtMs + 1_000 + round,
    })
}

test("重Roll换季作废旧活跃run，保留29关进度且要求从第1关重新参榜", () => {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "revision-boundary",
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    updatePlayerSync({ id: player.id, name: "Floor 29", rankPoint: 100000 })

    insertPlayerRushEventSync(player.id, {
        ...getDefaultPlayerRushEventSync(700099),
        activeRushBattleFolderId: 1,
    })
    insertPlayerRushEventPlayedPartySync(player.id, 700099, {
        ...party,
        round: 28,
        battleType: 1,
    })

    for (let round = 1; round <= 28; round++) {
        finishRound(player.id, round, 1_000_000 + round * 10_000)
    }
    const oldRun = getDb().prepare(`
        SELECT * FROM leaderboard_runs
        WHERE player_id = ? AND status = 'active'
    `).get(player.id)
    assert.equal(oldRun.tracked_from_round, 1)
    assert.equal(oldRun.rounds_cleared, 28)
    const oldSeason = getLeaderboardSeasonSync(competition.key)

    getDb().prepare(`
        UPDATE leaderboard_seasons SET content_revision = ?
        WHERE competition_key = ?
    `).run("abyss-reroll-seed-before-2026082902", competition.key)

    finishRound(player.id, 29, 2_000_000)
    finishRound(player.id, 30, 2_010_000)

    const currentSeason = getLeaderboardSeasonSync(competition.key)
    assert.equal(currentSeason, oldSeason + 1)
    assert.equal(
        getLeaderboardCompetitionSeasonSync(competition.key, 3_000_000),
        currentSeason,
    )
    assert.equal(
        getLeaderboardCompetitionSeasonSync(competition.key, 4_000_000),
        currentSeason,
    )
    const seasonRow = getDb().prepare(`
        SELECT season, source, content_revision
        FROM leaderboard_seasons WHERE competition_key = ?
    `).get(competition.key)
    assert.deepEqual(seasonRow, {
        season: currentSeason,
        source: `content:${competition.contentRevision}`,
        content_revision: competition.contentRevision,
    })
    assert.equal(
        getDb().prepare("SELECT status FROM leaderboard_runs WHERE id = ?").get(oldRun.id).status,
        "abandoned",
    )
    const partialRun = getDb().prepare(`
        SELECT * FROM leaderboard_runs
        WHERE player_id = ? AND season = ? ORDER BY id DESC LIMIT 1
    `).get(player.id, currentSeason)
    assert.equal(partialRun.status, "completed")
    assert.equal(partialRun.tracked_from_round, 29)
    assert.equal(partialRun.rounds_cleared, 30)
    assert.equal(
        getDb().prepare(`
            SELECT COUNT(*) AS count FROM leaderboard_run_rounds WHERE run_id = ?
        `).get(partialRun.id).count,
        2,
    )
    assert.equal(countLeaderboardRanksSync(competition.key, currentSeason), 0)
    assert.equal(
        getLeaderboardPlayerRankSync(competition.key, currentSeason, player.id),
        null,
    )

    const rushProgress = getPlayerRushEventSync(player.id, 700099)
    assert.equal(rushProgress.activeRushBattleFolderId, 1)
    assert.deepEqual(
        getPlayerRushEventPlayedPartiesSync(player.id, 700099).map(value => value.round),
        [28],
    )

    for (let round = 1; round <= 30; round++) {
        finishRound(player.id, round, 5_000_000 + round * 10_000)
    }
    assert.equal(countLeaderboardRanksSync(competition.key, currentSeason), 1)
    const ranked = getLeaderboardPlayerRankSync(
        competition.key,
        currentSeason,
        player.id,
    )
    assert.equal(ranked.trackedFromRound, 1)
    assert.equal(ranked.roundsCleared, 30)
})
