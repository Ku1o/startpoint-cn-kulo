import { createHash } from "crypto"
import { getDb } from "../../data/db"
import { getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import { getPlayerActiveQuestSync, updatePlayerActiveQuestContinueCountSync } from "../../data/domains/quest_active"
import { FIVE_BOSS_GAUNTLET, isFiveBossGauntletQuest } from "./contract"
import { runPersistenceTransaction, runPersistenceTransactionSync } from "../../lib/persistence-coordinator"

export class FiveBossContinueError extends Error {}

interface ContinueRequest {
    playerId: number
    isMulti: boolean
    category: number
    questId: number
    playId: unknown
    apiCount: unknown
    statistics?: unknown
}

/** Also catches a forged ordinary-quest request during a registered gauntlet. */
export function isFiveBossContinueRequest(playerId: number, category: number, questId: number, playId: unknown): boolean {
    if (isFiveBossGauntletQuest(category, questId)) return true
    const active = getPlayerActiveQuestSync(playerId)
    if (active && isFiveBossGauntletQuest(active.category, active.questId)) return true
    if (typeof playId !== "string") return false
    return !!getDb().prepare(`SELECT 1 FROM five_boss_solo_runs WHERE player_id = ? AND play_id = ?
        UNION ALL SELECT 1 FROM five_boss_gauntlet_members WHERE player_id = ? AND client_play_id = ? LIMIT 1`)
        .get(playerId, playId, playerId, playId)
}

function stableJson(value: unknown): string {
    if (Array.isArray(value)) return "[" + value.map(stableJson).join(",") + "]"
    if (value !== null && typeof value === "object") {
        const record = value as Record<string, unknown>
        return "{" + Object.keys(record).sort().map(key => JSON.stringify(key) + ":" + stableJson(record[key])).join(",") + "}"
    }
    return JSON.stringify(value) ?? "null"
}

/** Debit and count commit together. Native HTTP retries keep api_count and statistics. */
function continueFiveBossInTransaction(input: ContinueRequest) {
    const apiCount = Number(input.apiCount)
    if (!isFiveBossGauntletQuest(input.category, input.questId)
        || typeof input.playId !== "string" || !input.playId.length || input.playId.length > 255
        || input.apiCount === undefined || input.apiCount === null || input.apiCount === ""
        || !Number.isSafeInteger(apiCount) || apiCount < 0) {
        throw new FiveBossContinueError("Invalid five-boss continue identity.")
    }
    const playId = input.playId
    const requestKey = apiCount + ":" + createHash("sha256").update(stableJson(input.statistics)).digest("hex")
    const db = getDb()
    {
        // Persistent state is authoritative even if an in-memory entry is stale after reconnect.
        const active = getPlayerActiveQuestSync(input.playerId)
        if (!active || active.playId !== playId || active.isMulti !== input.isMulti
            || !isFiveBossGauntletQuest(active.category, active.questId)) {
            throw new FiveBossContinueError("No matching active five-boss quest to continue.")
        }
        const registered = input.isMulti
            ? db.prepare(`SELECT 1 FROM five_boss_gauntlet_members m
                JOIN five_boss_gauntlet_runs r ON r.run_id = m.run_id
                LEFT JOIN five_boss_gauntlet_receipts receipt ON receipt.run_id = m.run_id AND receipt.player_id = m.player_id
                WHERE m.player_id = ? AND m.client_play_id = ? AND r.status = 'active'
                    AND m.started_at IS NOT NULL AND m.aborted_at IS NULL AND m.finalized_at IS NULL
                    AND receipt.player_id IS NULL AND r.room_number = ?`)
                .get(input.playerId, playId, active.roomNumber)
            : db.prepare(`SELECT 1 FROM five_boss_solo_runs WHERE player_id = ? AND play_id = ? AND status = 'active'`)
                .get(input.playerId, playId)
        if (!registered) throw new FiveBossContinueError("Five-boss run is no longer active.")

        const receipt = db.prepare(`SELECT request_key FROM five_boss_continue_receipts
            WHERE player_id = ? AND play_id = ? AND is_multi = ?`)
            .get(input.playerId, playId, Number(input.isMulti)) as { request_key: string } | undefined
        if (receipt && receipt.request_key !== requestKey
            || !receipt && active.continueCount >= FIVE_BOSS_GAUNTLET.maxContinueCount) {
            throw new FiveBossContinueError("Each player can continue only once per five-boss run.")
        }
        const player = getPlayerSync(input.playerId)
        if (!player) throw new FiveBossContinueError("Player does not exist.")
        if (!receipt) {
            const freeCost = Math.min(player.freeVmoney, FIVE_BOSS_GAUNTLET.continueVmoneyCost)
            const paidCost = FIVE_BOSS_GAUNTLET.continueVmoneyCost - freeCost
            if (player.vmoney < paidCost) throw new FiveBossContinueError("Not enough vmoney to continue.")
            player.freeVmoney -= freeCost
            player.vmoney -= paidCost
            updatePlayerSync({ id: input.playerId, freeVmoney: player.freeVmoney, vmoney: player.vmoney })
            updatePlayerActiveQuestContinueCountSync(input.playerId, FIVE_BOSS_GAUNTLET.maxContinueCount)
            db.prepare(`INSERT INTO five_boss_continue_receipts(player_id, play_id, is_multi, request_key) VALUES (?, ?, ?, ?)`)
                .run(input.playerId, playId, Number(input.isMulti), requestKey)
        }
        return { continue_count: FIVE_BOSS_GAUNTLET.maxContinueCount,
            user_info: { free_vmoney: player.freeVmoney, vmoney: player.vmoney }, mail_arrived: false }
    }
}

/** Synchronous compatibility API for legacy callers and isolated tests. */
export function continueFiveBossSync(input: ContinueRequest) {
    return runPersistenceTransactionSync({
        domain: "multi-settlement", playerId: input.playerId, operation: "five_boss_continue_sync",
    }, () => continueFiveBossInTransaction(input))
}

/** Async HTTP path; the transaction is owned by the persistence boundary. */
export function continueFiveBoss(input: ContinueRequest) {
    return runPersistenceTransaction({
        domain: "multi-settlement", playerId: input.playerId, operation: "five_boss_continue",
    }, () => continueFiveBossInTransaction(input))
}
