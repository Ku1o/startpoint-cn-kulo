import { readFileSync } from "node:fs"
import path from "node:path"
import { getDb } from "../data/db"
import { grantPlayerDegreeSync } from "../data/domains/degree"

export const ABYSS_SPHEAL_DEGREE = 9_911_301
export const SPHEAL_CHARACTER = 129990
export const ABYSS_SPHEAL_CONFIG_PATH = path.resolve(
    __dirname, "..", "..", "assets", "abyss_spheal_degree_reward.json",
)

interface SphealConfig {
    schema_version: number
    enabled: boolean
    event_id: number
    folder_id: number
    degree_id: number
    character_id: number
    party_scope: string
}

function readConfig(configPath: string): SphealConfig | null {
    try {
        const config = JSON.parse(readFileSync(configPath, "utf8")) as Partial<SphealConfig>
        if (config.schema_version !== 1 || config.enabled !== true
            || config.event_id !== 700099 || config.folder_id !== 1
            || config.degree_id !== ABYSS_SPHEAL_DEGREE || config.character_id !== SPHEAL_CHARACTER
            || config.party_scope !== "final_clear_main_or_unison") return null
        return config as SphealConfig
    } catch {
        return null
    }
}

export function sphealDegreeEnabled(configPath = ABYSS_SPHEAL_CONFIG_PATH): boolean {
    return readConfig(configPath) !== null
}

/**
 * Grant the Spheal title only when every one of the 30 main-tower rounds in a
 * completed run included Spheal in either the main or unison party.
 */
export function grantAbyssSphealDegreeSync(
    playerId: number,
    options: { configPath?: string } = {},
): number[] {
    if (!Number.isSafeInteger(playerId) || playerId <= 0) return []
    const config = readConfig(options.configPath ?? ABYSS_SPHEAL_CONFIG_PATH)
    if (config === null) return []

    const db = getDb()
    return db.transaction(() => {
        if (!db.prepare("SELECT id FROM players WHERE id = ?").get(playerId)) return []
        if (db.prepare("SELECT 1 FROM players_degrees WHERE player_id = ? AND degree_id = ?")
            .get(playerId, config.degree_id)) return []
        const runs = db.prepare(`
            SELECT id
            FROM leaderboard_runs
            WHERE player_id = ? AND competition_key = 'achievement:abyss-endurance:700099:1'
                AND status = 'completed' AND tracked_from_round = 1
                AND total_rounds = 30 AND rounds_cleared = 30
            ORDER BY id DESC
        `).all(playerId) as { id: number }[]
        const roundCheck = db.prepare(`
            SELECT COUNT(*) AS round_count,
                SUM(CASE WHEN character_id_1 = ? OR character_id_2 = ? OR character_id_3 = ?
                    OR unison_character_id_1 = ? OR unison_character_id_2 = ?
                    OR unison_character_id_3 = ? THEN 1 ELSE 0 END) AS spheal_rounds
            FROM leaderboard_run_rounds WHERE run_id = ?
        `)
        for (const run of runs) {
            const result = roundCheck.get(
                config.character_id, config.character_id, config.character_id,
                config.character_id, config.character_id, config.character_id, run.id,
            ) as { round_count: number; spheal_rounds: number | null }
            if (result.round_count !== 30 || result.spheal_rounds !== 30) continue
            return grantPlayerDegreeSync(playerId, config.degree_id, Date.now())
                ? [config.degree_id] : []
        }
        return []
    })()
}
