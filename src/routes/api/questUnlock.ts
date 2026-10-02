import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getPlayerItemSync, updatePlayerItemSync } from "../../data/domains/item"
import { getPlayerQuestProgressSync, insertPlayerQuestProgressSync, updatePlayerQuestProgressSync } from "../../data/domains/quest"
import { getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import { resolvePlayerIdSync } from "../../data/activeAccount";
import { getQuestFromCategorySync } from "../../lib/assets";
import { generateDataHeaders } from "../../utils";
import questUnlockCosts from "../../../assets/quest_unlock_costs.json";
import { runPersistenceTransaction } from "../../lib/persistence-coordinator";

interface UnlockBody {
    category: number
    quest_id: number
    viewer_id: number
    api_count: number
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/unlock", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as UnlockBody

        const viewerId = body.viewer_id
        const category = body.category
        const questId = body.quest_id

        if (isNaN(viewerId) || isNaN(category) || isNaN(questId)) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            })
        }

        const session = await getSession(viewerId.toString())
        if (!session) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid viewer id."
            })
        }

        const playerId = resolvePlayerIdSync(session.accountId)
        if (playerId === null) {
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No player bound to account."
            })
        }

        const player = getPlayerSync(playerId)
        if (player === null) {
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No player data."
            })
        }

        // Look up quest data
        const questData = getQuestFromCategorySync(category, questId)
        if (questData === null) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Quest not found."
            })
        }

        const result = await runPersistenceTransaction({
            domain: "player", playerId, operation: "quest_unlock",
        }, () => {
            const progress = getPlayerQuestProgressSync(playerId)
            const sectionProg = progress[String(category)] ?? []
            const existing = sectionProg.find(p => p.questId === questId)
            if (existing?.unlocked) return { error: "Quest already unlocked." }

            const unlockCost = (questUnlockCosts as Record<string, {itemIds: number[], itemCounts: number[]}>)[String(questId)]
            const itemList: Record<string, number> = {}
            if (unlockCost) {
                for (let i = 0; i < unlockCost.itemIds.length; i++) {
                    const itemId = unlockCost.itemIds[i]
                    const cost = unlockCost.itemCounts[i] ?? 1
                    const current = getPlayerItemSync(playerId, itemId) ?? 0
                    if (current < cost) return { error: `Not enough of item ${itemId} to unlock quest.` }
                    updatePlayerItemSync(playerId, itemId, current - cost)
                    itemList[String(itemId)] = current - cost
                }
            }
            if (existing) updatePlayerQuestProgressSync(playerId, category, { questId, unlocked: true })
            else insertPlayerQuestProgressSync(playerId, category, { questId, finished: false, unlocked: true })
            return { itemList }
        })
        if (result.error !== undefined) return reply.status(400).send({
            "error": "Bad Request", "message": result.error,
        })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "item_list": result.itemList,
                "mail_arrived": false
            }
        })
    })
}

export default routes
