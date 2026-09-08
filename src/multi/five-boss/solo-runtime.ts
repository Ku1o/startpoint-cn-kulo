import { getDb } from "../../data/db"
import { getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import { getPlayerActiveQuestSync } from "../../data/domains/quest_active"
import { computeRealTimeStamina } from "../../lib/stamina"
import { FIVE_BOSS_GAUNTLET, isFiveBossGauntletQuest } from "./contract"

export function startFiveBossSoloSync<T>(playerId: number, playId: string, persist: () => T): T | null {
    if (typeof playId !== "string" || !playId.length || playId.length > 255) throw new Error("Invalid play id.")
    const db = getDb()
    return db.transaction(() => {
        const active = getPlayerActiveQuestSync(playerId)
        if (active?.isMulti && isFiveBossGauntletQuest(active.category, active.questId)) {
            throw new Error("Finish or abort the multiplayer run before starting solo.")
        }
        const old = db.prepare("SELECT status FROM five_boss_solo_runs WHERE player_id = ? AND play_id = ?")
            .get(playerId, playId) as { status: string } | undefined
        if (old) {
            if (old.status !== "active" || active?.playId !== playId) throw new Error("This play id has ended.")
            return null
        }
        const player = getPlayerSync(playerId)
        if (!player) throw new Error("Player does not exist.")
        // The legacy helper rounds now to seconds. Subsecond heal timestamps
        // must not make its negative fraction consume an extra stamina point.
        const stamina = Math.max(player.stamina, computeRealTimeStamina(player))
        const staminaCost = FIVE_BOSS_GAUNTLET.staminaCost
        if (stamina < staminaCost) throw new Error("Insufficient stamina.")
        const debit = db.prepare(`UPDATE players_items SET amount = amount - 1
            WHERE player_id = ? AND id = ? AND amount >= 1`).run(playerId, FIVE_BOSS_GAUNTLET.ticketItemId)
        if (debit.changes !== 1) throw new Error("Not enough entry tickets.")
        updatePlayerSync({ id: playerId, stamina: stamina - staminaCost, staminaHealTime: new Date(),
            totalStaminaUsed: (player.totalStaminaUsed ?? 0) + staminaCost })
        db.prepare("UPDATE five_boss_solo_runs SET status = 'aborted' WHERE player_id = ? AND status = 'active'").run(playerId)
        db.prepare("INSERT INTO five_boss_solo_runs(player_id, play_id, status) VALUES (?, ?, 'active')").run(playerId, playId)
        return persist()
    }).immediate()
}

/** Called in the single-abort transaction before its active quest is cleared. */
export function abortFiveBossSoloSync(playerId: number, playId: string): void {
    getDb().prepare(`UPDATE five_boss_solo_runs SET status = 'aborted'
        WHERE player_id = ? AND play_id = ? AND status = 'active'`).run(playerId, playId)
}

export function getFiveBossSoloReceiptSync(playerId: number, requestKey: string | null): unknown | undefined {
    if (!requestKey) return undefined
    const row = getDb().prepare(`SELECT response_json FROM five_boss_solo_runs
        WHERE player_id = ? AND finish_request_key = ? AND status = 'settled'`)
        .get(playerId, requestKey) as { response_json: string } | undefined
    return row ? JSON.parse(row.response_json) : undefined
}

export function isActiveFiveBossSoloSync(playerId: number, playId: string): boolean {
    return !!getDb().prepare(`SELECT 1 FROM five_boss_solo_runs
        WHERE player_id = ? AND play_id = ? AND status = 'active'`).get(playerId, playId)
}

/** Called inside the ordinary single-finish transaction with all rewards. */
export function saveFiveBossSoloReceiptSync(playerId: number, playId: string, requestKey: string | null, response: unknown): void {
    if (!requestKey) throw new Error("Missing five-boss finish request identity.")
    const result = getDb().prepare(`UPDATE five_boss_solo_runs
        SET status = 'settled', finish_request_key = ?, response_json = ?
        WHERE player_id = ? AND play_id = ? AND status = 'active'`)
        .run(requestKey, JSON.stringify(response), playerId, playId)
    if (result.changes !== 1) throw new Error("Five-boss solo run is no longer active.")
}
