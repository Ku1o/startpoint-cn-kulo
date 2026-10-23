/** Candidate selection only. This does not grant participation or player eligibility. */
export const JULY_REFERENCE = { date: "2025-07-20", timeZone: "UTC+08:00", startMs: 1752940800000,
    endMsExclusive: 1753027200000 } as const

export function isFixedJulyCandidate(row: { personalWindow?: boolean; originalStartMs: number | null; originalEndMs: number | null }): boolean {
    return !row.personalWindow && (row.originalStartMs === null || row.originalStartMs <= JULY_REFERENCE.startMs)
        && (row.originalEndMs === null || row.originalEndMs >= JULY_REFERENCE.endMsExclusive - 1000)
}
