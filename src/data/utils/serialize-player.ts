import type { MergedPlayerData } from "../types"
import { getTimeOffset } from "../../utils"
import { availableAssetVersion } from "../../routes/api/asset"
import { getPlayerMailCountSync } from "../domains/mail"
import { getPlayerClearedCollectItemEventMissionListSync } from "../domains/mission"
import { updatePlayerSync } from "../domains/player"
import { computeRealTimeStamina } from "../../lib/stamina"
import { isMode15RuntimeLoaded, MODE15_RUSH_EVENT_ID } from "../../lib/mode15-optional"
import { serializePlayerSnapshot, type SerializePlayerDataOptions, type PlayerSerializationContext } from "./client-player-snapshot"
export { SerializePlayerDataOptions } from "./client-player-snapshot"

export function preparePlayerSerialization(toSerialize: MergedPlayerData, options?: SerializePlayerDataOptions) {
    const playerData = toSerialize.player
    const realTimeStamina = computeRealTimeStamina(playerData)
    if (realTimeStamina !== playerData.stamina) {
        updatePlayerSync({ id: playerData.id, stamina: realTimeStamina, staminaHealTime: new Date() })
        playerData.stamina = realTimeStamina
    }
    const context: PlayerSerializationContext = {
        assetVersion: availableAssetVersion, timeOffset: getTimeOffset() ?? 0,
        mailArrived: getPlayerMailCountSync(playerData.id, true) > 0,
        clearedCollectMissions: getPlayerClearedCollectItemEventMissionListSync(playerData.id),
        summonComSeconds: parseInt(process.env.SUMMON_COM_SECONDS || "5"),
        mode15Enabled: isMode15RuntimeLoaded(), mode15EventId: MODE15_RUSH_EVENT_ID,
        mode15Reuse: process.env.MODE15_ALLOW_CHARACTER_REUSE === "true",
    }
    return { data: toSerialize, context, options }
}
export type PreparedPlayerSerialization = ReturnType<typeof preparePlayerSerialization>

export function serializePlayerData(data: MergedPlayerData, options?: SerializePlayerDataOptions) {
    const prepared = preparePlayerSerialization(data, options)
    return serializePlayerSnapshot(prepared.data, prepared.context, prepared.options)
}
