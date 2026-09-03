"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.matchLeaderboardRewardTier = exports.getLeaderboardRewardTiers = exports.isLegacyDefaultLeaderboardRewardTiers = exports.DEEP_ABYSS_REWARD_TIERS = void 0;
const LEGACY_DEEP_ABYSS_REWARD_TIERS = [
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
];
// One early local database used 999015 for all legacy item rows.  Recognize
// it too so that an existing installation is upgraded instead of retaining
// the obsolete four-tier display indefinitely.
const LEGACY_DEEP_ABYSS_REWARD_TIERS_ALT = [
    Object.assign(Object.assign({}, LEGACY_DEEP_ABYSS_REWARD_TIERS[0]), { itemId: 999015, itemName: "终焉裁定券" }),
    Object.assign(Object.assign({}, LEGACY_DEEP_ABYSS_REWARD_TIERS[1]), { itemId: 999015, itemName: "终焉裁定券" }),
    Object.assign(Object.assign({}, LEGACY_DEEP_ABYSS_REWARD_TIERS[2]), { itemId: 999015, itemName: "终焉裁定券" }),
    Object.assign(Object.assign({}, LEGACY_DEEP_ABYSS_REWARD_TIERS[3]), { itemId: null, itemName: null, itemCount: 0 }),
];
exports.DEEP_ABYSS_REWARD_TIERS = [
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
];
function isLegacyDefaultLeaderboardRewardTiers(competitionKey, tiers) {
    if (competitionKey !== "rush:700099:1" || tiers.length !== LEGACY_DEEP_ABYSS_REWARD_TIERS.length) {
        return false;
    }
    const fields = [
        "fromRank", "toRank", "itemId", "itemName", "itemCount",
        "degreeId", "degreeName", "degreeImage",
    ];
    return [LEGACY_DEEP_ABYSS_REWARD_TIERS, LEGACY_DEEP_ABYSS_REWARD_TIERS_ALT].some(legacy => tiers.every((tier, index) => fields.every(field => tier[field] === legacy[index][field])));
}
exports.isLegacyDefaultLeaderboardRewardTiers = isLegacyDefaultLeaderboardRewardTiers;
function getLeaderboardRewardTiers(competitionKey) {
    return competitionKey === "rush:700099:1" ? exports.DEEP_ABYSS_REWARD_TIERS : [];
}
exports.getLeaderboardRewardTiers = getLeaderboardRewardTiers;
function matchLeaderboardRewardTier(tiers, rank) {
    var _a;
    return (_a = tiers.find(tier => rank >= tier.fromRank && (tier.toRank === null || rank <= tier.toRank))) !== null && _a !== void 0 ? _a : null;
}
exports.matchLeaderboardRewardTier = matchLeaderboardRewardTier;
