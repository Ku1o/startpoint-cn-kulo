// Character → quest mapping helpers

import charQuests from "../../../assets/character_quest_lookup.json"

export function getCharacterIdFromMission(missionId: number): string {
    const s = String(missionId)
    return s.length > 1 ? s.substring(0, s.length - 1) : s
}

export function getCharacterStoryQuestIds(characterId: number | string): number[] {
    const cid = String(characterId)
    const lookupId = cid === '1' ? '10' : cid
    const ids: number[] = []
    for (const [key, rows] of Object.entries(charQuests as Record<string, any[]>)) {
        if (key.startsWith(lookupId) && rows.length > 0) {
            ids.push(parseInt(key))
        }
    }
    return ids
}
