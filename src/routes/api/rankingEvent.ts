// Handles mail.

import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getPlayerSingleQuestProgressSync } from "../../data/domains/quest"
import { getSession } from "../../data/domains/session"
import { generateDataHeaders } from "../../utils";
import { QuestCategory } from "../../lib/types";
import { resolvePlayerIdSync } from "../../data/activeAccount";
import {
    getRankingPlacementSync,
    grantEligibleRankingEventDegreesSync,
    rankingEventIdQuestMap,
} from "../../lib/activity-degree-rewards";

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

const rankingEventTopTimesMs: Record<number, number> = {
    [1]: 54410,
    [2]: 25800,
    [3]: 18880,
    [4]: 31720,
    [5]: 6540
}

/**
 * Generates a ranking summary for a specific player & ranking event.
 * 
 * @param playerId 
 * @param eventId 
 * @returns 
 */
function getRankingSummary(
    playerId: number,
    eventId: number
): Object | null {
    // get quest
    const questId = rankingEventIdQuestMap[eventId]
    if (questId === undefined) return null;

    const topTime = rankingEventTopTimesMs[eventId] ?? 0

    // get data for the ranking quest
    const playerQuestData = getPlayerSingleQuestProgressSync(playerId, QuestCategory.RANKING_EVENT_SINGLE, questId)
    const isAccomplished = playerQuestData !== null && playerQuestData.bestElapsedTimeMs !== undefined && playerQuestData.bestElapsedTimeMs !== null
    const placement = getRankingPlacementSync(playerId, eventId)

    return {
        "best_record": {
            "elapsed_time_ms": isAccomplished ? playerQuestData.bestElapsedTimeMs ?? 0 : 0,
            "is_accomplished": isAccomplished,
            "score": isAccomplished ? playerQuestData.highScore ?? 0 : 0
        },
        "leader_character_evolution_img_level": 1,
        "leader_character_id": 1,
        "rank_border_top": {
            "elapsed_time_ms": topTime,
            "is_accomplished": true,
            "score": 1110111
        },
        "rank_percentage": placement?.percentile ?? 1
    }
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
        const summary = getRankingSummary(playerId, eventId)
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
        const summary = getRankingSummary(playerId, eventId)
        if (summary === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": `Summary could not be generated for '${eventId}' and PlayerId '${playerId}'.`
        })

        const degreeIds = grantEligibleRankingEventDegreesSync(playerId, eventId)
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "status": 1,
                "degree_list": degreeIds.map(degreeId => ({
                    viewer_id: viewerId,
                    degree_id: degreeId,
                })),
                ...summary
            }
        })
    })
}

export default routes;
