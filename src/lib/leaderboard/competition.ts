import { QuestCategory } from "../types"
import { getLeaderboardSeasonSync } from "../../data/domains/leaderboard"

export interface LeaderboardCompetition {
    key: string
    displayName: string
    category: QuestCategory
    eventId: number
    folderId: number
    pageSize: number
    displayLimit: number
    contentRevision: string
}

const competitions: readonly LeaderboardCompetition[] = [{
    key: "rush:700099:1",
    displayName: "深渊连战",
    category: QuestCategory.RUSH_EVENT,
    eventId: 700099,
    folderId: 1,
    pageSize: 100,
    displayLimit: 500,
    contentRevision: "abyss-reroll-seed-2026082902",
}]

export function getLeaderboardCompetitions(): readonly LeaderboardCompetition[] {
    return competitions
}

export function getLeaderboardCompetition(key: string): LeaderboardCompetition | null {
    return competitions.find(entry => entry.key === key) ?? null
}

export function getLeaderboardCompetitionForEvent(
    category: number,
    eventId: number,
): LeaderboardCompetition | null {
    return competitions.find(entry =>
        entry.category === category && entry.eventId === eventId
    ) ?? null
}

export function getLeaderboardCompetitionForQuest(input: {
    category: number
    eventId?: number
    folderId?: number
}): LeaderboardCompetition | null {
    return competitions.find(entry =>
        entry.category === input.category
        && entry.eventId === input.eventId
        && entry.folderId === input.folderId
    ) ?? null
}

export function getLeaderboardCompetitionSeasonSync(
    competitionKey: string,
    nowMs: number = Date.now(),
): number {
    const competition = getLeaderboardCompetition(competitionKey)
    return getLeaderboardSeasonSync(
        competitionKey,
        nowMs,
        competition?.contentRevision,
    )
}
