"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.resetLeaderboardCompetitionSync = exports.finishLeaderboardQuestSync = exports.startLeaderboardQuestSync = void 0;
const player_1 = require("../../data/domains/player");
const leaderboard_1 = require("../../data/domains/leaderboard");
const competition_1 = require("./competition");
const availability_1 = require("./availability");
function startLeaderboardQuestSync(playerId, quest, startedAtMs = Date.now()) {
    const competition = (0, competition_1.getLeaderboardCompetitionForQuest)(quest);
    const round = quest.round;
    if (competition === null
        || !(0, availability_1.isLeaderboardEnabledSync)(competition.key)
        || round === undefined
        || !Number.isSafeInteger(round)
        || !Number.isSafeInteger(quest.questId)
        || !Number.isSafeInteger(quest.totalRounds)
        || round < 1
        || round > quest.totalRounds
        || quest.totalRounds < 1) {
        return null;
    }
    return getDbTransaction(() => {
        var _a;
        const season = (0, competition_1.getLeaderboardCompetitionSeasonSync)(competition.key, startedAtMs);
        const active = (0, leaderboard_1.getActiveLeaderboardRunSync)(playerId, competition.key);
        const canContinue = active !== null
            && active.season === season
            && active.totalRounds === quest.totalRounds
            && active.roundsCleared === round - 1
            && round > 1;
        if (!canContinue) {
            (0, leaderboard_1.abandonLeaderboardRunsSync)({
                competitionKey: competition.key,
                playerId,
                endedAtMs: startedAtMs,
            });
            const player = (0, player_1.getPlayerSync)(playerId);
            return (0, leaderboard_1.insertLeaderboardRunSync)({
                competitionKey: competition.key,
                playerId,
                playerName: (_a = player === null || player === void 0 ? void 0 : player.name) !== null && _a !== void 0 ? _a : null,
                season,
                startedAtMs,
                totalRounds: quest.totalRounds,
                trackedFromRound: round,
                pendingRound: round,
                pendingQuestId: quest.questId,
            }).id;
        }
        (0, leaderboard_1.markLeaderboardRoundStartedSync)(active.id, round, quest.questId, startedAtMs);
        return active.id;
    });
}
exports.startLeaderboardQuestSync = startLeaderboardQuestSync;
function finishLeaderboardQuestSync(input) {
    var _a;
    if (!input.accomplished)
        return;
    const competition = (0, competition_1.getLeaderboardCompetitionForQuest)(input.quest);
    const round = input.quest.round;
    if (competition === null
        || !(0, availability_1.isLeaderboardEnabledSync)(competition.key)
        || round === undefined
        || round < 1)
        return;
    const clientBattleMs = Math.trunc(input.clientBattleMs);
    if (!Number.isSafeInteger(clientBattleMs)
        || clientBattleMs <= 0
        || clientBattleMs > 2147483647)
        return;
    const finishedAtMs = Math.trunc((_a = input.finishedAtMs) !== null && _a !== void 0 ? _a : Date.now());
    if (!Number.isSafeInteger(finishedAtMs) || finishedAtMs < 0)
        return;
    const run = (0, leaderboard_1.getActiveLeaderboardRunSync)(input.playerId, competition.key);
    if (run === null)
        return;
    (0, leaderboard_1.finishLeaderboardRoundSync)({
        run,
        round,
        questId: input.quest.questId,
        clientBattleMs,
        finishedAtMs,
        party: input.party,
    });
}
exports.finishLeaderboardQuestSync = finishLeaderboardQuestSync;
function resetLeaderboardCompetitionSync(playerId, quest, endedAtMs = Date.now()) {
    const competition = (0, competition_1.getLeaderboardCompetitionForQuest)(quest);
    if (competition === null)
        return 0;
    return (0, leaderboard_1.abandonLeaderboardRunsSync)({ competitionKey: competition.key, playerId, endedAtMs });
}
exports.resetLeaderboardCompetitionSync = resetLeaderboardCompetitionSync;
function getDbTransaction(operation) {
    // Keep the transaction boundary in one place without exposing better-sqlite3
    // from the public leaderboard service API.
    const { getDb } = require("../../data/db");
    const db = getDb();
    return db.inTransaction ? operation() : db.transaction(operation)();
}
