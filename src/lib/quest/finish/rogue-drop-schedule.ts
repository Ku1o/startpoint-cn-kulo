/**
 * Resolves fixed drops for one Rush round. Entries without `rounds` retain
 * the legacy every-round behaviour; `rounds: [min, max]` limits an entry to
 * an inclusive range so finite towers can use a progressive reward curve.
 */
export function resolveRogueRoundDrops(config: any, rushEventRound: number): any[] {
    const drops = Array.isArray(config?.per_round_drops) ? config.per_round_drops : []
    return drops.filter((drop: any) => {
        if (drop?.rounds === undefined) return true
        if (!Array.isArray(drop.rounds) || drop.rounds.length < 2) return false
        const minRound = Math.floor(Number(drop.rounds[0]))
        const maxRound = Math.floor(Number(drop.rounds[1]))
        if (!Number.isInteger(minRound) || !Number.isInteger(maxRound)) return false
        return rushEventRound >= Math.min(minRound, maxRound)
            && rushEventRound <= Math.max(minRound, maxRound)
    })
}
