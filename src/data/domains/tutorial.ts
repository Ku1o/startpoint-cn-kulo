import { getDb } from "../db";
import { RawPlayerTriggeredTutorial } from "../types";

/**
 * Gets a player's triggered tutorials.
 * 
 * @param playerId The ID of the player to get the triggered tutorials of.
 * @returns A list of the IDs of each triggered tutorial.
 */
export function getPlayerTriggeredTutorialsSync(
    playerId: number
): number[] {
    const db = getDb();
    const raw = db.prepare(`
    SELECT id
    FROM players_triggered_tutorials
    WHERE player_id = ?
    `).all(playerId) as RawPlayerTriggeredTutorial[]

    return raw.map(rawTrigger => rawTrigger.id)
}

/**
 * Marks a tutorial as having been triggered by a player.
 * 
 * @param playerId The ID of the player that triggered the tutorial.
 * @param tutorialId The ID of the tutorial that was triggered.
 */
export function insertPlayerTriggeredTutorialSync(
    playerId: number,
    tutorialId: number
) {
    const db = getDb();
    db.prepare(`
    INSERT INTO players_triggered_tutorials (id, player_id)
    VALUES (?, ?)
    `).run(tutorialId, playerId)
}

/**
 * Batch marks tutorials as having been triggered by a player.
 * 
 * @param playerId The ID of the player that triggered the tutorials.
 * @param tutorialIds An array of tutorial IDs which were triggered.
 */
export function insertPlayerTriggeredTutorialsSync(
    playerId: number,
    tutorialIds: number[]
) {
    const db = getDb();
    db.transaction(() => {
        for (const tutorialId of tutorialIds) {
            insertPlayerTriggeredTutorialSync(playerId, tutorialId)
        }
    })()
}
