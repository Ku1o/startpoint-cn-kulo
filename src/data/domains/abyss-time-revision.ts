import { getDb } from "../db"
import { ABYSS_EVENT_IDS, ABYSS_NORMAL_EVENT_ID, ABYSS_EX_EVENT_ID, isAbyssEvent } from "../../lib/abyss-modes"
import {
    ABYSS_FIRST_QUEST_ID,
    ABYSS_LAST_QUEST_ID,
    getAbyssTimeRevision,
} from "../../lib/abyss-time-revision"
import { QuestCategory } from "../../lib/types/quest"

/** Clear only the finite tower's times, including legacy saves and restored saves. */
export function refreshPlayerAbyssBestTimesSync(playerId: number, eventId?: number): string | null {
    if (eventId === undefined) {
        let normalRevision: string | null = null
        for (const id of ABYSS_EVENT_IDS) {
            const result = refreshPlayerAbyssBestTimesSync(playerId, id)
            if (id === ABYSS_NORMAL_EVENT_ID) normalRevision = result
        }
        return normalRevision
    }
    if (!isAbyssEvent(eventId)) return null
    const revision = getAbyssTimeRevision(eventId)
    if (revision === null) return null
    const hasStaleRows = getDb().prepare(`
        SELECT 1 AS found
        FROM players_quest_progress
        WHERE player_id = ? AND section = ? AND quest_id BETWEEN ? AND ?
          AND (best_time_revision IS NULL OR best_time_revision != ?)
        LIMIT 1
    `).get(playerId, QuestCategory.RUSH_EVENT,
        eventId * 1000 + 1, eventId * 1000 + (eventId === ABYSS_EX_EVENT_ID ? 30 : 98), revision)
    if (!hasStaleRows) return revision
    getDb().prepare(`
        UPDATE players_quest_progress
        SET best_elapsed_time_ms = NULL, best_time_revision = ?
        WHERE player_id = ? AND section = ? AND quest_id BETWEEN ? AND ?
          AND (best_time_revision IS NULL OR best_time_revision != ?)
    `).run(revision, playerId, QuestCategory.RUSH_EVENT,
        eventId * 1000 + 1, eventId * 1000 + (eventId === ABYSS_EX_EVENT_ID ? 30 : 98), revision)
    return revision
}
