import requirementsData from "../../assets/multi_guest_entry_requirements.json"
import { getDb } from "../data/db"
import { getPlayerItemSync } from "../data/domains/item"
import { getPlayerSync } from "../data/domains/player"
import type { Player } from "../data/types"
import { cachedStatement } from "../lib/cached-statement"
import { getQuestFromCategorySync } from "../lib/assets"
import { canJoinMode15RescueSync, isMode15Quest } from "../lib/mode15-optional"
import { getRankDegree } from "../lib/stamina"
import { FIVE_BOSS_GAUNTLET, isFiveBossGauntletQuest } from "./five-boss/contract"

interface RescueEntryRule {
    minimum_player_rank: number
    required_quest_categories: number[]
    required_quest_id: number
}

export type GuestEligibilityReason =
    | "eligible"
    | "player_not_found"
    | "player_rank"
    | "prerequisite_quest"
    | "mode15_progress"
    | "five_boss_ticket"

export interface GuestEligibility {
    allowed: boolean
    reason: GuestEligibilityReason
    minimumPlayerRank?: number
    playerRank?: number
    requiredQuestCategories?: number[]
    requiredQuestId?: number
    requiredItemId?: number
    currentItemCount?: number
}

export interface GuestEligibilityDependencies {
    getPlayer: (playerId: number) => Player | null
    hasFinishedQuest: (playerId: number, category: number, questId: number) => boolean
    getItemCount: (playerId: number, itemId: number) => number | null
}

function loadRules(value: unknown): ReadonlyMap<string, RescueEntryRule> {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("multi guest entry requirements must be an object")
    }
    const loaded = new Map<string, RescueEntryRule>()
    for (const [key, raw] of Object.entries(value)) {
        const match = key.match(/^(\d+):(\d+)$/)
        const candidate = raw as Partial<RescueEntryRule>
        const rule = {
            minimum_player_rank: Number(candidate?.minimum_player_rank),
            required_quest_categories: Array.isArray(candidate?.required_quest_categories)
                ? [...new Set(candidate.required_quest_categories.map(Number))]
                : [],
            required_quest_id: Number(candidate?.required_quest_id),
        }
        if (!match
            || !Number.isSafeInteger(rule.minimum_player_rank) || rule.minimum_player_rank <= 0
            || !Number.isSafeInteger(rule.required_quest_id) || rule.required_quest_id <= 0
            || rule.required_quest_categories.length === 0
            || !rule.required_quest_categories.every(number => Number.isSafeInteger(number) && number > 0)
            || getQuestFromCategorySync(Number(match[1]), Number(match[2])) === null
            || !rule.required_quest_categories.some(category =>
                getQuestFromCategorySync(category, rule.required_quest_id) !== null)) {
            throw new Error(`invalid multi guest entry requirement: ${key}`)
        }
        loaded.set(key, Object.freeze({
            ...rule,
            required_quest_categories: Object.freeze(rule.required_quest_categories),
        }) as RescueEntryRule)
    }
    return loaded
}

const rules = loadRules(requirementsData.rules)

function hasFinishedQuestSync(playerId: number, category: number, questId: number): boolean {
    return cachedStatement(getDb(), `
        SELECT 1 AS finished
        FROM players_quest_progress
        WHERE player_id = ? AND section = ? AND quest_id = ? AND finished = 1
        LIMIT 1
    `).get(playerId, category, questId) !== undefined
}

/**
 * Checks a new real guest before room admission. Hosts and returning room
 * members are handled by the callers and bypass this gate. Unknown quests
 * fail open because the server must not invent restrictions that are absent
 * from the audited client master table.
 */
export function canJoinMultiGuestQuestSync(
    playerId: number,
    category: number,
    questId: number,
    player?: Player | null,
    dependencies: Partial<GuestEligibilityDependencies> = {},
): GuestEligibility {
    if (isFiveBossGauntletQuest(category, questId)) {
        const resolvedPlayer = player ?? (dependencies.getPlayer ?? getPlayerSync)(playerId)
        if (!resolvedPlayer) return { allowed: false, reason: "player_not_found" }
        const playerRank = getRankDegree(resolvedPlayer.rankPoint || 0)
        if (playerRank < FIVE_BOSS_GAUNTLET.minimumGuestPlayerRank) {
            return {
                allowed: false,
                reason: "player_rank",
                minimumPlayerRank: FIVE_BOSS_GAUNTLET.minimumGuestPlayerRank,
                playerRank,
            }
        }
        const getItemCount = dependencies.getItemCount ?? getPlayerItemSync
        const currentItemCount = Math.max(
            0,
            Number(getItemCount(playerId, FIVE_BOSS_GAUNTLET.ticketItemId) ?? 0),
        )
        if (currentItemCount < 1) {
            return {
                allowed: false,
                reason: "five_boss_ticket",
                minimumPlayerRank: FIVE_BOSS_GAUNTLET.minimumGuestPlayerRank,
                playerRank,
                requiredItemId: FIVE_BOSS_GAUNTLET.ticketItemId,
                currentItemCount,
            }
        }
    }

    if (isMode15Quest(category, questId)) {
        const mode15 = canJoinMode15RescueSync(playerId, category, questId)
        if (!mode15.allowed) return { allowed: false, reason: "mode15_progress" }
    }

    const rule = rules.get(`${category}:${questId}`)
    if (!rule) return { allowed: true, reason: "eligible" }

    const resolvedPlayer = player ?? (dependencies.getPlayer ?? getPlayerSync)(playerId)
    if (!resolvedPlayer) return { allowed: false, reason: "player_not_found" }
    const playerRank = getRankDegree(resolvedPlayer.rankPoint || 0)
    if (playerRank < rule.minimum_player_rank) {
        return {
            allowed: false,
            reason: "player_rank",
            minimumPlayerRank: rule.minimum_player_rank,
            playerRank,
        }
    }

    const hasFinishedQuest = dependencies.hasFinishedQuest ?? hasFinishedQuestSync
    if (!rule.required_quest_categories.some(category =>
        hasFinishedQuest(playerId, category, rule.required_quest_id))) {
        return {
            allowed: false,
            reason: "prerequisite_quest",
            minimumPlayerRank: rule.minimum_player_rank,
            playerRank,
            requiredQuestCategories: [...rule.required_quest_categories],
            requiredQuestId: rule.required_quest_id,
        }
    }

    return {
        allowed: true,
        reason: "eligible",
        minimumPlayerRank: rule.minimum_player_rank,
        playerRank,
        requiredQuestCategories: [...rule.required_quest_categories],
        requiredQuestId: rule.required_quest_id,
    }
}
