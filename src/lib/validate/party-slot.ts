import { getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import { findValidNormalPartySlotSync } from "../../data/domains/party"
import { SaveValidator } from "./types"

const PARTY_SLOT_MAX = 120

export const PartySlotValidator: SaveValidator = {
    name: "party-slot",
    version: 2,

    validate(playerId: number, context): number {
        const player = context?.player ?? getPlayerSync(playerId)
        if (!player?.id) return 0

        const validPartySlot = findValidNormalPartySlotSync(playerId, player.partySlot)
        if (validPartySlot !== null) {
            if (validPartySlot === player.partySlot) return 0
            updatePlayerSync({ id: playerId, partySlot: validPartySlot })
            player.partySlot = validPartySlot
            return 1
        }

        // Preserve the old numeric fallback when a player has no usable
        // normal party yet; the party edit guard will prevent new empty
        // leaders from being persisted.
        if (player.partySlot >= 1 && player.partySlot <= PARTY_SLOT_MAX) return 0
        updatePlayerSync({ id: playerId, partySlot: 1 })
        player.partySlot = 1
        return 1
    }
}
