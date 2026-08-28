"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.givePlayerItemSync = exports.setPlayerItemSync = exports.updatePlayerItemSync = exports.insertPlayerItemsSync = exports.getPlayerCollectedItemTotalsByIdsSync = exports.getPlayerCollectedItemTotalsSync = exports.getPlayerCollectedItemTotalSync = exports.getPlayerItemsByIdsSync = exports.getPlayerItemsSync = exports.getPlayerItemSync = void 0;
const db_1 = require("../db");
/**
 * Gets the amount of a singular item that a player owns.
 *
 * @param playerId The ID of the player.
 * @param itemId The ID of the item.
 * @returns The amount of the item that the player owns, or null, indicating no ownership.
 */
function getPlayerItemSync(playerId, itemId) {
    const db = (0, db_1.getDb)();
    const rawItem = db.prepare(`
    SELECT id, amount
    FROM players_items
    WHERE player_id = ? AND id = ?
    `).get(playerId, Number(itemId));
    return rawItem === undefined ? null : rawItem.amount;
}
exports.getPlayerItemSync = getPlayerItemSync;
/**
 * Gets the items that a player owns.
 *
 * @param playerId The ID of the player.
 * @returns A record where the index is the item's ID and the value is the item's amount.
 */
function getPlayerItemsSync(playerId) {
    const db = (0, db_1.getDb)();
    const rawItems = db.prepare(`
    SELECT id, amount
    FROM players_items
    WHERE player_id = ?
    `).all(playerId);
    const output = {};
    for (const rawItem of rawItems) {
        output[rawItem.id.toString()] = rawItem.amount;
    }
    return output;
}
exports.getPlayerItemsSync = getPlayerItemsSync;
/** Retrieves only the requested inventory rows with one bounded read. */
function getPlayerItemsByIdsSync(playerId, itemIds) {
    const ids = [...new Set(itemIds)].filter(itemId => Number.isSafeInteger(itemId) && itemId > 0);
    if (ids.length === 0)
        return {};
    const placeholders = ids.map(() => "?").join(", ");
    const rows = (0, db_1.getDb)().prepare(`
    SELECT id, amount
    FROM players_items
    WHERE player_id = ? AND id IN (${placeholders})
    `).all(playerId, ...ids);
    return Object.fromEntries(rows.map(row => [String(row.id), row.amount]));
}
exports.getPlayerItemsByIdsSync = getPlayerItemsByIdsSync;
function getPlayerCollectedItemTotalSync(playerId, itemId) {
    var _a;
    const row = (0, db_1.getDb)().prepare(`
    SELECT total_obtained
    FROM players_collected_items
    WHERE player_id = ? AND item_id = ?
    `).get(playerId, Number(itemId));
    return (_a = row === null || row === void 0 ? void 0 : row.total_obtained) !== null && _a !== void 0 ? _a : 0;
}
exports.getPlayerCollectedItemTotalSync = getPlayerCollectedItemTotalSync;
function getPlayerCollectedItemTotalsSync(playerId) {
    const rows = (0, db_1.getDb)().prepare(`
    SELECT item_id, total_obtained
    FROM players_collected_items
    WHERE player_id = ?
    `).all(playerId);
    return Object.fromEntries(rows.map(row => [String(row.item_id), row.total_obtained]));
}
exports.getPlayerCollectedItemTotalsSync = getPlayerCollectedItemTotalsSync;
/** Retrieves lifetime acquisition totals for only the requested item IDs. */
function getPlayerCollectedItemTotalsByIdsSync(playerId, itemIds) {
    const ids = [...new Set(itemIds)].filter(itemId => Number.isSafeInteger(itemId) && itemId > 0);
    if (ids.length === 0)
        return {};
    const placeholders = ids.map(() => "?").join(", ");
    const rows = (0, db_1.getDb)().prepare(`
    SELECT item_id, total_obtained
    FROM players_collected_items
    WHERE player_id = ? AND item_id IN (${placeholders})
    `).all(playerId, ...ids);
    return Object.fromEntries(rows.map(row => [String(row.item_id), row.total_obtained]));
}
exports.getPlayerCollectedItemTotalsByIdsSync = getPlayerCollectedItemTotalsByIdsSync;
function recordPlayerCollectedItemSync(playerId, itemId, obtainedAmount) {
    if (!Number.isSafeInteger(obtainedAmount) || obtainedAmount <= 0)
        return;
    (0, db_1.getDb)().prepare(`
    INSERT INTO players_collected_items (player_id, item_id, total_obtained)
    VALUES (?, ?, ?)
    ON CONFLICT(player_id, item_id) DO UPDATE SET
        total_obtained = total_obtained + excluded.total_obtained
    `).run(playerId, Number(itemId), obtainedAmount);
}
/**
 * Inserts a singular item into the player's inventory.
 *
 * @param playerId The ID of the player.
 * @param itemId The ID of the item to insert.
 * @param amount The amount of the item to insert.
 */
function insertPlayerItemSync(playerId, itemId, amount) {
    const db = (0, db_1.getDb)();
    db.prepare(`
    INSERT INTO players_items (id, amount, player_id)
    VALUES (?, ?, ?)
    `).run(Number(itemId), amount, playerId);
}
/**
 * Batch inserts a record of player items into a player's inventory.
 *
 * @param playerId The ID of the player.
 * @param items The record of items.
 */
function insertPlayerItemsSync(playerId, items) {
    const db = (0, db_1.getDb)();
    db.transaction(() => {
        for (const [itemId, amount] of Object.entries(items)) {
            insertPlayerItemSync(playerId, itemId, amount);
        }
    })();
}
exports.insertPlayerItemsSync = insertPlayerItemsSync;
/**
 * Updates a player's item's amount.
 *
 * @param playerId The ID of the player.
 * @param itemId The item's ID.
 * @param amount The new amount the item should have.
 */
function updatePlayerItemSync(playerId, itemId, amount) {
    const db = (0, db_1.getDb)();
    db.prepare(`
    UPDATE players_items
    SET amount = ?
    WHERE player_id = ? AND id = ?
    `).run(amount, playerId, Number(itemId));
}
exports.updatePlayerItemSync = updatePlayerItemSync;
/**
 * Sets a player's item to an exact amount, inserting the row first if the player does not yet
 * own the item.
 *
 * updatePlayerItemSync on its own is a bare UPDATE that silently affects zero rows when the
 * player does not already own the item, so callers that mean "add or set this item" (e.g. the
 * web admin's POST /:id/item) would return success while writing nothing for a not-yet-owned item.
 *
 * @param playerId The ID of the player.
 * @param itemId The item's ID.
 * @param amount The exact amount the item should have.
 */
function setPlayerItemSync(playerId, itemId, amount) {
    if (getPlayerItemSync(playerId, itemId) === null) {
        insertPlayerItemSync(playerId, itemId, amount);
    }
    else {
        updatePlayerItemSync(playerId, itemId, amount);
    }
}
exports.setPlayerItemSync = setPlayerItemSync;
/**
 * Gives a player giveAmount of an item.
 *
 * @param playerId The ID of the player.
 * @param itemId The ID of the item.
 * @param giveAmount The amount of the item to give.
 * @returns The new total amount of the item that the player owns.
 */
function givePlayerItemSync(playerId, itemId, giveAmount) {
    return (0, db_1.getDb)().transaction(() => {
        const ownedAmount = getPlayerItemSync(playerId, itemId);
        const newAmount = (ownedAmount !== null && ownedAmount !== void 0 ? ownedAmount : 0) + giveAmount;
        if (ownedAmount === null)
            insertPlayerItemSync(playerId, itemId, newAmount);
        else
            updatePlayerItemSync(playerId, itemId, newAmount);
        recordPlayerCollectedItemSync(playerId, itemId, giveAmount);
        return newAmount;
    })();
}
exports.givePlayerItemSync = givePlayerItemSync;
