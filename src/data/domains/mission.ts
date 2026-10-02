import { cachedStatement } from "../../lib/cached-statement"
import { getDb } from "../db";
import { PlayerActiveMission, RawPlayerClearedRegularMission, RawPlayerActiveMission, RawPlayerActiveMissionStage } from "../types";
import { deserializeBoolean, serializeBoolean } from "../utils";
import { runPersistenceTransactionSync } from "../../lib/persistence-coordinator";

/**
 * Retrieve a list of a player's cleared regular missions.
 * 
 * @param playerId The ID of the player.
 * @returns A record, where the index is the id of the mission and the value is ???.
 */
export function getPlayerClearedRegularMissionListSync(
    playerId: number
): Record<string, number> {

    const raw = cachedStatement(getDb(), `
    SELECT id, value
    FROM players_cleared_regular_missions
    WHERE player_id = ?
    `).all(playerId) as RawPlayerClearedRegularMission[]

    const record: Record<string, number> = {}

    for (const rawClear of raw) {
        record[rawClear.id.toString()] = rawClear.value
    }

    return record
}

/**
 * Sets a regular mission as having been cleared by a player.
 * 
 * @param playerId The ID of the player.
 * @param missionId The ID of the mission that was cleared.
 * @param value 
 */
function insertPlayerClearedRegularMissionSync(
    playerId: number,
    missionId: number | string,
    value: number
) {
    cachedStatement(getDb(), `
    INSERT INTO players_cleared_regular_missions (id, value, player_id)
    VALUES (?, ?, ?)
    `).run(
        Number(missionId),
        value,
        playerId
    )
}

/**
 * Sets a list of regular missions as having been cleared by a player.
 * 
 * @param playerId The ID of the player.
 * @param missionList The list of missions that were cleared.
 */
export function insertPlayerClearedRegularMissionListSync(
    playerId: number,
    missionList: Record<string, number>
) {
    runPersistenceTransactionSync({ domain: "mission", playerId, operation: "insert_cleared_regular_missions" }, () => {
        for (const [missionId, value] of Object.entries(missionList)) {
            insertPlayerClearedRegularMissionSync(playerId, missionId, value)
        }
    })
}
/**
/**
/**
 * Inserts a singular item into the player's inventory.
 * 
 * @param playerId The ID of the player.
 * @param itemId The ID of the item to insert.
 * @param amount The amount of the item to insert.
 */
function insertPlayerItemSync(
    playerId: number,
    itemId: number | string,
    amount: number
) {
    cachedStatement(getDb(), `
    INSERT INTO players_items (id, amount, player_id)
    VALUES (?, ?, ?)
    `).run(
        Number(itemId),
        amount,
        playerId
    )
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
/**
 * Retrieves the missions that a player is currently completing.
 * 
 * @param playerId The ID of the player.
 * @returns A record of each mission and its current progress.
 */
export function getPlayerActiveMissionsSync(
    playerId: number
): Record<string, PlayerActiveMission> {
    const rawMissions = cachedStatement(getDb(), `
    SELECT id, progress
    FROM players_active_missions
    WHERE player_id = ?
    `).all(playerId) as RawPlayerActiveMission[]

    const rawStages = cachedStatement(getDb(), `
    SELECT id, status, mission_id
    FROM players_active_missions_stages
    WHERE player_id = ?
    `).all(playerId) as RawPlayerActiveMissionStage[]

    const stageBuckets: Record<string, Record<string, boolean>> = {}

    for (const rawStage of rawStages) {
        const missionId = rawStage.mission_id.toString()
        let bucket = stageBuckets[missionId]
        if (!bucket) {
            bucket = {}
            stageBuckets[missionId] = bucket
        }

        bucket[rawStage.id] = deserializeBoolean(rawStage.status)
    }

    const final: Record<string, PlayerActiveMission> = {}

    for (const rawMission of rawMissions) {
        const id = rawMission.id.toString()

        final[id] = {
            progress: rawMission.progress,
            stages: stageBuckets[id] || []
        }
    }

    return final
}

/**
 * Inserts the data for a singular active mission stage into the database.
 * 
 * @param playerId The player's ID.
 * @param stageId The ID of the stage.
 * @param missionId The ID of the mission that this stage belongs to.
 * @param status The status of the stage.
 */
function insertPlayerActiveMissionStageSync(
    playerId: number,
    stageId: number | string,
    missionId: number | string,
    status: boolean
) {
    cachedStatement(getDb(), `
    INSERT INTO players_active_missions_stages (id, status, player_id, mission_id)
    VALUES (?, ?, ?, ?)   
    `).run(
        Number(stageId),
        serializeBoolean(status),
        playerId,
        Number(missionId)
    )
}

/**
 * Inserts a singular active mission into the database.
 * 
 * @param playerId The player's iD>
 * @param missionId The ID of the mission to insert.
 * @param mission The mission's data.
 */
function insertPlayerActiveMissionSync(
    playerId: number,
    missionId: number | string,
    mission: PlayerActiveMission
) {
    cachedStatement(getDb(), `
    INSERT INTO players_active_missions (id, progress, player_id)
    VALUES (?, ?, ?)
    `).run(
        Number(missionId),
        mission.progress,
        playerId
    )

    const stages = mission.stages
    if (stages) {
        for (const [stageId, stage] of Object.entries(stages)) {
            insertPlayerActiveMissionStageSync(playerId, stageId, missionId, stage)
        }
    }
}

/**
 * Batch inserts a record of active missions into the database.
 * 
 * @param playerId The player's ID.
 * @param missions The record of active missions to insert.
 */
export function insertPlayerActiveMissionsSync(
    playerId: number,
    missions: Record<string, PlayerActiveMission>
) {
    runPersistenceTransactionSync({ domain: "mission", playerId, operation: "insert_active_missions" }, () => {
        for (const [missionId, mission] of Object.entries(missions)) {
            insertPlayerActiveMissionSync(playerId, missionId, mission)
        }
    })
}

/**
 * Updates the progress value of a single active mission.
 */
export function updatePlayerActiveMissionSync(
    playerId: number,
    missionId: number | string,
    progress: number
) {
    cachedStatement(getDb(), `
    INSERT INTO players_active_missions (id, progress, player_id)
    VALUES (?, ?, ?)
    ON CONFLICT(id, player_id) DO UPDATE SET progress = excluded.progress
    `).run(Number(missionId), progress, playerId)
}

/** Atomically adds a client-reported counter delta to a mission. */
export function incrementPlayerActiveMissionSync(
    playerId: number,
    missionId: number | string,
    delta: number
) {
    cachedStatement(getDb(), `
    INSERT INTO players_active_missions (id, progress, player_id)
    VALUES (?, ?, ?)
    ON CONFLICT(id, player_id) DO UPDATE SET progress = progress + excluded.progress
    `).run(Number(missionId), delta, playerId)
}

/** Retrieves category-scoped mission progress without mixing equal IDs. */
export function getPlayerCategoryMissionsSync(
    playerId: number,
    category: number,
    missionIds?: readonly number[],
): Record<string, PlayerActiveMission> {
    const ids = missionIds === undefined ? undefined : [...new Set(missionIds)].filter(Number.isSafeInteger)
    if (ids?.length === 0) return {}
    const placeholders = ids?.map(() => "?").join(", ")
    const parameters = [playerId, category, ...(ids ?? [])]
    const missions = cachedStatement(getDb(), `
    SELECT id, progress
    FROM players_category_missions
    WHERE player_id = ? AND category = ?
    ${ids ? `AND id IN (${placeholders})` : ""}
    `).all(...parameters) as RawPlayerActiveMission[]
    const stages = cachedStatement(getDb(), `
    SELECT id, status, mission_id
    FROM players_category_mission_stages
    WHERE player_id = ? AND category = ?
    ${ids ? `AND mission_id IN (${placeholders})` : ""}
    `).all(...parameters) as RawPlayerActiveMissionStage[]

    const stageBuckets: Record<string, Record<string, boolean>> = {}
    for (const stage of stages) {
        const missionId = String(stage.mission_id)
        const bucket = stageBuckets[missionId] ?? {}
        bucket[String(stage.id)] = deserializeBoolean(stage.status)
        stageBuckets[missionId] = bucket
    }

    const result: Record<string, PlayerActiveMission> = {}
    for (const mission of missions) {
        result[String(mission.id)] = {
            progress: mission.progress,
            stages: stageBuckets[String(mission.id)] ?? [],
        }
    }
    return result
}

/** Retrieves several category buckets with two SQLite reads total. */
export function getPlayerCategoryMissionsForCategoriesSync(
    playerId: number,
    categories: readonly number[],
): Record<string, Record<string, PlayerActiveMission>> {
    const uniqueCategories = [...new Set(categories.filter(Number.isSafeInteger))]
    if (uniqueCategories.length === 0) return {}
    const placeholders = uniqueCategories.map(() => "?").join(", ")
    const missions = cachedStatement(getDb(), `
    SELECT category, id, progress
    FROM players_category_missions
    WHERE player_id = ? AND category IN (${placeholders})
    `).all(playerId, ...uniqueCategories) as { category: number, id: number, progress: number }[]
    const stages = cachedStatement(getDb(), `
    SELECT category, id, status, mission_id
    FROM players_category_mission_stages
    WHERE player_id = ? AND category IN (${placeholders})
    `).all(playerId, ...uniqueCategories) as {
        category: number
        id: number
        status: number
        mission_id: number
    }[]

    const stageBuckets = new Map<string, Record<string, boolean>>()
    for (const stage of stages) {
        const missionKey = `${stage.category}:${stage.mission_id}`
        const bucket = stageBuckets.get(missionKey) ?? {}
        bucket[String(stage.id)] = deserializeBoolean(stage.status)
        stageBuckets.set(missionKey, bucket)
    }

    const result: Record<string, Record<string, PlayerActiveMission>> = Object.fromEntries(
        uniqueCategories.map(category => [String(category), {}]),
    )
    for (const mission of missions) {
        result[String(mission.category)][String(mission.id)] = {
            progress: mission.progress,
            stages: stageBuckets.get(`${mission.category}:${mission.id}`) ?? [],
        }
    }
    return result
}

/** Two fixed query plans, restricted to the mission IDs this settlement evaluates. */
export function getPlayerCategoryMissionsForScopesSync(
    playerId: number,
    scopes: readonly { category: number; missionIds: readonly number[] }[],
): Record<string, Record<string, PlayerActiveMission>> {
    const requested = new Map<number, Set<number>>()
    for (const scope of scopes) {
        if (!Number.isSafeInteger(scope.category)) continue
        const ids = requested.get(scope.category) ?? new Set<number>()
        for (const id of scope.missionIds) if (Number.isSafeInteger(id)) ids.add(id)
        requested.set(scope.category, ids)
    }
    const result: Record<string, Record<string, PlayerActiveMission>> = {}
    const pairs: number[][] = []
    for (const [category, ids] of requested) {
        result[String(category)] = {}
        for (const id of ids) pairs.push([category, id])
    }
    if (pairs.length === 0) return result
    const selection = JSON.stringify(pairs)
    const missions = cachedStatement(getDb(), `
        SELECT m.category, m.id, m.progress
        FROM json_each(?) AS requested
        CROSS JOIN players_category_missions AS m
        WHERE m.category = CAST(json_extract(requested.value, '$[0]') AS INTEGER)
          AND m.id = CAST(json_extract(requested.value, '$[1]') AS INTEGER)
          AND m.player_id = ?
    `).all(selection, playerId) as { category: number; id: number; progress: number }[]
    for (const mission of missions) {
        result[String(mission.category)][String(mission.id)] = { progress: mission.progress, stages: [] }
    }
    const stages = cachedStatement(getDb(), `
        SELECT s.category, s.id, s.status, s.mission_id
        FROM json_each(?) AS requested
        CROSS JOIN players_category_mission_stages AS s
        WHERE s.category = CAST(json_extract(requested.value, '$[0]') AS INTEGER)
          AND s.mission_id = CAST(json_extract(requested.value, '$[1]') AS INTEGER)
          AND s.player_id = ?
    `).all(selection, playerId) as { category: number; id: number; status: number; mission_id: number }[]
    for (const stage of stages) {
        const mission = result[String(stage.category)][String(stage.mission_id)]
        if (!mission) continue
        if (Array.isArray(mission.stages)) mission.stages = {}
        mission.stages[String(stage.id)] = deserializeBoolean(stage.status)
    }
    return result
}

export function getPlayerCategoryMissionListSync(
    playerId: number
): Record<string, Record<string, PlayerActiveMission>> {
    const categories = cachedStatement(getDb(), `
    SELECT DISTINCT category
    FROM players_category_missions
    WHERE player_id = ?
    ORDER BY category
    `).all(playerId) as { category: number }[]
    return getPlayerCategoryMissionsForCategoriesSync(
        playerId,
        categories.map(({ category }) => category),
    )
}

export function getPlayerClearedCollectItemEventMissionListSync(
    playerId: number
): Record<string, number> {
    const rows = cachedStatement(getDb(), `
    SELECT mission_id, MAX(id) AS stage
    FROM players_category_mission_stages
    WHERE player_id = ? AND category = 4 AND status = 1
    GROUP BY mission_id
    ORDER BY mission_id
    `).all(playerId) as { mission_id: number; stage: number }[]
    return Object.fromEntries(rows.map(row => [String(row.mission_id), row.stage]))
}

export function insertPlayerCategoryMissionListSync(
    playerId: number,
    categories: Record<string, Record<string, PlayerActiveMission>>
) {
    runPersistenceTransactionSync({ domain: "mission", playerId, operation: "insert_category_missions" }, () => {
        for (const [categoryKey, missions] of Object.entries(categories)) {
            const category = Number(categoryKey)
            if (!Number.isInteger(category)) continue
            for (const [missionId, mission] of Object.entries(missions)) {
                updatePlayerCategoryMissionSync(playerId, category, missionId, mission.progress)
                if (!mission.stages || Array.isArray(mission.stages)) continue
                for (const [stageId, received] of Object.entries(mission.stages)) {
                    updatePlayerCategoryMissionStageSync(playerId, category, stageId, missionId, received)
                }
            }
        }
    })
}

export function updatePlayerCategoryMissionSync(
    playerId: number,
    category: number,
    missionId: number | string,
    progress: number
) {
    cachedStatement(getDb(), `
    INSERT INTO players_category_missions (category, id, progress, player_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(category, id, player_id) DO UPDATE SET progress = excluded.progress
    `).run(category, Number(missionId), progress, playerId)
}

export interface PlayerCategoryMissionProgressUpdate {
    readonly category: number
    readonly missionId: number
    readonly progress: number
}

export function updatePlayerCategoryMissionBatchSync(
    playerId: number,
    updates: readonly PlayerCategoryMissionProgressUpdate[],
): void {
    if (updates.length === 0) return
    const statement = cachedStatement(getDb(), `
    INSERT INTO players_category_missions (category, id, progress, player_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(category, id, player_id) DO UPDATE SET progress = excluded.progress
    `)
    for (const update of updates) {
        statement.run(update.category, update.missionId, update.progress, playerId)
    }
}

export function incrementPlayerCategoryMissionSync(
    playerId: number,
    category: number,
    missionId: number | string,
    delta: number
) {
    cachedStatement(getDb(), `
    INSERT INTO players_category_missions (category, id, progress, player_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(category, id, player_id) DO UPDATE SET progress = progress + excluded.progress
    `).run(category, Number(missionId), delta, playerId)
}

export function updatePlayerCategoryMissionStageSync(
    playerId: number,
    category: number,
    stageId: number | string,
    missionId: number | string,
    status: boolean
) {
    cachedStatement(getDb(), `
    INSERT INTO players_category_mission_stages (category, id, status, player_id, mission_id)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(category, id, mission_id, player_id) DO UPDATE SET status = excluded.status
    `).run(category, Number(stageId), serializeBoolean(status), playerId, Number(missionId))
}

export interface PlayerCategoryMissionStageUpdate {
    readonly category: number
    readonly missionId: number
    readonly stageId: number
    readonly status: boolean
}

export function updatePlayerCategoryMissionStageBatchSync(
    playerId: number,
    updates: readonly PlayerCategoryMissionStageUpdate[],
): void {
    if (updates.length === 0) return
    const statement = cachedStatement(getDb(), `
    INSERT INTO players_category_mission_stages (category, id, status, player_id, mission_id)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(category, id, mission_id, player_id) DO UPDATE SET status = excluded.status
    `)
    for (const update of updates) {
        statement.run(
            update.category,
            update.stageId,
            serializeBoolean(update.status),
            playerId,
            update.missionId,
        )
    }
}

export function deletePlayerCategoryMissionsSync(playerId: number, category: number) {
    runPersistenceTransactionSync({ domain: "mission", playerId, operation: "delete_category_missions" }, () => {
        cachedStatement(getDb(), `DELETE FROM players_category_mission_stages WHERE player_id = ? AND category = ?`).run(playerId, category)
        cachedStatement(getDb(), `DELETE FROM players_category_missions WHERE player_id = ? AND category = ?`).run(playerId, category)
    })
}

/**
 * Updates the status of a single active mission stage (claimed/unclaimed).
 */
export function updatePlayerActiveMissionStageSync(
    playerId: number,
    stageId: number | string,
    missionId: number | string,
    status: boolean
) {
    cachedStatement(getDb(), `
    INSERT OR REPLACE INTO players_active_missions_stages (id, status, player_id, mission_id)
    VALUES (?, ?, ?, ?)
    `).run(
        Number(stageId),
        serializeBoolean(status),
        playerId,
        Number(missionId)
    )
}
