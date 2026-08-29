import type { Player, PlayerEquipment } from "../../data/types"

// SaveValidator interface — each validator checks and repairs one data category.
// Permanent validators can write to DB. Temporal filters modify output only.

export interface SaveValidationContext {
    /** Request-local data that is known to be current for fields read by validators. */
    readonly player?: Player
    readonly equipmentList?: Record<string, PlayerEquipment>
}

export interface SaveValidator {
    readonly name: string
    /** Increment only when the repair logic must be applied again to old saves. */
    readonly version: number
    /**
     * Validate & repair one player save.
     * @returns number of fixes applied (0 = clean).
     */
    validate(playerId: number, context?: SaveValidationContext): number
}

/** Filter applied to serialized output (does not modify DB). */
export interface TemporalFilter {
    readonly name: string
    /** @returns filtered output object (shallow copy with removed entries). */
    apply<T extends Record<string, any>>(output: T): T
}
