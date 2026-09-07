import awakeExtensionsJson from "../../assets/character_awake_extension.json"
import { getCharacterManaNodesSync } from "./assets"

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

/**
 * Hides linked extension boards from an incremental mana response.
 *
 * The 1.8.1 client's common-response parser applies `mana_board_awake` but
 * ignores `user_character_mana_node_list`. Publishing a linked board here
 * therefore switches the board to Awake mode while its local node levels are
 * still stale. Keep the persisted state server-side and expose it on the next
 * full `/load`, where character and mana-node state are initialized together.
 */
export function deferLinkedManaBoardAwakeLevels(
    characterId: number,
    levels: Record<number, number> | undefined,
): Record<number, number> | undefined {
    if (!levels) return undefined
    const extension = getExtension(characterId)
    if (!extension) return levels

    const deferredBoards = new Set(
        extension.linked_mana_node_slots.map(link => link.board_index),
    )
    const immediate: Record<number, number> = {}
    for (const [boardIndexText, awakeLevel] of Object.entries(levels)) {
        const boardIndex = Number(boardIndexText)
        if (deferredBoards.has(boardIndex)) continue
        immediate[boardIndex] = awakeLevel
    }
    return Object.keys(immediate).length > 0 ? immediate : undefined
}

function getExtension(characterId: number): CharacterAwakeExtension | null {
    return awakeExtensions[String(characterId)] ?? null
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
        if (nodeIds.every(nodeId => boardNodes[String(nodeId)] !== undefined)) return boardIndex
    }
    return null
}

/**
 * Builds free whole-board updates when an awakened design changes an ability
 * stored on a later mana board.
 *
 * The client has one learn mode per board, not per ability. Mixing awake nodes
 * with normal nodes on the same board makes an already learned node appear as
 * a lower normal upgrade. Keep an incomplete extension board entirely normal;
 * once it is complete, advance every node together so the board mode and all
 * persisted node levels stay coherent.
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
    const boardAwakeLevels = new Map<number, number>()
    for (const link of extension.linked_mana_node_slots) {
        const linkedAwakeLevel = Math.min(targetAwakeLevel, link.awake_level)
        boardAwakeLevels.set(
            link.board_index,
            Math.max(boardAwakeLevels.get(link.board_index) ?? 0, linkedAwakeLevel),
        )
    }

    for (const [boardIndex, boardAwakeLevel] of boardAwakeLevels) {
        if (boardAwakeLevel <= 0) continue
        const boardNodes = getCharacterManaNodesSync(characterId, boardIndex)
        if (!boardNodes) continue
        const boardNodeIds = Object.keys(boardNodes).map(Number)
        if (!boardNodeIds.every(nodeId => learnedNodeIds.has(nodeId))) continue

        for (const nodeId of boardNodeIds) {
            if ((currentAwakeLevels.get(nodeId) ?? 0) >= boardAwakeLevel) continue
            updates.push({ nodeId, awakeLevel: boardAwakeLevel })
        }
    }
    return updates
}
