import rules from "../../assets/quest_continue_rules.json"
import { QuestCategory } from "./types/quest"

/** Preserve all other native limits and costs; only the agreed highest tier is disabled. */
export function isQuestContinueForbidden(category: number, questId: number): boolean {
    return category === QuestCategory.BOSS_BATTLE && rules.bossBattleHighest.includes(questId)
        || (category === QuestCategory.ADVENT_EVENT_SINGLE || category === QuestCategory.ADVENT_EVENT_MULTI)
            && rules.adventHighest.includes(questId)
}
