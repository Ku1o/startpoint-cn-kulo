import { getDb } from "../db"
import {
    ABYSS_FIRST_QUEST_ID,
    ABYSS_LAST_QUEST_ID,
    getAbyssTimeRevision,
} from "../../lib/abyss-time-revision"
import { QuestCategory } from "../../lib/types/quest"

/** Clear only the finite tower's times, including legacy saves and restored saves. */
export function refreshPlayerAbyssBestTimesSync(playerId: number): string | null {
    const revision = getAbyssTimeRevision()
    if (revision === null) return null
    getDb().prepare(`
        UPDATE players_quest_progress
        SET best_elapsed_time_ms = NULL, best_time_revision = ?
        WHERE player_id = ? AND section = ? AND quest_id BETWEEN ? AND ?
          AND (best_time_revision IS NULL OR best_time_revision != ?)
    `).run(revision, playerId, QuestCategory.RUSH_EVENT,
        ABYSS_FIRST_QUEST_ID, ABYSS_LAST_QUEST_ID, revision)
    return revision
}
