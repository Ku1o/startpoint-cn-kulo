import type { Database } from "better-sqlite3"
import { getDb } from "../db"

export interface WaterGeraldClaim { claimedAt: number }
export class WaterGeraldImportConflictError extends Error {}

/** Never retain a spent entitlement while replacing its character with absence. */
export function assertWaterGeraldImportContinuitySync(playerId: number, sourceClaimed: boolean,
    sourceHasCharacter: boolean, db: Database = getDb()): void {
    if (!sourceHasCharacter && (sourceClaimed || getWaterGeraldClaimsSync(playerId, db).length > 0)) {
        throw new WaterGeraldImportConflictError(
            "水杰奖励已经领取，此存档缺少水杰（129989）；为避免角色丢失且无法再次领取，已拒绝覆盖，请使用包含水杰的存档。",
        )
    }
}

export function validateWaterGeraldClaims(value: unknown): asserts value is WaterGeraldClaim[] | undefined {
    if (value === undefined) return
    if (!Array.isArray(value) || value.length > 1 || value.some(row =>
        !row || typeof row !== "object" || !Number.isSafeInteger(row.claimedAt) || row.claimedAt < 0)) {
        throw new Error("Invalid permanent water Gerald reward progress")
    }
}

export function getWaterGeraldClaimsSync(playerId: number, db: Database = getDb()): WaterGeraldClaim[] {
    return db.prepare("SELECT claimed_at AS claimedAt FROM players_water_gerald_claims WHERE player_id=?")
        .all(playerId) as WaterGeraldClaim[]
}

/** Import is monotonic: neither an old archive nor an empty new archive reopens a claim. */
export function importWaterGeraldClaimsSync(playerId: number, claims: WaterGeraldClaim[] | undefined,
    db: Database = getDb()): void {
    validateWaterGeraldClaims(claims)
    for (const claim of claims ?? []) {
        db.prepare("INSERT OR IGNORE INTO players_water_gerald_claims(player_id,claimed_at) VALUES(?,?)")
            .run(playerId, claim.claimedAt)
    }
}
