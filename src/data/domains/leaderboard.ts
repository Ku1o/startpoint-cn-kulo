import { getDb } from "../db"

export type LeaderboardRunStatus = "active" | "completed" | "abandoned"

export interface LeaderboardRun {
    id: number
    competitionKey: string
    playerId: number
    playerName: string | null
    season: number
    status: LeaderboardRunStatus
    startedAtMs: number
    finishedAtMs: number | null
    serverDurationMs: number | null
    clientBattleMs: number
    roundsCleared: number
    totalRounds: number
    trackedFromRound: number
    pendingRound: number | null
    pendingQuestId: number | null
    pendingStartedAtMs: number | null
    characterIds: (number | null)[]
    unisonCharacterIds: (number | null)[]
    evolutionImgLevels: (number | null)[]
}

interface RawRun {
    id: number
    competition_key: string
    player_id: number
    player_name: string | null
    season: number
    status: LeaderboardRunStatus
    started_at_ms: number
    finished_at_ms: number | null
    server_duration_ms: number | null
    client_battle_ms: number
    rounds_cleared: number
    total_rounds: number
    tracked_from_round: number
    pending_round: number | null
    pending_quest_id: number | null
    pending_started_at_ms: number | null
    character_id_1: number | null
    character_id_2: number | null
    character_id_3: number | null
    unison_character_id_1: number | null
    unison_character_id_2: number | null
    unison_character_id_3: number | null
    evolution_img_level_1: number | null
    evolution_img_level_2: number | null
    evolution_img_level_3: number | null
}

const RUN_COLUMNS = `id, competition_key, player_id, player_name, season, status,
    started_at_ms, finished_at_ms, server_duration_ms, client_battle_ms,
    rounds_cleared, total_rounds, tracked_from_round, pending_round,
    pending_quest_id, pending_started_at_ms,
    character_id_1, character_id_2, character_id_3,
    unison_character_id_1, unison_character_id_2, unison_character_id_3,
    evolution_img_level_1, evolution_img_level_2, evolution_img_level_3`

function deserializeRun(raw: RawRun): LeaderboardRun {
    return {
        id: raw.id,
        competitionKey: raw.competition_key,
        playerId: raw.player_id,
        playerName: raw.player_name,
        season: raw.season,
        status: raw.status,
        startedAtMs: raw.started_at_ms,
        finishedAtMs: raw.finished_at_ms,
        serverDurationMs: raw.server_duration_ms,
        clientBattleMs: raw.client_battle_ms,
        roundsCleared: raw.rounds_cleared,
        totalRounds: raw.total_rounds,
        trackedFromRound: raw.tracked_from_round,
        pendingRound: raw.pending_round,
        pendingQuestId: raw.pending_quest_id,
        pendingStartedAtMs: raw.pending_started_at_ms,
        characterIds: [raw.character_id_1, raw.character_id_2, raw.character_id_3],
        unisonCharacterIds: [raw.unison_character_id_1, raw.unison_character_id_2, raw.unison_character_id_3],
        evolutionImgLevels: [raw.evolution_img_level_1, raw.evolution_img_level_2, raw.evolution_img_level_3],
    }
}

export function getLeaderboardSeasonSync(
    competitionKey: string,
    nowMs: number = Date.now(),
    contentRevision?: string,
): number {
    if (contentRevision !== undefined && contentRevision.trim() === "") {
        throw new Error("contentRevision must be a non-empty string when provided.")
    }
    const db = getDb()
    return db.transaction(() => {
        db.prepare(`
            INSERT OR IGNORE INTO leaderboard_seasons
                (competition_key, season, started_at_ms, source, content_revision)
            VALUES (?, 1, ?, 'initial', ?)
        `).run(competitionKey, nowMs, contentRevision ?? null)
        const row = db.prepare(`
            SELECT season, content_revision
            FROM leaderboard_seasons WHERE competition_key = ?
        `).get(competitionKey) as {
            season: number
            content_revision: string | null
        }
        if (contentRevision === undefined || row.content_revision === contentRevision) {
            return row.season
        }

        const nextSeason = row.season + 1
        db.prepare(`
            UPDATE leaderboard_seasons
            SET season = ?, started_at_ms = ?, source = ?, content_revision = ?
            WHERE competition_key = ? AND season = ?
        `).run(
            nextSeason,
            nowMs,
            `content:${contentRevision}`,
            contentRevision,
            competitionKey,
            row.season,
        )
        abandonLeaderboardRunsSync({ competitionKey, endedAtMs: nowMs })
        return nextSeason
    })()
}

export function getActiveLeaderboardRunSync(
    playerId: number,
    competitionKey: string,
): LeaderboardRun | null {
    const row = getDb().prepare(`
        SELECT ${RUN_COLUMNS}
        FROM leaderboard_runs
        WHERE player_id = ? AND competition_key = ? AND status = 'active'
        ORDER BY id DESC LIMIT 1
    `).get(playerId, competitionKey) as RawRun | undefined
    return row === undefined ? null : deserializeRun(row)
}

export function insertLeaderboardRunSync(input: {
    competitionKey: string
    playerId: number
    playerName: string | null
    season: number
    startedAtMs: number
    totalRounds: number
    trackedFromRound: number
    pendingRound: number
    pendingQuestId: number
}): LeaderboardRun {
    const db = getDb()
    const result = db.prepare(`
        INSERT INTO leaderboard_runs (
            competition_key, player_id, player_name, season, status,
            started_at_ms, client_battle_ms, rounds_cleared, total_rounds,
            tracked_from_round, pending_round, pending_quest_id, pending_started_at_ms
        ) VALUES (?, ?, ?, ?, 'active', ?, 0, ?, ?, ?, ?, ?, ?)
    `).run(
        input.competitionKey,
        input.playerId,
        input.playerName,
        input.season,
        input.startedAtMs,
        Math.max(0, input.trackedFromRound - 1),
        input.totalRounds,
        input.trackedFromRound,
        input.pendingRound,
        input.pendingQuestId,
        input.startedAtMs,
    )
    const row = db.prepare(`SELECT ${RUN_COLUMNS} FROM leaderboard_runs WHERE id = ?`)
        .get(Number(result.lastInsertRowid)) as RawRun
    return deserializeRun(row)
}

export function abandonLeaderboardRunsSync(input: {
    competitionKey: string
    endedAtMs: number
    playerId?: number
}): number {
    const result = input.playerId === undefined
        ? getDb().prepare(`
            UPDATE leaderboard_runs
            SET status = 'abandoned', finished_at_ms = ?,
                server_duration_ms = MAX(0, ? - started_at_ms),
                pending_round = NULL, pending_quest_id = NULL, pending_started_at_ms = NULL
            WHERE competition_key = ? AND status = 'active'
        `).run(input.endedAtMs, input.endedAtMs, input.competitionKey)
        : getDb().prepare(`
            UPDATE leaderboard_runs
            SET status = 'abandoned', finished_at_ms = ?,
                server_duration_ms = MAX(0, ? - started_at_ms),
                pending_round = NULL, pending_quest_id = NULL, pending_started_at_ms = NULL
            WHERE competition_key = ? AND player_id = ? AND status = 'active'
        `).run(input.endedAtMs, input.endedAtMs, input.competitionKey, input.playerId)
    return result.changes
}

export function markLeaderboardRoundStartedSync(
    runId: number,
    round: number,
    questId: number,
    startedAtMs: number,
): void {
    getDb().prepare(`
        UPDATE leaderboard_runs
        SET pending_round = ?, pending_quest_id = ?, pending_started_at_ms = ?
        WHERE id = ? AND status = 'active'
    `).run(round, questId, startedAtMs, runId)
}

export interface LeaderboardRoundParty {
    characterIds: (number | null)[]
    unisonCharacterIds: (number | null)[]
    equipmentIds: (number | null)[]
    abilitySoulIds: (number | null)[]
    evolutionImgLevels: (number | null)[]
    unisonEvolutionImgLevels: (number | null)[]
}

function normalizePartySlots(values: readonly (number | null)[]): (number | null)[] {
    return [0, 1, 2].map(index => {
        const value = values[index]
        return value !== null && Number.isSafeInteger(value) ? value : null
    })
}

export function finishLeaderboardRoundSync(input: {
    run: LeaderboardRun
    round: number
    questId: number
    clientBattleMs: number
    finishedAtMs: number
    party: LeaderboardRoundParty
}): LeaderboardRun | null {
    const { run, party } = input
    const characterIds = normalizePartySlots(party.characterIds)
    const unisonCharacterIds = normalizePartySlots(party.unisonCharacterIds)
    const equipmentIds = normalizePartySlots(party.equipmentIds)
    const abilitySoulIds = normalizePartySlots(party.abilitySoulIds)
    const evolutionImgLevels = normalizePartySlots(party.evolutionImgLevels)
    const unisonEvolutionImgLevels = normalizePartySlots(party.unisonEvolutionImgLevels)
    return getDb().transaction(() => {
        const current = getActiveLeaderboardRunSync(run.playerId, run.competitionKey)
        if (
            current === null
            || current.id !== run.id
            || current.pendingRound !== input.round
            || current.pendingQuestId !== input.questId
            || current.roundsCleared !== input.round - 1
            || input.round > current.totalRounds
        ) return null

        const serverElapsedMs = Math.max(
            0,
            input.finishedAtMs - (current.pendingStartedAtMs ?? input.finishedAtMs),
        )
        getDb().prepare(`
            INSERT INTO leaderboard_run_rounds (
                run_id, round_number, quest_id, client_battle_ms, server_elapsed_ms,
                started_at_ms, finished_at_ms,
                character_id_1, character_id_2, character_id_3,
                unison_character_id_1, unison_character_id_2, unison_character_id_3,
                equipment_id_1, equipment_id_2, equipment_id_3,
                ability_soul_id_1, ability_soul_id_2, ability_soul_id_3,
                evolution_img_level_1, evolution_img_level_2, evolution_img_level_3,
                unison_evolution_img_level_1, unison_evolution_img_level_2,
                unison_evolution_img_level_3
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
            current.id, input.round, input.questId, input.clientBattleMs, serverElapsedMs,
            current.pendingStartedAtMs ?? input.finishedAtMs, input.finishedAtMs,
            ...characterIds, ...unisonCharacterIds,
            ...equipmentIds, ...abilitySoulIds,
            ...evolutionImgLevels, ...unisonEvolutionImgLevels,
        )

        const completed = input.round >= current.totalRounds
        getDb().prepare(`
            UPDATE leaderboard_runs
            SET status = ?, finished_at_ms = ?, server_duration_ms = ?,
                client_battle_ms = client_battle_ms + ?, rounds_cleared = ?,
                pending_round = NULL, pending_quest_id = NULL, pending_started_at_ms = NULL,
                character_id_1 = ?, character_id_2 = ?, character_id_3 = ?,
                unison_character_id_1 = ?, unison_character_id_2 = ?, unison_character_id_3 = ?,
                evolution_img_level_1 = ?, evolution_img_level_2 = ?, evolution_img_level_3 = ?
            WHERE id = ? AND status = 'active'
        `).run(
            completed ? "completed" : "active",
            completed ? input.finishedAtMs : null,
            completed ? Math.max(0, input.finishedAtMs - current.startedAtMs) : null,
            input.clientBattleMs,
            input.round,
            ...characterIds, ...unisonCharacterIds,
            ...evolutionImgLevels, current.id,
        )
        const raw = getDb().prepare(`SELECT ${RUN_COLUMNS} FROM leaderboard_runs WHERE id = ?`)
            .get(current.id) as RawRun | undefined
        return raw === undefined ? null : deserializeRun(raw)
    })()
}

export interface LeaderboardRankRecord extends LeaderboardRun {
    rankNumber: number
    displayName: string
    playerExists: boolean
    rankPoint: number
}

interface RawRankRecord extends RawRun {
    rank_number: number
    live_name: string | null
    player_exists: number
    rank_point: number | null
}

function rankCte(): string {
    return `WITH eligible AS (
        SELECT r.*, ROW_NUMBER() OVER (
            PARTITION BY r.player_id
            ORDER BY r.client_battle_ms ASC, r.finished_at_ms ASC, r.id ASC
        ) AS player_record_number
        FROM leaderboard_runs r
        WHERE r.competition_key = ? AND r.season = ?
            AND r.status = 'completed' AND r.tracked_from_round = 1
            AND r.rounds_cleared = r.total_rounds AND r.client_battle_ms > 0
            AND (SELECT COUNT(*) FROM leaderboard_run_rounds rr WHERE rr.run_id = r.id)
                = r.total_rounds
    ), ranked AS (
        SELECT eligible.*, ROW_NUMBER() OVER (
            ORDER BY client_battle_ms ASC, finished_at_ms ASC, id ASC
        ) AS rank_number
        FROM eligible WHERE player_record_number = 1
    )`
}

function deserializeRank(raw: RawRankRecord): LeaderboardRankRecord {
    const run = deserializeRun(raw)
    return {
        ...run,
        rankNumber: raw.rank_number,
        displayName: raw.live_name ?? run.playerName ?? `Player${run.playerId}`,
        playerExists: raw.player_exists !== 0,
        rankPoint: raw.rank_point ?? 0,
    }
}

export function countLeaderboardRanksSync(competitionKey: string, season: number): number {
    const row = getDb().prepare(`${rankCte()}
        SELECT COUNT(*) AS count FROM ranked
    `).get(competitionKey, season) as { count: number }
    return row.count
}

export function getLeaderboardRankPageSync(input: {
    competitionKey: string
    season: number
    offset: number
    limit: number
}): LeaderboardRankRecord[] {
    const rows = getDb().prepare(`${rankCte()}
        SELECT ranked.*, COALESCE(p.name, ranked.player_name) AS live_name,
            CASE WHEN p.id IS NULL THEN 0 ELSE 1 END AS player_exists,
            p.rank_point
        FROM ranked LEFT JOIN players p ON p.id = ranked.player_id
        ORDER BY rank_number ASC LIMIT ? OFFSET ?
    `).all(input.competitionKey, input.season, input.limit, input.offset) as RawRankRecord[]
    return rows.map(deserializeRank)
}

export function getLeaderboardPlayerRankSync(
    competitionKey: string,
    season: number,
    playerId: number,
): LeaderboardRankRecord | null {
    const row = getDb().prepare(`${rankCte()}
        SELECT ranked.*, COALESCE(p.name, ranked.player_name) AS live_name,
            CASE WHEN p.id IS NULL THEN 0 ELSE 1 END AS player_exists,
            p.rank_point
        FROM ranked LEFT JOIN players p ON p.id = ranked.player_id
        WHERE ranked.player_id = ? LIMIT 1
    `).get(competitionKey, season, playerId) as RawRankRecord | undefined
    return row === undefined ? null : deserializeRank(row)
}

export interface LeaderboardRoundRecord {
    roundNumber: number
    questId: number
    clientBattleMs: number
    serverElapsedMs: number
    characterIds: (number | null)[]
    unisonCharacterIds: (number | null)[]
    equipmentIds: (number | null)[]
    abilitySoulIds: (number | null)[]
    evolutionImgLevels: (number | null)[]
    unisonEvolutionImgLevels: (number | null)[]
}

export function getLeaderboardRunRoundsSync(runId: number): LeaderboardRoundRecord[] {
    const rows = getDb().prepare(`
        SELECT * FROM leaderboard_run_rounds
        WHERE run_id = ? ORDER BY round_number ASC
    `).all(runId) as Record<string, number | null>[]
    return rows.map(row => ({
        roundNumber: Number(row.round_number),
        questId: Number(row.quest_id),
        clientBattleMs: Number(row.client_battle_ms),
        serverElapsedMs: Number(row.server_elapsed_ms),
        characterIds: [row.character_id_1, row.character_id_2, row.character_id_3] as (number | null)[],
        unisonCharacterIds: [row.unison_character_id_1, row.unison_character_id_2, row.unison_character_id_3] as (number | null)[],
        equipmentIds: [row.equipment_id_1, row.equipment_id_2, row.equipment_id_3] as (number | null)[],
        abilitySoulIds: [row.ability_soul_id_1, row.ability_soul_id_2, row.ability_soul_id_3] as (number | null)[],
        evolutionImgLevels: [row.evolution_img_level_1, row.evolution_img_level_2, row.evolution_img_level_3] as (number | null)[],
        unisonEvolutionImgLevels: [
            row.unison_evolution_img_level_1,
            row.unison_evolution_img_level_2,
            row.unison_evolution_img_level_3,
        ] as (number | null)[],
    }))
}
