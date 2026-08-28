"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.upsertPlayerCharacterAwakeUnlockSync = exports.getPlayerCharacterAwakeUnlocksByCharacterIdsSync = exports.getPlayerCharacterAwakeUnlocksSync = void 0;
const db_1 = require("../db");
function getPlayerCharacterAwakeUnlocksSync(playerId) {
    var _a;
    const rows = (0, db_1.getDb)().prepare(`
        SELECT character_id, board_index, awake_level
        FROM players_character_awake_unlocks
        WHERE player_id = ?
    `).all(playerId);
    const result = new Map();
    for (const row of rows) {
        const characterId = String(row.character_id);
        const awakeLevels = (_a = result.get(characterId)) !== null && _a !== void 0 ? _a : {};
        awakeLevels[row.board_index] = row.awake_level;
        result.set(characterId, awakeLevels);
    }
    return result;
}
exports.getPlayerCharacterAwakeUnlocksSync = getPlayerCharacterAwakeUnlocksSync;
/** Retrieves Awake unlocks for only the requested characters. */
function getPlayerCharacterAwakeUnlocksByCharacterIdsSync(playerId, characterIds) {
    var _a;
    const ids = [...new Set(characterIds)].filter(characterId => Number.isSafeInteger(characterId) && characterId > 0);
    if (ids.length === 0)
        return new Map();
    const placeholders = ids.map(() => "?").join(", ");
    const rows = (0, db_1.getDb)().prepare(`
        SELECT character_id, board_index, awake_level
        FROM players_character_awake_unlocks
        WHERE player_id = ? AND character_id IN (${placeholders})
    `).all(playerId, ...ids);
    const result = new Map();
    for (const row of rows) {
        const characterId = String(row.character_id);
        const awakeLevels = (_a = result.get(characterId)) !== null && _a !== void 0 ? _a : {};
        awakeLevels[row.board_index] = row.awake_level;
        result.set(characterId, awakeLevels);
    }
    return result;
}
exports.getPlayerCharacterAwakeUnlocksByCharacterIdsSync = getPlayerCharacterAwakeUnlocksByCharacterIdsSync;
function upsertPlayerCharacterAwakeUnlockSync(playerId, characterId, boardIndex, awakeLevel) {
    const result = (0, db_1.getDb)().prepare(`
        INSERT INTO players_character_awake_unlocks
            (player_id, character_id, board_index, awake_level)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(player_id, character_id, board_index) DO UPDATE SET
            awake_level = excluded.awake_level
        WHERE excluded.awake_level > players_character_awake_unlocks.awake_level
    `).run(playerId, characterId, boardIndex, awakeLevel);
    return result.changes > 0;
}
exports.upsertPlayerCharacterAwakeUnlockSync = upsertPlayerCharacterAwakeUnlockSync;
