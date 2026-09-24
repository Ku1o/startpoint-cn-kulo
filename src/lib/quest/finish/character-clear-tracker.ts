// Tracks character quest clears for awakening missions
// Leader (position 0) tracked separately for "以X为队长" tasks
// Other party members for "队伍中编有X" tasks

import { incrementPlayerCharacterClearsSync } from "../../../data/domains/character_clear"
import type { FinishContext } from "./types"

export function trackCharacterClears(ctx: FinishContext): void {
    const party = ctx.party
    const leaderId = party.characters[0]?.id
    const isMulti = ctx.isMulti ?? false
    const members: { characterId: number, isLeader: boolean }[] = []

    if (leaderId) {
        members.push({ characterId: leaderId, isLeader: true })
    }

    const seen = new Set<number>([leaderId].filter(Boolean) as number[])
    for (let i = 1; i < party.characters.length; i++) {
        const c = party.characters[i]
        if (c?.id && !seen.has(c.id)) {
            members.push({ characterId: c.id, isLeader: false })
            seen.add(c.id)
        }
    }
    for (const c of party.unison_characters) {
        if (c?.id && !seen.has(c.id)) {
            members.push({ characterId: c.id, isLeader: false })
            seen.add(c.id)
        }
    }
    incrementPlayerCharacterClearsSync(ctx.playerId, members, isMulti)
}
