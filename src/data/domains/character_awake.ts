import { getDb } from "../db"

export type CharacterAwakeUnlockMap = Map<string, Record<number, number>>

interface RawCharacterAwakeUnlock {
    character_id: number
    board_index: number
    awake_level: number
}

export function getPlayerCharacterAwakeUnlocksSync(
    playerId: number
): CharacterAwakeUnlockMap {
    const rows = getDb().prepare(`
        SELECT character_id, board_index, awake_level
        FROM players_character_awake_unlocks
        WHERE player_id = ?
    `).all(playerId) as RawCharacterAwakeUnlock[]

    const result: CharacterAwakeUnlockMap = new Map()
    for (const row of rows) {
        const characterId = String(row.character_id)
        const awakeLevels = result.get(characterId) ?? {}
        awakeLevels[row.board_index] = row.awake_level
        result.set(characterId, awakeLevels)
    }
    return result
}

/** Retrieves Awake unlocks for only the requested characters. */
export function getPlayerCharacterAwakeUnlocksByCharacterIdsSync(
    playerId: number,
    characterIds: readonly number[],
): CharacterAwakeUnlockMap {
    const ids = [...new Set(characterIds)].filter(
        characterId => Number.isSafeInteger(characterId) && characterId > 0,
    )
    if (ids.length === 0) return new Map()

    const placeholders = ids.map(() => "?").join(", ")
    const rows = getDb().prepare(`
        SELECT character_id, board_index, awake_level
        FROM players_character_awake_unlocks
        WHERE player_id = ? AND character_id IN (${placeholders})
    `).all(playerId, ...ids) as RawCharacterAwakeUnlock[]
    const result: CharacterAwakeUnlockMap = new Map()
    for (const row of rows) {
        const characterId = String(row.character_id)
        const awakeLevels = result.get(characterId) ?? {}
        awakeLevels[row.board_index] = row.awake_level
        result.set(characterId, awakeLevels)
    }
    return result
}

export function upsertPlayerCharacterAwakeUnlockSync(
    playerId: number,
    characterId: number,
    boardIndex: number,
    awakeLevel: number
): boolean {
    const result = getDb().prepare(`
        INSERT INTO players_character_awake_unlocks
            (player_id, character_id, board_index, awake_level)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(player_id, character_id, board_index) DO UPDATE SET
            awake_level = excluded.awake_level
        WHERE excluded.awake_level > players_character_awake_unlocks.awake_level
    `).run(playerId, characterId, boardIndex, awakeLevel)

    return result.changes > 0
}
