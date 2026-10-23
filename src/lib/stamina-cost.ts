import questEntryCosts from "../../assets/quest_entry_costs.json";
import { getActiveCampaignRate } from "./stamina-campaign";
import { QuestCategory } from "./types";
import { getServerDate } from "../utils";
import { getContentNativeStaminaCost } from "./content-quest-rules";

const entryCostMap = questEntryCosts as Record<string, { itemId: number; itemCount: number; stamina: number }>;

export function getStaminaCost(questKey: string): { baseCost: number; cost: number; rate: number } {
    const entry = entryCostMap[questKey];
    const parts = questKey.split("_");
    const category = parseInt(parts[0]) as QuestCategory;
    const questId = parseInt(parts.slice(1).join("_"));
    // Multiplayer category 8 keeps its existing cost policy. Single entry is
    // still free; this corrects the existing nominal mission credit only.
    const nativeCost = category === 8 ? null : getContentNativeStaminaCost(category, questId);
    const baseCost = nativeCost ?? entry?.stamina ?? 0;
    if (!baseCost) return { baseCost: 0, cost: 0, rate: 1 };

    const rate = getActiveCampaignRate(category, questId, getServerDate());
    const cost = Math.max(1, Math.floor(baseCost * rate));

    return { baseCost, cost, rate };
}
