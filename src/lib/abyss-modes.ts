import { QuestCategory } from "./types/quest"

export const ABYSS_NORMAL_EVENT_ID = 700099
export const ABYSS_EX_EVENT_ID = 700100
export const ABYSS_EVENT_IDS = [ABYSS_NORMAL_EVENT_ID, ABYSS_EX_EVENT_ID] as const
export const ABYSS_FINITE_FOLDER_ID = 1
export const ABYSS_ENDLESS_FOLDER_ID = 2
export const ABYSS_FINITE_ROUNDS = 30

export function isAbyssEvent(eventId: number): boolean {
    return ABYSS_EVENT_IDS.some(id => id === eventId)
}

export function abyssEventFromQuest(category: number | string, questId: number | string): number | null {
    const id = Number(questId)
    const eventId = Math.floor(id / 1000)
    return Number(category) === QuestCategory.RUSH_EVENT && Number.isSafeInteger(id)
        && isAbyssEvent(eventId) ? eventId : null
}

export function isAbyssExEndlessQuest(category: number | string, questId: number | string): boolean {
    return Number(category) === QuestCategory.RUSH_EVENT && Number(questId) === ABYSS_EX_EVENT_ID * 1000 + 99
}
