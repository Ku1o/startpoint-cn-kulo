/** Public card fields only. State and its nested scopes are kept intact: a
 * compact read must never change the subsequent action/deadline write contract.
 */
const CARD_FIELDS = ["key", "name", "type", "id", "state", "originalStartMs", "originalEndMs", "effectiveFlags",
    "presentation", "primaryControl", "limitations", "rightsNotice", "linkedActivity", "deadlineControl", "discovery"] as const
const LIST_FIELDS = ["revision", "catalogDigest", "total", "rows", "groups", "typeOptions", "statusCounts", "searchInfo",
    "view", "contentTotal", "seriesGroups"] as const

function pick(value: Record<string, unknown>, fields: readonly string[]): Record<string, unknown> {
    const result: Record<string, unknown> = {}
    for (const field of fields) if (Object.prototype.hasOwnProperty.call(value, field)) result[field] = value[field]
    return result
}
export function projectContentManagementCard(row: Record<string, unknown>): Record<string, unknown> {
    return pick(row, CARD_FIELDS)
}
export function projectContentManagementCards(value: Record<string, unknown>): Record<string, unknown> {
    const result = pick(value, LIST_FIELDS)
    result.rows = (value.rows as Record<string, unknown>[]).map(projectContentManagementCard)
    if (Array.isArray(value.seriesGroups)) result.seriesGroups = value.seriesGroups.map(group => {
        const { preview: _preview, ...summary } = group as Record<string, unknown>
        return summary
    })
    return result
}
