"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.isStaleDeepAbyssEndlessFolderLock = exports.classifyDeepAbyssFolderReset = exports.classifyDeepAbyssFolderSelection = exports.DEEP_ABYSS_ENDLESS_FOLDER_ID = exports.DEEP_ABYSS_RUSH_FOLDER_ID = exports.DEEP_ABYSS_RUSH_EVENT_ID = void 0;
exports.DEEP_ABYSS_RUSH_EVENT_ID = 700099;
exports.DEEP_ABYSS_RUSH_FOLDER_ID = 1;
exports.DEEP_ABYSS_ENDLESS_FOLDER_ID = 2;
/**
 * Folder 2 is the Deep Abyss endless battle. It is viewable while a regular
 * Rush folder is active, but must never be persisted as the regular-folder
 * selection lock.
 */
function classifyDeepAbyssFolderSelection(eventId, folderId) {
    if (eventId !== exports.DEEP_ABYSS_RUSH_EVENT_ID)
        return "standard";
    if (folderId === exports.DEEP_ABYSS_RUSH_FOLDER_ID)
        return "standard";
    if (folderId === exports.DEEP_ABYSS_ENDLESS_FOLDER_ID)
        return "endless_compat";
    return "invalid";
}
exports.classifyDeepAbyssFolderSelection = classifyDeepAbyssFolderSelection;
/** Deep Abyss never supports returning to a chosen finite-folder round. */
function classifyDeepAbyssFolderReset(eventId) {
    return eventId === exports.DEEP_ABYSS_RUSH_EVENT_ID
        ? "restart_from_first"
        : "native";
}
exports.classifyDeepAbyssFolderReset = classifyDeepAbyssFolderReset;
/** Match only the known stale value; other Rush events keep their own rules. */
function isStaleDeepAbyssEndlessFolderLock(eventId, activeFolderId) {
    return eventId === exports.DEEP_ABYSS_RUSH_EVENT_ID
        && activeFolderId === exports.DEEP_ABYSS_ENDLESS_FOLDER_ID;
}
exports.isStaleDeepAbyssEndlessFolderLock = isStaleDeepAbyssEndlessFolderLock;
