import { getPlayerSync } from "../../data/domains/player"
import {
    abandonLeaderboardRunsSync,
    finishLeaderboardRoundSync,
    getActiveLeaderboardRunSync,
    insertLeaderboardRunSync,
    LeaderboardRoundParty,
    markLeaderboardRoundStartedSync,
} from "../../data/domains/leaderboard"
import {
    getLeaderboardCompetitionForQuest,
    getLeaderboardCompetitionSeasonSync,
} from "./competition"
import { isLeaderboardEnabledSync } from "./availability"

export interface LeaderboardQuestIdentity {
    category: number
    eventId?: number
    folderId?: number
    round?: number
    questId: number
    totalRounds: number
}

export function startLeaderboardQuestSync(
    playerId: number,
    quest: LeaderboardQuestIdentity,
    startedAtMs: number = Date.now(),
): number | null {
    const competition = getLeaderboardCompetitionForQuest(quest)
    const round = quest.round
    if (
        competition === null
        || !isLeaderboardEnabledSync(competition.key)
        || round === undefined
        || !Number.isSafeInteger(round)
        || !Number.isSafeInteger(quest.questId)
        || !Number.isSafeInteger(quest.totalRounds)
        || round < 1
        || round > quest.totalRounds
        || quest.totalRounds < 1
    ) {
        return null
    }

    return getDbTransaction(() => {
        const season = getLeaderboardCompetitionSeasonSync(competition.key, startedAtMs)
        const active = getActiveLeaderboardRunSync(playerId, competition.key)
        const canContinue = active !== null
            && active.season === season
            && active.totalRounds === quest.totalRounds
            && active.roundsCleared === round - 1
            && round > 1

        if (!canContinue) {
            abandonLeaderboardRunsSync({
                competitionKey: competition.key,
                playerId,
                endedAtMs: startedAtMs,
            })
            const player = getPlayerSync(playerId)
            return insertLeaderboardRunSync({
                competitionKey: competition.key,
                playerId,
                playerName: player?.name ?? null,
                season,
                startedAtMs,
                totalRounds: quest.totalRounds,
                trackedFromRound: round,
                pendingRound: round,
                pendingQuestId: quest.questId,
            }).id
        }

        markLeaderboardRoundStartedSync(active.id, round, quest.questId, startedAtMs)
        return active.id
    })
}

export function finishLeaderboardQuestSync(input: {
    playerId: number
    quest: LeaderboardQuestIdentity
    accomplished: boolean
    clientBattleMs: number
    party: LeaderboardRoundParty
    finishedAtMs?: number
}): void {
    if (!input.accomplished) return
    const competition = getLeaderboardCompetitionForQuest(input.quest)
    const round = input.quest.round
    if (
        competition === null
        || !isLeaderboardEnabledSync(competition.key)
        || round === undefined
        || round < 1
    ) return
    const clientBattleMs = Math.trunc(input.clientBattleMs)
    if (
        !Number.isSafeInteger(clientBattleMs)
        || clientBattleMs <= 0
        || clientBattleMs > 2_147_483_647
    ) return
    const finishedAtMs = Math.trunc(input.finishedAtMs ?? Date.now())
    if (!Number.isSafeInteger(finishedAtMs) || finishedAtMs < 0) return

    const run = getActiveLeaderboardRunSync(input.playerId, competition.key)
    if (run === null) return
    finishLeaderboardRoundSync({
        run,
        round,
        questId: input.quest.questId,
        clientBattleMs,
        finishedAtMs,
        party: input.party,
    })
}

export function resetLeaderboardCompetitionSync(
    playerId: number,
    quest: Pick<LeaderboardQuestIdentity, "category" | "eventId" | "folderId">,
    endedAtMs: number = Date.now(),
): number {
    const competition = getLeaderboardCompetitionForQuest(quest)
    if (competition === null) return 0
    return abandonLeaderboardRunsSync({ competitionKey: competition.key, playerId, endedAtMs })
}

function getDbTransaction<T>(operation: () => T): T {
    // Keep the transaction boundary in one place without exposing better-sqlite3
    // from the public leaderboard service API.
    const { getDb } = require("../../data/db") as typeof import("../../data/db")
    const db = getDb()
    return db.inTransaction ? operation() : db.transaction(operation)()
}
