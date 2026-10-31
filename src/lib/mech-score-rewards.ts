// Restore the original gear/core groups only for the six projected mech quests.
// Matching both identities leaves other events with overlapping quest IDs alone.
const MECH_SCORE_REWARD_GROUPS: Readonly<Record<number, readonly [number, number]>> = {
    1001001: [11000930, 7000010],
    1002001: [11000931, 7000011],
    1003001: [11000932, 7000012],
    1004001: [11000933, 7000013],
    1005001: [11000934, 7000014],
    1006001: [11000935, 7000015],
}

export function resolveMechScoreRewardGroupId(
    questId?: number,
    scoreGroupId?: number,
): number | undefined {
    const groups = questId === undefined ? undefined : MECH_SCORE_REWARD_GROUPS[questId]
    return groups?.[0] === scoreGroupId ? groups?.[1] : scoreGroupId
}
