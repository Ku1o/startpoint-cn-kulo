export interface Mode15ActiveQuestOwnership {
    isMulti: boolean
    isMultiHost: boolean
}

/**
 * A stale multiplayer active quest proves only that its room can no longer be
 * resumed. It does not distinguish a defeat from a transport failure, so
 * deleting earlier Fantasy progress would incorrectly send the owner back to
 * stage 1. Explicit solo failure and the Rush reset endpoint still own full
 * run resets.
 */
export function shouldResetMode15RunForStaleActiveQuest(
    isMode15: boolean,
    quest: Mode15ActiveQuestOwnership,
): boolean {
    if (!isMode15) return false
    return !quest.isMulti
}
