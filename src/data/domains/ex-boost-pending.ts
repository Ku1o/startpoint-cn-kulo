import { getDb } from "../db"
import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "./player-operation-receipt"
import { getCharacterDataSync, getExBoostItemSync, getExStatusPoolSync } from "../../lib/assets"
import { ALL_ABILITIES } from "../../lib/ex-boost-abilities"

export interface PendingExBoostDraw {
    drawId: string
    characterId: number
    statusId: number
    abilityIdList: number[]
    costItemId: number
    costItemCount: number
}
const completionOperation = "ex_boost_completion"
const abilityGroups = new Map(ALL_ABILITIES.map(ability => [ability.id, ability.group]))

export function validateExBoostPendingDraw(draw: PendingExBoostDraw): void {
    if (!draw || typeof draw.drawId !== "string" || !/^[a-f0-9-]{36}$/i.test(draw.drawId)
        || [draw.characterId, draw.statusId, draw.costItemId, draw.costItemCount].some(value => !Number.isSafeInteger(value) || value <= 0)
        || !Array.isArray(draw.abilityIdList) || draw.abilityIdList.length > 2
        || new Set(draw.abilityIdList).size !== draw.abilityIdList.length
        || draw.abilityIdList.some(value => !Number.isSafeInteger(value) || value <= 0 || !abilityGroups.has(value))
        || new Set(draw.abilityIdList.map(value => abilityGroups.get(value))).size !== draw.abilityIdList.length) {
        throw new Error("Invalid persisted EX boost draw")
    }
    const character = getCharacterDataSync(draw.characterId), material = getExBoostItemSync(draw.costItemId)
    if (!character || !material || material.count !== draw.costItemCount
        || (material.element !== undefined && material.element !== character.element)
        || !getExStatusPoolSync(material.tier)?.includes(draw.statusId)) {
        throw new Error("Persisted EX boost draw does not match character/material/status content")
    }
}
/** Shared by row readers and archive validation, before destructive restore writes. */
export function parseExBoostPendingRow(row: Record<string, unknown>): PendingExBoostDraw {
    if (typeof row.ability_id_list !== "string") throw new Error("Invalid EX boost ability list encoding")
    const draw: PendingExBoostDraw = { drawId: row.draw_id as string, characterId: row.character_id as number,
        statusId: row.status_id as number, abilityIdList: JSON.parse(row.ability_id_list),
        costItemId: row.cost_item_id as number, costItemCount: row.cost_item_count as number }
    validateExBoostPendingDraw(draw)
    return draw
}
function requireTransaction(): void {
    if (!getDb().inTransaction) throw new Error("EX boost mutation requires a persistence transaction")
}
export function getPendingExBoostDrawSync(playerId: number): PendingExBoostDraw | null {
    const row = getDb().prepare(`SELECT * FROM players_ex_boost_pending_draws WHERE player_id=?`).get(playerId) as {
        draw_id: string; character_id: number; status_id: number; ability_id_list: string; cost_item_id: number; cost_item_count: number
    } | undefined
    if (!row) return null
    return parseExBoostPendingRow(row)
}
export function deletePendingExBoostDrawSync(playerId: number): void {
    requireTransaction()
    getDb().prepare("DELETE FROM players_ex_boost_pending_draws WHERE player_id=?").run(playerId)
}
export function writePendingExBoostDrawSync(playerId: number, draw: PendingExBoostDraw): void {
    requireTransaction()
    validateExBoostPendingDraw(draw)
    getDb().prepare(`INSERT INTO players_ex_boost_pending_draws
        (player_id,draw_id,character_id,status_id,ability_id_list,cost_item_id,cost_item_count) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(player_id) DO UPDATE SET draw_id=excluded.draw_id,character_id=excluded.character_id,
        status_id=excluded.status_id,ability_id_list=excluded.ability_id_list,cost_item_id=excluded.cost_item_id,
        cost_item_count=excluded.cost_item_count`).run(playerId, draw.drawId, draw.characterId, draw.statusId,
            JSON.stringify(draw.abilityIdList), draw.costItemId, draw.costItemCount)
}
export function completeExBoostDrawSync(playerId: number, draw: PendingExBoostDraw, confirmed: boolean): void {
    requireTransaction()
    validateExBoostPendingDraw(draw)
    insertPlayerOperationReceiptSync({ playerId, operation: completionOperation, requestKey: draw.drawId,
        response: { version: 1, confirmed, draw } })
    deletePendingExBoostDrawSync(playerId)
}
/** A restored old archive may not reactivate a draw already resolved on this server. */
export function reconcilePendingExBoostDrawSync(playerId: number): PendingExBoostDraw | null {
    requireTransaction()
    const draw = getPendingExBoostDrawSync(playerId)
    if (!draw || !getPlayerOperationReceiptSync(playerId, completionOperation, draw.drawId)) return draw
    deletePendingExBoostDrawSync(playerId)
    return null
}
