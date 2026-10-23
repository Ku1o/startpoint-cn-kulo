import exchangeData from "../../assets/star_crumb_exchange.json"

const exchanges = exchangeData as Record<string, string[][]>
// Preserve the ordinary shop visible on this fixed China Standard Time date.
// Personal comeback/stars windows are deliberately excluded from this set.
const retainedReferenceMs = Date.parse("2025-07-20T12:00:00+08:00")

function isPersonalProduct(row: readonly string[]): boolean {
    return row[6] !== "(None)" || row[7] !== "(None)"
}

function withinOriginalPeriod(row: readonly string[], nowMs: number): boolean {
    const start = Date.parse(`${row[3].replace(" ", "T")}+08:00`)
    const end = Date.parse(`${row[4].replace(" ", "T")}+08:00`)
    return Number.isFinite(nowMs) && Number.isFinite(start) && Number.isFinite(end)
        && start <= nowMs && nowMs <= end
}

const retainedIds = Object.freeze([...new Set(Object.entries(exchanges)
    .filter(([, rows]) => rows[0] && !isPersonalProduct(rows[0])
        && withinOriginalPeriod(rows[0], retainedReferenceMs))
    .map(([id]) => Number(id))
    .filter(id => Number.isSafeInteger(id) && id > 0))]
    .sort((left, right) => left - right))
const retainedIdSet = new Set(retainedIds)

/** A fresh response array keeps callers from changing the retained rules. */
export function getRetainedStarCrumbExchangeIds(): number[] {
    return [...retainedIds]
}

export function isStarCrumbExchangeAvailable(exchangeId: number, nowMs: number = Date.now()): boolean {
    if (!Number.isSafeInteger(exchangeId) || exchangeId <= 0) return false
    const row = exchanges[String(exchangeId)]?.[0]
    if (!row) return false
    // Existing personal windows are not persisted by the server. Keep their
    // existing exchange behavior; this ordinary-shop repair grants no new
    // client eligibility and does not invent or revoke personal entitlements.
    if (isPersonalProduct(row)) return true
    return retainedIdSet.has(exchangeId) || withinOriginalPeriod(row, nowMs)
}
