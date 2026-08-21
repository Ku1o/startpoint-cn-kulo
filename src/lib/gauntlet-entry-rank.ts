export const GAUNTLET_MIN_PLAYER_RANK = 130;

const RANK_GATED_RUSH_EVENT_IDS = new Set<number>([
    700098, // Fantasy Gauntlet
    700099, // Deep Abyss Gauntlet
]);

export function isRankGatedGauntletRushEvent(rushEventId: number): boolean {
    return RANK_GATED_RUSH_EVENT_IDS.has(rushEventId);
}

export function canStartRankGatedGauntletRush(
    rushEventId: number,
    playerRank: number,
): boolean {
    return !isRankGatedGauntletRushEvent(rushEventId)
        || playerRank >= GAUNTLET_MIN_PLAYER_RANK;
}
