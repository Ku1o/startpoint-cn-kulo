import policy from "../../../assets/leaderboard_reward_policy.json"

export interface LeaderboardReward {
    itemId: number | null
    itemName: string | null
    itemCount: number
    degreeId: number | null
    degreeName: string | null
    degreeImage: string | null
}

// Keep rank ranges on the wire: existing clients already render these fields.
export interface LeaderboardRewardTier extends LeaderboardReward {
    fromRank: number
    toRank: number | null
}

export interface LeaderboardPercentRewardTier extends LeaderboardReward {
    fromPercent: number
    toPercent: number
}

export type LeaderboardRewardRule = LeaderboardRewardTier | LeaderboardPercentRewardTier

export function isPercentRewardTier(tier: LeaderboardRewardRule): tier is LeaderboardPercentRewardTier {
    return "fromPercent" in tier
}

const LEGACY_DEEP_ABYSS_REWARD_TIERS: readonly LeaderboardRewardTier[] = [
    {
        fromRank: 1, toRank: 1, itemId: 999016, itemName: "终焉裁定十连券", itemCount: 10,
        degreeId: 9900002, degreeName: "深渊冠军",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_champion.png",
    },
    {
        fromRank: 2, toRank: 3, itemId: 999016, itemName: "终焉裁定十连券", itemCount: 5,
        degreeId: 9900003, degreeName: "深渊亚季军",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_runner_up.png",
    },
    {
        fromRank: 4, toRank: 15, itemId: 999016, itemName: "终焉裁定十连券", itemCount: 2,
        degreeId: 9900004, degreeName: "深渊上位者",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_upper_rank.png",
    },
    {
        fromRank: 16, toRank: null, itemId: 999015, itemName: "终焉裁定券", itemCount: 1,
        degreeId: 9900005, degreeName: "深渊参与者",
        degreeImage: "dynamic/degree/degree_mod_abyss_rush_participant.png",
    },
]

// One early local database used 999015 for all legacy item rows.  Recognize
// it too so that an existing installation is upgraded instead of retaining
// the obsolete four-tier display indefinitely.
const LEGACY_DEEP_ABYSS_REWARD_TIERS_ALT: readonly LeaderboardRewardTier[] = [
    { ...LEGACY_DEEP_ABYSS_REWARD_TIERS[0], itemId: 999015, itemName: "终焉裁定券" },
    { ...LEGACY_DEEP_ABYSS_REWARD_TIERS[1], itemId: 999015, itemName: "终焉裁定券" },
    { ...LEGACY_DEEP_ABYSS_REWARD_TIERS[2], itemId: 999015, itemName: "终焉裁定券" },
    { ...LEGACY_DEEP_ABYSS_REWARD_TIERS[3], itemId: null, itemName: null, itemCount: 0 },
]

const FIXED_DEEP_ABYSS_REWARD_TIERS: readonly LeaderboardRewardTier[] = [
    {
        fromRank: 1,
        toRank: 1,
        itemId: 999018,
        itemName: "竞速池十连券",
        itemCount: 10,
        degreeId: 9900007,
        degreeName: "星渊主宰者",
        degreeImage: "dynamic/degree/degree_mod_stellar_abyss_overlord.png",
    },
    {
        fromRank: 2,
        toRank: 2,
        itemId: 999018,
        itemName: "竞速池十连券",
        itemCount: 5,
        degreeId: 9900008,
        degreeName: "星渊征服者",
        degreeImage: "dynamic/degree/degree_mod_stellar_abyss_conqueror.png",
    },
    {
        fromRank: 3,
        toRank: 3,
        itemId: 999018,
        itemName: "竞速池十连券",
        itemCount: 5,
        degreeId: 9900009,
        degreeName: "星渊讨伐者",
        degreeImage: "dynamic/degree/degree_mod_stellar_abyss_slayer.png",
    },
    {
        fromRank: 4,
        toRank: 15,
        itemId: 999018,
        itemName: "竞速池十连券",
        itemCount: 2,
        degreeId: 9900010,
        degreeName: "破阵先行者",
        degreeImage: "dynamic/degree/degree_mod_breakthrough_pioneer.png",
    },
    {
        fromRank: 16,
        toRank: null,
        itemId: 999017,
        itemName: "竞速池扭蛋券",
        itemCount: 1,
        degreeId: 9900011,
        degreeName: "共赴星渊",
        degreeImage: "dynamic/degree/degree_mod_stellar_abyss_together.png",
    },
]

export const DEEP_ABYSS_REWARD_TIERS: readonly LeaderboardPercentRewardTier[] =
    FIXED_DEEP_ABYSS_REWARD_TIERS.map(({ fromRank, toRank, ...reward }, index) => ({
        ...reward,
        fromPercent: index === 0 ? 0 : policy.percentileCutoffs[index - 1],
        toPercent: policy.percentileCutoffs[index],
    }))

// Upgrade the five existing positions without overwriting customized rewards.
export function upgradeLeaderboardRewardRules(
    competitionKey: string,
    tiers: readonly LeaderboardRewardRule[],
): LeaderboardRewardRule[] | null {
    if (competitionKey !== "rush:700099:1") return null
    if (isLegacyDefaultLeaderboardRewardTiers(competitionKey, tiers)) {
        return [...DEEP_ABYSS_REWARD_TIERS]
    }
    // Existing databases already persisted the first 1% policy. Upgrade only
    // those exact five boundaries; retain prizes and unrelated custom ranges.
    const previousCutoffs = [1, 5, 10, 20, 100]
    if (tiers.length === previousCutoffs.length && tiers.every((tier, index) =>
        isPercentRewardTier(tier)
        && tier.fromPercent === (index === 0 ? 0 : previousCutoffs[index - 1])
        && tier.toPercent === previousCutoffs[index]
    )) {
        return tiers.map((tier, index) => ({ ...tier,
            fromPercent: DEEP_ABYSS_REWARD_TIERS[index].fromPercent,
            toPercent: DEEP_ABYSS_REWARD_TIERS[index].toPercent,
        }))
    }
    if (tiers.length !== FIXED_DEEP_ABYSS_REWARD_TIERS.length || !tiers.every((tier, index) =>
        !isPercentRewardTier(tier)
        && tier.fromRank === FIXED_DEEP_ABYSS_REWARD_TIERS[index].fromRank
        && tier.toRank === FIXED_DEEP_ABYSS_REWARD_TIERS[index].toRank
    )) return null
    return tiers.map((tier, index) => {
        const { fromRank, toRank, ...reward } = tier as LeaderboardRewardTier
        return { ...reward, fromPercent: DEEP_ABYSS_REWARD_TIERS[index].fromPercent,
            toPercent: DEEP_ABYSS_REWARD_TIERS[index].toPercent }
    })
}

export function resolveLeaderboardRewardTiers(
    rules: readonly LeaderboardRewardRule[],
    total: number,
): LeaderboardRewardTier[] {
    if (!Number.isSafeInteger(total) || total < 0) throw new Error("Invalid ranked player count.")
    return rules.flatMap(rule => {
        if (!isPercentRewardTier(rule)) return [{ ...rule }]
        const { fromPercent, toPercent, ...reward } = rule
        // Integer percentages avoid rounding a floating-point product twice.
        const fromRank = Number((BigInt(total) * BigInt(fromPercent) + BigInt(99)) / BigInt(100)) + 1
        const endRank = Number((BigInt(total) * BigInt(toPercent) + BigInt(99)) / BigInt(100))
        if (fromRank > endRank) return []
        return [{ ...reward, fromRank, toRank: toPercent === 100 ? null : endRank }]
    })
}

export function isLegacyDefaultLeaderboardRewardTiers(
    competitionKey: string,
    tiers: readonly LeaderboardRewardRule[],
): boolean {
    if (competitionKey !== "rush:700099:1" || tiers.length !== LEGACY_DEEP_ABYSS_REWARD_TIERS.length) {
        return false
    }
    const fields: readonly (keyof LeaderboardRewardTier)[] = [
        "fromRank", "toRank", "itemId", "itemName", "itemCount",
        "degreeId", "degreeName", "degreeImage",
    ]
    return [LEGACY_DEEP_ABYSS_REWARD_TIERS, LEGACY_DEEP_ABYSS_REWARD_TIERS_ALT].some(legacy =>
        tiers.every((tier, index) => !isPercentRewardTier(tier)
            && fields.every(field => tier[field] === legacy[index][field]))
    )
}

export function getLeaderboardRewardTiers(
    competitionKey: string,
): readonly LeaderboardRewardRule[] {
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
