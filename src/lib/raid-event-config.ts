export interface RaidEventProgressRule {
    requiredKillCount: number
    questWeights: Record<number, number>
}

export const RAID_EVENT_CALCULATION_VERSION = 4

// Official master data for raid event 7 (Battle Banquet).
const RAID_EVENT_PROGRESS_RULES: Record<number, RaidEventProgressRule> = {
    7: {
        requiredKillCount: 76000,
        questWeights: {
            7001: 51,
            7002: 255,
            7003: 1,
            7004: 3,
            7005: 30,
            7006: 180,
            7007: 1,
            7008: 3,
            7009: 26,
            7010: 157,
            7011: 1,
            7012: 3,
            7013: 22,
            7014: 135,
            7015: 1,
            7016: 3,
            7017: 18,
            7018: 115,
            7019: 1,
            7020: 3,
            7021: 15,
            7022: 97,
            7023: 1,
            7024: 3,
            7025: 12,
            7026: 80,
        },
    },
}

// mission_event master entries whose col[7]/col[8] identify Raid event 7.
const RAID_EVENT_MISSION_IDS: Record<number, number[]> = {
    7: [400093, 400094, 400095, 400096],
}

export function isSupportedRaidEventId(eventId: number): boolean {
    return Number.isInteger(eventId) && RAID_EVENT_PROGRESS_RULES[eventId] !== undefined
}

export function getRaidEventProgressRule(eventId: number): RaidEventProgressRule {
    const rule = RAID_EVENT_PROGRESS_RULES[eventId]
    if (!rule) throw new Error(`Unsupported raid event: ${eventId}`)
    return rule
}

export function getRaidEventIdForQuest(questId: number): number | null {
    if (!Number.isInteger(questId)) return null
    for (const [rawEventId, rule] of Object.entries(RAID_EVENT_PROGRESS_RULES)) {
        if (rule.questWeights[questId] !== undefined) return Number(rawEventId)
    }
    return null
}

export function isRaidEventQuestId(eventId: number, questId: number): boolean {
    if (!isSupportedRaidEventId(eventId) || !Number.isInteger(questId)) return false
    return RAID_EVENT_PROGRESS_RULES[eventId].questWeights[questId] !== undefined
}

export function getRaidEventQuestIds(eventId: number): number[] {
    return Object.keys(getRaidEventProgressRule(eventId).questWeights).map(Number)
}

export function getRaidEventMissionIds(eventId: number): number[] {
    getRaidEventProgressRule(eventId)
    return [...(RAID_EVENT_MISSION_IDS[eventId] ?? [])]
}
