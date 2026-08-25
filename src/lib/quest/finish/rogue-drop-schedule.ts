interface RogueChanceCurve {
    start: number
    per_round?: number
    base_round?: number
}

function appliesToRound(drop: any, rushEventRound: number): boolean {
    if (drop?.rounds !== undefined) {
        if (!Array.isArray(drop.rounds) || drop.rounds.length < 2) return false
        const minRound = Math.floor(Number(drop.rounds[0]))
        const maxRound = Math.floor(Number(drop.rounds[1]))
        if (!Number.isInteger(minRound) || !Number.isInteger(maxRound)) return false
        if (
            rushEventRound < Math.min(minRound, maxRound)
            || rushEventRound > Math.max(minRound, maxRound)
        ) return false
    }
    const excluded = Array.isArray(drop?.exclude_rounds)
        ? drop.exclude_rounds.map(Number)
        : []
    return !excluded.includes(rushEventRound)
}

function resolveChance(value: unknown, rushEventRound: number): number | null {
    if (value === undefined) return null
    if (typeof value === "number") {
        return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0
    }
    if (value === null || typeof value !== "object") return 0
    const curve = value as RogueChanceCurve
    const start = Number(curve.start)
    const perRound = Number(curve.per_round ?? 0)
    const baseRound = Number(curve.base_round ?? rushEventRound)
    if (![start, perRound, baseRound].every(Number.isFinite)) return 0
    return Math.max(0, Math.min(1, start + (rushEventRound - baseRound) * perRound))
}

/**
 * Resolves the independent reward slots for one Rush round.
 *
 * Legacy entries without slot controls remain one guaranteed drop. New
 * entries may declare `slots`, `guaranteed_slots`, and either a numeric
 * `chance` or a `{start, per_round, base_round}` curve. Every optional slot
 * rolls independently. `additional_reward_index_start` assigns stable client
 * result-table indices to the expanded slots.
 */
export function resolveRogueRoundDrops(
    config: any,
    rushEventRound: number,
    random: () => number = Math.random,
): any[] {
    const drops = Array.isArray(config?.per_round_drops) ? config.per_round_drops : []
    const resolved: any[] = []
    for (const drop of drops) {
        if (!appliesToRound(drop, rushEventRound)) continue
        const slotsRaw = drop?.slots === undefined ? 1 : Number(drop.slots)
        const slots = Number.isInteger(slotsRaw) && slotsRaw > 0 ? slotsRaw : 0
        if (slots === 0) continue
        const chance = resolveChance(drop?.chance, rushEventRound)
        const guaranteedRaw = drop?.guaranteed_slots === undefined
            ? (chance === null ? slots : 0)
            : Number(drop.guaranteed_slots)
        const guaranteed = Number.isInteger(guaranteedRaw)
            ? Math.max(0, Math.min(slots, guaranteedRaw))
            : 0
        const indexStart = Number(drop?.additional_reward_index_start)
        for (let slot = 0; slot < slots; slot++) {
            if (slot >= guaranteed && !(random() < (chance ?? 0))) continue
            const copy = { ...drop }
            delete copy.rounds
            delete copy.exclude_rounds
            delete copy.slots
            delete copy.guaranteed_slots
            delete copy.chance
            delete copy.additional_reward_index_start
            if (Number.isInteger(indexStart) && indexStart > 0) {
                copy.additional_reward_index = indexStart + slot
            }
            resolved.push(copy)
        }
    }
    return resolved
}
