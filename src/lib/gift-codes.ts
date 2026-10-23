import { getDb } from "../data/db"
import { getPlayerSync } from "../data/domains/player"
import { getPlayerItemSync } from "../data/domains/item"
import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "../data/domains/player-operation-receipt"
import { insertReceiveHistorySync } from "../data/domains/mail"
import { serverCharacters, serverItemIds } from "./content-master"
import equipmentIds from "../../assets/equipment_ids.json"
import { canReceiveMana } from "./mana"
import { getConfigSync } from "./assets"
import { givePlayerRewardsSync } from "./quest"
import { reconcileAwakeUnlockCharacterList } from "./mission"
import { Reward, RewardType } from "./types"

export interface GiftReward { type: number; type_id: number | null; number: number }
export interface GiftCodeRow { id: number; code: string; note: string; rewards_json: string; enabled: number; revision: number; created_at: number }
const OPERATION = "gift_code_redemption"
const MAX = 2147483647
const types: Record<number, RewardType> = { 1: RewardType.ITEM, 4: RewardType.BEADS,
    5: RewardType.CHARACTER, 6: RewardType.EQUIPMENT, 8: RewardType.MANA, 9: RewardType.EXP }
export class GiftInputError extends Error {}
/** The management picker must offer only IDs accepted by reward validation. */
export function giftRewardIds() {
    return { 1: serverItemIds, 5: Object.keys(serverCharacters).map(Number), 6: equipmentIds }
}
export function validGiftCode(code: unknown): code is string {
    return typeof code === "string" && code.length >= 1 && code.length <= 20
        && code.trim() === code && !/[\s\x00-\x1f\x7f]/.test(code)
}
export function validateGiftRewards(value: unknown): GiftReward[] {
    if (!Array.isArray(value) || !value.length || value.length > 20) throw new GiftInputError("奖励数量须为 1–20 项")
    return value.map(raw => {
        if (!raw || typeof raw !== "object" || Array.isArray(raw)
            || Object.keys(raw).some(key => !["type", "type_id", "number"].includes(key))
            || !Object.prototype.hasOwnProperty.call(types, raw.type) || !Number.isSafeInteger(raw.type)
            || !Number.isSafeInteger(raw.number) || raw.number < 1 || raw.number > MAX)
            throw new GiftInputError("奖励类型或数量无效")
        const id = raw.type_id ?? null
        const known = raw.type === 1 ? (serverItemIds as number[]).includes(id)
            : raw.type === 5 ? Object.prototype.hasOwnProperty.call(serverCharacters, String(id))
            : raw.type === 6 ? (equipmentIds as number[]).includes(id) : id === null
        if (!known || ([1, 5, 6].includes(raw.type) && (!Number.isSafeInteger(id) || id < 1)))
            throw new GiftInputError("奖励 ID 不存在")
        if ([5, 6].includes(raw.type) && raw.number !== 1) throw new GiftInputError("每项角色或装备奖励须为一份")
        return { type: raw.type, type_id: id, number: raw.number }
    })
}
export function isGiftEnabledSync(): boolean {
    return !!getDb().prepare("SELECT 1 FROM server_gift_codes WHERE enabled=1 LIMIT 1").get()
}
export function listGiftCodesSync() {
    return (getDb().prepare(`SELECT g.*,
        (SELECT COUNT(*) FROM player_operation_receipts r WHERE r.operation=? AND r.request_key=CAST(g.id AS TEXT)) AS redeemed_count
        FROM server_gift_codes g ORDER BY g.id DESC LIMIT 500`).all(OPERATION) as (GiftCodeRow & { redeemed_count: number })[])
        .map(({ rewards_json, ...row }) => ({ ...row, rewards: JSON.parse(rewards_json) as GiftReward[] }))
}
export function createGiftCodeSync(value: unknown) {
    const body = value as { code?: unknown; note?: unknown; rewards?: unknown } | null
    if (!body || !validGiftCode(body.code) || typeof body.note !== "string" || body.note.length > 512)
        throw new GiftInputError("礼包码须为 1–20 个非空白字符，备注不能超过 512 字")
    const rewards = validateGiftRewards(body.rewards)
    const db = getDb()
    if (!db.inTransaction) throw new Error("Gift creation requires a transaction")
    if (db.prepare("SELECT 1 FROM server_gift_codes WHERE code=?").get(body.code)) throw new GiftInputError("礼包码已存在，不能重复使用")
    const result = db.prepare("INSERT INTO server_gift_codes(code,note,rewards_json,created_at) VALUES(?,?,?,?)")
        .run(body.code, body.note, JSON.stringify(rewards), Date.now())
    return { id: Number(result.lastInsertRowid), enabled: false, revision: 1 }
}
export function setGiftCodeEnabledSync(id: number, revision: number, enabled: boolean): boolean {
    if (!Number.isSafeInteger(id) || id < 1 || !Number.isSafeInteger(revision) || revision < 1 || typeof enabled !== "boolean")
        throw new GiftInputError("礼包码状态参数无效")
    if (!getDb().inTransaction) throw new Error("Gift status change requires a transaction")
    return getDb().prepare("UPDATE server_gift_codes SET enabled=?,revision=revision+1 WHERE id=? AND revision=?")
        .run(Number(enabled), id, revision).changes === 1
}

/** Native gift protocol uses MailKind values; inventory grants use RewardType. */
export function redeemGiftCodeWithinTransactionSync(playerId: number, key: unknown) {
    const db = getDb()
    if (!db.inTransaction) throw new Error("Gift redemption requires a transaction")
    const rejected = (result_code: number) => ({ result_code, all_gift_info: [] as GiftReward[] })
    if (!validGiftCode(key)) return rejected(6101)
    const gift = db.prepare("SELECT * FROM server_gift_codes WHERE code=?").get(key) as GiftCodeRow | undefined
    if (!gift) return rejected(6101)
    if (!gift.enabled) return rejected(6103)
    if (getPlayerOperationReceiptSync(playerId, OPERATION, String(gift.id))) return rejected(6104)
    const rewards = validateGiftRewards(JSON.parse(gift.rewards_json))
    const player = getPlayerSync(playerId)
    if (!player) throw new Error("Gift player disappeared")
    const sum = (type: number) => rewards.filter(entry => entry.type === type).reduce((total, entry) => total + entry.number, 0)
    // Never consume a code while silently clipping its currency reward.
    if (!canReceiveMana(player, sum(8)) || player.freeVmoney + sum(4) > getConfigSync().max_virtual_money
        || player.expPool + sum(9) > MAX) throw new GiftInputError("资源容量不足，礼包码尚未使用")
    const itemTotals = new Map<number, number>()
    for (const reward of rewards) if (reward.type === 1) itemTotals.set(reward.type_id!, (itemTotals.get(reward.type_id!) ?? 0) + reward.number)
    for (const [id, count] of itemTotals) if ((getPlayerItemSync(playerId, id) ?? 0) + count > MAX)
        throw new GiftInputError("物品容量不足，礼包码尚未使用")
    const commands = rewards.map(entry => ({ type: types[entry.type], ...(entry.type_id === null ? {} : { id: entry.type_id }), count: entry.number }) as Reward)
    const grant = givePlayerRewardsSync(playerId, commands)
    if (!grant || grant.equipment_list.some(value => value == null)) throw new Error("Gift reward grant failed")
    const characters = reconcileAwakeUnlockCharacterList(playerId, grant.character_list)
    for (const reward of rewards) insertReceiveHistorySync(playerId, reward)
    const after = getPlayerSync(playerId)!
    const result = { result_code: 1, all_gift_info: rewards, character_list: characters,
        equipment_list: grant.equipment_list, item_list: grant.items,
        user_info: { free_mana: after.freeMana, free_vmoney: after.freeVmoney, exp_pool: after.expPool } }
    insertPlayerOperationReceiptSync({ playerId, operation: OPERATION, requestKey: String(gift.id), response: result })
    return result
}
