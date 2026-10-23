/** Each client zone reports revives already accepted before this request. */
export function parseSingleContinueExpectedCount(statistics: unknown): number | null {
    if (typeof statistics === "string") {
        // GET requests carry statistics as URL-encoded JSON. Bound parsing before
        // decoding it, while keeping the object form used by POST clients.
        if (Buffer.byteLength(statistics, "utf8") > 64 * 1024) return null
        try { statistics = JSON.parse(statistics) }
        catch { return null }
    }
    if (statistics === null || typeof statistics !== "object" || Array.isArray(statistics)) return null
    const zones = (statistics as { zones?: unknown }).zones
    if (!Array.isArray(zones) || zones.length === 0 || zones.length > 128) return null
    let count = 0
    for (const zone of zones) {
        if (zone === null || typeof zone !== "object" || Array.isArray(zone)) return null
        const value = (zone as { continue_count?: unknown }).continue_count
        if (!Number.isSafeInteger(value) || (value as number) < 0) return null
        count += value as number
        if (!Number.isSafeInteger(count)) return null
    }
    return count
}
