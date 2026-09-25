export type BossRewardMode = "solo" | "multi"

export interface BossRewardContext {
    readonly questId?: number
    readonly mode: BossRewardMode
}

export interface BossRewardProfile {
    readonly profileId: string
    readonly questId: number
    readonly scoreGroupId: number
    readonly tokenItemId: number
    readonly tokenCount: Readonly<Record<BossRewardMode, number>>
    readonly rareGroupId: number
    readonly rareCharacterId: number
    /** 1% is represented as 100 basis points out of 10,000 rolls. */
    readonly rareChanceBasisPoints: number
}

/**
 * Permanent boss reward profiles are keyed by both quest and score group.
 * Adding another boss means appending one immutable profile and its master
 * tables; existing bosses keep their original reward behavior.
 */
const BOSS_REWARD_PROFILES: readonly BossRewardProfile[] = Object.freeze([
    Object.freeze({
        profileId: "orochi-boss-v2",
        questId: 1020004,
        scoreGroupId: 209990,
        tokenItemId: 40193,
        tokenCount: Object.freeze({ solo: 1, multi: 3 }),
        rareGroupId: 3099900,
        rareCharacterId: 129990,
        rareChanceBasisPoints: 100,
    }),
])

function optionalSafeInteger(value: number | undefined): number | undefined {
    return value !== undefined && Number.isSafeInteger(value) && value > 0
        ? value
        : undefined
}

export function getBossRewardProfile(
    questId?: number,
    scoreGroupId?: number,
): BossRewardProfile | null {
    const normalizedQuestId = optionalSafeInteger(questId)
    const normalizedScoreGroupId = optionalSafeInteger(scoreGroupId)
    if (normalizedQuestId === undefined && normalizedScoreGroupId === undefined) return null
    return BOSS_REWARD_PROFILES.find(profile =>
        (normalizedQuestId === undefined || profile.questId === normalizedQuestId)
        && (normalizedScoreGroupId === undefined || profile.scoreGroupId === normalizedScoreGroupId),
    ) ?? null
}

export function resolveBossTokenCount(
    profile: BossRewardProfile,
    mode: BossRewardMode,
): number {
    return profile.tokenCount[mode]
}

export function listBossRewardProfiles(): readonly BossRewardProfile[] {
    return BOSS_REWARD_PROFILES
}
