import { getDb } from "../../data/db"
import { abandonLeaderboardRunsSync } from "../../data/domains/leaderboard"

export interface LeaderboardAvailability {
    competitionKey: string
    enabled: boolean
    updatedAtMs: number
}

export interface LeaderboardAvailabilityUpdate {
    availability: LeaderboardAvailability
    abandonedRuns: number
}

interface RawAvailability {
    competition_key: string
    enabled: number
    updated_at_ms: number
}

function deserializeAvailability(row: RawAvailability): LeaderboardAvailability {
    return {
        competitionKey: row.competition_key,
        enabled: row.enabled !== 0,
        updatedAtMs: row.updated_at_ms,
    }
}

export function getLeaderboardAvailabilitySync(
    competitionKey: string,
    nowMs: number = Date.now(),
): LeaderboardAvailability {
    getDb().prepare(`
        INSERT OR IGNORE INTO leaderboard_availability (
            competition_key, enabled, updated_at_ms
        ) VALUES (?, 1, ?)
    `).run(competitionKey, nowMs)
    const row = getDb().prepare(`
        SELECT competition_key, enabled, updated_at_ms
        FROM leaderboard_availability
        WHERE competition_key = ?
    `).get(competitionKey) as RawAvailability
    return deserializeAvailability(row)
}

export function isLeaderboardEnabledSync(competitionKey: string): boolean {
    return getLeaderboardAvailabilitySync(competitionKey).enabled
}

export function setLeaderboardAvailabilitySync(
    competitionKey: string,
    enabled: boolean,
    updatedAtMs: number = Date.now(),
): LeaderboardAvailabilityUpdate {
    if (!Number.isSafeInteger(updatedAtMs) || updatedAtMs < 0) {
        throw new Error("updatedAtMs must be a non-negative epoch millisecond value.")
    }
    const db = getDb()
    const operation = () => {
        db.prepare(`
            INSERT INTO leaderboard_availability (
                competition_key, enabled, updated_at_ms
            ) VALUES (?, ?, ?)
            ON CONFLICT (competition_key) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at_ms = excluded.updated_at_ms
        `).run(competitionKey, enabled ? 1 : 0, updatedAtMs)
        const abandonedRuns = enabled ? 0 : abandonLeaderboardRunsSync({
            competitionKey,
            endedAtMs: updatedAtMs,
        })
        return {
            availability: getLeaderboardAvailabilitySync(competitionKey, updatedAtMs),
            abandonedRuns,
        }
    }
    return db.inTransaction ? operation() : db.transaction(operation)()
}
