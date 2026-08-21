import { getDb } from "../data/db";
import { QuestCategory } from "./types";


interface GauntletCompletionRule {
    firstRegularQuestId: number;
    lastRegularQuestId: number;
    completionQuestId: number;
}

const GAUNTLET_COMPLETION_RULES: Readonly<Record<number, GauntletCompletionRule>> = {
    700098: {
        firstRegularQuestId: 700098001,
        lastRegularQuestId: 700098015,
        completionQuestId: 700098016,
    },
    700099: {
        firstRegularQuestId: 700099001,
        lastRegularQuestId: 700099030,
        completionQuestId: 700099099,
    },
};

/**
 * Preserve the native EventFolder "completed" classification without making
 * the optional practice/endless battle part of the required finite run.
 *
 * This row is historical UI state only. Current practice/endless rounds remain
 * driven by players_rush_events and players_rush_events_played_parties.
 */
export function repairGauntletCompletionClassificationSync(
    playerId: number,
    eventId: number,
): boolean {
    const rule = GAUNTLET_COMPLETION_RULES[eventId];
    if (rule === undefined) return false;

    const expectedRegularQuestCount =
        rule.lastRegularQuestId - rule.firstRegularQuestId + 1;
    const regularProgress = getDb().prepare(`
        SELECT COUNT(*) AS cleared_quest_count
        FROM players_quest_progress
        WHERE player_id = ?
          AND section = ?
          AND quest_id BETWEEN ? AND ?
          AND finished = 1
    `).get(
        playerId,
        Number(QuestCategory.RUSH_EVENT),
        rule.firstRegularQuestId,
        rule.lastRegularQuestId,
    ) as { cleared_quest_count?: number } | undefined;
    if (Number(regularProgress?.cleared_quest_count ?? 0) !== expectedRegularQuestCount) {
        return false;
    }

    const completionProgress = getDb().prepare(`
        SELECT finished
        FROM players_quest_progress
        WHERE player_id = ? AND section = ? AND quest_id = ?
    `).get(
        playerId,
        Number(QuestCategory.RUSH_EVENT),
        rule.completionQuestId,
    ) as { finished?: number } | undefined;
    if (Number(completionProgress?.finished ?? 0) === 1) return false;

    getDb().prepare(`
        INSERT INTO players_quest_progress (
            section, quest_id, finished, host_finished, unlocked,
            high_score, clear_rank, best_elapsed_time_ms,
            leader_character_id, multi_clear_count,
            s_plus_reward_received, player_id
        ) VALUES (?, ?, 1, 0, 1, NULL, 5, NULL, NULL, 0, 0, ?)
        ON CONFLICT(section, quest_id, player_id) DO UPDATE SET
            finished = 1,
            unlocked = 1,
            clear_rank = MAX(COALESCE(players_quest_progress.clear_rank, 0), 5)
    `).run(
        Number(QuestCategory.RUSH_EVENT),
        rule.completionQuestId,
        playerId,
    );
    return true;
}

export function repairAllGauntletCompletionClassificationsSync(
    playerId: number,
): number[] {
    return Object.keys(GAUNTLET_COMPLETION_RULES)
        .map(Number)
        .filter(eventId => repairGauntletCompletionClassificationSync(
            playerId,
            eventId,
        ));
}
