import type { Database as BetterSqlite3Database } from "better-sqlite3"
import {
    getRaidEventMissionIds,
    getRaidEventQuestIds,
    isSupportedRaidEventId,
} from "./raid-event-config"
import { QuestCategory } from "./types"

export interface RaidEventResetCounts {
    globalState: number
    globalKillLedger: number
    overallRewardReceipts: number
    questProgress: number
    drawnQuests: number
    eventMissions: number
    eventMissionStages: number
    rushCompatibilityState: number
    rushClearedFolders: number
    rushPlayedParties: number
    activeQuests: number
}

function validateEventId(eventId: number): number[] {
    if (!isSupportedRaidEventId(eventId)) {
        throw new Error(`Unsupported raid event: ${eventId}`)
    }
    return getRaidEventQuestIds(eventId)
}

function questPlaceholders(questIds: number[]): string {
    return questIds.map(() => "?").join(", ")
}

function countSync(
    database: BetterSqlite3Database,
    sql: string,
    ...params: unknown[]
): number {
    const row = database.prepare(sql).get(...params) as { count: number }
    return Number(row.count)
}

export function previewRaidEventResetSync(
    database: BetterSqlite3Database,
    eventId: number,
): RaidEventResetCounts {
    const questIds = validateEventId(eventId)
    const missionIds = getRaidEventMissionIds(eventId)
    const placeholders = questPlaceholders(questIds)
    const missionPlaceholders = questPlaceholders(missionIds)
    const raidCategory = Number(QuestCategory.RAID_EVENT)

    return {
        globalState: countSync(
            database,
            `SELECT COUNT(*) AS count FROM raid_event_global_state WHERE event_id = ?`,
            eventId,
        ),
        globalKillLedger: countSync(
            database,
            `SELECT COUNT(*) AS count FROM raid_event_global_kill_ledger WHERE event_id = ?`,
            eventId,
        ),
        overallRewardReceipts: countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_raid_event_overall_rewards WHERE event_id = ?`,
            eventId,
        ),
        questProgress: countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_quest_progress
             WHERE section = ? AND quest_id IN (${placeholders})`,
            raidCategory,
            ...questIds,
        ),
        drawnQuests: countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_drawn_quests
             WHERE category_id = ? AND quest_id IN (${placeholders})`,
            raidCategory,
            ...questIds,
        ),
        eventMissions: missionIds.length === 0 ? 0 : countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_category_missions
             WHERE category = 3 AND id IN (${missionPlaceholders})`,
            ...missionIds,
        ),
        eventMissionStages: missionIds.length === 0 ? 0 : countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_category_mission_stages
             WHERE category = 3 AND mission_id IN (${missionPlaceholders})`,
            ...missionIds,
        ),
        rushCompatibilityState: countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_rush_events WHERE event_id = ?`,
            eventId,
        ),
        rushClearedFolders: countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_rush_events_cleared_folders WHERE event_id = ?`,
            eventId,
        ),
        rushPlayedParties: countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_rush_events_played_parties WHERE event_id = ?`,
            eventId,
        ),
        activeQuests: countSync(
            database,
            `SELECT COUNT(*) AS count FROM players_active_quests
             WHERE event_id = ? OR (category = ? AND quest_id IN (${placeholders}))`,
            eventId,
            raidCategory,
            ...questIds,
        ),
    }
}

/**
 * Reset one Raid event into a fresh run while preserving player inventory,
 * already-issued rewards, accounts, and edited Raid formations.
 *
 * Callers must stop the game service first so no in-memory active battle can
 * settle after this transaction commits.
 */
export function resetRaidEventSync(
    database: BetterSqlite3Database,
    eventId: number,
): RaidEventResetCounts {
    const questIds = validateEventId(eventId)
    const missionIds = getRaidEventMissionIds(eventId)
    const placeholders = questPlaceholders(questIds)
    const missionPlaceholders = questPlaceholders(missionIds)
    const raidCategory = Number(QuestCategory.RAID_EVENT)

    return database.transaction(() => {
        const before = previewRaidEventResetSync(database, eventId)

        database.prepare(`DELETE FROM players_active_quests
            WHERE event_id = ? OR (category = ? AND quest_id IN (${placeholders}))`
        ).run(eventId, raidCategory, ...questIds)
        database.prepare(`DELETE FROM players_drawn_quests
            WHERE category_id = ? AND quest_id IN (${placeholders})`
        ).run(raidCategory, ...questIds)
        database.prepare(`DELETE FROM players_quest_progress
            WHERE section = ? AND quest_id IN (${placeholders})`
        ).run(raidCategory, ...questIds)
        if (missionIds.length > 0) {
            database.prepare(`DELETE FROM players_category_mission_stages
                WHERE category = 3 AND mission_id IN (${missionPlaceholders})`
            ).run(...missionIds)
            database.prepare(`DELETE FROM players_category_missions
                WHERE category = 3 AND id IN (${missionPlaceholders})`
            ).run(...missionIds)
        }
        database.prepare(`DELETE FROM players_rush_events_played_parties WHERE event_id = ?`)
            .run(eventId)
        database.prepare(`DELETE FROM players_rush_events_cleared_folders WHERE event_id = ?`)
            .run(eventId)
        database.prepare(`DELETE FROM players_rush_events WHERE event_id = ?`).run(eventId)
        database.prepare(`DELETE FROM players_raid_event_overall_rewards WHERE event_id = ?`)
            .run(eventId)
        database.prepare(`DELETE FROM raid_event_global_kill_ledger WHERE event_id = ?`)
            .run(eventId)
        database.prepare(`DELETE FROM raid_event_global_state WHERE event_id = ?`).run(eventId)

        return before
    })()
}
