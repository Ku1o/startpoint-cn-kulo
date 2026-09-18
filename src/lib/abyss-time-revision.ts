import { compareVersion, getPatchManifest, PatchMeta } from "./version"
import { QuestCategory } from "./types/quest"
import { ABYSS_NORMAL_EVENT_ID, ABYSS_EX_EVENT_ID, abyssEventFromQuest, isAbyssEvent } from "./abyss-modes"

export const ABYSS_TIME_REVISION_KEY = "rush:700099"
export const ABYSS_FIRST_QUEST_ID = 700099001
export const ABYSS_LAST_QUEST_ID = 700099098

export function isAbyssFiniteQuest(category: number | string, questId: number | string): boolean {
    const eventId = abyssEventFromQuest(category, questId)
    const round = Number(questId) % 1000
    return eventId !== null && round >= 1 && round <= (eventId === ABYSS_EX_EVENT_ID ? 30 : 98)
}

/** Only a published tower revision changes records; CDN versions alone do not. */
export function resolveAbyssTimeRevision(patches: readonly PatchMeta[], eventId: number = ABYSS_NORMAL_EVENT_ID): string | null {
    if (!isAbyssEvent(eventId)) return null
    let winningVersion: string | null = null
    let revision: string | null = null
    for (const patch of patches) {
        if (!patch.enabled || patch.type !== "patch") continue
        const candidate = patch.quest_time_revisions?.[`rush:${eventId}`]
        if (candidate === undefined) continue
        if (!/^[a-f0-9]{64}$/.test(candidate)) {
            throw new Error(`Invalid Deep Abyss time revision in patch ${patch.id}`)
        }
        const order = winningVersion === null ? 1 : compareVersion(patch.version, winningVersion)
        if (order === 0 && revision !== candidate) {
            throw new Error(`Conflicting Deep Abyss time revisions at ${patch.version}`)
        }
        if (order > 0) {
            winningVersion = patch.version
            revision = candidate
        }
    }
    return revision
}

export function getAbyssTimeRevision(eventId: number = ABYSS_NORMAL_EVENT_ID): string | null {
    return resolveAbyssTimeRevision(getPatchManifest().patches, eventId)
}

/** Rebuilt starts are accepted only when the client reports the current tower. */
export function getAbyssTimeRevisionAtVersion(resourceVersion: unknown, eventId: number = ABYSS_NORMAL_EVENT_ID): string | null {
    if (typeof resourceVersion !== "string" || !/^\d+\.\d+\.\d+$/.test(resourceVersion)) return null
    return resolveAbyssTimeRevision(getPatchManifest().patches.filter(patch =>
        compareVersion(patch.version, resourceVersion) <= 0
    ), eventId)
}

export function isStaleAbyssClient(category: number, questId: number, resourceVersion: unknown): boolean {
    if (!isAbyssFiniteQuest(category, questId) || resourceVersion === undefined) return false
    const eventId = abyssEventFromQuest(category, questId)!
    const current = getAbyssTimeRevision(eventId)
    return current !== null && getAbyssTimeRevisionAtVersion(resourceVersion, eventId) !== current
}

export function isStaleAbyssBattle(quest: {
    category: number
    questId: number
    questTimeRevision?: string | null
}): boolean {
    if (!isAbyssFiniteQuest(quest.category, quest.questId)) return false
    const current = getAbyssTimeRevision(abyssEventFromQuest(quest.category, quest.questId)!)
    return current !== null && quest.questTimeRevision !== current
}
