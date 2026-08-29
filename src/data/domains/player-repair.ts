import { getDb } from "../db"

export function getPlayerRepairVersionsSync(playerId: number): Map<string, number> {
    const rows = getDb().prepare(`
        SELECT repair_key, repair_version
        FROM players_repair_versions
        WHERE player_id = ?
    `).all(playerId) as { repair_key: string, repair_version: number }[]
    return new Map(rows.map(row => [row.repair_key, row.repair_version]))
}

export function setPlayerRepairVersionSync(
    playerId: number,
    repairKey: string,
    repairVersion: number,
): void {
    getDb().prepare(`
        INSERT INTO players_repair_versions
            (player_id, repair_key, repair_version, applied_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(player_id, repair_key) DO UPDATE SET
            repair_version = MAX(repair_version, excluded.repair_version),
            applied_at = excluded.applied_at
    `).run(playerId, repairKey, repairVersion, new Date().toISOString())
}
