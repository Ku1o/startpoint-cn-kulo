// Save validator system — runs permanent validators on /load.
// Temporal filters are applied at serialization time (see load.ts).

import { SaveValidationContext, SaveValidator, TemporalFilter } from "./types"
import { MaxLevelValidator } from "./max-level"
import { PartySlotValidator } from "./party-slot"
import { UnisonUnlockValidator } from "./unison-unlock"
import { getPlayerRepairVersionsSync, setPlayerRepairVersionSync } from "../../data/domains/player-repair"

const PERMANENT_VALIDATORS: SaveValidator[] = [
    MaxLevelValidator,
    PartySlotValidator,
    UnisonUnlockValidator,
]

const TEMPORAL_FILTERS: TemporalFilter[] = [
    // Add temporal filters here (e.g. ExBoostReleaseFilter, ItemReleaseFilter)
]

/** Run all permanent validators. Returns total fixes applied. */
export function runPermanentValidators(
    playerId: number,
    context: SaveValidationContext = {},
): number {
    let totalFixes = 0
    const appliedVersions = getPlayerRepairVersionsSync(playerId)
    for (const v of PERMANENT_VALIDATORS) {
        if ((appliedVersions.get(v.name) ?? 0) >= v.version) continue
        try {
            totalFixes += v.validate(playerId, context)
            setPlayerRepairVersionSync(playerId, v.name, v.version)
        } catch (e) {
            console.error(`[VALIDATE:${v.name}] error:`, e)
        }
    }
    if (totalFixes > 0) {
        console.log(`[VALIDATE] player=${playerId}: ${totalFixes} total permanent fixes`)
    }
    return totalFixes
}

/** Apply all temporal filters to serialized output. */
export function applyTemporalFilters<T extends Record<string, any>>(output: T): T {
    for (const f of TEMPORAL_FILTERS) {
        try {
            output = f.apply(output)
        } catch (e) {
            console.error(`[VALIDATE:${f.name}] filter error:`, e)
        }
    }
    return output
}
