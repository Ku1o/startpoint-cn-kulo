import catalog from "../../assets/bond_token_exchange.json"
import equipmentIds from "../../assets/equipment_ids.json"
import { getDb } from "../data/db"
import { getPlayerSync, updatePlayerSync } from "../data/domains/player"
import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "../data/domains/player-operation-receipt"
import { addPlayerShopPurchaseCountSync, getPlayerShopPurchaseCountSync } from "../data/domains/shopPurchase"
import { getPlayerMailCountSync } from "../data/domains/mail"
import { givePlayerEquipmentSync } from "./equipment"
import { getServerDate } from "../utils"

const OPERATION = "bond_token_exchange"
const MAX_INTEGER = 2147483647
function products(now = getServerDate().getTime()) {
    return Object.entries(catalog).map(([id, rows]) => {
        const [cost, stock, start, end] = rows[0]
        const equipmentId = Number(id)
        if (!(equipmentIds as number[]).includes(equipmentId)
            || !Number.isSafeInteger(Number(cost)) || Number(cost) < 1
            || !Number.isSafeInteger(Number(stock)) || Number(stock) < 1)
            throw new Error("Invalid bond-token exchange catalog")
        return { equipmentId, cost: Number(cost), stock: Number(stock),
            from: Date.parse(start.replace(" ", "T") + "+08:00"), until: Date.parse(end.replace(" ", "T") + "+08:00") }
    }).filter(product => now >= product.from && now <= product.until)
}

const legacyShopItems: Record<number, number> = { 5010005: 100001, 5030005: 100002 }
export function bondTokenEquipmentForShopItem(shopType: number, itemId: number): number | null {
    if (shopType !== 8) return null
    return itemId === 100001 ? 5010005 : itemId === 100002 ? 5030005 : null
}
export function getBondTokenExchangeCountSync(playerId: number, equipmentId: number): number {
    const row = getDb().prepare("SELECT exchange_count FROM players_bond_token_exchanges WHERE player_id=? AND equipment_id=?")
        .get(playerId, equipmentId) as { exchange_count: number } | undefined
    // Target-local receipt survives importing an older portable inventory/quota.
    const receipt = getPlayerOperationReceiptSync<{ count: number }>(playerId, OPERATION, String(equipmentId))
    const legacyItemId = legacyShopItems[equipmentId]
    const legacy = legacyItemId === undefined ? 0 : getPlayerShopPurchaseCountSync(playerId, legacyItemId)
    return Math.max(row?.exchange_count ?? 0, receipt?.response.count ?? 0, legacy)
}

export function listBondTokenExchangesSync(playerId: number) {
    return products().map(product => ({ equipment_id: product.equipmentId,
        exchange_count: getBondTokenExchangeCountSync(playerId, product.equipmentId) }))
}

/** Caller owns the persistence transaction, including the returned projection. */
export function exchangeBondTokenWithinTransactionSync(playerId: number, equipmentId: number) {
    const db = getDb()
    if (!db.inTransaction) throw new Error("Bond-token exchange requires a transaction")
    const product = products().find(entry => entry.equipmentId === equipmentId)
    if (!product) return { error: "Unknown or unavailable bond-token exchange." }
    const count = getBondTokenExchangeCountSync(playerId, equipmentId)
    if (count >= product.stock) return { error: "Bond-token exchange is out of stock." }
    const player = getPlayerSync(playerId)
    if (!player || player.bondToken < product.cost) return { error: "Not enough bond_token." }
    if (!Number.isSafeInteger(player.bondToken) || player.bondToken > MAX_INTEGER) throw new Error("Invalid bond-token balance")
    const after = player.bondToken - product.cost
    updatePlayerSync({ id: playerId, bondToken: after })
    const equipment = givePlayerEquipmentSync(playerId, equipmentId, 1)
    if (!equipment) throw new Error("Bond-token equipment grant failed")
    db.prepare(`INSERT INTO players_bond_token_exchanges(player_id,equipment_id,exchange_count) VALUES(?,?,?)
        ON CONFLICT(player_id,equipment_id) DO UPDATE SET exchange_count=excluded.exchange_count`)
        .run(playerId, equipmentId, count + 1)
    // Current native products are once-only. Any future repeatable catalog must
    // introduce a per-exchange identity before increasing its stock.
    if (product.stock !== 1) throw new Error("Unsupported repeatable bond-token product")
    insertPlayerOperationReceiptSync({ playerId, operation: OPERATION, requestKey: String(equipmentId), response: { count: count + 1 } })
    // The older general-shop endpoint exposes the same native once-only offer.
    // It has no day/month quota; share its lifetime count instead of summing two ledgers.
    addPlayerShopPurchaseCountSync(playerId, legacyShopItems[equipmentId], 1)
    return { data: { user_info: { bond_token: after }, equipment_list: [equipment], item_list: null,
        character_list: null, active_mission_list: null, mission_info: null, over_max: null,
        mail_arrived: getPlayerMailCountSync(playerId, true) > 0, config: null, user_daily_challenge_point_list: null, encyclopedia_info: null,
        fund_receive_list: null, monthly_charge_bonus_info: null, crazy_gacha_result_list: null } }
}
