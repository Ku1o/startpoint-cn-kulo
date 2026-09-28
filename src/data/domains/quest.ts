import { cachedStatement } from "../../lib/cached-statement"
import { getDb } from "../db";
import { PlayerQuestProgress, PlayerDrawnQuest, RawPlayerQuestProgress, RawPlayerDrawnQuest } from "../types";
import { deserializeBoolean, serializeBoolean } from "../utils";
import { refreshPlayerAbyssBestTimesSync } from "./abyss-time-revision";
import { abyssEventFromQuest } from "../../lib/abyss-modes";
import { isAbyssFiniteQuest } from "../../lib/abyss-time-revision";
import { runPersistenceTransactionSync } from "../../lib/persistence-coordinator";

/**
 * Converts a RawPlayerQuestProgress object into a PlayerQuestProgress object.
 * 
 * @param raw The raw object to convert.
 * @returns The converted object.
 */
function buildPlayerQuestProgress(
    raw: RawPlayerQuestProgress
): PlayerQuestProgress {
    return {
        questId: raw.quest_id,
        finished: deserializeBoolean(raw.finished),
        hostFinished: deserializeBoolean(raw.host_finished ?? 0),
        unlocked: deserializeBoolean(raw.unlocked),
        highScore: raw.high_score,
        clearRank: raw.clear_rank,
        bestElapsedTimeMs: raw.best_elapsed_time_ms,
        leaderCharacterId: raw.leader_character_id,
        multiClearCount: raw.multi_clear_count,
        sPlusRewardReceived: deserializeBoolean(raw.s_plus_reward_received ?? 0)
    }
}

/**
 * Gets a player's overall quest progressfrom the database.
 * 
 * @param playerId The player's ID.
 * @returns A record where the index is the section and the value is a list of PlayerQuestProgress.
 */
export function getPlayerQuestProgressSync(
    playerId: number
): Record<string, PlayerQuestProgress[]> {
    refreshPlayerAbyssBestTimesSync(playerId)
    const rawProgress = cachedStatement(getDb(), `
    SELECT section, quest_id, finished, host_finished, unlocked, high_score, clear_rank, best_elapsed_time_ms, leader_character_id, multi_clear_count, s_plus_reward_received
    FROM players_quest_progress
    WHERE player_id = ?
    `).all(playerId) as RawPlayerQuestProgress[]

    const mapped: Record<string, PlayerQuestProgress[]> = {}

    for (const raw of rawProgress) {
        const section = raw.section.toString()
        let bucket: PlayerQuestProgress[] = mapped[section]
        if (!bucket) {
            bucket = []
            mapped[section] = bucket
        }
        bucket.push(buildPlayerQuestProgress(raw))
    }

    return mapped
}

export interface PlayerQuestProgressScope {
    /** Whole quest sections required by range-based mission conditions. */
    readonly sections?: readonly number[]
    /** Normalized or stored quest ids required by exact mission conditions. */
    readonly questIds?: readonly number[]
}

export interface PlayerSingleQuestHistorySummary {
    bestElapsedTimeMs: number | null
    highScore: number
    ssCount: number
}

/** Historical single-only facts; shared single/co-op categories cannot prove the mode. */
export function getPlayerSingleQuestHistorySummarySync(playerId: number): PlayerSingleQuestHistorySummary {
    refreshPlayerAbyssBestTimesSync(playerId)
    return cachedStatement(getDb(), `
        SELECT MIN(CASE WHEN finished = 1 AND best_elapsed_time_ms > 0
                       AND best_elapsed_time_ms <= 1.7976931348623157e308
                       THEN best_elapsed_time_ms END) AS bestElapsedTimeMs,
               MAX(0, COALESCE(MAX(high_score), 0)) AS highScore,
               COALESCE(SUM(CASE WHEN finished = 1 AND clear_rank = 5 THEN 1 ELSE 0 END), 0) AS ssCount
        FROM players_quest_progress
        WHERE player_id = ? AND section NOT IN (2, 8, 19, 26)
    `).get(playerId) as PlayerSingleQuestHistorySummary
}

/**
 * Reads only the quest rows needed by an Active Mission reconciliation.
 * Section 4 ids are accepted in either stored or 10,000,000-offset form.
 */
export function getPlayerQuestProgressSubsetSync(
    playerId: number,
    scope: PlayerQuestProgressScope,
): Record<string, PlayerQuestProgress[]> {
    refreshPlayerAbyssBestTimesSync(playerId)
    const sections = [...new Set((scope.sections ?? [])
        .map(Number)
        .filter(value => Number.isSafeInteger(value) && value >= 0))]
    const requestedQuestIds = [...new Set((scope.questIds ?? [])
        .map(Number)
        .filter(value => Number.isSafeInteger(value) && value >= 0))]
    const storedQuestIds = [...new Set(requestedQuestIds.flatMap(questId => (
        questId >= 10_000_000 ? [questId, questId - 10_000_000] : [questId]
    )))]
    if (sections.length === 0 && storedQuestIds.length === 0) return {}

    const rows = new Map<string, RawPlayerQuestProgress>()
    const remember = (raw: RawPlayerQuestProgress) => {
        rows.set(`${raw.section}:${raw.quest_id}`, raw)
    }
    const columns = `section, quest_id, finished, host_finished, unlocked, high_score,
        clear_rank, best_elapsed_time_ms, leader_character_id, multi_clear_count,
        s_plus_reward_received`

    if (sections.length > 0) {
        const placeholders = sections.map(() => "?").join(", ")
        const found = cachedStatement(getDb(), `
            SELECT ${columns}
            FROM players_quest_progress
            WHERE player_id = ? AND section IN (${placeholders})
        `).all(playerId, ...sections) as RawPlayerQuestProgress[]
        for (const raw of found) remember(raw)
    }

    // Keep comfortably below SQLite builds with a 999-variable default.
    for (let offset = 0; offset < storedQuestIds.length; offset += 400) {
        const chunk = storedQuestIds.slice(offset, offset + 400)
        const placeholders = chunk.map(() => "?").join(", ")
        const found = cachedStatement(getDb(), `
            SELECT ${columns}
            FROM players_quest_progress
            WHERE player_id = ? AND quest_id IN (${placeholders})
        `).all(playerId, ...chunk) as RawPlayerQuestProgress[]
        for (const raw of found) remember(raw)
    }

    const mapped: Record<string, PlayerQuestProgress[]> = {}
    for (const raw of rows.values()) {
        const section = String(raw.section)
        ;(mapped[section] ??= []).push(buildPlayerQuestProgress(raw))
    }
    return mapped
}

export function countFinishedPlayerQuestsByCategorySync(
    playerId: number,
    category: number,
): number {
    const row = cachedStatement(getDb(), `
    SELECT COUNT(*) AS count
    FROM players_quest_progress
    WHERE player_id = ? AND section = ? AND finished = 1
    `).get(playerId, category) as { count?: unknown } | undefined
    const count = Number(row?.count)
    return Number.isSafeInteger(count) && count >= 0 ? count : 0
}

export function countFinishedPlayerQuestsSync(playerId: number): number {
    const row = cachedStatement(getDb(), `
    SELECT COUNT(*) AS count
    FROM players_quest_progress
    WHERE player_id = ? AND finished = 1
    `).get(playerId) as { count?: unknown } | undefined
    const count = Number(row?.count)
    return Number.isSafeInteger(count) && count >= 0 ? count : 0
}

/**
 * Gets the progress of a singular quest for a player..
 * 
 * @param playerId The ID of the player.
 * @param section The section of the quest.
 * @param questId The ID of the quest.
 * @returns The quest's progress data, or null if it doesn't exist.
 */
export function getPlayerSingleQuestProgressSync(
    playerId: number,
    section: number | string,
    questId: number | string
): PlayerQuestProgress | null {
    const abyssEventId = isAbyssFiniteQuest(section, questId)
        ? abyssEventFromQuest(section, questId)
        : null
    if (abyssEventId !== null) refreshPlayerAbyssBestTimesSync(playerId, abyssEventId)
    const rawProgress = cachedStatement(getDb(), `
    SELECT section, quest_id, finished, host_finished, unlocked, high_score, clear_rank, best_elapsed_time_ms, leader_character_id, multi_clear_count, s_plus_reward_received
    FROM players_quest_progress
    WHERE player_id = ? AND section = ? AND quest_id = ?
    `).get(playerId, Number(section), Number(questId)) as RawPlayerQuestProgress

    if (rawProgress === undefined) return null;

    return buildPlayerQuestProgress(rawProgress)
}

/** Reads exact ids in one section without broadening to other quest categories. */
export function getPlayerQuestProgressBySectionAndIdsSync(
    playerId: number,
    section: number | string,
    questIds: readonly number[],
): PlayerQuestProgress[] {
    const sectionId = Number(section)
    const ids = [...new Set(questIds)].filter(id => Number.isSafeInteger(id) && id >= 0)
    if (!Number.isSafeInteger(sectionId) || sectionId < 0 || ids.length === 0) return []
    if (ids.some(id => isAbyssFiniteQuest(sectionId, id))) refreshPlayerAbyssBestTimesSync(playerId)
    const result: PlayerQuestProgress[] = []
    for (let offset = 0; offset < ids.length; offset += 400) {
        const chunk = ids.slice(offset, offset + 400)
        const rows = cachedStatement(getDb(), `
            SELECT section, quest_id, finished, host_finished, unlocked, high_score, clear_rank,
                best_elapsed_time_ms, leader_character_id, multi_clear_count, s_plus_reward_received
            FROM players_quest_progress
            WHERE player_id = ? AND section = ? AND quest_id IN (${chunk.map(() => "?").join(", ")})
        `).all(playerId, sectionId, ...chunk) as RawPlayerQuestProgress[]
        result.push(...rows.map(buildPlayerQuestProgress))
    }
    return result
}

/**
 * Inserts a singular quest progress into the database.
 * 
 * @param playerId The ID of the player.
 * @param section The section that this quest progress belongs to.
 * @param data The data of this quest progress.
 */
export function insertPlayerQuestProgressSync(
    playerId: number,
    section: number | string,
    data: PlayerQuestProgress
) {
    const timeRevision = isAbyssFiniteQuest(section, data.questId)
        ? refreshPlayerAbyssBestTimesSync(playerId, Math.floor(data.questId / 1000)) : null
    cachedStatement(getDb(), `
    INSERT INTO players_quest_progress (section, quest_id, finished, host_finished, unlocked, high_score, clear_rank, best_elapsed_time_ms, leader_character_id, s_plus_reward_received, player_id, best_time_revision)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
        Number(section),
        data.questId,
        serializeBoolean(data.finished),
        serializeBoolean(data.hostFinished ?? false),
        serializeBoolean(data.unlocked ?? false),
        data.highScore ?? null,
        data.clearRank ?? null,
        data.bestElapsedTimeMs ?? null,
        data.leaderCharacterId ?? null,
        serializeBoolean(data.sPlusRewardReceived ?? false),
        playerId,
        timeRevision
    )
}

/**
 * Batch inserts a record of quest progress into the database.
 * 
 * @param playerId The player's ID.
 * @param progressList The record of quest progress.
 */
export function insertPlayerQuestProgressListSync(
    playerId: number,
    progressList: Record<string, PlayerQuestProgress[]>
) {
    runPersistenceTransactionSync({ domain: "single-quest", playerId, operation: "insert_quest_progress_list" }, () => {
        for (const [section, progresses] of Object.entries(progressList)) {
            for (const progress of progresses) {
                insertPlayerQuestProgressSync(playerId, section, progress)
            }
        }
    })
}

/**
 * Updates the progress for a single player's quest.
 * 
 * @param playerId The ID of the player.
 * @param section The section that the quest belongs to.
 * @param data The partial data of the quest progress to update.
 */
export function updatePlayerQuestProgressSync(
    playerId: number,
    section: number | string,
    data: Partial<PlayerQuestProgress> & Pick<PlayerQuestProgress, 'questId'>
) {
    if (isAbyssFiniteQuest(section, data.questId)) refreshPlayerAbyssBestTimesSync(playerId)
    const fieldMap: Record<string, string> = {
        'finished': 'finished',
        'hostFinished': 'host_finished',
        'unlocked': 'unlocked',
        'highScore': 'high_score',
        'clearRank': 'clear_rank',
        'bestElapsedTimeMs': 'best_elapsed_time_ms',
        'leaderCharacterId': 'leader_character_id',
        'sPlusRewardReceived': 's_plus_reward_received'
    }

    const sets: string[] = []
    const values: any[] = []
    for (const key in data) {
        const value = data[key as keyof PlayerQuestProgress]
        const mapped = fieldMap[key]
        if (mapped && value !== undefined) {
            sets.push(`${mapped} = ?`)
            if (typeof (value) === "boolean") {
                values.push(serializeBoolean(value))
            } else {
                values.push(value)
            }
        }
    }

    if (sets.length > 0) cachedStatement(getDb(), `
        UPDATE players_quest_progress
        SET ${sets.join(', ')}
        WHERE section = ? AND quest_id = ? AND player_id = ?
        `).run([...values, Number(section), data.questId, playerId]);
}

export function incrementPlayerQuestMultiClearSync(
    playerId: number,
    section: number | string,
    questId: number | string,
): void {
    cachedStatement(getDb(), `
    UPDATE players_quest_progress
    SET multi_clear_count = multi_clear_count + 1
    WHERE player_id = ? AND section = ? AND quest_id = ?
    `).run(playerId, Number(section), Number(questId))
}

/**
 * Converts a RawPlayerGachaInfo object into a PlayerGachaInfo object.
 * 
 * @param rawInfo The raw object to convert.
 * @returns The converted object.
 */
/**
 * Gets a player's drawn quests list.
 * 
 * @param playerId The player's ID.
 * @returns A list of the player's drawn quests.
 */
export function getPlayerDrawnQuestsSync(
    playerId: number
): PlayerDrawnQuest[] {
    const rawQuests = cachedStatement(getDb(), `
    SELECT category_id, quest_id, odds_id
    FROM players_drawn_quests
    WHERE player_id = ?
    `).all(playerId) as RawPlayerDrawnQuest[]

    return rawQuests.map(raw => {
        return {
            categoryId: raw.category_id,
            questId: raw.quest_id,
            oddsId: raw.odds_id
        }
    })
}

/**
 * Inserts a singular drawn quest into a player's data.
 * 
 * @param playerId The ID of the player.
 * @param drawnQuest The drawn quest to insert.
 */
function insertPlayerDrawnQuestSync(
    playerId: number,
    drawnQuest: PlayerDrawnQuest
) {
    cachedStatement(getDb(), `
    INSERT INTO players_drawn_quests (category_id, quest_id, odds_id, player_id)
    VALUES (?, ?, ?, ?)
    `).run(
        drawnQuest.categoryId,
        drawnQuest.questId,
        drawnQuest.oddsId,
        playerId
    )
}

/**
 * Batch inserts a list of drawn quests into the database.
 * 
 * @param playerId The ID of the player.
 * @param drawnQuests The list of drawn quests to insert.
 */
export function insertPlayerDrawnQuestsSync(
    playerId: number,
    drawnQuests: PlayerDrawnQuest[]
) {
    runPersistenceTransactionSync({ domain: "single-quest", playerId, operation: "insert_drawn_quests" }, () => {
        for (const drawnQuest of drawnQuests) {
            insertPlayerDrawnQuestSync(playerId, drawnQuest)
        }
    })
}

/**
/**
/**
/**
 * Retrieves the missions that a player is currently completing.
 * 
 * @param playerId The ID of the player.
 * @returns A record of each mission and its current progress.
 */
