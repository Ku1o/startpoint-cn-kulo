import { compareVersion, getPatchManifest, PatchMeta } from "./version"
import { QuestCategory } from "./types/quest"

export const ABYSS_TIME_REVISION_KEY = "rush:700099"
export const ABYSS_FIRST_QUEST_ID = 700099001
export const ABYSS_LAST_QUEST_ID = 700099098

export function isAbyssFiniteQuest(category: number | string, questId: number | string): boolean {
    return Number(category) === QuestCategory.RUSH_EVENT
        && Number(questId) >= ABYSS_FIRST_QUEST_ID
        && Number(questId) <= ABYSS_LAST_QUEST_ID
}

/** Only a published tower revision changes records; CDN versions alone do not. */
export function resolveAbyssTimeRevision(patches: readonly PatchMeta[]): string | null {
    let winningVersion: string | null = null
    let revision: string | null = null
    for (const patch of patches) {
        if (!patch.enabled || patch.type !== "patch") continue
        const candidate = patch.quest_time_revisions?.[ABYSS_TIME_REVISION_KEY]
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

export function getAbyssTimeRevision(): string | null {
    return resolveAbyssTimeRevision(getPatchManifest().patches)
}

/** Rebuilt starts are accepted only when the client reports the current tower. */
export function getAbyssTimeRevisionAtVersion(resourceVersion: unknown): string | null {
    if (typeof resourceVersion !== "string" || !/^\d+\.\d+\.\d+$/.test(resourceVersion)) return null
    return resolveAbyssTimeRevision(getPatchManifest().patches.filter(patch =>
        compareVersion(patch.version, resourceVersion) <= 0
    ))
}

export function isStaleAbyssClient(category: number, questId: number, resourceVersion: unknown): boolean {
    if (!isAbyssFiniteQuest(category, questId) || resourceVersion === undefined) return false
    const current = getAbyssTimeRevision()
    return current !== null && getAbyssTimeRevisionAtVersion(resourceVersion) !== current
}

export function isStaleAbyssBattle(quest: {
    category: number
    questId: number
    questTimeRevision?: string | null
}): boolean {
    if (!isAbyssFiniteQuest(quest.category, quest.questId)) return false
    const current = getAbyssTimeRevision()
    return current !== null && quest.questTimeRevision !== current
}
