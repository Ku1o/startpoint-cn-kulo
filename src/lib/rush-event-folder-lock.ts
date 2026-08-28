export const DEEP_ABYSS_RUSH_EVENT_ID = 700099;
export const DEEP_ABYSS_RUSH_FOLDER_ID = 1;
export const DEEP_ABYSS_ENDLESS_FOLDER_ID = 2;

export type DeepAbyssFolderSelection = "standard" | "endless_compat" | "invalid";
export type DeepAbyssFolderReset = "native" | "restart_from_first";

/**
 * Folder 2 is the Deep Abyss endless battle. It is viewable while a regular
 * Rush folder is active, but must never be persisted as the regular-folder
 * selection lock.
 */
export function classifyDeepAbyssFolderSelection(
    eventId: number,
    folderId: number,
): DeepAbyssFolderSelection {
    if (eventId !== DEEP_ABYSS_RUSH_EVENT_ID) return "standard";
    if (folderId === DEEP_ABYSS_RUSH_FOLDER_ID) return "standard";
    if (folderId === DEEP_ABYSS_ENDLESS_FOLDER_ID) return "endless_compat";
    return "invalid";
}

/** Deep Abyss never supports returning to a chosen finite-folder round. */
export function classifyDeepAbyssFolderReset(
    eventId: number,
): DeepAbyssFolderReset {
    return eventId === DEEP_ABYSS_RUSH_EVENT_ID
        ? "restart_from_first"
        : "native";
}

/** Match only the known stale value; other Rush events keep their own rules. */
export function isStaleDeepAbyssEndlessFolderLock(
    eventId: number,
    activeFolderId: number | null,
): boolean {
    return eventId === DEEP_ABYSS_RUSH_EVENT_ID
        && activeFolderId === DEEP_ABYSS_ENDLESS_FOLDER_ID;
}
