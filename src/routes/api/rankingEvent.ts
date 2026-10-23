// Handles mail.

import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getSession } from "../../data/domains/session"
import { generateDataHeaders } from "../../utils";
import { resolvePlayerIdSync } from "../../data/activeAccount";
import { getRankingSummarySync } from "../../lib/ranking-summary";
import { claimRankingEventRewardsSync } from "../../lib/ranking-event-rewards";
import { runPersistenceTransaction } from "../../lib/persistence-coordinator";

interface ReceiveRewardBody {
    api_count: number,
    viewer_id: number,
    ranking_event_id: number
}

interface GetSummaryBody {
    viewer_id: number,
    ranking_event_id: number,
    quest_kind: number
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/get_summary", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as GetSummaryBody

        const viewerId = body.viewer_id
        const eventId = body.ranking_event_id
        if (isNaN(viewerId) || isNaN(eventId)) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!

        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No player bound to account."
        })

        // get summary
        const summary = getRankingSummarySync(playerId, eventId)
        if (summary === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": `Summary could not be generated for '${eventId}' and PlayerId '${playerId}'.`
        })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": summary
        })
    })

    fastify.post("/receive_reward", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as ReceiveRewardBody

        const viewerId = body.viewer_id
        const eventId = body.ranking_event_id
        if (isNaN(viewerId) || isNaN(eventId)) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player id
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!

        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No player bound to account."
        })

        // get summary
        const summary = getRankingSummarySync(playerId, eventId)
        if (summary === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": `Summary could not be generated for '${eventId}' and PlayerId '${playerId}'.`
        })

        // Eligibility and the original-event receipt are read after entering the
        // player write queue. Closed events still pay already earned results.
        const settlement = await runPersistenceTransaction({ domain: "event", playerId, operation: "ranking_event_receive" },
            () => claimRankingEventRewardsSync(playerId, eventId))
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "status": settlement.replayed ? 2 : settlement.received ? 1 : 3,
                "degree_list": settlement.degreeIds.map(degreeId => ({
                    viewer_id: viewerId,
                    degree_id: degreeId,
                })),
                ...summary,
                ...(settlement.userInfo ? { user_info: settlement.userInfo } : {}),
                ...(settlement.rewardResult ? {
                    item_list: settlement.rewardResult.items,
                    character_list: settlement.rewardResult.character_list,
                    joined_character_id_list: settlement.rewardResult.joined_character_id_list,
                    equipment_list: settlement.rewardResult.equipment_list,
                } : {}),
            }
        })
    })
}

export default routes;
