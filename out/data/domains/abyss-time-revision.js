"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.refreshPlayerAbyssBestTimesSync = void 0;
const db_1 = require("../db");
const abyss_time_revision_1 = require("../../lib/abyss-time-revision");
const quest_1 = require("../../lib/types/quest");
/** Clear only the finite tower's times, including legacy saves and restored saves. */
function refreshPlayerAbyssBestTimesSync(playerId) {
    const revision = (0, abyss_time_revision_1.getAbyssTimeRevision)();
    if (revision === null)
        return null;
    (0, db_1.getDb)().prepare(`
        UPDATE players_quest_progress
        SET best_elapsed_time_ms = NULL, best_time_revision = ?
        WHERE player_id = ? AND section = ? AND quest_id BETWEEN ? AND ?
          AND (best_time_revision IS NULL OR best_time_revision != ?)
    `).run(revision, playerId, quest_1.QuestCategory.RUSH_EVENT, abyss_time_revision_1.ABYSS_FIRST_QUEST_ID, abyss_time_revision_1.ABYSS_LAST_QUEST_ID, revision);
    return revision;
}
exports.refreshPlayerAbyssBestTimesSync = refreshPlayerAbyssBestTimesSync;
