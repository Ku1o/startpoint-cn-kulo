// Character mana node endpoints — learn and awake

import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getPlayerCharacterManaNodesSync, getPlayerCharacterSync, getPlayerCharactersManaNodesSync, hasPlayerUnlockedCharacterManaNodeSync, insertPlayerCharacterManaNodesSync, getPlayerCharactersManaNodeAwakeLevelsSync, updatePlayerCharacterManaNodeAwakeLevelSync, updatePlayerCharacterSync } from "../../../data/domains/character"
import { getPlayerItemSync, updatePlayerItemSync } from "../../../data/domains/item"
import { getPlayerSync, updatePlayerSync } from "../../../data/domains/player"
import { getSession } from "../../../data/domains/session"
import { getDb } from "../../../data/db"
import { getPlayerCharacterAwakeUnlocksSync } from "../../../data/domains/character_awake";
import { getCharacterDataSync, getCharacterManaNodesSync, getManaNodeAwakeCost } from "../../../lib/assets";
import { clientSerializeDate } from "../../../data/utils";
import { resolvePlayerIdSync } from "../../../data/activeAccount";
import { validateSessionAndPlayer, validateCharacterOwnership, computeManaDeduction, computeItemDeductions, buildCharacterListEntry, sendCharacterResponse, computeBondTokenAndEvolution, validateManaBoardAwakeRequest } from "../../../lib/character-helpers";
import { incrementActiveMissionUsedManaCountSync } from "../../../data/domains/active_mission_counters";
import { gameVerboseLog } from "../../../lib/game-logging";
import { deriveAwakeEvolutionLevel } from "../../../lib/character-awake-evolution";
import { collectLinkedManaNodeAwakeUpdates, getInheritedLinkedManaNodeAwakeLevel, resolveLinkedManaNodeBoardIndex } from "../../../lib/character-awake-extension";

interface LearnManaNodeBody {
    viewer_id: number,
    character_id: number,
    api_count: number,
    mana_node_multiplied_id_list: number[]
}

interface AwakeManaNodeBody {
    viewer_id: number,
    character_id: number,
    api_count: number,
    mana_node_multiplied_id_list: number[],
    awake_level: number
}

const routes = async (fastify: FastifyInstance) => {

    fastify.post("/learn_mana_node", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as LearnManaNodeBody

        const viewerId = body.viewer_id
        const characterId = body.character_id
        const toUnlockNodeIds = body.mana_node_multiplied_id_list
        gameVerboseLog(() => `[MANA] learn_mana_node: viewer=${viewerId} char=${characterId} nodes=${JSON.stringify(toUnlockNodeIds)}`)
        if (!viewerId || isNaN(viewerId) || !characterId || isNaN(characterId)
            || !Array.isArray(toUnlockNodeIds) || toUnlockNodeIds.length === 0
            || toUnlockNodeIds.some(nodeId => !Number.isInteger(nodeId))) return reply.status(400).send({
            "error": "Bad Request", "message": "Invalid request body."
        })

        const sess = await validateSessionAndPlayer(viewerId, reply)
        if (!sess) return
        const { playerId, player } = sess

        const characterData = validateCharacterOwnership(playerId, characterId, reply)
        if (!characterData) return

        // compute the combined cost of each node
        let manaCost = 0
        const itemsCosts: Record<string, number> = {}
        const userCharacterManaNodeListItem: Object[] = []
        const inheritedAwakeNodeLevels = new Map<number, number>()
        const nodesToInsert: number[] = []
        const requestedNodeIds = [...new Set(toUnlockNodeIds)]

        let currentManaNodeIndex = characterData.manaBoardIndex
        let characterManaNodes = getCharacterManaNodesSync(characterId, currentManaNodeIndex)
        if (!characterManaNodes || requestedNodeIds.some(nodeId => characterManaNodes?.[nodeId] === undefined)) {
            const linkedBoardIndex = resolveLinkedManaNodeBoardIndex(
                characterId,
                requestedNodeIds,
                characterData.evolutionLevel,
            )
            if (linkedBoardIndex !== null) {
                currentManaNodeIndex = linkedBoardIndex
                characterManaNodes = getCharacterManaNodesSync(characterId, currentManaNodeIndex)
            }
        }
        if (characterManaNodes === null) return reply.status(400).send({
            "error": "Bad Request", "message": `Character does not have mana nodes of index '${currentManaNodeIndex}'.`
        })

        const unlockedManaNodes = getPlayerCharacterManaNodesSync(playerId, characterId);
        const unlockedManaNodesRecord: Record<string, boolean> = {}
        for (const manaNodeId of unlockedManaNodes) {
            unlockedManaNodesRecord[manaNodeId] = true
        }
        const persistedAwakeLevels = getPlayerCharactersManaNodeAwakeLevelsSync(playerId)[String(characterId)] ?? {}

        for (const manaNodeId of requestedNodeIds) {
            const nodeData = characterManaNodes[manaNodeId];
            if (nodeData === undefined) return reply.status(400).send({
                "error": "Bad Request", "message": `Mana node '${manaNodeId}' does not exist.`
            })

            // The client can retain a stale learn button after an awakening
            // response updates an already learned, linked board-2 node. Treat
            // the resulting replay as an idempotent state refresh instead of
            // forcing the client back to the login screen with HTTP 400.
            if (unlockedManaNodesRecord[manaNodeId]) {
                userCharacterManaNodeListItem.push({
                    "multiplied_id": manaNodeId,
                    "awake_level": persistedAwakeLevels[manaNodeId] ?? 0,
                })
                continue
            }

            nodesToInsert.push(manaNodeId)
            if (nodeData !== null) {
                manaCost += nodeData.manaCost
                for (const [itemId, itemCost] of Object.entries(nodeData.items)) {
                    itemsCosts[itemId] = (itemsCosts[itemId] ?? 0) + itemCost
                }
                const inheritedAwakeLevel = getInheritedLinkedManaNodeAwakeLevel(
                    characterId,
                    currentManaNodeIndex,
                    nodeData,
                    characterData.evolutionLevel,
                )
                userCharacterManaNodeListItem.push({
                    "multiplied_id": manaNodeId,
                    "awake_level": inheritedAwakeLevel,
                })
                if (inheritedAwakeLevel > 0) {
                    inheritedAwakeNodeLevels.set(manaNodeId, inheritedAwakeLevel)
                }
            }
        }

        if (nodesToInsert.length === 0) {
            gameVerboseLog(() => `[MANA] learn_mana_node: replayed=${userCharacterManaNodeListItem.length}, returning current state`)
            return sendCharacterResponse(reply, viewerId, {
                user_info: { free_mana: player.freeMana, paid_mana: player.paidMana },
                character_list: [buildCharacterListEntry(characterId, characterData, {
                    mana_board_index: currentManaNodeIndex,
                    bond_token_list: characterData.bondTokenList.map(token => ({
                        mana_board_index: token.manaBoardIndex,
                        status: token.status,
                    })),
                })],
                user_character_mana_node_list: { [String(characterId)]: userCharacterManaNodeListItem as { multiplied_id: number; awake_level: number }[] },
                item_list: {},
                evolution: [],
                mail_arrived: false,
            }, playerId)
        }

        // Deduct mana
        const manaResult = computeManaDeduction(player, manaCost)
        if (!manaResult) return reply.status(400).send({ "error": "Bad Request", "message": "Not enough mana." })
        const { newFreeMana, newPaidMana } = manaResult

        // Deduct items
        const itemResult = computeItemDeductions(playerId, itemsCosts, reply)
        if (!itemResult) return
        const newItemAmounts = itemResult

        let characterEvolutionLevel = characterData.evolutionLevel
        let evolutionData: Object = []
        let bondTokenList: Object[] = []
        const learnedAfterRequest = new Set(unlockedManaNodes)
        for (const manaNodeId of nodesToInsert) learnedAfterRequest.add(manaNodeId)
        const isBoardComplete = Object.keys(characterManaNodes)
            .every(manaNodeId => learnedAfterRequest.has(Number(manaNodeId)))

        getDb().transaction(() => {
            updatePlayerSync({ id: playerId, freeMana: newFreeMana, paidMana: newPaidMana })
            if (currentManaNodeIndex !== characterData.manaBoardIndex) {
                updatePlayerCharacterSync(playerId, characterId, { manaBoardIndex: currentManaNodeIndex })
            }
            incrementActiveMissionUsedManaCountSync(playerId, manaCost)
            for (const [itemId, newAmount] of Object.entries(newItemAmounts)) {
                updatePlayerItemSync(playerId, itemId, newAmount)
            }
            insertPlayerCharacterManaNodesSync(playerId, characterId, nodesToInsert)
            for (const [nodeId, awakeLevel] of inheritedAwakeNodeLevels) {
                updatePlayerCharacterManaNodeAwakeLevelSync(
                    playerId, characterId, nodeId, awakeLevel,
                )
            }

            const bond = computeBondTokenAndEvolution(
                playerId, characterId, characterData, currentManaNodeIndex, isBoardComplete
            )
            characterEvolutionLevel = bond.characterEvolutionLevel
            evolutionData = bond.evolutionData
            bondTokenList = bond.bondTokenList
        })()

        gameVerboseLog(() => `[MANA] learn_mana_node done: board=${currentManaNodeIndex} inserted=${nodesToInsert.length} replayed=${requestedNodeIds.length - nodesToInsert.length} boardComplete=${isBoardComplete} bondGiven=${!!bondTokenList.length} evoLevel=${characterEvolutionLevel}`)

        return sendCharacterResponse(reply, viewerId, {
            user_info: { free_mana: newFreeMana, paid_mana: newPaidMana },
            character_list: [buildCharacterListEntry(characterId, characterData, {
                mana_board_index: currentManaNodeIndex,
                evolution_level: characterEvolutionLevel,
                evolution_img_level: characterEvolutionLevel,
                bond_token_list: bondTokenList,
            })],
            user_character_mana_node_list: { [String(characterId)]: userCharacterManaNodeListItem as { multiplied_id: number; awake_level: number }[] },
            item_list: newItemAmounts,
            evolution: evolutionData,
            mail_arrived: false,
        }, playerId)
    })

    fastify.post("/awake_mana_node", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as AwakeManaNodeBody

        const viewerId = body.viewer_id
        const characterId = body.character_id
        const toAwakenNodeIds = body.mana_node_multiplied_id_list
        const targetAwakeLevel = body.awake_level
        gameVerboseLog(() => `[MANA] awake_mana_node: viewer=${viewerId} char=${characterId} nodes=${JSON.stringify(toAwakenNodeIds)} level=${targetAwakeLevel}`)
        if (!viewerId || isNaN(viewerId) || !characterId || isNaN(characterId) || !toAwakenNodeIds || !targetAwakeLevel) return reply.status(400).send({
            "error": "Bad Request", "message": "Invalid request body."
        })

        const sess = await validateSessionAndPlayer(viewerId, reply)
        if (!sess) return
        const { playerId, player } = sess

        const characterData = validateCharacterOwnership(playerId, characterId, reply)
        if (!characterData) return

        const board1Nodes = getCharacterManaNodesSync(characterId, 1)
        if (!board1Nodes) return reply.status(400).send({
            "error": "Bad Request", "message": "Character does not have an awake mana board."
        })
        const board1NodeIds = Object.keys(board1Nodes).map(Number)
        const awakeLevels = getPlayerCharactersManaNodeAwakeLevelsSync(playerId)
        const charAwakeLevels = awakeLevels[String(characterId)] ?? {}
        const persistedUnlockLevel = getPlayerCharacterAwakeUnlocksSync(playerId)
            .get(String(characterId))?.[1] ?? 0
        const existingNodeAwakeLevel = Object.values(charAwakeLevels)
            .reduce((highest, level) => Math.max(highest, level ?? 0), 0)
        // Existing awakened nodes remain valid for legacy saves, but new
        // awakening is never authorized before the base board is complete.
        const expectedAwakeLevel = Math.max(persistedUnlockLevel, existingNodeAwakeLevel)
        const learnedNodeIds = getPlayerCharactersManaNodesSync(playerId)[String(characterId)] ?? []
        const validationError = validateManaBoardAwakeRequest(
            toAwakenNodeIds,
            targetAwakeLevel,
            expectedAwakeLevel,
            board1NodeIds,
            learnedNodeIds,
        )
        if (validationError) return reply.status(400).send({
            "error": "Bad Request", "message": validationError
        })

        // Compute costs for each awakening node
        let manaCost = 0
        const itemsCosts: Record<string, number> = {}
        const nodeUpdates: { nodeId: number; awakeLevel: number }[] = []
        const finalAwakeLevels = new Map(
            Object.entries(charAwakeLevels).map(([nodeId, level]) => [Number(nodeId), level]),
        )
        const learnedNodeSet = new Set(learnedNodeIds)

        // Cache character rarity outside the loop
        const charAssetData = getCharacterDataSync(characterId)
        if (charAssetData === null) return reply.status(400).send({
            "error": "Bad Request", "message": `Character asset data not found for ID ${characterId}.`
        })
        const rarity = charAssetData.rarity

        for (const manaNodeId of toAwakenNodeIds) {
            if (!hasPlayerUnlockedCharacterManaNodeSync(playerId, characterId, manaNodeId)) return reply.status(400).send({
                "error": "Bad Request", "message": `Mana node '${manaNodeId}' is not unlocked.`
            })

            const currentAwakeLevel = charAwakeLevels[manaNodeId] ?? 0
            if (currentAwakeLevel >= targetAwakeLevel) {
                continue
            }

            const cost = getManaNodeAwakeCost(characterId, manaNodeId, rarity)
            if (cost === null) return reply.status(400).send({
                "error": "Bad Request", "message": `No awake cost found for node '${manaNodeId}' (rarity=${rarity}).`
            })

            manaCost += cost.manaAmount
            for (const [itemId, itemCost] of Object.entries(cost.items)) {
                itemsCosts[itemId] = (itemsCosts[itemId] ?? 0) + itemCost
            }
            nodeUpdates.push({ nodeId: manaNodeId, awakeLevel: targetAwakeLevel })
            finalAwakeLevels.set(manaNodeId, targetAwakeLevel)
        }

        const characterEvolutionLevel = deriveAwakeEvolutionLevel(
            characterData.evolutionLevel,
            board1Nodes,
            finalAwakeLevels,
        )
        const linkedNodeUpdates = characterEvolutionLevel >= 2
            ? collectLinkedManaNodeAwakeUpdates(
                characterId,
                learnedNodeSet,
                finalAwakeLevels,
                characterEvolutionLevel - 1,
            )
            : []
        for (const update of linkedNodeUpdates) {
            finalAwakeLevels.set(update.nodeId, update.awakeLevel)
        }
        // The awake endpoint is handled as an authoritative character refresh
        // by the client. Return every learned node, not only the rows whose
        // awake level changed, so already learned board-2 nodes cannot reappear
        // as learnable after their linked ability is awakened.
        const authoritativeManaNodeList = learnedNodeIds.map(nodeId => ({
            "multiplied_id": nodeId,
            "awake_level": finalAwakeLevels.get(nodeId) ?? 0,
        }))

        const manaBoardAwake = board1NodeIds.every(nodeId => (
            (finalAwakeLevels.get(nodeId) ?? 0) >= targetAwakeLevel
        )) ? { "1": targetAwakeLevel } : undefined
        const hasStateUpdates = nodeUpdates.length > 0
            || linkedNodeUpdates.length > 0
            || characterEvolutionLevel !== characterData.evolutionLevel

        // All nodes already at target — return current state
        if (manaCost === 0 && !hasStateUpdates) {
            gameVerboseLog(() => `[MANA] awake_mana_node: all nodes at level ${targetAwakeLevel}, returning current state`)
            return sendCharacterResponse(reply, viewerId, {
                user_info: { free_mana: player.freeMana, paid_mana: player.paidMana },
                character_list: [buildCharacterListEntry(characterId, characterData, {
                    ...(manaBoardAwake ? { mana_board_awake: manaBoardAwake } : {}),
                    evolution_level: characterEvolutionLevel,
                    evolution_img_level: characterEvolutionLevel,
                    bond_token_list: (characterData.bondTokenList || []).map((e: any) => ({ mana_board_index: e.manaBoardIndex, status: e.status })),
                })],
                user_character_mana_node_list: { [String(characterId)]: authoritativeManaNodeList },
                item_list: {},
                evolution: [],
                mail_arrived: false,
            }, playerId)
        }

        // Deduct mana
        const manaResult = computeManaDeduction(player, manaCost)
        if (!manaResult) return reply.status(400).send({ "error": "Bad Request", "message": "Not enough mana." })
        const { newFreeMana, newPaidMana } = manaResult

        // Deduct items
        const itemResult = computeItemDeductions(playerId, itemsCosts, reply)
        if (!itemResult) return
        const newItemAmounts = itemResult

        // Apply every state change atomically. An unexpected write failure must
        // not leave mana/items deducted without the corresponding node level.
        getDb().transaction(() => {
            updatePlayerSync({ id: playerId, freeMana: newFreeMana, paidMana: newPaidMana })
            incrementActiveMissionUsedManaCountSync(playerId, manaCost)
            for (const [itemId, newAmount] of Object.entries(newItemAmounts)) {
                updatePlayerItemSync(playerId, itemId, newAmount)
            }

            for (const update of [...nodeUpdates, ...linkedNodeUpdates]) {
                updatePlayerCharacterManaNodeAwakeLevelSync(
                    playerId, characterId, update.nodeId, update.awakeLevel,
                )
            }
            if (characterEvolutionLevel !== characterData.evolutionLevel) {
                updatePlayerCharacterSync(playerId, characterId, {
                    evolutionLevel: characterEvolutionLevel,
                })
            }
        })()

        gameVerboseLog(() => `[MANA] awake_mana_node done: manaCost=${manaCost} nodes=${toAwakenNodeIds.length} manaBoardAwake=${!!manaBoardAwake}`)
        return sendCharacterResponse(reply, viewerId, {
            user_info: { free_mana: newFreeMana, paid_mana: newPaidMana },
            character_list: [buildCharacterListEntry(characterId, characterData, {
                ...(manaBoardAwake ? { mana_board_awake: manaBoardAwake } : {}),
                evolution_level: characterEvolutionLevel,
                evolution_img_level: characterEvolutionLevel,
            })],
            user_character_mana_node_list: { [String(characterId)]: authoritativeManaNodeList },
            item_list: newItemAmounts,
            evolution: characterEvolutionLevel > characterData.evolutionLevel
                ? { "character_id": characterId, "level": characterEvolutionLevel, "img_level": characterEvolutionLevel }
                : [],
            mail_arrived: false,
        }, playerId)
    })
}

export default routes;
