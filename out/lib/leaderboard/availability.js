"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.setLeaderboardAvailabilitySync = exports.isLeaderboardEnabledSync = exports.getLeaderboardAvailabilitySync = void 0;
const db_1 = require("../../data/db");
const leaderboard_1 = require("../../data/domains/leaderboard");
function deserializeAvailability(row) {
    return {
        competitionKey: row.competition_key,
        enabled: row.enabled !== 0,
        updatedAtMs: row.updated_at_ms,
    };
}
function getLeaderboardAvailabilitySync(competitionKey, nowMs = Date.now()) {
    (0, db_1.getDb)().prepare(`
        INSERT OR IGNORE INTO leaderboard_availability (
            competition_key, enabled, updated_at_ms
        ) VALUES (?, 1, ?)
    `).run(competitionKey, nowMs);
    const row = (0, db_1.getDb)().prepare(`
        SELECT competition_key, enabled, updated_at_ms
        FROM leaderboard_availability
        WHERE competition_key = ?
    `).get(competitionKey);
    return deserializeAvailability(row);
}
exports.getLeaderboardAvailabilitySync = getLeaderboardAvailabilitySync;
function isLeaderboardEnabledSync(competitionKey) {
    return getLeaderboardAvailabilitySync(competitionKey).enabled;
}
exports.isLeaderboardEnabledSync = isLeaderboardEnabledSync;
function setLeaderboardAvailabilitySync(competitionKey, enabled, updatedAtMs = Date.now()) {
    if (!Number.isSafeInteger(updatedAtMs) || updatedAtMs < 0) {
        throw new Error("updatedAtMs must be a non-negative epoch millisecond value.");
    }
    const db = (0, db_1.getDb)();
    const operation = () => {
        db.prepare(`
            INSERT INTO leaderboard_availability (
                competition_key, enabled, updated_at_ms
            ) VALUES (?, ?, ?)
            ON CONFLICT (competition_key) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at_ms = excluded.updated_at_ms
        `).run(competitionKey, enabled ? 1 : 0, updatedAtMs);
        const abandonedRuns = enabled ? 0 : (0, leaderboard_1.abandonLeaderboardRunsSync)({
            competitionKey,
            endedAtMs: updatedAtMs,
        });
        return {
            availability: getLeaderboardAvailabilitySync(competitionKey, updatedAtMs),
            abandonedRuns,
        };
    };
    return db.inTransaction ? operation() : db.transaction(operation)();
}
exports.setLeaderboardAvailabilitySync = setLeaderboardAvailabilitySync;
