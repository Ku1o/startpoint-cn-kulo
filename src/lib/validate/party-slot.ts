import { getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import { SaveValidator } from "./types"

const PARTY_SLOT_MAX = 120

export const PartySlotValidator: SaveValidator = {
    name: "party-slot",
    version: 1,

    validate(playerId: number, context): number {
        const player = context?.player ?? getPlayerSync(playerId)
        if (!player?.id) return 0

        if (player.partySlot >= 1 && player.partySlot <= PARTY_SLOT_MAX) return 0

        updatePlayerSync({ id: playerId, partySlot: 1 })
        player.partySlot = 1
        return 1
    }
}
