import { getRogueEventConfig, getRushEventFolderMaxRoundSync } from "./assets"
import { isAbyssEvent } from "./abyss-modes"
import { isMode15RuntimeLoaded, MODE15_RUSH_EVENT_ID } from "./mode15-optional"
import { RushEventFolder } from "./types"

/**
 * Rush folder round counts.
 *
 * This helper used to live in the rush-event route module. The single battle
 * finish settlement now executes inside the SQLite writer thread, and a domain
 * module must not import a route module just to resolve folder rounds.
 */
export const rushEventFolderMaxRounds: { [key in RushEventFolder]?: number } = {
    [RushEventFolder.INTERMEDIATE]: 2,
    [RushEventFolder.ADVANCED]: 2,
    [RushEventFolder.GODLY]: 2,
}

export function getRushEventFolderMaxRounds(eventId: number, folderId: number): number {
    // Deep Abyss is a data-driven 30-floor tower.  The legacy fallback map
    // only knows the three official two-round folders, so keep its finite
    // folder open for the configured roguelike run.
    if (isAbyssEvent(eventId) && folderId === RushEventFolder.INTERMEDIATE) {
        const configured = Number((getRogueEventConfig(eventId) as any)?.rounds)
        return Number.isInteger(configured) && configured > 0 ? configured : 30
    }
    if (
        isMode15RuntimeLoaded()
        && eventId === MODE15_RUSH_EVENT_ID
        && folderId === RushEventFolder.INTERMEDIATE
    ) {
        // Mode15 exposes all fifteen rounds in the Rush folder.  The three
        // boss rows are placeholders completed by AdventEvent settlement.
        // Keep one sentinel round beyond stage 15 so native Rush completion
        // never closes the folder before stage-15 settlement resets the run.
        return 16;
    }

    const configuredMaxRound = getRushEventFolderMaxRoundSync(eventId, folderId)
    if (configuredMaxRound > 0) return configuredMaxRound

    // Retain the legacy defaults only for old/custom rows that have no quest
    // master data. Official event folders are resolved from their actual rows.
    return rushEventFolderMaxRounds[folderId as RushEventFolder] ?? 0;
}
