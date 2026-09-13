// Character → quest mapping helpers

import charQuests from "../../../assets/character_quest_lookup.json"

// The master table is immutable for this server process. Preserve its prefix
// matching and row order, but index it once instead of scanning it for every
// awakening condition (including repeated final-mission dependencies).
const storyQuestIdsByPrefix = new Map<string, number[]>()
for (const [key, rows] of Object.entries(charQuests as Record<string, any[]>)) {
    if (rows.length === 0) continue
    for (let length = 0; length <= key.length; length += 1) {
        const prefix = key.substring(0, length)
        const ids = storyQuestIdsByPrefix.get(prefix) ?? []
        ids.push(parseInt(key))
        storyQuestIdsByPrefix.set(prefix, ids)
    }
}

export function getCharacterIdFromMission(missionId: number): string {
    const s = String(missionId)
    return s.length > 1 ? s.substring(0, s.length - 1) : s
}

export function getCharacterStoryQuestIds(characterId: number | string): number[] {
    const cid = String(characterId)
    const lookupId = cid === '1' ? '10' : cid
    // Callers receive their own array, as with the original scan.
    return [...(storyQuestIdsByPrefix.get(lookupId) ?? [])]
}
