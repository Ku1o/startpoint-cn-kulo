import { getDb } from "../../data/db"
import { SaveValidator } from "./types"

const MAIN_QUEST_SECTION = 1
const UNISON_UNLOCK_QUEST_ID = 1006001
const FIRST_QUEST_AFTER_UNISON_UNLOCK = 1006002

export type UnisonUnlockRepairStatus = "not_eligible" | "needs_repair" | "already_unlocked"

interface RawUnisonUnlockProgress {
    finished: number
}

/**
 * A finished 1-6-1 row is the authoritative unison unlock record. Only a
 * completed later main quest is accepted as evidence that a missing or
 * unfinished 1-6-1 row is damaged legacy data.
 */
export function getUnisonUnlockRepairStatusSync(playerId: number): UnisonUnlockRepairStatus {
    const progress = getDb().prepare(`
        SELECT finished
        FROM players_quest_progress
        WHERE player_id = ?
          AND section = ?
          AND quest_id = ?
    `).get(
        playerId,
        MAIN_QUEST_SECTION,
        UNISON_UNLOCK_QUEST_ID,
    ) as RawUnisonUnlockProgress | undefined
    if (progress?.finished === 1) return "already_unlocked"

    const laterCompletedQuest = getDb().prepare(`
        SELECT 1
        FROM players_quest_progress
        WHERE player_id = ?
          AND section = ?
          AND quest_id >= ?
          AND finished = 1
        LIMIT 1
    `).get(playerId, MAIN_QUEST_SECTION, FIRST_QUEST_AFTER_UNISON_UNLOCK)

    return laterCompletedQuest ? "needs_repair" : "not_eligible"
}

/**
 * Repairs only the authoritative 1-6-1 completion bit. Tutorial hints,
 * multiplayer host completion, explicit unlocked flags and clear rank are
 * independent state and must not be fabricated by this compatibility repair.
 */
export function repairUnisonUnlockProgressSync(playerId: number): number {
    const db = getDb()
    const result = db.prepare(`
        INSERT INTO players_quest_progress (
            section,
            quest_id,
            finished,
            player_id
        )
        SELECT ?, ?, 1, ?
        WHERE EXISTS (
            SELECT 1
            FROM players_quest_progress
            WHERE player_id = ?
              AND section = ?
              AND quest_id >= ?
              AND finished = 1
        )
        ON CONFLICT(section, quest_id, player_id) DO UPDATE SET
            finished = 1
        WHERE players_quest_progress.finished = 0
          AND EXISTS (
            SELECT 1
            FROM players_quest_progress AS later_progress
            WHERE later_progress.player_id = players_quest_progress.player_id
              AND later_progress.section = ?
              AND later_progress.quest_id >= ?
              AND later_progress.finished = 1
        )
    `).run(
        MAIN_QUEST_SECTION,
        UNISON_UNLOCK_QUEST_ID,
        playerId,
        playerId,
        MAIN_QUEST_SECTION,
        FIRST_QUEST_AFTER_UNISON_UNLOCK,
        MAIN_QUEST_SECTION,
        FIRST_QUEST_AFTER_UNISON_UNLOCK,
    )

    const changes = result.changes
    if (changes > 0) {
        console.log(
            `[UNISON_UNLOCK] repaired player=${playerId} `
            + `quest=${UNISON_UNLOCK_QUEST_ID} finished=1`
        )
    }
    return changes
}

export const UnisonUnlockValidator: SaveValidator = {
    name: "unison-unlock",
    validate: repairUnisonUnlockProgressSync
}
