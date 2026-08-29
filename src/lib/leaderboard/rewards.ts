export interface LeaderboardRewardTier {
    fromRank: number
    toRank: number | null
    itemId: number | null
    itemName: string | null
    itemCount: number
    degreeId: number | null
    degreeName: string | null
    degreeImage: string | null
}

const LEGACY_DEEP_ABYSS_REWARD_TIERS: readonly LeaderboardRewardTier[] = [
    {
        fromRank: 1, toRank: 1, itemId: 999015, itemName: "终焉裁定券", itemCount: 10,
        degreeId: 9900002, degreeName: "深渊冠军",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_champion.png",
    },
    {
        fromRank: 2, toRank: 3, itemId: 999015, itemName: "终焉裁定券", itemCount: 5,
        degreeId: 9900003, degreeName: "深渊亚季军",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_runner_up.png",
    },
    {
        fromRank: 4, toRank: 15, itemId: 999015, itemName: "终焉裁定券", itemCount: 2,
        degreeId: 9900004, degreeName: "深渊上位者",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_upper_rank.png",
    },
    {
        fromRank: 16, toRank: null, itemId: null, itemName: null, itemCount: 0,
        degreeId: 9900005, degreeName: "深渊参与者",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_participant.png",
    },
]

export const DEEP_ABYSS_REWARD_TIERS: readonly LeaderboardRewardTier[] = [
    {
        fromRank: 1,
        toRank: 1,
        itemId: 999016,
        itemName: "终焉裁定十连券",
        itemCount: 10,
        degreeId: 9900002,
        degreeName: "深渊冠军",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_champion.png",
    },
    {
        fromRank: 2,
        toRank: 3,
        itemId: 999016,
        itemName: "终焉裁定十连券",
        itemCount: 5,
        degreeId: 9900003,
        degreeName: "深渊亚季军",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_runner_up.png",
    },
    {
        fromRank: 4,
        toRank: 15,
        itemId: 999016,
        itemName: "终焉裁定十连券",
        itemCount: 2,
        degreeId: 9900004,
        degreeName: "深渊上位者",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_upper_rank.png",
    },
    {
        fromRank: 16,
        toRank: null,
        itemId: 999015,
        itemName: "终焉裁定券",
        itemCount: 1,
        degreeId: 9900005,
        degreeName: "深渊参与者",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_participant.png",
    },
]

export function isLegacyDefaultLeaderboardRewardTiers(
    competitionKey: string,
    tiers: readonly LeaderboardRewardTier[],
): boolean {
    if (competitionKey !== "rush:700099:1" || tiers.length !== LEGACY_DEEP_ABYSS_REWARD_TIERS.length) {
        return false
    }
    const fields: readonly (keyof LeaderboardRewardTier)[] = [
        "fromRank", "toRank", "itemId", "itemName", "itemCount",
        "degreeId", "degreeName", "degreeImage",
    ]
    return tiers.every((tier, index) => fields.every(field =>
        tier[field] === LEGACY_DEEP_ABYSS_REWARD_TIERS[index][field]
    ))
}

export function getLeaderboardRewardTiers(
    competitionKey: string,
): readonly LeaderboardRewardTier[] {
    return competitionKey === "rush:700099:1" ? DEEP_ABYSS_REWARD_TIERS : []
}

export function matchLeaderboardRewardTier(
    tiers: readonly LeaderboardRewardTier[],
    rank: number,
): LeaderboardRewardTier | null {
    return tiers.find(tier =>
        rank >= tier.fromRank && (tier.toRank === null || rank <= tier.toRank)
    ) ?? null
}
