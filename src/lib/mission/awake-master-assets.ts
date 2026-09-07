import baseDefinitions from "../../../assets/mission_char_awake.json"
import cnmodDefinitions from "../../../assets/mission_char_awake_cnmod.json"
import baseRewards from "../../../assets/mission_char_awake_reward.json"
import cnmodRewards from "../../../assets/mission_char_awake_reward_cnmod.json"

type RawMissionTable = Record<string, unknown>
type RawRewardTable = Record<string, Record<string, any[]>>

function mergeDisjoint<T extends Record<string, unknown>>(
    label: string,
    base: T,
    extension: T,
): T {
    const duplicated = Object.keys(extension).filter(key => (
        Object.prototype.hasOwnProperty.call(base, key)
    ))
    if (duplicated.length > 0) {
        throw new Error(`${label} extension duplicates base mission IDs: ${duplicated.join(",")}`)
    }
    return { ...base, ...extension }
}

export const characterAwakeDefinitions = mergeDisjoint(
    "character awake definition",
    baseDefinitions as RawMissionTable,
    cnmodDefinitions as RawMissionTable,
)

export const characterAwakeRewards = mergeDisjoint(
    "character awake reward",
    baseRewards as RawRewardTable,
    cnmodRewards as RawRewardTable,
)
