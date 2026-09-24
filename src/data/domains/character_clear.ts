import { cachedStatement } from "../../lib/cached-statement"
import { getDb } from "../db";

export function getPlayerCharacterClearSync(playerId: number, characterId: number) {
    const row = cachedStatement(getDb(), `
    SELECT clear_count, multi_count, leader_clear_count, leader_multi_count, leader_power_flip_count FROM players_character_quest_clears
    WHERE player_id = ? AND character_id = ?
    `).get(playerId, characterId) as { clear_count: number; multi_count: number; leader_clear_count: number; leader_multi_count: number; leader_power_flip_count: number } | undefined;
    return row || { clear_count: 0, multi_count: 0, leader_clear_count: 0, leader_multi_count: 0, leader_power_flip_count: 0 };
}

export function getPlayerCharacterClearsSync(playerId: number, characterIds?: readonly number[]) {
    const ids = characterIds === undefined ? undefined : [...new Set(characterIds)]
        .filter(id => Number.isSafeInteger(id) && id > 0)
    const scopes: (number[] | undefined)[] = ids === undefined ? [undefined] : []
    for (let offset = 0; ids && offset < ids.length; offset += 400) scopes.push(ids.slice(offset, offset + 400))
    const rows = scopes.flatMap(scope => cachedStatement(getDb(), `
    SELECT character_id, clear_count, multi_count, leader_clear_count, leader_multi_count, leader_power_flip_count
    FROM players_character_quest_clears
    WHERE player_id = ?
    ${scope ? `AND character_id IN (${scope.map(() => "?").join(", ")})` : ""}
    `).all(playerId, ...(scope ?? []))) as Array<{
        character_id: number
        clear_count: number
        multi_count: number
        leader_clear_count: number
        leader_multi_count: number
        leader_power_flip_count: number
    }>
    return Object.fromEntries(rows.map(row => [String(row.character_id), {
        clear_count: row.clear_count,
        multi_count: row.multi_count,
        leader_clear_count: row.leader_clear_count,
        leader_multi_count: row.leader_multi_count,
        leader_power_flip_count: row.leader_power_flip_count,
    }]))
}

export function incrementPlayerCharacterClearSync(playerId: number, characterId: number, isMulti: boolean, isLeader = false) {
    incrementPlayerCharacterClearsSync(playerId, [{ characterId, isLeader }], isMulti)
}

/** One atomic upsert for the at-most-six distinct members of a battle party. */
export function incrementPlayerCharacterClearsSync(
    playerId: number,
    members: readonly { characterId: number, isLeader: boolean }[],
    isMulti: boolean,
): void {
    if (members.length === 0) return
    for (let offset = 0; offset < members.length; offset += 150) {
        const chunk = members.slice(offset, offset + 150)
        cachedStatement(getDb(), `
    INSERT INTO players_character_quest_clears (player_id, character_id, clear_count, multi_count, leader_clear_count, leader_multi_count)
    VALUES ${chunk.map(() => "(?, ?, 1, ?, ?, ?)").join(", ")}
    ON CONFLICT(player_id, character_id) DO UPDATE SET
        clear_count = clear_count + 1,
        multi_count = multi_count + excluded.multi_count,
        leader_clear_count = leader_clear_count + excluded.leader_clear_count,
        leader_multi_count = leader_multi_count + excluded.leader_multi_count
    `).run(...chunk.flatMap(({ characterId, isLeader }) => [
        playerId, characterId, isMulti ? 1 : 0, isLeader ? 1 : 0, isMulti && isLeader ? 1 : 0,
    ]))
    }
}
