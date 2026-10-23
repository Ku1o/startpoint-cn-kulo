import { getDb } from "../data/db"
import { getPlayerShopPurchaseCountSync } from "../data/domains/shopPurchase"
import { buildShopSalesEntry, getShopPurchaseKey } from "./shop-sales"
import { getDayBucket } from "./time-utils"
import type { ShopItem } from "./types/shop"
import { readServerClockStateSync } from "./server-clock-state"
import { applyContentNativeShopRules } from "./content-shop-rules"

export function hasShopQuota(item: ShopItem): boolean {
    return !!item.nativeStockLimits || [item.dailyStock, item.monthlyStock, item.maxFrequency].some(value => (value ?? 0) > 0)
}

export function validShopQuotaRules(item: ShopItem): boolean {
    return [item.dailyStock, item.monthlyStock, item.maxFrequency, item.nativeStockLimits?.perRequest,
        item.nativeStockLimits?.lifetime].every(value =>
        value === undefined || value === null || (Number.isSafeInteger(value) && value >= 0))
}

function buckets(at: Date) {
    // Native DateUtil derives both day and month from the reset-aware business day.
    // The CN runtime's existing helper owns UTC+8 and DAILY_RESET_HOUR (default 05:00).
    const day = getDayBucket(at)
    return { day: `${day.y}-${day.m + 1}-${day.d}`, month: `${day.y}-${day.m + 1}` }
}

export function getShopQuotaStateSync(playerId: number, shopType: number, itemId: number, item: ShopItem, at: Date, explicitLegacyAnchorMs?: number) {
    const key = getShopPurchaseKey(shopType, itemId)
    const total = getPlayerShopPurchaseCountSync(playerId, key)
    const period = buckets(at)
    const periodic = (item.dailyStock ?? 0) > 0 || (item.monthlyStock ?? 0) > 0
    const rows = periodic ? getDb().prepare(`SELECT period_kind, period_key, count FROM players_shop_quotas
        WHERE player_id=? AND purchase_key=?`).all(playerId, key) as Array<{ period_kind: string; period_key: string; count: number }> : []
    const needsLegacyReservation = periodic && total > 0 && !rows.length
    const marker = rows.find(row => row.period_kind === "legacy")
    let legacyAnchorMs = marker ? Number(marker.period_key) : explicitLegacyAnchorMs
    if (needsLegacyReservation && legacyAnchorMs === undefined) {
        const clock = readServerClockStateSync(getDb())
        legacyAnchorMs = clock?.snapshot.mode === "real" ? clock.snapshot.cutoverRealMs ?? undefined : undefined
    }
    if (legacyAnchorMs !== undefined && (!Number.isSafeInteger(legacyAnchorMs) || legacyAnchorMs < 0
        || !Number.isFinite(new Date(legacyAnchorMs).getTime()))) throw new Error("Invalid quota legacy reservation anchor")
    // The marker is an explicit conservative reservation, never a claimed purchase date.
    // Bind it to the durable server cutover, not to a player's delayed first login.
    const legacyCount = marker?.count ?? (needsLegacyReservation && legacyAnchorMs !== undefined ? total : 0)
    const legacyPeriod = legacyAnchorMs === undefined ? null : buckets(new Date(legacyAnchorMs))
    const migrationState = needsLegacyReservation && legacyAnchorMs === undefined ? "unresolved"
        : marker || needsLegacyReservation ? "legacy-carry" : "known"
    const today = (rows.find(row => row.period_kind === "day" && row.period_key === period.day)?.count ?? 0)
        + ((item.dailyStock ?? 0) > 0 && legacyPeriod?.day === period.day ? legacyCount : 0)
    const thisMonth = (rows.find(row => row.period_kind === "month" && row.period_key === period.month)?.count ?? 0)
        + ((item.monthlyStock ?? 0) > 0 && legacyPeriod?.month === period.month ? legacyCount : 0)
    const caps: number[] = []
    if (item.nativeStockLimits?.lifetime !== undefined && item.nativeStockLimits.lifetime !== null)
        caps.push(Math.max(0, item.nativeStockLimits.lifetime - total))
    else if (!hasShopQuota(item) && item.stock > 0) caps.push(Math.max(0, item.stock - total))
    if ((item.maxFrequency ?? 0) > 0) caps.push(Math.max(0, item.maxFrequency! - total))
    if (item.dailyStock !== undefined && (item.nativeStockLimits || item.dailyStock > 0)) caps.push(Math.max(0, item.dailyStock - today))
    if (item.monthlyStock !== undefined && (item.nativeStockLimits || item.monthlyStock > 0)) caps.push(Math.max(0, item.monthlyStock - thisMonth))
    return { migrationState, today, thisMonth, total, period, key, legacyAnchorMs, legacyCount,
        needsLegacyReservation,
        remaining: migrationState === "unresolved" || !validShopQuotaRules(item) ? 0 : caps.length ? Math.min(...caps) : Infinity,
        // On quota-bearing native rows stock is buy_max_count, a per-request cap.
        singleLimit: item.nativeStockLimits ? item.nativeStockLimits.perRequest ?? Infinity
            : hasShopQuota(item) && item.stock > 0 ? item.stock : Infinity }
}

/** Call before incrementing lifetime history, under the same write transaction as costs/rewards. */
export function recordShopQuotaPurchaseSync(playerId: number, shopType: number, itemId: number, item: ShopItem, amount: number, at: Date, explicitLegacyAnchorMs?: number): void {
    if (!hasShopQuota(item)) return
    const state = getShopQuotaStateSync(playerId, shopType, itemId, item, at, explicitLegacyAnchorMs)
    if (state.migrationState === "unresolved" || amount > state.remaining || amount > state.singleLimit) {
        throw new Error("Shop quota changed or legacy periodic history is unresolved")
    }
    const insert = getDb().prepare(`INSERT INTO players_shop_quotas(player_id,purchase_key,period_kind,period_key,count)
        VALUES(?,?,?,?,?) ON CONFLICT(player_id,purchase_key,period_kind,period_key) DO UPDATE SET count=count+excluded.count`)
    if (state.needsLegacyReservation && state.legacyAnchorMs !== undefined) {
        getDb().prepare(`INSERT INTO players_shop_quotas(player_id,purchase_key,period_kind,period_key,count)
            VALUES(?,?,'legacy',?,?)`).run(playerId, state.key, String(state.legacyAnchorMs), state.legacyCount)
    }
    for (const [kind, limit] of [["day", item.dailyStock], ["month", item.monthlyStock]] as const) {
        if ((limit ?? 0) > 0) insert.run(playerId, state.key, kind, state.period[kind], amount)
    }
}

/** Shared by shop browsing and acquisition navigation; both show identical player stock. */
export function buildPlayerShopSalesEntrySync(playerId: number, shopType: number, itemId: number,
    item: ShopItem, purchases: Record<number, number>, at: Date, degreeOwned = false) {
    item = applyContentNativeShopRules(shopType, itemId, item)
    const sale = buildShopSalesEntry(shopType, itemId, item, purchases, degreeOwned)
    if (!hasShopQuota(item)) return sale
    const quota = getShopQuotaStateSync(playerId, shopType, itemId, item, at)
    sale.stock_quantity = degreeOwned ? 0 : Number.isFinite(quota.remaining) ? quota.remaining : -1
    sale.today_purchase_num = quota.today
    sale.this_month_purchase_num = quota.thisMonth
    sale.total_purchase_num = quota.total
    sale.group_info.group_total_stock_quantity = sale.stock_quantity
    // Native counters require integers; this extension distinguishes an unknown
    // legacy period from a proven zero-purchase period. Unknown stock stays zero.
    return { ...sale, quota_migration_state: quota.migrationState }
}
