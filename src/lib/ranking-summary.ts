import { getDb } from "../data/db"
import { getPlayerCharacterSync } from "../data/domains/character"
import { getPlayerSingleQuestProgressSync } from "../data/domains/quest"
import { getRankingPlacementSync, rankingEventIdQuestMap } from "./activity-degree-rewards"
import { QuestCategory } from "./types"

/** Client percentages are 0-100; reward placement deliberately stays 0-1. */
export function getRankingSummarySync(playerId: number, eventId: number): Record<string, unknown> | null {
    const questId = rankingEventIdQuestMap[eventId]
    if (questId === undefined) return null
    const progress = getPlayerSingleQuestProgressSync(playerId, QuestCategory.RANKING_EVENT_SINGLE, questId)
    const completed = progress?.finished === true && Number(progress.bestElapsedTimeMs) > 0
    const leaderId = progress?.leaderCharacterId
    const leader = Number.isSafeInteger(leaderId) && Number(leaderId) > 0
        ? getPlayerCharacterSync(playerId, Number(leaderId)) : null
    // The client treats null as no recorded entry. Never project an invented
    // character id (or id 0, which has no character resource) for missing data.
    if (!progress || !leader) return { best_record: null }
    const top = getDb().prepare(`
        SELECT finished, best_elapsed_time_ms, high_score FROM players_quest_progress
        WHERE section=? AND quest_id=?
          AND ((finished=1 AND best_elapsed_time_ms>0) OR high_score IS NOT NULL)
        ORDER BY CASE WHEN finished=1 AND best_elapsed_time_ms>0 THEN 0 ELSE 1 END,
            CASE WHEN finished=1 AND best_elapsed_time_ms>0 THEN best_elapsed_time_ms END ASC,
            high_score DESC, player_id ASC LIMIT 1
    `).get(QuestCategory.RANKING_EVENT_SINGLE, questId) as {
        finished: number; best_elapsed_time_ms: number | null; high_score: number | null
    } | undefined
    const topCompleted = top?.finished === 1 && Number(top.best_elapsed_time_ms) > 0
    const placement = getRankingPlacementSync(playerId, eventId)
    const imageLevel = leader?.illustrationSettings?.[0] ?? leader?.evolutionLevel ?? 0
    return {
        best_record: { elapsed_time_ms: completed ? progress!.bestElapsedTimeMs : 0,
            is_accomplished: completed, score: progress?.highScore ?? 0 },
        leader_character_id: Number(leaderId),
        leader_character_evolution_img_level: imageLevel,
        rank_border_top: { elapsed_time_ms: topCompleted ? top!.best_elapsed_time_ms : 0,
            is_accomplished: topCompleted, score: top?.high_score ?? 0 },
        // The CN result animation cannot consume a zero percentage.
        rank_percentage: placement ? Math.max(0.5, Math.min(100, placement.percentile * 100)) : 100,
    }
}
