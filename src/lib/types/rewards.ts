export enum RewardType {
    ITEM,
    EQUIPMENT,
    CHARACTER,
    BEADS,
    MANA,
    EXP,
    ELEMENT,
    AETHER
}


export enum ScoreRewardType {
    ITEM,
    RARE_POOL
}


export enum ShopItemRewardType {
    ITEM,
    EXP,
    MANA,
    CHARACTER,
    EQUIPMENT,
    DEGREE
}


export interface Reward {
    name?: string,
    type: RewardType,
    id?: number,
}


export interface EquipmentItemReward extends Reward {
    id: number,
    count: number
}


export interface CharacterReward extends Reward {
    id: number
}


export interface CurrencyReward extends Reward {
    count: number
}


export interface RareScoreReward extends Reward {
    rarity: number
}


export type ClearRewards = Record<string, Reward>

// score rewards

export interface ScoreReward {
    name: string,
    type: ScoreRewardType,
    /** Newly introduced clear-only rewards must not be paid on a failed finish. */
    requires_clear?: boolean,
    position?: number, // orderedmap position (preserved from CDN), used as drop_score_reward_ids index
}


export interface CommonScoreReward extends ScoreReward {
    reward_type: RewardType
}


export interface CurrencyScoreReward extends CommonScoreReward {
    count: number
    field5: number
}


export interface ItemScoreReward extends CommonScoreReward {
    id: number,
    count: number,
    field5: number,
    ignore_drop_multiplier?: boolean
}


export interface RareScoreRewardGroup extends ScoreReward {
    id: number,
    rarity: number
    /** Optional exact server-side probability; omitted masters retain their legacy behavior. */
    chance_basis_points?: number
}


export type ScoreRewardGroups = Record<string, ScoreReward[]>


export type RareScoreRewardGroups = Record<string, Reward[]>

// shop rewards

export interface ShopItemReward {
    type: ShopItemRewardType,
}


export interface EquipmentItemShopItemReward extends ShopItemReward {
    id: number,
    count: number
}


export interface CharacterShopItemReward extends ShopItemReward {
    id: number
}


export interface CurrencyShopItemReward extends ShopItemReward {
    count: number
}

export interface DegreeShopItemReward extends ShopItemReward {
    id: number
    count: 1
}


export interface PlayerRewardResult {
    user_info: {
        free_mana: number
        free_vmoney: number
        exp_pool: number
    },
    character_list: Object[]
    joined_character_id_list: number[]
    equipment_list: Object[]
    items: Record<string, number>
}


export interface DropScoreRewardId {
    group_id: number,
    index: number,
    number: number
}


export interface GivePlayerScoreRewardsResult extends PlayerRewardResult {
    drop_score_reward_ids: DropScoreRewardId[]
    drop_rare_reward_ids: DropScoreRewardId[]
}
