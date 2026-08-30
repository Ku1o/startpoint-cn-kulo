import awakeExtensionsJson from "../../assets/character_awake_extension.json"
import { getCharacterManaNodesSync } from "./assets"
import type { ManaNode } from "./types"

interface LinkedManaNodeSlot {
    board_index: number
    ability_slot: number
    awake_level: number
}

interface CharacterAwakeExtension {
    linked_mana_node_slots: LinkedManaNodeSlot[]
}

const awakeExtensions = awakeExtensionsJson as Record<string, CharacterAwakeExtension>

export interface LinkedManaNodeAwakeUpdate {
    nodeId: number
    awakeLevel: number
}

function getExtension(characterId: number): CharacterAwakeExtension | null {
    return awakeExtensions[String(characterId)] ?? null
}

function findLinkedNode(
    extension: CharacterAwakeExtension,
    boardIndex: number,
    node: ManaNode,
): LinkedManaNodeSlot | null {
    const abilitySlot = Number(node.field6)
    return extension.linked_mana_node_slots.find(link => (
        link.board_index === boardIndex && link.ability_slot === abilitySlot
    )) ?? null
}

/** Returns the inherited awake level for a newly learned extension node. */
export function getInheritedLinkedManaNodeAwakeLevel(
    characterId: number,
    boardIndex: number,
    node: ManaNode,
    evolutionLevel: number,
): number {
    const extension = getExtension(characterId)
    if (!extension || evolutionLevel < 2) return 0
    return findLinkedNode(extension, boardIndex, node)?.awake_level ?? 0
}

/**
 * Resolves a configured extension board for a learn request when the player's
 * persisted current board still points at the official awakening board.
 */
export function resolveLinkedManaNodeBoardIndex(
    characterId: number,
    nodeIds: readonly number[],
    evolutionLevel: number,
): number | null {
    const extension = getExtension(characterId)
    if (!extension || evolutionLevel < 2 || nodeIds.length === 0) return null

    const boardIndices = new Set(extension.linked_mana_node_slots.map(link => link.board_index))
    for (const boardIndex of boardIndices) {
        const boardNodes = getCharacterManaNodesSync(characterId, boardIndex)
        if (!boardNodes) continue
        if (nodeIds.every(nodeId => {
            const node = boardNodes[String(nodeId)]
            return node !== undefined && findLinkedNode(extension, boardIndex, node) !== null
        })) return boardIndex
    }
    return null
}

/**
 * Builds free node updates when an awakened design changes an ability stored
 * on mana board 2. Only already learned nodes are included; later learning is
 * handled by getInheritedLinkedManaNodeAwakeLevel.
 */
export function collectLinkedManaNodeAwakeUpdates(
    characterId: number,
    learnedNodeIds: ReadonlySet<number>,
    currentAwakeLevels: ReadonlyMap<number, number>,
    targetAwakeLevel: number,
): LinkedManaNodeAwakeUpdate[] {
    const extension = getExtension(characterId)
    if (!extension || targetAwakeLevel <= 0) return []

    const updates: LinkedManaNodeAwakeUpdate[] = []
    for (const link of extension.linked_mana_node_slots) {
        const boardNodes = getCharacterManaNodesSync(characterId, link.board_index)
        if (!boardNodes) continue
        const linkedAwakeLevel = Math.min(targetAwakeLevel, link.awake_level)
        for (const [nodeIdText, node] of Object.entries(boardNodes)) {
            const nodeId = Number(nodeIdText)
            if (Number(node.field6) !== link.ability_slot
                || !learnedNodeIds.has(nodeId)
                || (currentAwakeLevels.get(nodeId) ?? 0) >= linkedAwakeLevel) continue
            updates.push({ nodeId, awakeLevel: linkedAwakeLevel })
        }
    }
    return updates
}
