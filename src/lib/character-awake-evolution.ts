import type { ManaNode } from "./types"

/**
 * Awakening the skill-evolution node on mana board 1 promotes the character
 * evolution level used by awakened leader and action-skill master data.
 */
export function deriveAwakeEvolutionLevel(
    currentEvolutionLevel: number,
    board1Nodes: Readonly<Record<string, ManaNode>>,
    finalAwakeLevels: ReadonlyMap<number, number>,
): number {
    const skillEvolutionNode = Object.entries(board1Nodes).find(([, node]) => (
        node.field5 === "2" && node.field6 === ""
    ))
    if (!skillEvolutionNode) return currentEvolutionLevel

    const awakeLevel = finalAwakeLevels.get(Number(skillEvolutionNode[0])) ?? 0
    return awakeLevel > 0
        ? Math.max(currentEvolutionLevel, 1 + awakeLevel)
        : currentEvolutionLevel
}
